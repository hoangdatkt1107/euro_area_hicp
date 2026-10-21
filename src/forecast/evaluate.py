"""Backtest scores, the model choice and the forecast intervals. Writes reports/forecast_evaluation.md, a figure, and data/gold/evaluation.json for the forecast.
Errors are forecast minus outcome, so a positive bias means the model ran too high"""
import json
import numpy as np
import pandas as pd
from scipy import stats
from src.config import settings
from src.qa import INK, MUTED, _figure, _save, _style, _table

PERIODS = {"2015-19": ("2015-01", "2019-12"), "2020-23": ("2020-01", "2023-12"),
           "2024-26": ("2024-01", "2026-12")}
LEVELS = {50: (0.25, 0.75), 90: (0.05, 0.95)}
COLORS = {"no_change": "silver", "seasonal": "darkgray", "direct": "tab:orange", "bottom_up": "tab:blue",
          "average": "tab:green", "bottom_up_ridge": "tab:purple"}
BENCHMARK = "no_change"

def load() -> pd.DataFrame:
    return pd.read_parquet(settings.gold / "backtest.parquet")

def sample(bt, variant="full") -> pd.DataFrame:
    """Origins from eval_start with all three horizons out, so every model and horizon is scored
    on the same months."""
    d = bt[(bt.variant == variant) & (bt.origin >= pd.Timestamp(settings.eval_start))]
    done = d.groupby("origin").actual_yoy.apply(lambda s: s.notna().all())
    return d[d.origin.isin(done[done].index)]

def scores(d, target="actual_yoy") -> pd.DataFrame:
    g = d.assign(e=d.yoy - d[target]).groupby(["model", "h"]).e
    return pd.DataFrame({"rmse": g.apply(lambda e: np.sqrt((e ** 2).mean())),
                         "mae": g.apply(lambda e: e.abs().mean()), "bias": g.mean(), "n": g.size()})

