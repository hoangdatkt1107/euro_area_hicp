"""Monthly table the models work from, built from a snapshot only. It runs to T + horizon, T being
the last HICP month; row T+1 only has the first two weeks of oil and pump prices, what's known on the 20th."""
from functools import cache
import pandas as pd
from dateutil.easter import easter
from src import chain as ch
from src.config import settings

@cache
def _easter_share(year: int) -> dict[int, float]:
    # share of the eight days up to Easter Sunday in March and in April; package holidays move with it
    e = pd.Timestamp(easter(year))
    days = pd.date_range(e - pd.Timedelta(days=7), e)
    return {m: float((days.month == m).mean()) for m in (3, 4)}

def _monthly(daily: pd.Series | None, months: pd.PeriodIndex, last: pd.Period) -> pd.DataFrame:
    """Whole-month mean (only for months up to T, the later ones aren't over) and the mean
    over the first two weeks"""
    if daily is None or daily.empty:
        return pd.DataFrame(index=months, columns=["full", "early"], dtype=float)
    full = daily.groupby(daily.index.to_period("M")).mean()
    early = daily[daily.index.day <= settings.early_day]
    early = early.groupby(early.index.to_period("M")).mean()
    return pd.DataFrame({"full": full[full.index <= last], "early": early}).reindex(months)

def _brent_eur(snap) -> pd.Series | None:
    if "brent_usd" not in snap or "eurusd" not in snap:
        return None
    usd = snap["brent_usd"].set_index("date").value
    fx = snap["eurusd"].set_index("date").value
    # the ECB doesn't fix on every day Brent trades
    fx = fx.reindex(fx.index.union(usd.index)).ffill().reindex(usd.index)
    return (usd / fx).dropna()

def _pump(snap) -> pd.Series | None:
    if "oil_bulletin" not in snap:
        return None
    wob = snap["oil_bulletin"]
    wob = wob[(wob.geo == "EUR") & (wob.tax == "with_tax")]
    w = wob.pivot_table(index="date", columns="product", values="price").reindex(columns=["euro95", "diesel"])
    return w.dropna().mean(axis=1)

def _gas_eur(snap, months: pd.PeriodIndex) -> pd.Series:
    if "gas_eu_usd" not in snap or "eurusd" not in snap:
        return pd.Series(index=months, dtype=float)
    gas = snap["gas_eu_usd"].set_index("date").value
    gas.index = gas.index.to_period("M")
    fx = snap["eurusd"].set_index("date").value
    fx = fx.groupby(fx.index.to_period("M")).mean()
    return (gas / fx.reindex(gas.index)).reindex(months)

def _chg(now: pd.Series, before: pd.Series) -> pd.Series:
    return (now / before - 1) * 100

def build(snap, horizon: int = settings.forecast_horizon) -> pd.DataFrame:
    """mom_* are monthly % changes of the euro area indices; % rather than log so the groups add
    up exactly to the headline. *_early_chg is the first two weeks of a month against the whole
    month before, the only part of T+1 there is on the 20th"""
    levels = ch.wide(snap["index"], settings.euro_area, ["TOTAL", *settings.groups])
    last = levels.index.max()
    months = pd.period_range(levels.index.min(), last + horizon, freq="M")

    out = pd.DataFrame(index=months)
    out["month"] = months.month
    out["easter"] = [_easter_share(p.year).get(p.month, 0.0) for p in months]
    out = out.join(_chg(levels, levels.shift(1)).add_prefix("mom_"))

    surveys = snap["surveys"].pivot_table(index="month", columns="series", values="value")
    surveys.index = surveys.index.to_period("M")
    # keep the columns even when a source is empty, models drop what has no data
    out = out.join(surveys.reindex(columns=[name for _, _, name in settings.surveys]))

    for name, daily in (("brent", _brent_eur(snap)), ("pump", _pump(snap))):
        m = _monthly(daily, months, last)
        out[name] = m.full
        out[f"{name}_chg"] = _chg(m.full, m.full.shift(1))
        out[f"{name}_early_chg"] = _chg(m.early, m.full.shift(1))

    out["gas"] = _gas_eur(snap, months)
    out["gas_chg"] = _chg(out.gas, out.gas.shift(1))

    out.attrs["last_hicp"] = last
    return out
