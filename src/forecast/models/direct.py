"""One regression straight on the headline"""
from src.forecast.models.common import arx

# on top of month dummies, Easter and momentum; picked on one-step errors over 2010-2014,
# before the 2015-2026 sample the models are judged on
EXTRA = ["pump_early_chg", "services_l1"]

def forecast(f, snap, done):
    return arx(f, "TOTAL", EXTRA), None
