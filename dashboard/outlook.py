"""Outlook: the three-month forecast, what it rests on, and how far to trust it"""
import pandas as pd
import streamlit as st
from dashboard import charts, data
from src.config import settings

def _period(s):
    return pd.Period(s, freq="M")

def render():
    f, ev = data.gold("forecast"), data.gold("evaluation")
    model = settings.label(f["model"])
    months = pd.PeriodIndex([_period(x["month"]) for x in f["forecast"]])
    yoy = [x["yoy"] for x in f["forecast"]]
    bands = {q: [x[q] for x in f["forecast"]] for q in ("q05", "q25", "q75", "q95")}
    history = pd.Series(f["history"])
    history.index = pd.PeriodIndex([_period(m) for m in history.index])

    now = data.brent_now()
    cols = st.columns(len(months))
    previous = history.iloc[-1]
    for col, m, y, lo, hi in zip(cols, months, yoy, bands["q05"], bands["q95"], strict=True):
        col.metric(f"{m.strftime('%B %Y')}", f"{y:.2f}%", f"{y - previous:+.2f} pp on the month before",
                   delta_color="inverse", help=f"90% band {lo:.1f} to {hi:.1f}%, from the model's past errors")
        previous = y
    st.caption(f"With Brent staying at \\${now:.0f}. The slider below reruns the forecast at another price.")

    st.markdown("#### Forecast and the oil price")
    usd = st.slider("Brent from the second half of the coming month, \\$ per barrel", 60, 160, int(round(now)),
                    help=f"About \\${now:.0f} in the first two weeks after the last HICP month. Pump prices "
                         "follow with the pass-through estimated since 2005.")
    moved = data.at_brent(float(usd)) if abs(usd - now) > 0.5 else None
    st.plotly_chart(charts.fan(history.iloc[-18:], months, yoy, bands, ecb=settings.ecb_q4, other=moved,
                               other_name=f"Brent at ${usd}" if moved else None), theme=None)
    q4 = [y for m, y in zip(months, moved or yoy, strict=True) if m.quarter == 4]
    if len(q4) == 3:
        st.caption(f"Q4 average {sum(q4) / 3:.2f}% with Brent at \\${usd if moved else now:.0f}. "
                   f"{settings.ecb_source}: {settings.ecb_q4}% with oil at about \\${settings.ecb_oil_usd:.0f}.")
    if f.get("ecb_brent_usd"):
        st.markdown(f"To get to the ECB's {settings.ecb_q4}% for Q4, this model needs Brent near "
                    f"**\\${f['ecb_brent_usd']:.0f}**. It averaged \\${now:.0f} in the first half of "
                    f"{months[0].strftime('%B')}, so most of the gap to the ECB is the oil price.")
    st.caption(f"Model: {model}. Made as of {f['made']} with HICP to {f['last_hicp']}, Brent to "
               f"{f['data']['brent_usd']}, pump prices to {f['data']['oil_bulletin']}.")

    left, right = st.columns(2)
    with left:
        last = f["forecast"][-1]
        start = history.iloc[-1]
        st.markdown(f"#### How {months[-1].strftime('%B')} is built")
        st.caption(f"From {history.index[-1].strftime('%B')}'s rate: the year-ago months dropping out of the "
                   "comparison are already known, only the new months are forecast.")
        st.plotly_chart(charts.build_up(history.index[-1].strftime("%b"), start,
                                        {"base effect": last["dropping_out"], "new months": last["new_months"]},
                                        months[-1].strftime("%b"), last["yoy"]), theme=None)
    with right:
        fuel = f["fuel_check"]
        st.markdown(f"#### {months[0].strftime('%B')}: pump prices fell while oil rose")
        st.caption(f"Early {months[0].strftime('%B')}: pump prices {fuel['pump']:+.1f}% on the month before, "
                   f"Brent {fuel['brent']:+.0f}%. Fuel tax cuts in Germany and Spain.")
        st.plotly_chart(charts.pump_vs_brent(data.pump_and_brent()), theme=None)
        st.caption("European Commission Weekly Oil Bulletin, euro area average of petrol and diesel; Brent "
                   "from FRED in euro at ECB rates. Both = 100 at the first week shown.")

    st.markdown("#### Track record")
    rmse = data.track_record()
    gain = 1 - rmse.loc[f["model"], 1] / rmse.loc["no_change", 1]
    st.markdown(f"Real-time backtest, {ev['sample'][0]} to {ev['sample'][1]}: every forecast uses only what "
                f"was published on the day. {model} misses by {rmse.loc[f['model'], 1]:.2f} pp a month "
                f"ahead on average (RMSE), {gain:.0%} less than assuming no change.")
    st.plotly_chart(charts.track_record(rmse, f["model"]), theme=None)
    split = pd.DataFrame(ev["time_split"])
    first = split.iloc[0]
    st.markdown(f"Picked with data to {first['picked on'][-4:]} only, {first['pick']} still ranked "
                f"{first['rank later']} on the {first['later origins']} forecasts made after that.")
    st.dataframe(split, hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%.2f")
                                for c in ("its RMSE later", "no change later")})
    st.caption("More in reports/forecast_evaluation.md.")

    st.info(f"Check it later: the {months[0].strftime('%B')} flash estimate comes out around the start of "
            f"{(months[0] + 1).strftime('%B')}. This forecast says {yoy[0]:.2f}% "
            f"(90% band {bands['q05'][0]:.1f} to {bands['q95'][0]:.1f}).")
