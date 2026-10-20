import json
from datetime import UTC, datetime
import pandas as pd
from loguru import logger
from src.config import settings
from src.sources import eurostat, external
from src.sources import httpx as net

# Eurostat's observation flags, as they show up in this data
FLAG_MEANING = {"b": "break in series", "d": "definition differs", "e": "estimated",
                "p": "provisional", "u": "low reliability"}

def _month(col):
    return pd.PeriodIndex(col.astype(str), freq="M").to_timestamp()

def _vintage(raw):
    # when Eurostat last updated the dataset
    if "last_update" not in raw or raw["last_update"].isna().all():
        return None
    return str(pd.to_datetime(raw["last_update"], utc=True).max())

def _tidy(raw, value, keep):
    df = raw.rename(columns={"coicop18": "coicop", "obs_value": value, "obs_flag": "flag"})
    df = df.dropna(subset=[value])
    if "month" in keep:
        df = df.assign(month=_month(df.time_period))
    if "year" in keep:
        df = df.assign(year=df.time_period.astype(int))
    return df[keep]

def _save(name, df):
    df.reset_index(drop=True).to_parquet(settings.silver / f"{name}.parquet", index=False)
    logger.info(f"silver/{name}: {len(df):,} rows")

def _read(name):
    path = settings.silver / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else None

def build_eurostat(refresh=False):
    # download everything before writing anything, so one failed request can't leave
    # silver half old and half new
    idx = eurostat.indices(refresh)
    rates = eurostat.official_rates(refresh)
    iw = eurostat.item_weights(refresh)
    cw = eurostat.country_weights(refresh)
    ctr = eurostat.contributions(refresh)
    fpd = eurostat.first_release(refresh)
    srv = eurostat.surveys(refresh)

    settings.silver.mkdir(parents=True, exist_ok=True)
    _save("index", _tidy(idx, "value", ["geo", "coicop", "month", "value", "flag"]))
    _save("official_rates", _tidy(rates, "value", ["coicop", "month", "value", "flag"]))
    _save("item_weights", _tidy(iw, "weight", ["geo", "coicop", "year", "weight", "flag"]))
    weights = _tidy(cw, "weight", ["geo", "year", "weight", "flag"])
    _save("country_weights", weights[weights.weight > 0])  # a zero weight is not membership
    _save("contributions", _tidy(ctr, "pp", ["coicop", "month", "pp", "flag"]))
    _save("first_release", _tidy(fpd, "value", ["coicop", "release", "month", "value", "flag"]))
    _save("surveys", _tidy(srv, "value", ["series", "month", "value", "flag"]))
    _save("labels", eurostat.all_labels())

    return {"prc_hicp_minr": _vintage(idx), "prc_hicp_iw": _vintage(iw), "prc_hicp_cw": _vintage(cw),
            "prc_hicp_ctr": _vintage(ctr), "prc_hicp_fpd": _vintage(fpd), "business_surveys": _vintage(srv)}

def _frame(s):
    return s.rename_axis("date").reset_index(name="value")

def build_external(refresh=False):
    # optional layer: a source that fails is logged and noted, the run carries on
    loaders = {
        "brent_usd": lambda: _frame(external.brent_usd(refresh)),
        "eurusd": lambda: _frame(external.eurusd(refresh)),
        "gas_eu_usd": lambda: _frame(external.gas_usd_mmbtu(refresh)),
        "oil_bulletin": lambda: external.oil_bulletin(refresh),
    }
    status = {}
    for name, load in loaders.items():
        try:
            df = load()
        except Exception as exc:
            logger.warning(f"{name} failed: {exc}")
            status[name] = f"failed: {exc}"
            continue
        _save(name, df)
        status[name] = str(df.date.max().date())
    return status

def _full_years(iw, geo, codes):
    # years in which every code of the partition has a weight and they add up to 1000
    w = iw[(iw.geo == geo) & iw.coicop.isin(codes)]
    w = w.pivot_table(index="year", columns="coicop", values="weight").reindex(columns=codes).dropna()
    return sorted(w.index[(w.sum(axis=1) - 1000).abs() <= settings.weight_sum_tolerance].tolist())

def coverage():
    """One row per geo: when each partition becomes usable, and how many flagged observations"""
    idx, iw, cw = _read("index"), _read("item_weights"), _read("country_weights")
    starts = idx.groupby(["geo", "coicop"]).month.min().unstack()
    ends = idx.groupby(["geo", "coicop"]).month.max().unstack()
    rows = []
    for geo in [settings.euro_area, *settings.countries]:
        row = {"geo": geo, "total_from": starts.loc[geo, "TOTAL"], "last_month": ends.loc[geo].max()}
        for part, codes in settings.partitions.items():
            complete = all(c in starts.columns and pd.notna(starts.loc[geo, c]) for c in codes)
            row[f"{part}_index_from"] = starts.loc[geo, codes].max() if complete else None
            years = _full_years(iw, geo, codes)
            row[f"{part}_weights_from"] = years[0] if years else None
            row[f"{part}_weights_to"] = years[-1] if years else None
        member = cw[cw.geo == geo].year
        row["in_ea_weights_from"] = int(member.min()) if len(member) else None
        row["flagged_obs"] = int(((idx.geo == geo) & idx.flag.notna()).sum())
        rows.append(row)
    return pd.DataFrame(rows)

