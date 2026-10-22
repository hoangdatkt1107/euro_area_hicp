"""Plotly figures for the dashboard. Titles and sources go in the page, and pages use theme=None
so Streamlit's dark theme can't turn the text white."""
import pandas as pd
import plotly.graph_objects as go

from src.config import settings

INK, MUTED, GRID, SURFACE = "black", "dimgray", "gainsboro", "white"
BLUE, ORANGE, RED, NEUTRAL = "royalblue", "coral", "crimson", "whitesmoke"
FONT = "Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"


def _style(fig, height=340, legend=True, percent=True):
    fig.update_layout(height=height, font=dict(family=FONT, size=13, color=INK), plot_bgcolor=SURFACE,
                      paper_bgcolor=SURFACE, margin=dict(l=4, r=4, t=36 if legend else 8, b=4),
                      showlegend=legend, hoverlabel=dict(font_family=FONT, bgcolor="white"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None))
    # automargin keeps tick labels inside the figure, the margins above are only a minimum
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED), automargin=True)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=MUTED, zerolinewidth=1, tickfont=dict(color=MUTED),
                     automargin=True)
    if percent:
        fig.update_yaxes(ticksuffix="%")
    return fig


def _months(index):
    return index.to_timestamp() if isinstance(index, pd.PeriodIndex) else pd.to_datetime(index)


