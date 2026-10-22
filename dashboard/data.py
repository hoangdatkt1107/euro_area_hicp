"""What the dashboard reads, loaded once. Only the pipeline's outputs and the engine the reports use,
so the numbers here are the numbers in the reports"""
import json
import pandas as pd
import streamlit as st
from src import chain as ch
from src.config import settings
from src.forecast import evaluate, live
from src.forecast import realtime as rt
from src.shocks import engine as en

@st.cache_data
def gold(name: str) -> dict:
    return json.loads((settings.gold / f"{name}.json").read_text())

@st.cache_resource
def tables() -> dict:
    return rt.load()

@st.cache_resource
def snapshot() -> dict:
    t = tables()
    return rt.snapshot(t, t["index"].month.max())

@st.cache_resource
def baseline(partition: str) -> en.Baseline:
    return en.baseline(tables(), partition)

@st.cache_resource
def _oil_basis() -> dict:
    return live.oil_basis(snapshot())

def brent_now() -> float:
    b = _oil_basis()
    return float(b["brent"] * b["fx"])

@st.cache_data
def at_brent(usd: float) -> list[float]:
    """Forecast YoY for the months ahead with Brent at `usd` from mid-month on."""
    model = gold("evaluation")["selected"]
    return live.at_brent(snapshot(), model, usd, _oil_basis()).tolist()

@st.cache_data
def official() -> pd.DataFrame:
    """Published annual rates for the euro area, month x code."""
    r = tables()["official_rates"].pivot_table(index="month", columns="coicop", values="value")
    r.index = r.index.to_period("M")
    return r

@st.cache_data
def contributions(months: int = 36) -> pd.DataFrame:
    snap = snapshot()
    levels = ch.wide(snap["index"], settings.euro_area, settings.groups)
    weights = ch.weight_table(snap["item_weights"], settings.groups, geo=settings.euro_area)
    return ch.contributions(levels, weights).iloc[-months:]

@st.cache_data
def by_country() -> pd.DataFrame:
    """Annual rate in the latest month, every country, all items and the six groups"""
    idx = tables()["index"]
    last = idx.month.max()
    now = idx[idx.month == last].pivot_table(index="geo", columns="coicop", values="value")
    before = idx[idx.month == last - pd.DateOffset(years=1)].pivot_table(index="geo", columns="coicop",
                                                                        values="value")
    yoy = ((now / before - 1) * 100)[["TOTAL", *settings.group_order]]
    order = [settings.euro_area, *yoy.drop(index=settings.euro_area).TOTAL.sort_values(ascending=False).index]
    return yoy.loc[order]

@st.cache_data
def pump_and_brent(weeks: int = 20) -> pd.DataFrame:
    """Weekly euro area pump price with taxes and Brent in euro, both = 100 at the first week shown"""
    t = tables()
    wob = t["oil_bulletin"]
    pump = wob[(wob.geo == "EUR") & (wob.tax == "with_tax")].pivot_table(index="date", columns="product",
                                                                          values="price")
    pump = pump[["euro95", "diesel"]].mean(axis=1)
    usd = t["brent_usd"].set_index("date").value
    fx = t["eurusd"].set_index("date").value.reindex(usd.index, method="ffill")
    brent = (usd / fx).dropna()
    pump = pump[pump.index >= pump.index.max() - pd.Timedelta(weeks=weeks)]
    brent = brent[brent.index >= pump.index.min()].resample("W-MON", label="left", closed="left").mean()
    out = pd.DataFrame({"pump": pump, "brent": brent.reindex(pump.index)}).dropna()
    return out / out.iloc[0] * 100

@st.cache_data
def track_record() -> pd.DataFrame:
    """RMSE by model and horizon on the scored sample"""
    d = evaluate.sample(evaluate.load())
    return evaluate.scores(d).rmse.unstack()