def late_series():
    """Series that start later than the all-items index of the same geo"""
    starts = _read("index").groupby(["geo", "coicop"]).month.min().rename("start").reset_index()
    total = starts[starts.coicop == "TOTAL"].set_index("geo").start
    late = starts.assign(total_start=starts.geo.map(total)).query("start > total_start")
    return late.sort_values(["geo", "coicop"]).reset_index(drop=True)

def find_gaps(idx):
    """Series with a missing month somewhere between their first and last observation"""
    out = []
    for (geo, code), g in idx.groupby(["geo", "coicop"]):
        if len(pd.period_range(g.month.min(), g.month.max(), freq="M")) != g.month.nunique():
            out.append(f"{geo}/{code}")
    return out

def weight_deviation(iw, codes, part, accepted):
    """Distance from 1000 for every geo-year with a complete partition. Returns the deviations without the accepted exceptions, the exceptions that were left out,
    and the index of complete geo-years"""
    w = iw[iw.coicop.isin(codes)].pivot_table(index=["geo", "year"], columns="coicop", values="weight")
    full = w.reindex(columns=codes).dropna()
    dev = (full.sum(axis=1) - 1000).abs()
    known = [k for k in dev.index if f"{k[0]}/{k[1]}/{part}" in accepted]
    return dev.drop(known), known, full.index

def membership_errors(cw, join, since=1999):
    """Years where the countries with a weight don't match who was in the euro that year"""
    out = []
    for year, g in cw[cw.year >= since].groupby("year"):
        expected = {c for c, y in join.items() if y <= year}
        have = set(g.geo)
        if have != expected:
            out.append(f"{year}: extra {sorted(have - expected)}, missing {sorted(expected - have)}")
    return out

