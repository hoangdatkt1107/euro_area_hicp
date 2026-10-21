"""What had been published on the day a forecast is made. Models only ever see a snapshot.Values are today's vintage, so small later revisions do leak in,
first_release keeps the headline as it was first published"""
import pandas as pd
from src.config import settings

TABLES = ["index", "official_rates", "item_weights", "country_weights", "contributions",
          "first_release", "surveys", "brent_usd", "eurusd", "gas_eu_usd", "oil_bulletin"]
MONTHLY = {"index", "official_rates", "contributions", "first_release", "surveys"}
YEARLY = {"item_weights", "country_weights"}

def load(names=TABLES) -> dict[str, pd.DataFrame]:
    # the external tables are optional, skip any that weren't built
    paths = {n: settings.silver / f"{n}.parquet" for n in names}
    return {n: pd.read_parquet(p) for n, p in paths.items() if p.exists()}

def origin_date(month) -> pd.Timestamp:
    """Day the forecast after month T is made: T's final HICP is out by the 20th of T+1.
    January's final comes later, with the new weights, so that one waits for the end of February"""
    t = pd.Period(month, freq="M")
    if t.month == 1:
        return (t + 1).end_time.normalize()
    return (t + 1).start_time.replace(day=settings.hicp_release_lag_days)


def snapshot(tables: dict[str, pd.DataFrame], month) -> dict[str, pd.DataFrame]:
    """Every table cut to what was out on origin_date(month)"""
    t = pd.Period(month, freq="M")
    day = origin_date(t)
    out = {}
    for name, df in tables.items():
        if name in MONTHLY:
            keep = df.month <= t.start_time
        elif name in YEARLY:
            keep = df.year <= t.year 
        elif name == "gas_eu_usd":
            keep = df.date <= (t - settings.gas_lag_months).start_time
        elif name in settings.release_lag_days:
            keep = df.date <= day - pd.Timedelta(days=settings.release_lag_days[name])
        else:
            raise KeyError(f"no release rule for {name}")
        out[name] = df[keep]
    return out


def last_dates(snap: dict[str, pd.DataFrame]) -> dict[str, str | None]:
    """Latest observation in each table, for logs and the forecast report"""
    out = {}
    for name, df in snap.items():
        col = next(c for c in ("month", "date", "year") if c in df)
        last = df[col].max()
        if pd.isna(last):
            out[name] = None
        elif col == "year":
            out[name] = str(last)
        else:
            out[name] = f"{last:%Y-%m}" if col == "month" else f"{last:%Y-%m-%d}"
    return out
