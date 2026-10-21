"""Benchmark: the YoY stays where it is. Repeating last year's change in each month does exactly that"""
import pandas as pd
from src.forecast.models.common import ahead

def forecast(f, snap, done):
    months = ahead(f)
    return pd.Series(f.mom_TOTAL[months - 12].to_numpy(), index=months), None
