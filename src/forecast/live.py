import json
import numpy as np
import pandas as pd
from matplotlib import dates as mdates
from src import chain as ch
from src.config import settings
from src.forecast import features as ft
from src.forecast import models as md
from src.forecast.models.common import chain_groups
from src.forecast import realtime as rt
from src.qa import BLUE, INK, MUTED, _figure, _save, _style, _table

QUANTILES = ["q05", "q25", "q75", "q95"]

def _passthrough(f) -> tuple[float, float]:
    """% change in pump prices per 1% on Brent in euro, this month and the month after."""
    d = pd.DataFrame({"pump": f.pump_chg, "now": f.brent_chg, "before": f.brent_chg.shift(1)}).dropna()
    X = np.column_stack([np.ones(len(d)), d.now, d.before])
    beta, *_ = np.linalg.lstsq(X, d.pump.to_numpy(), rcond=None)
    return float(beta[1]), float(beta[2])

def oil_basis(snap) -> dict:
    """Where Brent (EUR) and pump prices are now, the euro rate, and how pump prices follow Brent."""
    f = ft.build(snap)
    last = f.attrs["last_hicp"]
    now, later = _passthrough(f)
    return {"brent": f.at[last, "brent"] * (1 + f.at[last + 1, "brent_early_chg"] / 100),
            "pump": f.at[last, "pump"] * (1 + f.at[last + 1, "pump_early_chg"] / 100),
            "fx": snap["eurusd"].sort_values("date").value.iloc[-1], "now": now, "later": later}


def at_brent(snap, model, brent_usd, basis=None) -> pd.Series:
    """Headline YoY if Brent moves to brent_usd for the rest of the coming month and stays there.
    Pump prices follow with the estimated pass-through, gas and surveys stay put."""
    b = basis or oil_basis(snap)
    brent = brent_usd / b["fx"]
    move = brent / b["brent"] - 1
    later_months = settings.forecast_horizon - 1
    pump = [b["pump"] * (1 + b["now"] * move)] + [b["pump"] * (1 + (b["now"] + b["later"]) * move)] * later_months
    return md.predict(snap, models=[model], brent=brent, pump=pump)[model].yoy


def brent_for(snap, model, target, basis=None, lo=20.0, hi=200.0) -> float | None:
    """Brent ($) that puts the Q4 average at target, by bisection. None if it's outside lo to hi."""
    b = basis or oil_basis(snap)

    def q4(usd):
        yoy = at_brent(snap, model, usd, b)
        return yoy[yoy.index.quarter == 4].mean()

    if not q4(lo) <= target <= q4(hi):
        return None
    for _ in range(14):  # a cent or so is plenty
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if q4(mid) < target else (lo, mid)
    return (lo + hi) / 2


def scenarios(snap, model) -> dict:
    """Headline YoY under each oil path in settings.oil_scenarios."""
    b = oil_basis(snap)
    out = {}
    for name, (kind, value) in settings.oil_scenarios.items():
        usd = b["brent"] * b["fx"]
        if kind == "usd":
            usd = value
        elif kind == "pct":
            usd *= 1 + value / 100
        out[name] = {"brent_usd": float(usd), "yoy": at_brent(snap, model, usd, b)}
    return out


def _contributions(snap, groups) -> pd.DataFrame:
    """Each group's contribution to the headline YoY (pp), with the forecast group paths appended."""
    levels = ch.wide(snap["index"], settings.euro_area, settings.groups)
    weights = ch.weight_table(snap["item_weights"], settings.groups, geo=settings.euro_area)
    for year in sorted(set(groups.index.year) - set(weights.index)):
        weights.loc[year] = weights.iloc[-1]
    for t in groups.index:
        levels.loc[t] = levels.loc[t - 1] * (1 + groups.loc[t] / 100)
    return ch.contributions(levels, weights)

def _fuel_check(snap, groups) -> dict:
    """First-month fuels from pump prices alone, the figure qa_findings.md gives, against the model,
    and what the gap is worth on the headline."""
    f = ft.build(snap)
    last = f.attrs["last_hicp"]
    d = pd.DataFrame({"fuel": f.mom_FUEL, "pump": f.pump_chg}).dropna()
    slope, intercept = np.polyfit(d.pump[d.index >= pd.Period("2006-01", freq="M")],
                                  d.fuel[d.index >= pd.Period("2006-01", freq="M")], 1)
    pump = f.at[last + 1, "pump_early_chg"]
    alone = intercept + slope * pump
    swapped = groups.copy()
    swapped.iloc[0, swapped.columns.get_loc("FUEL")] = alone
    gap = chain_groups(snap, swapped).iloc[0] - chain_groups(snap, groups).iloc[0]
    return {"pump": pump, "pump_only": alone, "model": groups.FUEL.iloc[0],
            "brent": f.at[last + 1, "brent_early_chg"], "headline_pp": gap}


