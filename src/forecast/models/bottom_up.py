"""A regression per group, then chain-linked into the headline with the year's weights"""
import pandas as pd
from src.config import settings
from src.forecast.models.common import arx, chain_groups

# extra regressors per group, on top of month dummies, Easter and momentum. Picked on one-step
# errors over 2010-2014, before the 2015-2026 sample the models are judged on
EXTRA = {
    "FOOD_P": ["retail_l1"],
    "FOOD_NP": [],
    "FUEL": ["pump_early_chg", "brent_early_chg"],
    "ELC_GAS": ["gas_l3_6"],
    "IGD_NNRG": [],
    "SERV": ["services_l1"]}

def forecast(f, snap, done):
    groups = pd.DataFrame({g: arx(f, g, EXTRA[g]) for g in settings.groups})
    return chain_groups(snap, groups), groups
