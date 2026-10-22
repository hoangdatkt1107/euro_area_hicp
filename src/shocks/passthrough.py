"""Local projections: how far each group moves after a 1% oil, gas or energy shock that holds.
Responses are scaled by the shock's own path; Newey-West with h+1 lags as the windows overlap"""
import json
import numpy as np
import pandas as pd
from src import chain as ch
from src.config import settings
from src.forecast import features as ft
from src.forecast import realtime as rt
from src.qa import INK, _figure, _save, _style, _table

# shock -> groups it is traced into. Gas only into electricity and gas: its estimates for fuels and
# food just pick up oil moving with it. Energy is the HICP energy surprise, so only the second round
TARGETS = {"brent": settings.groups, "gas": ["ELC_GAS"], "energy": ["FOOD_P", "FOOD_NP", "IGD_NNRG", "SERV"]}
SHOWN = [1, 3, 6, 12, 18]

def _newey_west(X, e, lags):
    u = X * e[:, None]
    S = u.T @ u
    for k in range(1, lags + 1):
        g = u[k:].T @ u[:-k]
        S += (1 - k / (lags + 1)) * (g + g.T)
    # pinv: for a variable's response to its own shock, its lags and the shock's lags are the same columns
    bread = np.linalg.pinv(X.T @ X)
    return bread @ S @ bread

def irf(level: pd.Series, shock: pd.Series, exclude=None) -> pd.DataFrame:
    """Response of 100*log(level) from t-1 to t+h to a one-unit shock at t, for h = 0..lp_horizon"""
    y = 100 * np.log(level)
    dy = y.diff()
    lags = settings.lp_lags
    controls = [shock.shift(k) for k in range(1, lags + 1)] + [dy.shift(k) for k in range(1, lags + 1)]
    months = pd.get_dummies(pd.Series(y.index.month, index=y.index)).astype(float)

    rows = []
    for h in range(settings.lp_horizon + 1):
        d = pd.concat([y.shift(-h) - y.shift(1), shock, *controls, months], axis=1).dropna()
        if exclude:
            d = d[(d.index < pd.Period(exclude[0], freq="M")) | (d.index > pd.Period(exclude[1], freq="M"))]
        X, target = d.iloc[:, 1:].to_numpy(), d.iloc[:, 0].to_numpy()
        beta, *_ = np.linalg.lstsq(X, target, rcond=None)
        V = _newey_west(X, target - X @ beta, h + 1)
        rows.append({"h": h, "beta": beta[0], "se": np.sqrt(V[0, 0]), "n": len(d)})
    return pd.DataFrame(rows).set_index("h")

def _energy_surprise(energy: pd.Series) -> pd.Series:
    """Monthly % change of HICP energy that its own recent past and the month don't explain"""
    m = 100 * np.log(energy).diff()
    X = pd.concat([m.shift(k) for k in range(1, settings.lp_lags + 1)], axis=1)
    X = X.join(pd.get_dummies(pd.Series(m.index.month, index=m.index)).astype(float))
    d = pd.concat([m, X], axis=1).dropna()
    beta, *_ = np.linalg.lstsq(d.iloc[:, 1:].to_numpy(), d.iloc[:, 0].to_numpy(), rcond=None)
    return pd.Series(d.iloc[:, 0].to_numpy() - d.iloc[:, 1:].to_numpy() @ beta, index=d.index)

def estimate(snap) -> dict:
    """shock -> {"self": own response, group: response per 1% rise in the shock variable that holds}"""
    f = ft.build(snap)
    f = f[f.index <= f.attrs["last_hicp"]]
    levels = ch.wide(snap["index"], settings.euro_area, ["TOTAL", "NRG", *settings.groups])
    drivers = {"brent": f.brent, "gas": f.gas, "energy": levels.NRG}
    shocks = {"brent": 100 * np.log(f.brent).diff(), "gas": 100 * np.log(f.gas).diff(),
              "energy": _energy_surprise(levels.NRG)}

    out = {}
    for name, shock in shocks.items():
        own = irf(drivers[name].dropna(), shock)
        own_ex = irf(drivers[name].dropna(), shock, exclude=settings.lp_exclude)
        res = {"self": own}
        for g in [*TARGETS[name], "TOTAL"]:
            r = irf(levels[g].dropna(), shock)
            robust = irf(levels[g].dropna(), shock, exclude=settings.lp_exclude)
            res[g] = pd.DataFrame({"elasticity": r.beta / own.beta, "beta": r.beta, "se": r.se,
                                   "elasticity_ex": robust.beta / own_ex.beta, "n": r.n})
        out[name] = res
    return out

