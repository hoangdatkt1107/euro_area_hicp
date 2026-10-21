"""Each month gets the median change of the same month over the last few years"""
import pandas as pd
from src.config import settings
from src.forecast.models.common import ahead

def forecast(f, snap, done):
    months = ahead(f)
    years = range(1, settings.seasonal_years + 1)
    return pd.Series([f.mom_TOTAL[[t - 12 * k for k in years]].median() for t in months], index=months), None