def checks():
    out = []
    def check(name, ok, detail, layer="eurostat"):
        out.append({"check": name, "ok": bool(ok), "detail": detail, "layer": layer})
    idx = _read("index")
    geos = [settings.euro_area, *settings.countries]
    codes = settings.codes

    # the index itself
    dupes = int(idx.duplicated(["geo", "coicop", "month"]).sum())
    check("index: no duplicate keys", dupes == 0, f"{dupes} duplicates")

    gaps = find_gaps(idx)
    check("index: no missing months inside a series", not gaps,
          f"{len(gaps)} series with gaps" + (f": {', '.join(gaps[:10])}" if gaps else ""))

    bad = int((idx.value <= 0).sum())
    check("index: all values positive", bad == 0, f"{bad} non-positive values")
    present = set(map(tuple, idx[["geo", "coicop"]].drop_duplicates().values))
    known = {tuple(k.split("/")) for k in settings.known_gaps}
    missing = [f"{g}/{c}" for g in geos for c in codes if (g, c) not in present and (g, c) not in known]
    total = len(geos) * len(codes)
    check("index: every requested series returned data", not missing,
          f"{total - len(missing) - len(known)} of {total} present"
          + (f"; missing: {', '.join(missing[:15])}" if missing else ""))

    last = idx.groupby(["geo", "coicop"]).month.max()
    behind = ", ".join(f"{g}/{c}" for g, c in last[last < last.max()].index[:10])
    check("index: every series reaches the latest month", not behind,
          f"latest month {last.max():%Y-%m}" + (f"; behind: {behind}" if behind else ""))

    # weights
    iw = _read("item_weights")
    latest_year = int(iw.year.max())
    tol = settings.weight_sum_tolerance
    for part, pcodes in settings.partitions.items():
        dev, accepted, complete = weight_deviation(iw, pcodes, part, settings.known_weight_issues)
        incomplete = [g for g in geos if (g, latest_year) not in complete]
        check(f"weights: {part} sum to 1000 in every complete year", dev.max() <= tol and not incomplete,
              f"max deviation {dev.max():.2f} over {len(dev)} geo-years"
              + (f"; accepted exceptions: {', '.join(f'{g} {y}' for g, y in accepted)}" if accepted else "")
              + (f"; incomplete in {latest_year}: {', '.join(incomplete)}" if incomplete else ""))

    cw = _read("country_weights")
    dev = (cw.groupby("year").weight.sum() - 1000).abs()
    check("country weights: sum to 1000 every year", dev.max() <= tol,
          f"max deviation {dev.max():.2f} over {dev.size} years")

    wrong = membership_errors(cw, settings.euro_join)
    check("country weights: members match the euro area of each year", not wrong,
          "; ".join(wrong[:5]) or "membership correct for every year since 1999")

    # a typo in the config would otherwise just come back as an empty series
    lab = _read("labels")
    official = set(map(tuple, lab[["dimension", "code"]].values))
    wanted = [("coicop18", c) for c in codes + settings.contribution_codes] + [("geo", g) for g in geos]
    unknown = sorted({f"{d}={c}" for d, c in wanted if (d, c) not in official})
    check("codes: every configured code exists in Eurostat's code lists", not unknown,
          f"{len(set(wanted))} codes checked" + (f"; unknown: {', '.join(unknown)}" if unknown else ""))

    # the other Eurostat tables should be as recent as the index
    ctr = _read("contributions")
    check("contributions: available for the latest month", ctr.month.max() == last.max(),
          f"latest {ctr.month.max():%Y-%m}")

    fpd = _read("first_release")
    fin = fpd[(fpd.coicop == "TOTAL") & (fpd.release == "FIN")]
    check("first releases: final release up to the latest month", fin.month.max() == last.max(),
          f"{len(fin)} months, {fin.month.min():%Y-%m} to {fin.month.max():%Y-%m}")

    s_last = _read("surveys").groupby("series").month.max()
    check("surveys: all three series reach the latest HICP month",
          len(s_last) == len(settings.surveys) and (s_last >= last.max()).all(),
          ", ".join(f"{k} {v:%Y-%m}" for k, v in s_last.items()))

    # optional layer: these get reported but never stop the pipeline
    for name in ("brent_usd", "eurusd", "gas_eu_usd"):
        d = _read(name)
        if d is None:
            check(f"external: {name} available", False, "not built", "external")
        else:
            check(f"external: {name} available", (d.value > 0).all() and not d.date.duplicated().any(),
                  f"{len(d):,} obs to {d.date.max():%Y-%m-%d}", "external")

    wob = _read("oil_bulletin")
    if wob is None:
        check("external: oil bulletin available", False, "not built", "external")
    else:
        need = {(g, t) for g in ("EUR", "DE", "ES") for t in ("with_tax", "without_tax")}
        have = set(map(tuple, wob[["geo", "tax"]].drop_duplicates().values))
        check("external: oil bulletin has euro area, DE and ES, with and without tax", need <= have,
              f"{wob.geo.nunique()} geos, weeks to {wob.date.max():%Y-%m-%d}", "external")
    return out

def flag_summary(name="index"):
    """Where each observation flag shows up in a table: period, geographies, main series."""
    df = _read(name)
    when = "month" if "month" in df else "year"
    show = (lambda v: f"{v:%Y-%m}") if when == "month" else str
    series = next(c for c in ("coicop", "series", "geo") if c in df)
    n_geos = 1 + len(settings.countries)
    rows = []
    for flag, g in df[df.flag.notna()].groupby("flag"):
        geos = sorted(g.geo.unique()) if "geo" in g else [settings.euro_area]
        row = {"flag": flag, "meaning": FLAG_MEANING.get(flag, "?"), "observations": len(g),
               f"{when}s": f"{show(g[when].min())} to {show(g[when].max())}",
               "geographies": f"all {len(geos)}" if len(geos) == n_geos else ", ".join(geos),
               "main series": ", ".join(g[series].value_counts().head(4).index)}
        if "release" in g:
            row["release"] = ", ".join(sorted(g.release.unique()))
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("observations", ascending=False)

def fuel_tax_table(weeks=6, geos=("EUR", "DE", "ES", "IT", "FR", "NL")):
    """Tax per litre (price with tax minus price without) over the last few weeks."""
    wob = _read("oil_bulletin")
    if wob is None:
        return pd.DataFrame()
    w = wob[wob.geo.isin(geos)].pivot_table(index=["date", "geo", "product"], columns="tax", values="price")
    w = (w["with_tax"] - w["without_tax"]).rename("tax_per_litre").reset_index()
    recent = sorted(w.date.unique())[-weeks:]
    t = w[w.date.isin(recent)].pivot_table(index=["geo", "product"], columns="date", values="tax_per_litre")
    t["change"] = t.iloc[:, -1] - t.iloc[:, 0]
    return t.round(3)

def build(refresh=False, with_external=True):
    net.events.clear()
    vintage = build_eurostat(refresh)
    ext = build_external(refresh) if with_external else {}
    report = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "vintage": vintage,
        "external": ext,
        "fallbacks": list(net.events),
        "checks": checks(),
    }
    coverage().to_parquet(settings.silver / "coverage.parquet", index=False)
    (settings.silver / "manifest.json").write_text(json.dumps(report, indent=2, default=str))
    return report