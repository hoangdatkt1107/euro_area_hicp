"""Ridge per group on everything at hand, then chain-linked like bottom_up"""
import numpy as np
import pandas as pd
from src.config import settings
from src.forecast.models.common import ahead, chain_groups, usable

EXTRA = ["easter", "pump_early_chg", "brent_early_chg", "brent_chg_l1", "gas_l3_6",
         "retail_l1", "services_l1", "industry_l1"]
PENALTIES = np.logspace(-1, 3, 13)
VALIDATION = 24

def _ridge(X, y, penalty):
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    beta = np.linalg.solve(Z.T @ Z + penalty * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    return lambda x: y.mean() + ((x - mu) / sd) @ beta

def _groups(f) -> pd.DataFrame:
    last, months = f.attrs["last_hicp"], ahead(f)
    train = (f.index <= last) & (f.index > last - settings.window_months)
    groups = settings.groups
    y = pd.DataFrame({g: f[f"mom_{g}"] for g in groups})
    seasonal = y[train].groupby(f.month[train]).mean()
    extra = usable(f, EXTRA, train)

    def adjusted(t):
        return (y.loc[t] - seasonal.loc[t.month]).to_numpy()

    def row(t):
        return np.r_[adjusted(t - 1), adjusted(t - 2), f.loc[t, extra].to_numpy(float)]

    fitted = [t for t in f.index[train] if t - 2 >= f.index[0]]
    X = np.array([row(t) for t in fitted])
    Y = np.array([adjusted(t) for t in fitted])
    keep = ~np.isnan(X).any(axis=1) & ~np.isnan(Y).any(axis=1)
    X, Y = X[keep], Y[keep]

    fits = {}
    for j, g in enumerate(groups):
        fit, val = slice(None, -VALIDATION), slice(-VALIDATION, None)
        errors = [np.mean((_ridge(X[fit], Y[fit, j], p)(X[val]) - Y[val, j]) ** 2) for p in PENALTIES]
        fits[g] = _ridge(X, Y[:, j], PENALTIES[int(np.argmin(errors))])

    for t in months:
        x = row(t)
        y.loc[t] = [seasonal.at[t.month, g] + fits[g](x) for g in groups]
    return y.loc[months]

def forecast(f, snap, done):
    groups = _groups(f)
    return chain_groups(snap, groups), groups
