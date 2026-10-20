"""reports/data_quality.md and reports/series_coverage.csv, rebuilt on every 'make data'."""
import json
import pandas as pd
from src import silver
from src.config import settings

def _cell(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    if isinstance(v, pd.Timestamp):
        return f"{v:%Y-%m}"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)

def _table(df):
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)

def data_quality():
    manifest = json.loads((settings.silver / "manifest.json").read_text())
    cov = pd.read_parquet(settings.silver / "coverage.parquet")
    idx = pd.read_parquet(settings.silver / "index.parquet")

    out = ["# Data quality", "", f"Built {manifest['built_at']} UTC by 'make data'.", ""]

    out += ["## Checks", "", "| layer | check | result | detail |", "|---|---|---|---|"]
    for c in manifest["checks"]:
        out.append(f"| {c['layer']} | {c['check']} | {'pass' if c['ok'] else 'FAIL'} | {c['detail']} |")

    out += ["", "## Vintages", "", "| source | last update |", "|---|---|"]
    for source, when in {**manifest["vintage"], **manifest["external"]}.items():
        out.append(f"| {source} | {when} |")
    if manifest["fallbacks"]:
        out += ["", "Fetch failed, used the last stored copy:", ""]
        out += [f"- {e['source']}/{e['name']}: {e['fallback']} ({e['error']})" for e in manifest["fallbacks"]]

    if settings.known_weight_issues:
        out += ["", "## Accepted issues", ""]
        out += [f"- `{k}`: {v}" for k, v in settings.known_weight_issues.items()]

    cols = ["geo", "country", "total_from", "groups_index_from", "groups_weights_from",
            "divisions_index_from", "divisions_weights_from", "in_ea_weights_from",
            "last_month", "flagged_obs"]
    out += ["", "## Coverage", "",
            "Index from: first month with every series. Weights from: first year the weights add up to 1000",
            "", _table(cov.assign(country=cov.geo.map(settings.label))[cols]),
            "", "Per series: `series_coverage.csv`."]

    late = silver.late_series()
    if not late.empty:
        late = late.assign(series=late.coicop.map(settings.label))
        out += ["", "## Series starting after all-items", "",
                _table(late[["geo", "coicop", "series", "start", "total_start"]])]

    out += ["", "## Flags", "", f"Index: {idx.flag.notna().sum():,} of {len(idx):,} observations flagged",
            "", _table(silver.flag_summary())]
    for name in ("official_rates", "item_weights", "country_weights", "contributions", "first_release",
                 "surveys"):
        flags = silver.flag_summary(name)
        if not flags.empty:
            out += ["", f"### {name}", "", _table(flags)]

    tax = silver.fuel_tax_table()
    if not tax.empty:
        tax.columns = [c if isinstance(c, str) else f"{c:%d %b}" for c in tax.columns]
        out += ["", "## Fuel tax per litre, last 6 bulletins (EUR)", "",
                "With-tax minus without-tax price. EUR = euro area average.", "", _table(tax.reset_index())]
    return "\n".join(out) + "\n"

def series_coverage():
    """One row per series: first and last month, observations, how many are flagged"""
    idx = pd.read_parquet(settings.silver / "index.parquet")
    g = idx.groupby(["geo", "coicop"])
    out = pd.DataFrame({"first_month": g.month.min().dt.strftime("%Y-%m"),
                        "last_month": g.month.max().dt.strftime("%Y-%m"),
                        "observations": g.size(), "flagged": g.flag.count()}).reset_index()
    out.insert(2, "series", out.coicop.map(settings.label))
    return out

def write():
    settings.reports.mkdir(exist_ok=True)
    series_coverage().to_csv(settings.reports / "series_coverage.csv", index=False)
    path = settings.reports / "data_quality.md"
    path.write_text(data_quality())
    return str(path)
