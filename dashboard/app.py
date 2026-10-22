"""Euro area inflation dashboard. Run from the repo root: streamlit run dashboard/app.py"""
import json
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 

import streamlit as st 
from dashboard import data, method, outlook, shock_lab, today 
from src.config import settings 

st.set_page_config(page_title="Euro area inflation", layout="wide")

forecast = data.gold("forecast")
pulled = pd.Timestamp(json.loads((settings.silver / "manifest.json").read_text())["built_at"])

def month(s):
    return pd.Period(s, freq="M").strftime("%B %Y")

st.title("Euro area inflation")
st.caption(f"HICP to {month(forecast['last_hicp'])} · forecast to {month(forecast['forecast'][-1]['month'])} · "
           f"data pulled {pulled.day} {pulled:%b %Y}")

tabs = st.tabs(["Today", "Outlook", "What if", "How it's built"])
for tab, page in zip(tabs, (today, outlook, shock_lab, method), strict=True):
    with tab:
        page.render()
st.divider()
st.caption(f"Built by {settings.author}. Sources: Eurostat, ECB, FRED, European Commission Weekly Oil Bulletin.")
