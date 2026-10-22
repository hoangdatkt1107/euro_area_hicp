"""Where inflation is right now."""
import streamlit as st
from dashboard import charts, data
from src.config import settings

TILES = {"TOTAL": "All items", "NRG": "Energy", "SERV": "Services", "TOT_X_NRG_FOOD": "Core"}

def render():
    rates = data.official()
    last = rates.index.max()
    cols = st.columns(len(TILES))
    for col, (code, name) in zip(cols, TILES.items(), strict=True):
        now, before = rates.at[last, code], rates.at[last - 1, code]
        col.metric(f"{name}, {last.strftime('%B %Y')}", f"{now:.1f}%", f"{now - before:+.1f} pp on the month before",
                   delta_color="inverse")

    contrib = data.contributions()
    energy = contrib.iloc[-1][settings.energy_groups].sum()
    st.markdown("#### Contributions to the annual rate")
    st.caption(f"By group, in pp. In {last.strftime('%B')} energy alone adds {energy:.2f} of the "
               f"{rates.at[last, 'TOTAL']:.1f}%.")
    st.plotly_chart(charts.contributions(contrib), theme=None)
    st.caption("Our chain-linked calculation from Eurostat indices and weights (prc_hicp_minr, prc_hicp_iw). "
               "It matches Eurostat's own contributions to within 0.01 pp.")

    st.markdown("#### Annual rate by country and group")
    st.caption("Blue is under the ECB's 2% target, red over it. The colours stop at -4% and 8%, so energy "
               "reads red almost everywhere.")
    st.plotly_chart(charts.heatmap(data.by_country()), theme=None)
    st.caption(f"Eurostat, prc_hicp_minr, {last.strftime('%B %Y')}. Countries sorted by their all-items rate.")
