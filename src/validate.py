import json
from datetime import date
import pandas as pd
from src import chain as ch
from src.config import settings

TABLES = ("index", "item_weights", "country_weights", "contributions", "official_rates")

def _load():
    return {name: pd.read_parquet(settings.silver / f"{name}.parquet") for name in TABLES}

def _official(data, geo="EA", code="TOTAL"):
    return ch.wide(data["index"], geo, [code])[code]

def _country_weights(data):
    cw = data["country_weights"].pivot_table(index="year", columns="geo", values="weight")
    return cw.reindex(columns=settings.countries)

def compare(rebuilt, official, published=None):
    """Annual rates of a rebuilt index against the official index, and against the published
    rates if given. Returns a summary and the monthly gaps"""
    ours, theirs = ch.yoy(rebuilt), ch.yoy(official)
    diff = (ours - theirs).dropna()
    since_2017 = diff[diff.index >= pd.Period("2017-01", freq="M")]
    out = {"months": int(diff.size), "from": str(diff.index.min()),
           "max_abs_pp": float(diff.abs().max()), "mean_abs_pp": float(diff.abs().mean()),
           "worst_month": str(diff.abs().idxmax()), "max_abs_since_2017_pp": float(since_2017.abs().max())}
    if published is not None:
        pub = published.reindex(diff.index).dropna()
        mine = ours.reindex(pub.index)
        out["published_1dp_match"] = float((mine.round(1) == pub.round(1)).mean())
        # published rates have one decimal, so up to 0.05 of this is just rounding
        out["max_abs_vs_published_pp"] = float((mine - pub).abs().max())
    return out, diff

def rebuild_partition(data, part, geo="EA"):
    codes = settings.partitions[part]
    weights = ch.weight_table(data["item_weights"], codes, geo=geo)
    return ch.chain(ch.wide(data["index"], geo, codes), weights, require_all=True)

def rebuild_from_countries(data):
    levels = pd.DataFrame({g: _official(data, g) for g in settings.countries})
    return ch.chain(levels, _country_weights(data))

def rebuild_two_level(data, part="groups"):
    codes = settings.partitions[part]
    levels = {g: ch.wide(data["index"], g, codes) for g in settings.countries}
    weights = {g: ch.weight_table(data["item_weights"], codes, geo=g) for g in settings.countries}
    ea, _ = ch.two_level(levels, weights, _country_weights(data))
    return ea

def contribution_gap(data):
    codes = settings.contribution_codes
    ours = ch.contributions(ch.wide(data["index"], "EA", codes),
                            ch.weight_table(data["item_weights"], codes, geo="EA"))
    theirs = data["contributions"][data["contributions"].coicop.isin(codes)]
    theirs = theirs.pivot_table(index="month", columns="coicop", values="pp")
    theirs.index = ch.to_periods(theirs.index)

    common = ours.index.intersection(theirs.index)
    gap = (ours.loc[common, codes] - theirs.loc[common, codes]).dropna(how="all")
    worst = gap.abs().stack().idxmax()
    stats = {"months": int(len(gap)), "from": str(gap.index.min()),
             "max_abs_pp": float(gap.abs().max().max()), "mean_abs_pp": float(gap.abs().stack().mean()),
             "worst": f"{worst[1]} {worst[0]}"}
    return stats, gap

def freshness(data, today=None):
    today = pd.Timestamp(today or date.today())
    # Eurostat first: by this date last month's final HICP should be out
    latest = data["index"].month.max()
    expected = (today - pd.Timedelta(days=settings.hicp_release_lag_days)).to_period("M") - 1
    out = [{"source": "Eurostat HICP", "latest": f"{latest:%Y-%m}",
            "ok": latest.to_period("M") >= expected, "rule": f"at least {expected}"}]

    for name, days in settings.freshness_days.items():
        path = settings.silver / f"{name}.parquet"
        if not path.exists():
            out.append({"source": name, "latest": None, "ok": False, "rule": "missing"})
            continue
        last = pd.read_parquet(path, columns=["date"]).date.max()
        out.append({"source": name, "latest": f"{last:%Y-%m-%d}",
                    "ok": (today - last).days <= days, "rule": f"within {days} days"})
    return out

def run():
    data = _load()
    official = _official(data)
    published = data["official_rates"].query("coicop == 'TOTAL'").set_index("month").value
    published.index = ch.to_periods(published.index)
    rebuilt = {
        "V1": ("euro area rebuilt from the 6 main groups", rebuild_partition(data, "groups")),
        "V2": ("euro area rebuilt from the 13 COICOP divisions", rebuild_partition(data, "divisions")),
        "V3": ("euro area rebuilt from the 21 national indices", rebuild_from_countries(data)),
        "V3b": ("euro area rebuilt two levels deep (groups within countries)", rebuild_two_level(data)),
        "V3c": ("euro area rebuilt two levels deep (divisions within countries)", rebuild_two_level(data, "divisions"))}
    gates, gaps = [], {}
    for gid, (name, series) in rebuilt.items():
        stats, diff = compare(series, official, published)
        gaps[gid] = diff
        gates.append({"id": gid, "name": name, "ok": stats["max_abs_pp"] <= settings.yoy_tolerance_pp,
                      "threshold_pp": settings.yoy_tolerance_pp, **stats})

    stats, contribution_gaps = contribution_gap(data)
    gates.append({"id": "V4", "name": "contributions match Eurostat's published contributions",
                  "ok": stats["max_abs_pp"] <= settings.contribution_tolerance_pp,
                  "threshold_pp": settings.contribution_tolerance_pp, **stats})

    fresh = freshness(data)
    hicp = fresh[0]  # only Eurostat can fail the gates, the rest just warn
    gates.append({"id": "V5", "name": "Eurostat data is current", "ok": hicp["ok"],
                  "detail": f"{hicp['rule']}, latest {hicp['latest']}"})

    result = {"gates": gates, "freshness": fresh}
    settings.gold.mkdir(parents=True, exist_ok=True)
    (settings.gold / "validation.json").write_text(json.dumps(result, indent=2, default=str))
    pd.DataFrame(gaps).to_parquet(settings.gold / "validation_yoy_gaps.parquet")
    contribution_gaps.to_parquet(settings.gold / "validation_contribution_gaps.parquet")
    return result