def _figure_forecast(history, main, band, scen, contrib) -> str:
    fig, (left, right) = _figure((10.5, 4.2), ncols=2, gridspec_kw={"width_ratios": [1.6, 1]})
    # start every forecast line at the last actual month so it joins the history
    start = history.index[-1]
    x = [start.to_timestamp(), *main.index.to_timestamp()]

    def joined(values):
        return [history.iloc[-1], *values]

    left.plot(history.index.to_timestamp(), history, color=INK, linewidth=1.6, label="actual")
    left.fill_between(x, joined(band.q05), joined(band.q95), color=BLUE, alpha=0.12, linewidth=0,
                      label="90% band")
    left.fill_between(x, joined(band.q25), joined(band.q75), color=BLUE, alpha=0.25, linewidth=0,
                      label="50% band")
    left.plot(x, joined(main.yoy), color=BLUE, marker="o", linewidth=1.8, label="forecast")
    # the first scenario is the forecast itself
    for (name, s), style in zip(list(scen.items())[1:], [":", "--"], strict=False):
        left.plot(x, joined(s["yoy"]), color=MUTED, linestyle=style, linewidth=1.2, label=name)
    left.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    left.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _style(left, "Euro area headline YoY (%)")
    left.legend(frameon=False, fontsize=8, loc="upper left")

    pos = np.zeros(len(contrib))
    neg = np.zeros(len(contrib))
    labels = [t.strftime("%b") for t in contrib.index]
    for g in settings.group_order:
        v = contrib[g].to_numpy()
        right.bar(labels, v, bottom=np.where(v >= 0, pos, neg), color=settings.colors[g],
                  label=settings.label(g))
        pos, neg = pos + np.clip(v, 0, None), neg + np.clip(v, None, 0)
    right.plot(labels, contrib.sum(axis=1), color=INK, marker="o", linewidth=0, label="total")
    _style(right, f"Contributions by group (pp), {labels[0]} actual")
    right.legend(frameon=False, fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    return _save(fig, "forecast.png")

def run() -> dict:
    tables = rt.load()
    last = tables["index"].month.max().to_period("M")
    snap = rt.snapshot(tables, last)
    ev = json.loads((settings.gold / "evaluation.json").read_text())
    model = ev["selected"]

    preds = md.predict(snap)
    main = preds[model]
    total = ch.wide(snap["index"], settings.euro_area, ["TOTAL"])["TOTAL"]
    split = ch.base_effect_split(total, main.mom.to_numpy())
    q = ev["error_quantiles"] 
    band = pd.DataFrame({k: main.yoy + [q[str(h)][k] for h in main.h] for k in QUANTILES})
    # the chosen model's own group paths, bottom_up's if it doesn't have any
    groups = preds[model] if set(settings.groups) <= set(preds[model].columns) else preds["bottom_up"]
    contrib = _contributions(snap, groups[settings.groups]).loc[last:]
    fuel = _fuel_check(snap, groups[settings.groups])
    scen = scenarios(snap, model)
    q4_only = bool((main.index.quarter == 4).all())
    ecb_brent = brent_for(snap, model, settings.ecb_q4) if q4_only else None
    history = ch.yoy(total).loc[last - 32:]

    path = _figure_forecast(history, main, band, scen, contrib)
    _write_report(snap, last, model, main, split, band, contrib, scen, preds, fuel, ecb_brent, path)

    result = {
        "made": f"{rt.origin_date(last):%Y-%m-%d}", "last_hicp": str(last), "data": rt.last_dates(snap),
        "model": model,
        "forecast": [{"month": str(t), "h": int(main.at[t, "h"]), "mom": main.at[t, "mom"],
                      "yoy": main.at[t, "yoy"], **band.loc[t].to_dict(),
                      "dropping_out": split.at[t, "dropping_out"], "new_months": split.at[t, "new_months"]}
                     for t in main.index],
        "contributions": {str(t): r.to_dict() for t, r in contrib.iterrows()},
        "scenarios": {name: {"brent_usd": s["brent_usd"], "yoy": s["yoy"].tolist()}
                      for name, s in scen.items()},
        "models": {name: p.yoy.tolist() for name, p in preds.items()},
        "fuel_check": fuel,
        "ecb_brent_usd": ecb_brent,
        "history": {str(t): v for t, v in history.items()}}
    (settings.gold / "forecast.json").write_text(json.dumps(result, indent=2, default=float))
    return result

def _write_report(snap, last, model, main, split, band, contrib, scen, preds, fuel, ecb_brent, fig) -> None:
    data = rt.last_dates(snap)
    first, end, last = main.index[0].to_timestamp(), main.index[-1].to_timestamp(), last.to_timestamp()
    table = pd.DataFrame({
        "month": [t.strftime("%b %Y") for t in main.index], "YoY %": main.yoy.to_numpy(),
        "50% band": [f"{a:.1f} to {b:.1f}" for a, b in zip(band.q25, band.q75, strict=True)],
        "90% band": [f"{a:.1f} to {b:.1f}" for a, b in zip(band.q05, band.q95, strict=True)],
        f"base effect since {last:%b} (pp)": split.dropping_out.to_numpy(),
        f"new months since {last:%b} (pp)": split.new_months.to_numpy()})
    groups = contrib[settings.group_order].rename(columns=settings.label)
    groups.index = [t.strftime("%b %Y") for t in groups.index]
    scen_table = pd.DataFrame({"scenario": list(scen),
                               "Brent ($)": [f"{s['brent_usd']:.0f}" for s in scen.values()],
                               **{t.strftime("%b"): [s["yoy"][t] for s in scen.values()]
                                  for t in main.index}})
    models = pd.DataFrame({settings.label(name): p.yoy.to_numpy() for name, p in preds.items()},
                          index=[t.strftime("%b") for t in main.index]).T.reset_index(names="model")
    q4 = main.yoy[main.index.quarter == 4].mean() if (main.index.quarter == 4).all() else None

    out = [f"# Forecast, {first:%B} to {end:%B %Y}", "",
           f"Made as of {rt.origin_date(last):%d %B %Y}: HICP to {data['index']}, "
           f"Brent to {data['brent_usd']}, "
           f"pump prices to {data['oil_bulletin']}, surveys to {data['surveys']}. "
           f"Model: {settings.label(model)}, picked in "
           "`forecast_evaluation.md`. Bands come from its past errors.", "",
           _table(table, "{:.2f}"), "",
           f"From {split.yoy_now.iloc[0]:.2f}% in {last:%B}: the months dropping out of the comparison add "
           f"{split.dropping_out.iloc[-1]:+.2f} pp by {end:%B} and the new months "
           f"{split.new_months.iloc[-1]:+.2f} pp.",
           "", f"Contributions by group (pp); {last:%B} is actual, the rest forecast:", "",
           _table(groups.round(2).reset_index(names="month"), "{:.2f}"), "",
           f"Fuels in {first:%B}: pump prices over the first two weeks are {fuel['pump']:+.1f}% on the "
           f"{last:%B} average, which on their own point to about {fuel['pump_only']:+.1f}% for HICP fuels "
           f"(the figure in `qa_findings.md`). {settings.label(model)} has {fuel['model']:+.2f}%: it also "
           f"weighs Brent's {fuel['brent']:+.0f}% move in the same weeks, more of which can still reach the "
           "pump later in the month, and the usual seasonal pattern for the month. Using the pump-only "
           f"figure instead would move the headline by {fuel['headline_pp']:+.2f} pp.", "",
           "Oil scenarios (YoY %). Brent moves from the second half of the coming month, pump prices "
           "follow with the pass-through estimated since 2005. The first month doesn't move: the model "
           "reads it off the first two weeks of pump prices, which are already in.", "",
           _table(scen_table, "{:.2f}"), "",
           "All models (YoY %):", "", _table(models, "{:.2f}"), ""]
    if q4 is not None:
        near = min(scen.values(), key=lambda s: abs(s["brent_usd"] - settings.ecb_oil_usd))
        q4_near = near["yoy"][near["yoy"].index.quarter == 4].mean()
        out += [f"Q4 average {q4:.2f}%. {settings.ecb_source} have {settings.ecb_q4}% for Q4 with oil at "
                f"about ${settings.ecb_oil_usd:.0f}. With Brent at ${near['brent_usd']:.0f}, the scenario "
                f"closest to that, the Q4 average is {q4_near:.2f}%, so most of the gap to the ECB is the "
                "oil price." + (f" Solving for it, the ECB's {settings.ecb_q4}% needs Brent near "
                                f"${ecb_brent:.0f}." if ecb_brent else ""), ""]
    out += [f"![]({fig})", ""]
    (settings.reports / "forecast.md").write_text("\n".join(out) + "\n")