def diebold_mariano(e1, e2, h) -> tuple[float, float]:
    """Squared-error DM test with the Harvey-Leybourne-Newbold small-sample fix. Negative means
    e1 is the smaller error. Returns the statistic and a two-sided p-value from t(n-1)"""
    d = np.asarray(e1) ** 2 - np.asarray(e2) ** 2
    n = len(d)
    dc = d - d.mean()
    # h-step errors overlap, so h-1 autocovariances
    var = dc @ dc / n + 2 * sum(dc[k:] @ dc[:-k] / n for k in range(1, h))
    if var <= 0:
        var = dc @ dc / n
    stat = d.mean() / np.sqrt(var / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return float(stat), float(2 * stats.t.sf(abs(stat), n - 1))

def _errors(d, model, h) -> pd.Series:
    rows = d[(d.model == model) & (d.h == h)].set_index("origin")
    return rows.yoy - rows.actual_yoy

def choose(table) -> tuple[str, pd.Series]:
    avg = table.rmse.groupby("model").mean()
    near = [m for m in settings.models if avg[m] <= avg.min() * (1 + settings.selection_tolerance)]
    return near[0], avg[settings.models]

def known_errors(bt, model, h, asof) -> pd.Series:
    """Outcome minus forecast for the last interval_errors forecasts whose outcome was out by
    the time of a forecast made after month 'asof'"""
    d = bt[(bt.variant == "full") & (bt.model == model) & (bt.h == h) & (bt.target <= asof)]
    d = d.dropna(subset=["actual_yoy"]).sort_values("target")
    return (d.actual_yoy - d.yoy).tail(settings.interval_errors)

def coverage(bt, d, model) -> pd.DataFrame:
    """How often the real-time intervals caught the outcome (%), overall and with the 2021-23
    surge split out, and how wide they were"""
    rows = []
    for _, r in d[d.model == model].iterrows():
        past = known_errors(bt, model, r.h, r.origin)
        if len(past) < settings.interval_min_errors:
            continue
        for level, (lo, hi) in LEVELS.items():
            low, high = r.yoy + past.quantile(lo), r.yoy + past.quantile(hi)
            rows.append({"level": f"{level}%", "h": int(r.h), "hit": 100 * (low <= r.actual_yoy <= high),
                         "surge": 2021 <= r.target.year <= 2023, "width": high - low})
    rows = pd.DataFrame(rows)
    g = rows.groupby(["level", "h"])
    return pd.DataFrame({"coverage": g.hit.mean(),
                         "excl. 2021-23": rows[~rows.surge].groupby(["level", "h"]).hit.mean(),
                         "2021-23": rows[rows.surge].groupby(["level", "h"]).hit.mean(),
                         "width (pp)": g.width.mean().map("{:.2f}".format), "n": g.size().astype(str)})

def _cov_line(cov, col) -> str:
    c = cov[cov.level == "90%"].set_index("h")[col]
    return ", ".join(f"{v:.0f}" for v in c)

def _figure_scores(d, table, model) -> str:
    fig, (left, right) = _figure((10, 3.6), ncols=2, gridspec_kw={"width_ratios": [1, 2.2]})
    for m in settings.models:
        r = table.loc[m]
        left.plot(r.index, r.rmse, marker="o", color=COLORS[m], linewidth=2 if m == model else 1.2,
                  label=settings.label(m))
    left.set_xticks([1, 2, 3])
    _style(left, "RMSE by horizon", "percentage points")
    left.set_xlabel("months ahead", fontsize=9, color=MUTED)
    left.legend(frameon=False, fontsize=8)

    one = d[(d.model == model) & (d.h == 1)].set_index("target").sort_index()
    three = d[(d.model == model) & (d.h == 3)].set_index("target").sort_index()
    right.plot(one.index, one.actual_yoy, color=INK, linewidth=1.6, label="actual")
    name = settings.label(model)
    right.plot(one.index, one.yoy, color=COLORS[model], linewidth=1, label=f"{name}, 1 month ahead")
    right.plot(three.index, three.yoy, color=COLORS[model], linewidth=1, linestyle="--",
               label=f"{name}, 3 months ahead")
    _style(right, "Euro area headline YoY: actual and forecasts", "%")
    right.legend(frameon=False, fontsize=8)
    return _save(fig, "forecast_backtest.png")

def write() -> str:
    bt = load()
    d = sample(bt)
    table = scores(d)
    model, avg = choose(table)

    # accuracy against no change, with DM p-values
    rows = []
    for (m, h), r in table.iterrows():
        p = np.nan if m == BENCHMARK else diebold_mariano(_errors(d, m, h), _errors(d, BENCHMARK, h), h)[1]
        rows.append({"model": m, "h": h, "RMSE": r.rmse, "MAE": r.mae, "bias": r.bias,
                     "RMSE / no change": r.rmse / table.loc[(BENCHMARK, h), "rmse"],
                     "DM p vs no change": "-" if np.isnan(p) else f"{p:.3f}"})
    acc = pd.DataFrame(rows).set_index("model").loc[settings.models].reset_index()
    acc["model"] = acc.model.map(settings.label)
    best_other = avg.drop(model).idxmin()
    dm = [diebold_mariano(_errors(d, model, h), _errors(d, best_other, h), h)[1] for h in (1, 2, 3)]

    by_period = {}
    for name, (start, end) in PERIODS.items():
        part = d[(d.target >= pd.Timestamp(start)) & (d.target <= pd.Timestamp(end))]
        by_period[name] = scores(part).rmse.groupby("model").mean()
    by_period = pd.DataFrame(by_period).loc[settings.models].rename(index=settings.label).reset_index()
    first = scores(d, "first_yoy").rmse.groupby("model").mean().loc[settings.models]

    # what each source adds: RMSE change when it's blanked out
    full_reg = table.rmse.unstack()
    abl = {}
    for variant in sorted(set(bt.variant) - {"full"}):
        t = scores(sample(bt, variant)).rmse.unstack()
        abl[variant] = ((t / full_reg.loc[t.index] - 1) * 100).mean(axis=1)
    abl = pd.DataFrame(abl).T.rename(columns=settings.label).reset_index(names="without")

    cov = coverage(bt, d, model).reset_index()
    asof = bt.target[bt.actual_yoy.notna()].max()
    live = {h: known_errors(bt, model, h, asof) for h in (1, 2, 3)}
    live_q = {h: {f"q{int(q * 100):02d}": float(e.quantile(q)) for lv in LEVELS.values() for q in lv}
              for h, e in live.items()}

    path = _figure_scores(d, table, model)
    gain = 1 - table.loc[(model, 1), "rmse"] / table.loc[(BENCHMARK, 1), "rmse"]
    name, other = settings.label(model), settings.label(best_other)
    n_origins = d.origin.nunique()
    out = ["# Forecast evaluation", "",
           f"Built by `python -m src evaluate`. {n_origins} origins, {d.origin.min():%Y-%m} to "
           f"{d.origin.max():%Y-%m}, every model scored on the same months against YoY from today's "
           "index.", "",
           "## Accuracy", "", _table(acc.round(3), "{:.3f}"), "",
           f"{name} has {gain:.0%} lower RMSE than no change one month ahead. Against {other}, the "
           f"runner-up, DM p-values by horizon are {', '.join(f'{p:.2f}' for p in dm)}.", "",
           f"![]({path})", "",
           "## Model choice", "",
           "Rule, set before the backtest ran: lowest RMSE averaged over the three horizons, and a "
           f"simpler model within {settings.selection_tolerance:.0%} of the best one wins. Order, simplest "
           f"first: {', '.join(map(settings.label, settings.models))}.", "",
           _table(avg.rename(index=settings.label).rename("avg RMSE").reset_index(), "{:.3f}"), "",
           f"Chosen: **{name}**.", "",
           "## By period", "", "Average RMSE over the three horizons, by target year:", "",
           _table(by_period, "{:.3f}"), "",
           "## Against the first release", "",
           "Same scores against YoY as first published (one decimal), average over horizons: "
           + ", ".join(f"{settings.label(m)} {v:.3f}" for m, v in first.items()) + ".", "",
           "## What each source adds", "",
           "Change in RMSE (%) when one source is blanked out, averaged over the horizons. Positive "
           "means the forecast gets worse without it.", "",
           _table(abl, "{:+.1f}"), "",
           "## Intervals", "",
           f"Quantiles of {name}'s last {settings.interval_errors} out-of-sample errors at each horizon, "
           "using only errors whose outcome was out at the time. Real-time coverage (%):", "",
           _table(cov, "{:.1f}"), "",
           f"Close to nominal outside 2021-23 ({_cov_line(cov, 'excl. 2021-23')} for the 90% band), far too "
           f"narrow during the surge ({_cov_line(cov, '2021-23')}): the errors before it gave no "
           "warning.", ""]
    path = settings.reports / "forecast_evaluation.md"
    path.write_text("\n".join(out) + "\n")

    result = {"selected": model, "sample": [f"{d.origin.min():%Y-%m}", f"{d.origin.max():%Y-%m}"],
              "avg_rmse": avg.round(4).to_dict(), "errors_up_to": f"{asof:%Y-%m}", "error_quantiles": live_q}
    (settings.gold / "evaluation.json").write_text(json.dumps(result, indent=2))
    return str(path)
