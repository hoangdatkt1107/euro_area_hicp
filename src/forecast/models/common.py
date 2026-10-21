"""Shared by the models: the assumptions for the months ahead, the regression most of them use,
and the way group forecasts turn into the headline."""
import numpy as np
import pandas as pd
from src import chain as ch
from src.config import settings

def ahead(f: pd.DataFrame) -> pd.PeriodIndex:
    return f.index[f.index > f.attrs["last_hicp"]]

def _path(f, name, level, months):
    """Fill brent or pump for the months ahead. T+1 is half known: the first two weeks are data, 
    the rest of the month follows the assumption"""
    last = f.attrs["last_hicp"]
    full_t = f.at[last, name]
    early = full_t * (1 + f.at[last + 1, f"{name}_early_chg"] / 100)
    if np.isnan(early):
        early = full_t
    level = pd.Series(early if level is None else level, index=months, dtype=float)

    first = months[0]
    known = settings.early_day / first.days_in_month
    f.loc[first, name] = known * early + (1 - known) * level[first]
    f.loc[months[1:], name] = level[months[1:]]
    full = f[name]
    f.loc[months, f"{name}_chg"] = (full / full.shift(1) - 1)[months] * 100
    f.loc[months[1:], f"{name}_early_chg"] = (level / full.shift(1) - 1)[months[1:]] * 100


def assume(f: pd.DataFrame, brent=None, pump=None, gas=None) -> pd.DataFrame:
    """The months ahead filled with the paths a forecast is conditional on. brent (EUR/bbl), pump (EUR/l) and gas (EUR/MMBtu) are levels for the months ahead, 
    one number or one per month. Left out, they stay where they are now. Surveys keep their last value"""
    f = f.copy()
    months = ahead(f)
    for name, level in (("brent", brent), ("pump", pump)):
        if f[name].notna().any():
            _path(f, name, level, months)

    known_gas = f.gas.last_valid_index()
    if known_gas is not None:
        gap = f.index[f.index > known_gas]
        f.loc[gap, "gas"] = f.at[known_gas, "gas"] if gas is None else gas
        f["gas_chg"] = (f.gas / f.gas.shift(1) - 1) * 100

    surveys = [name for _, _, name in settings.surveys]
    f[surveys] = f[surveys].ffill()

    f["retail_l1"] = f.retail_price_expectations.shift(1)
    f["services_l1"] = f.services_price_expectations.shift(1)
    f["industry_l1"] = f.industry_price_expectations.shift(1)
    f["brent_chg_l1"] = f.brent_chg.shift(1)
    f["gas_l3_6"] = f.gas_chg.shift(3).rolling(4).mean()  # retail energy follows wholesale gas slowly
    return f

def usable(f, columns, train) -> list[str]:
    """The regressors with enough history and a value in every month ahead."""
    months = ahead(f)
    return [c for c in columns
            if f.loc[train, c].notna().sum() >= settings.min_obs and f.loc[months, c].notna().all()]

def arx(f: pd.DataFrame, code: str, extra: list[str]) -> pd.Series:
    """Month dummies, Easter, momentum and 'extra', fitted by OLS on the last window_months up to T,
    then run forward one month at a time"""
    last, months = f.attrs["last_hicp"], ahead(f)
    y = f[f"mom_{code}"].copy()
    train = (f.index <= last) & (f.index > last - settings.window_months)
    extra = usable(f, extra, train)
    seasonal = y[train].groupby(f.month[train]).mean()

    def row(t):
        past = pd.period_range(t - 3, t - 1, freq="M")
        momentum = (y[past] - seasonal[past.month].values).mean()  # last 3 months, seasonally adjusted
        return np.r_[np.eye(12)[t.month - 1], f.at[t, "easter"], momentum, f.loc[t, extra].to_numpy(float)]

    fitted = [t for t in f.index[train] if t - 3 >= f.index[0]]
    X = np.array([row(t) for t in fitted])
    keep = ~np.isnan(X).any(axis=1) & y[fitted].notna().to_numpy()
    beta, *_ = np.linalg.lstsq(X[keep], y[fitted].to_numpy()[keep], rcond=None)

    for t in months:
        y[t] = row(t) @ beta
    return y[months]

def chain_groups(snap, groups: pd.DataFrame) -> pd.Series:
    """Headline monthly change implied by the groups' changes, chain-linked like Eurostat does"""
    levels = ch.wide(snap["index"], settings.euro_area, settings.groups)
    weights = ch.weight_table(snap["item_weights"], settings.groups, geo=settings.euro_area)
    for year in sorted(set(groups.index.year) - set(weights.index)):
        weights.loc[year] = weights.iloc[-1]  # next year's weights aren't out yet
    for t in groups.index:
        levels.loc[t] = levels.loc[t - 1] * (1 + groups.loc[t] / 100)
    agg = ch.chain(levels, weights, require_all=True)
    return ((agg / agg.shift(1) - 1) * 100)[groups.index]

def yoy(snap, mom: pd.Series) -> pd.Series:
    total = ch.wide(snap["index"], settings.euro_area, ["TOTAL"])["TOTAL"]
    return ch.yoy(ch.extend(total, mom.to_numpy()))[mom.index]
