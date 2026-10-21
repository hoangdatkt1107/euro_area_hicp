"""Pseudo real-time backtest: at every month from 2012 on, forecast the next three months with only
what was out on that day, then line the forecasts up with what actually came out.

Output: data/gold/backtest.parquet, one row per variant, origin, model and horizon.
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import numpy as np
import pandas as pd
from loguru import logger

from src import chain as ch
from src.config import settings
from src.forecast import models as md
from src.forecast import realtime as rt

# each extra run blanks one source to see what it adds; only the regression models use them
ABLATIONS = {"no_bulletin": ("oil_bulletin", "price"), "no_brent": ("brent_usd", "value"),
             "no_surveys": ("surveys", "value"), "no_gas": ("gas_eu_usd", "value")}
REGRESSIONS = ["direct", "bottom_up", "average", "bottom_up_ridge"]

_tables = None


def _init(variant):
    # runs once per worker, so the tables are read once and not shipped with every task
    global _tables
    _tables = rt.load()
    if variant in ABLATIONS:
        name, col = ABLATIONS[variant]
        _tables[name] = _tables[name].assign(**{col: np.nan})


def _one(origin, models):
    preds = md.predict(rt.snapshot(_tables, origin), models=models)
    out = pd.concat(preds, names=["model", "target"]).reset_index()
    return out.assign(origin=pd.Period(origin, freq="M"))


def actuals(tables) -> pd.DataFrame:
    """What came out for each month: YoY from today's index, YoY as first published, and the
    monthly changes of the headline and the groups."""
    levels = ch.wide(tables["index"], settings.euro_area, ["TOTAL", *settings.groups])
    first = tables["first_release"].query("coicop == 'TOTAL' and release == 'FIN'")
    first = pd.Series(first.value.to_numpy(), index=first.month.dt.to_period("M"))
    mom = (levels / levels.shift(1) - 1) * 100
    out = pd.DataFrame({"actual_yoy": ch.yoy(levels.TOTAL), "first_yoy": first, "actual_mom": mom.TOTAL})
    return out.join(mom[settings.groups].add_prefix("actual_"))


def run(variant="full", workers=None) -> pd.DataFrame:
    tables = rt.load()
    last = tables["index"].month.max().to_period("M")
    # the last origins only have their first horizons realised, evaluate sorts that out
    origins = [str(m) for m in pd.period_range(settings.backtest_start, last - 1, freq="M")]
    models = settings.models if variant == "full" else REGRESSIONS

    start = time.perf_counter()
    workers = workers or os.cpu_count()
    if workers == 1:
        _init(variant)
        parts = [_one(o, models) for o in origins]
    else:
        with ProcessPoolExecutor(workers, initializer=_init, initargs=(variant,)) as pool:
            parts = list(pool.map(_one, origins, repeat(models)))
    logger.info(f"backtest {variant}: {len(origins)} origins, {origins[0]} to {origins[-1]}, "
                f"{time.perf_counter() - start:.0f}s")

    out = pd.concat(parts, ignore_index=True).join(actuals(tables), on="target")
    out["origin_date"] = [rt.origin_date(o) for o in out.origin]
    out["variant"] = variant
    for col in ("origin", "target"):
        out[col] = out[col].dt.to_timestamp()  # parquet keeps timestamps more reliably than periods
    first = ["variant", "origin", "origin_date", "model", "h", "target", "mom", "yoy",
             "actual_mom", "actual_yoy", "first_yoy"]
    return out[first + [c for c in out.columns if c not in first]]


def build(ablations=True, workers=None) -> pd.DataFrame:
    variants = ["full", *ABLATIONS] if ablations else ["full"]
    out = pd.concat([run(v, workers) for v in variants], ignore_index=True)
    settings.gold.mkdir(parents=True, exist_ok=True)
    out.to_parquet(settings.gold / "backtest.parquet", index=False)
    logger.info(f"gold/backtest: {len(out):,} rows")
    return out