def _figure_irfs(est) -> str:
    fig, axes = _figure((11, 3.4), ncols=3)
    titles = {"brent": "Brent in euro", "gas": "Gas in euro", "energy": "HICP energy surprise"}
    for ax, (name, res) in zip(axes, est.items(), strict=True):
        for g in TARGETS[name]:
            r = res[g]
            ax.plot(r.index, r.elasticity, color=settings.colors[g], linewidth=1.5, label=settings.label(g))
        key = {"brent": "FUEL", "gas": "ELC_GAS", "energy": "SERV"}[name]
        r, own = res[key], res["self"].beta
        ax.fill_between(r.index, (r.beta - 1.645 * r.se) / own, (r.beta + 1.645 * r.se) / own,
                        color=settings.colors[key], alpha=0.15, linewidth=0)
        ax.axhline(0, color=INK, linewidth=0.6)
        _style(ax, f"{titles[name]}: % per 1% that holds")
        ax.set_xlabel("months after the shock", fontsize=9)
    axes[0].legend(frameon=False, fontsize=7)
    return _save(fig, "passthrough.png")

def write() -> dict:
    tables = rt.load()
    snap = rt.snapshot(tables, tables["index"].month.max())
    est = estimate(snap)
    path = _figure_irfs(est)

    parts = []
    ex = f"h=12 ex {settings.lp_exclude[0][:4]}-{settings.lp_exclude[1][2:4]}"
    for name, res in est.items():
        rows = [{"group": settings.label(g), **{f"h={h}": res[g].elasticity[h] for h in SHOWN},
                 ex: res[g].elasticity_ex[12]}
                for g in [*TARGETS[name], "TOTAL"]]
        parts += [f"### {name}", "", _table(pd.DataFrame(rows), "{:.3f}"), ""]
    brent12 = est["brent"]["TOTAL"].elasticity[12]
    brent12_ex = est["brent"]["TOTAL"].elasticity_ex[12]
    food = est["energy"]["FOOD_P"]
    out = ["# Pass-through", "",
           "Local projections, monthly, euro area. % change in each group's level h months after a 1% "
           f"rise in the shock variable that holds. {settings.lp_lags} lags, month dummies, Newey-West. "
           f"The last column re-estimates without {settings.lp_exclude[0][:4]} to "
           f"{settings.lp_exclude[1][:4]}.", "",
           *parts,
           f"A 10% rise in Brent that holds lifts the all-items price level by about {10 * brent12:.2f}% after "
           f"a year ({10 * brent12_ex:.2f}% without 2020-23), mostly through fuels and then electricity and "
           "gas.", "",
           "The second round from energy into food, goods and services depends on 2021-23: processed "
           f"food moves {food.elasticity[12]:.2f}% per 1% on energy after a year with it, "
           f"{food.elasticity_ex[12]:.2f}% without. In 2022 energy and food also rose together partly for "
           "shared reasons (the war, fertiliser prices), so the full-sample number is an upper end.", "",
           f"![]({path})", ""]
    (settings.reports / "passthrough.md").write_text("\n".join(out) + "\n")

    keep = {name: {g: {"elasticity": r.elasticity.round(5).tolist(),
                       "elasticity_ex": r.elasticity_ex.round(5).tolist()}
                   for g, r in res.items() if g != "self"}
            for name, res in est.items()}
    settings.gold.mkdir(parents=True, exist_ok=True)
    (settings.gold / "passthrough.json").write_text(json.dumps(keep, indent=1))
    return est
