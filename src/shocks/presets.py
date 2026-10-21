"""Shock presets sized from the data, not typed in. Oil and gas moves are 100 x log changes,
the unit the pass-through was estimated in"""
import json
import numpy as np
import pandas as pd
from src.config import settings
from src.forecast import features as ft
from src.forecast import realtime as rt
from src.qa import BLUE, INK, _figure, _save, _style, _table
from src.shocks import engine as en

def _brent_now(snap) -> float:
    """Brent in dollars over the first two weeks after the last HICP month, the forecast's flat level"""
    f = ft.build(snap)
    last = f.attrs["last_hicp"]
    eur = f.at[last, "brent"] * (1 + f.at[last + 1, "brent_early_chg"] / 100)
    return float(eur * snap["eurusd"].sort_values("date").value.iloc[-1])

def _tax_cut(snap, geo) -> tuple[float, float, pd.Timestamp]:
    """The latest big step in fuel tax per litre (petrol and diesel averaged), the pump price
    after it, and the week it happened"""
    wob = snap["oil_bulletin"]
    p = wob[wob.geo == geo].pivot_table(index="date", columns=["product", "tax"], values="price")
    tax = sum(p[(fuel, "with_tax")] - p[(fuel, "without_tax")] for fuel in ("euro95", "diesel")) / 2
    steps = tax.diff()
    when = steps[steps.abs() >= 0.10].index[-1]  # VAT alone never moves 10 cents in a week
    price = (p[("euro95", "with_tax")] + p[("diesel", "with_tax")]).iloc[-1] / 2
    return float(steps[when]), float(price), when

def build(tables=None) -> list[dict]:
    tables = tables or rt.load()
    last = tables["index"].month.max().to_period("M")
    snap = rt.snapshot(tables, last)
    start = str(last + 2)  # the month after the one already half known
    brent = _brent_now(snap)
    step, price, week = _tax_cut(snap, "DE")
    cut_end = f"{last.year + 1}-01"

    return [
        {"name": "Brent back to $90", "partition": "groups",
         "oil": {"size": 100 * np.log(90 / brent), "start": start},
         "note": f"From ${brent:.0f}, the average of the first half of {(last + 1).strftime('%B')}."},
        {"name": "Brent up 20%", "partition": "groups",
         "oil": {"size": 100 * np.log(1.2), "start": start},
         "note": f"To ${1.2 * brent:.0f}."},
        {"name": "Gas up 50%", "partition": "groups",
         "gas": {"size": 100 * np.log(1.5), "start": start},
         "note": "Wholesale gas in euro; retail electricity and gas follow over a year or more."},
        {"name": "Germany's fuel tax cut ends", "partition": "groups",
         "shocks": [{"countries": ["DE"], "components": ["FUEL"], "size": -step / price * 100,
                     "start": cut_end}],
         "note": f"Weekly Oil Bulletin: tax per litre fell {-100 * step:.1f} cents on {week.day} {week:%b %Y}. "
                 f"Undoing it on a pump price of {price:.2f} EUR/l, from January {last.year + 1}. FUEL also holds "
                 "heating oil, so this is the upper end."},
        {"name": "Food up 5% in Germany and France", "partition": "divisions",
         "shocks": [{"countries": ["DE", "FR"], "components": ["CP01"], "size": 5, "start": start}],
         "note": "Illustrative; food and non-alcoholic beverages only."}]


def run(preset, bases, regime="normal", indirect=True) -> dict:
    base = bases[preset["partition"]]
    r = en.simulate(base, preset.get("shocks", ()), preset.get("oil"), preset.get("gas"),
                    indirect=indirect, regime=regime)
    return {k: r[k].round(6).tolist() for k in ("impact", "direct", "indirect")}

def _summary(months, res) -> dict:
    s = pd.Series(res["impact"], index=months)
    ind = pd.Series(res["indirect"], index=months)
    year = months[-1].year - 1
    peak = s.abs().idxmax()
    return {f"Dec {months[2].year}": s[f"{months[2].year}-12"], f"Dec {year}": s[f"{year}-12"],
            f"{year} avg": s[str(year)].mean(), "of which indirect": ind[str(year)].mean(),
            "peak": f"{s[peak]:+.2f} in {peak.strftime('%b %y')}"}

def _figure_presets(months, results) -> str:
    fig, ax = _figure((9, 3.6))
    # oil in blues, the rest in the colour of the group they hit
    colors = [BLUE, "lightskyblue", *(settings.colors[g] for g in ("ELC_GAS", "FUEL", "FOOD_P"))]
    for (name, res), colour in zip(results.items(), colors, strict=False):
        ax.plot(months.to_timestamp(), res["impact"], color=colour, linewidth=1.6, label=name)
    ax.axhline(0, color=INK, linewidth=0.6)
    _style(ax, "Effect on euro area headline YoY (pp)")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    return _save(fig, "shock_presets.png")

def write() -> list[dict]:
    tables = rt.load()
    bases = {p: en.baseline(tables, p) for p in ("groups", "divisions")}
    months = bases["groups"].months
    presets = build(tables)
    results = {p["name"]: run(p, bases) for p in presets}
    worse = {p["name"]: run(p, bases, regime="2022") for p in presets}

    year = str(months[-1].year - 1)
    rows = [{"preset": p["name"], **_summary(months, results[p["name"]]),
             f"{year} avg, like 2022": pd.Series(worse[p["name"]]["impact"], index=months)[year].mean()}
            for p in presets]
    table = pd.DataFrame(rows)
    path = _figure_presets(months, results)
    out = ["# Shock presets", "",
           "Change in euro area headline YoY (pp) against the baseline: the forecast to "
           f"{months[2].strftime('%b %Y')}, "
           "then each country's components on their usual seasonal path. Pass-through estimated without "
           "2020-23; the last column uses the full sample, where second-round effects are stronger.", "",
           _table(table, "{:+.2f}"), "",
           "| preset | how it is sized |", "|---|---|",
           *[f"| {p['name']} | {p['note']} |" for p in presets], "",
           f"![]({path})", ""]
    (settings.reports / "shocks.md").write_text("\n".join(out) + "\n")

    saved = [{**p, "results": results[p["name"]], "results_2022": worse[p["name"]]} for p in presets]
    (settings.gold / "presets.json").write_text(json.dumps({"months": [str(m) for m in months],
                                                            "presets": saved}, indent=1))
    return saved