def fan(history: pd.Series, months, yoy, bands, ecb=None, other=None, other_name=None):
    """Actual YoY, the forecast with its 50% and 90% bands, and optionally a second path and the ECB."""
    hx, fx = _months(history.index), _months(months)
    x = [hx[-1], *fx]  # start the forecast at the last actual month so the lines join
    first = history.iloc[-1]
    fig = go.Figure()
    for lo, hi, name, alpha in (("q05", "q95", "90% band", 0.13), ("q25", "q75", "50% band", 0.26)):
        fig.add_scatter(x=x + x[::-1], y=[first, *bands[hi]] + [first, *bands[lo]][::-1], fill="toself",
                        fillcolor=BLUE, opacity=alpha, line=dict(width=0), mode="lines", name=name,
                        hoverinfo="skip")
    fig.add_scatter(x=hx, y=history, name="Actual", line=dict(color=INK, width=2), mode="lines",
                    hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra></extra>")
    fig.add_scatter(x=x, y=[first, *yoy], name="Forecast", line=dict(color=BLUE, width=2),
                    marker=dict(size=8), mode="lines+markers",
                    hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra>forecast</extra>")
    if other is not None:
        fig.add_scatter(x=x, y=[first, *other], name=other_name, mode="lines+markers",
                        line=dict(color=ORANGE, width=2, dash="dot"), marker=dict(size=8),
                        hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra>" + other_name + "</extra>")
    if ecb is not None:
        q4 = [d for d in fx if d.quarter == 4]
        if q4:
            fig.add_scatter(x=[q4[0] - pd.Timedelta(days=12), q4[-1] + pd.Timedelta(days=12)], y=[ecb, ecb],
                            mode="lines", name="ECB, Q4", line=dict(color=MUTED, width=2, dash="dash"),
                            hovertemplate=f"ECB September projection for Q4: {ecb}%<extra></extra>")
    return _style(fig, height=380)


def build_up(start_label, start, steps: dict, end_label, end):
    """Waterfall from one month's YoY to another: where the change comes from."""
    fig = go.Figure(go.Waterfall(
        x=[start_label, *steps, end_label], y=[start, *steps.values(), end],
        measure=["absolute", *["relative"] * len(steps), "total"],
        text=[f"{start:.2f}", *[f"{v:+.2f}" for v in steps.values()], f"{end:.2f}"], textposition="outside",
        increasing=dict(marker=dict(color=RED)), decreasing=dict(marker=dict(color=BLUE)),
        totals=dict(marker=dict(color=MUTED)), connector=dict(line=dict(color=GRID, width=1)),
        hovertemplate="%{x}: %{text}<extra></extra>"))
    fig.update_yaxes(range=[min(start, end) - 0.6, max(start, end) + 0.4])
    return _style(fig, height=320, legend=False)


def contributions(df: pd.DataFrame):
    """Stacked contributions by group, total as a dot on top."""
    x = _months(df.index)
    fig = go.Figure()
    for g in settings.group_order:
        fig.add_bar(x=x, y=df[g], name=settings.label(g), marker=dict(color=settings.colors[g], cornerradius=2),
                    hovertemplate="%{x|%b %Y}: %{y:+.2f} pp<extra>" + settings.label(g) + "</extra>")
    fig.add_scatter(x=x, y=df.sum(axis=1), name="All items", mode="markers", marker=dict(color=INK, size=7),
                    hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra>all items</extra>")
    fig.update_layout(barmode="relative", bargap=0.15)
    return _style(fig, height=380)


def heatmap(df: pd.DataFrame, target=2.0, spread=6.0):
    """Annual rates by country and group; blue under the 2% target, red over it."""
    cols = [settings.label(c) for c in df.columns]
    rows = [settings.label(r) for r in df.index]
    fig = go.Figure(go.Heatmap(
        z=df.to_numpy(), x=cols, y=rows, zmin=target - spread, zmax=target + spread, zmid=target,
        colorscale=[[0, BLUE], [0.5, NEUTRAL], [1, RED]], xgap=2, ygap=2,
        texttemplate="%{z:.1f}", textfont=dict(size=11),
        colorbar=dict(title="YoY %", ticks="outside", thickness=10),
        hovertemplate="%{y}, %{x}: %{z:.1f}%<extra></extra>"))
    fig.update_yaxes(autorange="reversed", ticksuffix="", ticks="")
    fig.update_xaxes(side="top", ticks="")
    return _style(fig, height=max(420, 22 * len(rows)), legend=False, percent=False)


def pump_vs_brent(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_scatter(x=df.index, y=df.brent, name="Brent in euro", line=dict(color=MUTED, width=2),
                    hovertemplate="week of %{x|%d %b}: %{y:.1f}<extra>Brent</extra>")
    fig.add_scatter(x=df.index, y=df.pump, name="Pump price with taxes", mode="lines+markers",
                    line=dict(color=settings.colors["FUEL"], width=2), marker=dict(size=8),
                    hovertemplate="week of %{x|%d %b}: %{y:.1f}<extra>pump</extra>")
    return _style(fig, height=300, percent=False)


def track_record(rmse: pd.DataFrame, chosen: str):
    fig = go.Figure()
    for m in settings.models:
        picked = m == chosen
        fig.add_scatter(x=rmse.columns, y=rmse.loc[m], name=settings.label(m), mode="lines+markers",
                        line=dict(color=BLUE if picked else (INK if m == "no_change" else "silver"),
                                  width=3 if picked else 1.5, dash="dash" if m == "no_change" else None),
                        marker=dict(size=8), hovertemplate="%{x} month(s) ahead: %{y:.3f} pp<extra>"
                        + settings.label(m) + "</extra>")
    fig.update_xaxes(tickvals=[1, 2, 3], title="months ahead")
    fig.update_yaxes(ticksuffix=" pp", rangemode="tozero")
    return _style(fig, height=300, percent=False)


def impact(months, direct, indirect, total):
    x = _months(months)
    fig = go.Figure()
    fig.add_bar(x=x, y=direct, name="Direct", marker=dict(color=BLUE, cornerradius=2),
                hovertemplate="%{x|%b %Y}: %{y:+.3f} pp<extra>direct</extra>")
    fig.add_bar(x=x, y=indirect, name="Indirect", marker=dict(color=ORANGE, cornerradius=2),
                hovertemplate="%{x|%b %Y}: %{y:+.3f} pp<extra>indirect</extra>")
    fig.add_scatter(x=x, y=total, name="Total", mode="lines+markers", line=dict(color=INK, width=2),
                    marker=dict(size=8), hovertemplate="%{x|%b %Y}: %{y:+.3f} pp<extra>total</extra>")
    fig.update_layout(barmode="relative", bargap=0.2)
    fig.update_yaxes(ticksuffix=" pp")
    return _style(fig, height=340, percent=False)


def with_and_without(months, base, shocked):
    x = _months(months)
    fig = go.Figure()
    fig.add_scatter(x=x, y=base, name="Baseline", line=dict(color=MUTED, width=2, dash="dash"),
                    hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra>baseline</extra>")
    fig.add_scatter(x=x, y=shocked, name="With the shock", line=dict(color=BLUE, width=2),
                    hovertemplate="%{x|%b %Y}: %{y:.2f}%<extra>with the shock</extra>")
    return _style(fig, height=300)


def bars(values: pd.Series):
    """Horizontal bars, biggest at the top."""
    v = values.sort_values()
    fig = go.Figure(go.Bar(x=v, y=[settings.label(i) for i in v.index], orientation="h",
                           marker=dict(color=[RED if x > 0 else BLUE for x in v], cornerradius=2),
                           text=[f"{x:+.3f}" for x in v], textposition="outside",
                           hovertemplate="%{y}: %{x:+.3f} pp<extra></extra>"))
    lo, hi = min(v.min(), 0), max(v.max(), 0)
    pad = 0.3 * (hi - lo) or 0.01  # room for the labels
    fig.update_xaxes(ticksuffix=" pp", showgrid=True, gridcolor=GRID,
                     range=[lo - pad if lo < 0 else 0, hi + pad if hi > 0 else 0])
    fig.update_yaxes(ticklabelstandoff=8)
    return _style(fig, height=max(180, 34 * len(v) + 40), legend=False, percent=False)
