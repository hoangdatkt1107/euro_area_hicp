"""How the numbers were made. Mostly text; the two tables come from gold and the silver manifest."""
import json
import pandas as pd
import streamlit as st
from dashboard import data
from src.config import settings

SOURCES = {
    "prc_hicp_minr": "HICP indices, monthly",
    "prc_hicp_iw": "Item weights",
    "prc_hicp_cw": "Country weights",
    "prc_hicp_ctr": "Contributions to the euro area rate",
    "prc_hicp_fpd": "Flash and final releases",
    "business_surveys": "Selling price expectations, EC surveys",
    "brent_usd": "Brent, USD a barrel (FRED)",
    "eurusd": "EUR/USD reference rate (ECB)",
    "gas_eu_usd": "Natural gas, Europe (FRED)",
    "oil_bulletin": "Pump prices, Weekly Oil Bulletin"}

def render():
    st.markdown("#### From the Eurostat API to this page")
    st.markdown(
        "The data comes from Eurostat's ECOICOP ver.2 HICP tables (indices, item and country weights, "
        "contributions, flash and final releases) and its business surveys, plus Brent, EUR/USD, wholesale gas "
        "and the Weekly Oil Bulletin. Raw responses are kept as they came back, with a new copy only when the "
        "source changes. The euro area changes composition, so the country weights are checked against who was in "
        "the euro each year, from 11 countries in 1999 to 21 in 2026 with Bulgaria. Before anything is modelled, "
        "the official headline is rebuilt from its parts. Six "
        "forecast models are then scored in a real-time backtest and the winner is picked by a rule set "
        "beforehand, while the shock engine works on each country's and group's weight, with pass-through "
        "estimated by local projections.")

    st.markdown("#### The headline rebuilt from its parts")
    gates = data.gold("validation")["gates"]
    table = pd.DataFrame([{"check": g["name"], "from": g["from"], "months": g["months"],
                           "largest gap, pp": g["max_abs_pp"], "allowed, pp": g["threshold_pp"],
                           "result": "pass" if g["ok"] else "FAIL"} for g in gates if "max_abs_pp" in g])
    st.dataframe(table, hide_index=True,
                 column_config={"largest gap, pp": st.column_config.NumberColumn(format="%.3f")})
    for g in gates:
        if "max_abs_pp" not in g:
            st.caption(f"{g['name']}: {'pass' if g['ok'] else 'FAIL'}, {g['detail']}.")

    st.markdown("#### Data behind this page")
    manifest = json.loads((settings.silver / "manifest.json").read_text())
    vintages = {**manifest["vintage"], **manifest["external"]}
    st.dataframe(pd.DataFrame({"data": [SOURCES.get(k, k) for k in vintages], "table": list(vintages),
                               "as of": [f"{pd.Timestamp(v):%d %b %Y}" for v in vintages.values()]}),
                 hide_index=True)
    st.caption(f"Eurostat tables: last updated. The rest: latest point. Pulled "
               f"{manifest['built_at'][:16].replace('T', ' ')} UTC.")

    st.markdown("#### Formulas")
    st.markdown("Chain-linking, as Eurostat compiles the HICP: each component against its own December, "
                "weighted with the year's weights.")
    st.latex(r"I(y,m) = I(y-1,12)\,\frac{\sum_i w_i(y)\, I_i(y,m)/I_i(y-1,12)}{\sum_i w_i(y)}")
    st.markdown("The base effect: only the new months are forecast, the ones dropping out are known.")
    st.latex(r"1+\pi_{t+h} = (1+\pi_t)\,\prod_{k=1}^{h}\frac{1+m_{t+k}}{1+m_{t+k-12}}")
    st.markdown("A shock x to country c's group i, through its effective weight θ, with the December link:")
    st.latex(r"M(t) = M(\text{Dec}_{t-1})\sum_{c,i}\theta_{ci}(t)\,\frac{1+x_{ci}(t)}{1+x_{ci}(\text{Dec}_{t-1})}")

    st.markdown("#### What it leaves out")
    st.markdown(
        "- Forecast bands are built from past errors; they were far too narrow during 2021-23.\n"
        "- No spillover between countries; next year's weights are taken equal to this year's.\n"
        "- Gas prices arrive two months late; country flash CPIs, futures and inflation swaps are not used.\n"
        "- Second-round effects depend on the period they are estimated on, hence the two settings.")
    st.caption("Full reports: reports/data_quality.md, qa_findings.md, forecast_evaluation.md, forecast.md, "
               "passthrough.md, shocks.md.")
