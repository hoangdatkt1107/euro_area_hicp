"""What if: shock any group in any set of countries, or move oil and gas, and see the headline react"""
import numpy as np
import pandas as pd
import streamlit as st
from dashboard import charts, data
from src.config import settings
from src.shocks import engine as en

SHAPES = {"Stays": "step", "Fades": "fade", "Builds up": "ramp"}
REGIMES = {"Normal times": "normal", "Like 2022": "2022"}
PARTITIONS = {"6 main groups": "groups", "13 COICOP divisions": "divisions"}
OWN = "Your own shock"

def _own(months) -> dict:
    left, mid, right = st.columns(3)
    with left:
        partition = PARTITIONS[st.radio("Split the basket into", list(PARTITIONS), horizontal=True)]
        base = data.baseline(partition)
        everyone = st.checkbox("Every euro area country")
        countries = "EA" if everyone else st.multiselect("Countries", settings.countries, default=["DE"],
                                                         format_func=settings.label)
        default = ["FUEL"] if partition == "groups" else ["CP07"]
        components = st.multiselect("Prices that move", base.codes, default=default, format_func=settings.label)
    with mid:
        size = st.slider("By how much, %", -20.0, 20.0, 10.0, step=0.5, format="%.1f",
                         help="Change in the price level of what you picked, against the baseline")
        start = st.selectbox("From", list(months[1:]), format_func=lambda m: m.strftime("%B %Y"))
        shape = SHAPES[st.radio("Then it", list(SHAPES), horizontal=True)]
        half_life = ramp = 6
        if shape == "fade":
            half_life = st.slider("Halves every ... months", 1, 24, 6)
        elif shape == "ramp":
            ramp = st.slider("Builds up over ... months", 2, 24, 6)
    with right:
        groups = partition == "groups"
        oil = st.slider("Brent, % change", -50, 50, 0, step=5, disabled=not groups,
                        help="Hits every country. Needs the 6 main groups: pass-through is estimated on them")
        gas = st.slider("Wholesale gas, % change", -50, 100, 0, step=10, disabled=not groups)
        indirect = st.toggle("Include second-round effects", value=True, disabled=not groups,
                             help="Energy feeding into food, goods and services prices over the following months")
        regime = REGIMES[st.radio("Second round as in", list(REGIMES), horizontal=True, disabled=not groups,
                                  help="Normal times leaves 2020-23 out of the estimates; in 2022 the second "
                                       "round was about three times stronger")]
    shocks = []
    if countries and components and size:
        shocks.append({"countries": countries, "components": components, "size": size, "start": str(start),
                       "kind": shape, "half_life": half_life, "ramp": ramp})

    def move(pct):  # the pass-through was estimated on 100 x log changes
        return {"size": 100 * np.log(1 + pct / 100), "start": str(start)} if pct and groups else None

    return {"partition": partition, "shocks": shocks, "oil": move(oil), "gas": move(gas),
            "indirect": indirect and groups, "regime": regime}

def render():
    presets = {p["name"]: p for p in data.gold("presets")["presets"]}
    months = data.baseline("groups").months

    pick = st.selectbox("Start from", [OWN, *presets],
                        help="The presets take their size from the data: the German tax cut is read off the "
                             "Weekly Oil Bulletin, oil from today's Brent")
    if pick == OWN:
        spec = _own(months)
    else:
        p = presets[pick]
        st.caption(p["note"].replace("$", r"\$"))
        groups = p["partition"] == "groups"
        regime = REGIMES[st.radio("Second round as in", list(REGIMES), horizontal=True, disabled=not groups)]
        spec = {"partition": p["partition"], "shocks": p.get("shocks", []), "oil": p.get("oil"),
                "gas": p.get("gas"), "indirect": groups, "regime": regime}

    base = data.baseline(spec["partition"])
    if not (spec["shocks"] or spec["oil"] or spec["gas"]):
        st.info("Pick at least one country and one group, or move oil or gas.")
        return
    r = en.simulate(base, spec["shocks"], spec["oil"], spec["gas"], indirect=spec["indirect"],
                    regime=spec["regime"])

    impact = r["impact"]
    year = months[-1].year - 1
    peak = impact.abs().idxmax()
    cols = st.columns(3)
    cols[0].metric(f"Biggest effect, {peak.strftime('%B %Y')}", f"{impact[peak]:+.2f} pp",
                   help="On the euro area annual rate")
    cols[1].metric(f"Average over {year}", f"{impact.loc[str(year)].mean():+.2f} pp")
    cols[2].metric(f"Of which second round, {year}", f"{r['indirect'].loc[str(year)].mean():+.2f} pp")

    st.markdown("#### Effect on the headline, month by month")
    st.plotly_chart(charts.impact(base.months, r["direct"], r["indirect"], impact), theme=None)
    st.caption("A one-off rise in the price level lifts the annual rate for twelve months, then drops out. "
               "Exact chain-linking with each country's and group's weight.")

    left, right = st.columns(2)
    with left:
        st.markdown(f"#### By country, {year} average")
        countries = r["by_country"].loc[str(year)].mean()
        if len(countries) == 1:  # a bar chart with one bar says nothing
            st.markdown(f"All of it comes from {settings.label(countries.index[0])}: {countries.iloc[0]:+.2f} pp "
                        "on the euro area rate.")
        else:
            st.plotly_chart(charts.bars(countries), theme=None)
    with right:
        st.markdown(f"#### By price group, {year} average")
        st.plotly_chart(charts.bars(r["by_component"].loc[str(year)].mean()), theme=None)

    with st.expander("Headline with and without the shock"):
        st.plotly_chart(charts.with_and_without(base.months, r["baseline"], r["yoy"]), theme=None)
        st.caption("Baseline: the forecast for the first months, then every country's prices on their usual "
                   "seasonal path.")

    out = pd.DataFrame({"month": base.months.astype(str), "baseline_yoy": r["baseline"].to_numpy(),
                        "shocked_yoy": r["yoy"].to_numpy(), "impact_pp": impact.to_numpy(),
                        "direct_pp": r["direct"].to_numpy(), "indirect_pp": r["indirect"].to_numpy()})
    st.download_button("Download this scenario (CSV)", out.to_csv(index=False), "shock_scenario.csv",
                       "text/csv")
