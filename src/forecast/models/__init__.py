"""Forecast models for the euro area headline, T+1 to T+H, one file each.
no_change: the YoY stays where it is
seasonal: median change of the same month in past years
direct: one regression on the headline
bottom_up: a regression per group, chain-linked into the headline
average: average of direct and bottom_up
bottom_up_ridge: ridge per group on everything at hand """

import pandas as pd
from src.config import settings
from src.forecast import features as ft
from src.forecast.models import average, bottom_up, bottom_up_ridge, direct, no_change, seasonal
from src.forecast.models.common import ahead, assume, yoy

MODELS = {"no_change": no_change, "seasonal": seasonal, "direct": direct, "bottom_up": bottom_up,
          "average": average, "bottom_up_ridge": bottom_up_ridge}

def predict(snap, models=None, **assumptions) -> dict[str, pd.DataFrame]:
    """Forecasts from one snapshot: model -> frame with h, mom and yoy for T+1..T+H, plus each
    group's monthly change for the models that go group by group."""
    models = models or settings.models
    f = assume(ft.build(snap), **assumptions)
    months = ahead(f)
    done = {}

    def run(name):
        if name not in done:
            for need in getattr(MODELS[name], "NEEDS", []):
                run(need)
            done[name] = MODELS[name].forecast(f, snap, done)
    out = {}
    for name in models:
        run(name)
        mom, groups = done[name]
        frame = pd.DataFrame({"h": range(1, len(months) + 1), "mom": mom, "yoy": yoy(snap, mom)})
        out[name] = frame if groups is None else frame.join(groups)
    return out
