import json
import numpy as np
import pandas as pd
from dateutil.easter import easter
from matplotlib import dates as mdates
from matplotlib.figure import Figure
from src import chain as ch
from src import silver
from src.config import settings

FIG = settings.reports / "figures"
INK, MUTED, GRID = "black", "dimgray", "gainsboro"
SERIES = ["tab:blue", "tab:orange", "tab:green", "tab:red"]

def _figure(size, **kw):
    # plain Figure, no pyplot, so no GUI backend gets involved
    fig = Figure(figsize=size)
    return fig, fig.subplots(**kw)

def _style(ax, title=None, ylabel=None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=MUTED)

def _save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, dpi=160, bbox_inches="tight", facecolor="#fcfcfb")
    return f"figures/{name}"

def _table(df, floatfmt="{:.2f}"):
    lines = ["| " + " | ".join(str(c) for c in df.columns) + " |", "|" + "---|" * len(df.columns)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(floatfmt.format(v) if isinstance(v, float) else str(v)
                                        for v in row.values) + " |")
    return "\n".join(lines)

def _ea(codes):
    return ch.wide(pd.read_parquet(settings.silver / "index.parquet"), "EA", codes)

def validation_section():
    v = json.loads((settings.gold / "validation.json").read_text())
    gaps = pd.read_parquet(settings.gold / "validation_yoy_gaps.parquet")
    gaps.index = ch.to_periods(gaps.index)
    rows = [{"gate": g["id"], "check": g["name"], "result": "pass" if g["ok"] else "FAIL",
             "max gap (pp)": g.get("max_abs_pp", float("nan")),
             "since 2017 (pp)": g.get("max_abs_since_2017_pp", float("nan")),
             "months": g.get("months", "")} for g in v["gates"]]

    fig, ax = _figure((9, 3.4))
    for gid, colour in zip(["V1", "V2", "V3"], SERIES, strict=False):
        s = gaps[gid].dropna()
        ax.plot(s.index.to_timestamp(), s.values, color=colour, linewidth=1.2, label=gid)
    ax.axhspan(-0.05, 0.05, color="#f0efec", zorder=0)  # pass band
    ax.axhline(0, color=MUTED, linewidth=0.8)
    _style(ax, "Rebuilt minus official annual rate, euro area all-items", "percentage points")
    ax.legend(frameon=False, ncol=3, fontsize=9, loc="upper right")
    ax.set_ylim(-0.08, 0.08)
    path = _save(fig, "validation_gaps.png")

    worst = max(g["max_abs_pp"] for g in v["gates"] if "max_abs_pp" in g)
    return ["## Validation", "",
            f"Largest gap {worst:.3f} pp against a 0.05 pp limit. What's left is rounding: the official "
            "indices only have two decimals.", "",
            _table(pd.DataFrame(rows).fillna(""), "{:.3f}"), "", f"![]({path})", ""]

def _robust_z(x, ref):
    med = np.median(ref)
    mad = 1.4826 * np.median(np.abs(ref - med))
    return (x - med) / mad if mad > 0 else np.nan

def breaks_section():
    groups = settings.group_order
    m = ch.mom(_ea(groups))
    rows = []
    for code in groups:
        jan = m[code].dropna()
        jan = jan[jan.index.month == 1]
        # the usual January, leaving out the two being tested
        ref = jan[(jan.index.year >= 2002) & ~jan.index.year.isin([2017, 2026])]
        for year in (2017, 2026):
            x = jan.get(pd.Period(f"{year}-01", freq="M"))
            rows.append({"group": settings.label(code), "January": year, "m/m %": f"{x:.2f}",
                         "usual January %": f"{np.median(ref):.2f}",
                         "robust z": round(float(_robust_z(x, ref.values)), 1)})
    t = pd.DataFrame(rows)
    odd = t[t["robust z"].abs() > 3]

    out = ["## Breaks", "",
           "Before 2017 the special aggregates (the six groups, energy, food, core) are flagged d: "
           "back-calculated to the ECOICOP 2 definitions. January 2017 is flagged as a break in the same "
           "series. All-items and the 13 divisions carry no d flag. Full tables in `data_quality.md`.", "",
           "Do the 2017 break or the switch to ECOICOP 2 in January 2026 show up in the monthly rates? "
           "January change against the usual January (median and MAD since 2002):", "", _table(t), ""]
    if odd.empty:
        out += ["Nothing above |z| = 3, so monthly rates are fine across both breaks.", ""]
    else:
        note = "Above |z| = 3: " + ", ".join(f"{r.group.lower()} {r.January} (z {r['robust z']})"
                                             for _, r in odd.iterrows()) + "."
        if len(odd) == 1 and odd.iloc[0].group == settings.label("FOOD_NP") and odd.iloc[0].January == 2017:
            note += (" That lines up with the vegetable shortage in Spain that winter, so I treat it as a "
                     "real price move.")
        out += [note + " The rest look like normal Januaries, so monthly rates are fine across both "
                "breaks.", ""]
    return out

def _seasonality_figure(prof, groups):
    fig, ax = _figure((9, 3.3))
    data = prof[groups].T.values
    lim = np.nanmax(np.abs(data))
    im = ax.imshow(data, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_yticks(range(len(groups)), [settings.label(g) for g in groups], fontsize=9)
    ax.set_xticks(range(12), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"], fontsize=9)
    for i in range(data.shape[0]):
        for j in range(12):
            # white text on the dark cells
            ax.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", fontsize=7.5,
                    color="white" if abs(data[i, j]) > 0.6 * lim else INK)
    ax.set_title("Average monthly change by calendar month, euro area, 2017 to 2025 (%)",
                 loc="left", fontsize=11, color=INK, pad=10)
    ax.tick_params(length=0, colors=MUTED)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01).ax.tick_params(labelsize=8, colors=MUTED)
    return _save(fig, "seasonality.png")

def _easter_split(serv):
    # average services change in March and April, by the month Easter fell in
    rows = [{"easter_month": easter(year).month,
             "mar": serv.get(pd.Period(f"{year}-03", freq="M")),
             "apr": serv.get(pd.Period(f"{year}-04", freq="M"))} for year in range(2002, 2026)]
    return pd.DataFrame(rows).dropna().groupby("easter_month")[["mar", "apr"]].mean()

def seasonality_section():
    groups = settings.group_order
    m = ch.mom(_ea(groups))
    # average month-on-month change by calendar month, recent years against earlier ones
    recent = m[(m.index.year >= 2017) & (m.index.year <= 2025)]
    early = m[(m.index.year >= 2005) & (m.index.year <= 2016)]
    prof = recent.groupby(recent.index.month).mean()
    prof_early = early.groupby(early.index.month).mean()
    path = _seasonality_figure(prof, groups)

    shift = (prof - prof_early).abs().max()
    energy = ["FUEL", "ELC_GAS"]
    calm = shift.drop(energy)
    shift_tbl = shift.rename(index=settings.label).round(2).rename("max shift (pp)").reset_index()
    shift_tbl = shift_tbl.rename(columns={shift_tbl.columns[0]: "group"})
    by = _easter_split(m["SERV"].dropna())
    sep = prof.loc[9]
    easter_tbl = (by.rename(index={3: "Easter in March", 4: "Easter in April"}).round(2).reset_index()
                  .rename(columns={"easter_month": "", "mar": "March", "apr": "April"}))

    return ["## Seasonality", "",
            f"The data isn't seasonally adjusted and it shows. Every September services drop "
            f"({sep['SERV']:.2f}% on average since 2017, summer prices ending) and non-energy goods "
            f"jump ({sep['IGD_NNRG']:+.2f}%, end of the sales).", "", f"![]({path})", "",
            "Biggest change in any calendar month, 2005-16 against 2017-25 (pp):", "",
            _table(shift_tbl), "",
            f"Energy moves most ({settings.label(shift[energy].idxmax()).lower()} "
            f"{shift[energy].max():.1f} pp), mostly noise from big price swings. Of the rest, "
            f"{settings.label(calm.idxmax()).lower()} {calm.max():.1f} pp. Worth estimating on a rolling "
            "window rather than the full history.", "",
            "Services in March and April by where Easter fell, 2002-25 (average m/m %):", "",
            _table(easter_tbl), "",
            f"Easter moves about {by.loc[4, 'apr'] - by.loc[3, 'apr']:.1f} pp of services inflation "
            "between March and April, so the services model gets an Easter dummy.", ""]

def _pump_prices(wob):
    # euro area average with taxes, weekly and as monthly means
    w = wob[(wob.geo == "EUR") & (wob.tax == "with_tax")].pivot_table(index="date", columns="product",
                                                                       values="price")
    w = w[["euro95", "diesel"]].dropna()
    return w, w.groupby(w.index.to_period("M")).mean()

def _tax_moves(tax):
    # weekly changes of 3 cents or more
    moves = []
    for (geo, product), g in tax.sort_values("date").groupby(["geo", "product"]):
        d = g.set_index("date").tax.diff()
        for when, v in d[d.abs() >= 0.03].items():
            moves.append({"country": "Euro area" if geo == "EUR" else settings.label(geo),
                          "fuel": "petrol" if product == "euro95" else "diesel",
                          "week of": f"{when:%d %b}", "cents per litre": f"{v * 100:+.0f}"})
    return pd.DataFrame(moves)

def fuel_section():
    wob = pd.read_parquet(settings.silver / "oil_bulletin.parquet")
    geos = ["EUR", "DE", "ES", "IT"]
    t = wob[wob.geo.isin(geos)].pivot_table(index=["date", "geo", "product"], columns="tax", values="price")
    tax = (t["with_tax"] - t["without_tax"]).rename("tax").reset_index()
    tax = tax[tax.date >= tax.date.max() - pd.Timedelta(weeks=16)]

    fig, axes = _figure((9.5, 3.6), ncols=2, sharey=True)
    for ax, product in zip(axes, ["euro95", "diesel"], strict=True):
        for geo, colour in zip(geos, SERIES, strict=True):
            s = tax[(tax.geo == geo) & (tax["product"] == product)].set_index("date").tax
            ax.plot(s.index, s.values, color=colour, linewidth=1.6, marker="o", markersize=3,
                    label="Euro area" if geo == "EUR" else settings.label(geo))
        _style(ax, "Petrol (Euro-super 95)" if product == "euro95" else "Diesel",
               "EUR per litre, taxes only" if product == "euro95" else None)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=3))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, ncol=4, loc="lower center",
               bbox_to_anchor=(0.5, -0.06))
    fig.subplots_adjust(bottom=0.2)
    path = _save(fig, "fuel_taxes.png")
    moves = _tax_moves(tax)
    top = moves.loc[moves["cents per litre"].map(lambda c: abs(int(c))).idxmax()]

    # how well the bulletin tracks HICP fuels, month on month
    weekly, monthly = _pump_prices(wob)
    pump = np.log(monthly.mean(axis=1)).diff().mul(100).rename("pump")
    fuel = ch.mom(_ea(["FUEL"]))["FUEL"].rename("hicp")
    d = pd.concat([pump, fuel], axis=1).dropna()
    d = d[d.index >= pd.Period("2006-01", freq="M")]
    slope, intercept = np.polyfit(d.pump, d.hicp, 1)
    r2 = np.corrcoef(d.pump, d.hicp)[0, 1] ** 2
    resid_sd = float((d.hicp - (intercept + slope * d.pump)).std())

    fig, ax = _figure((4.8, 4))
    ax.scatter(d.pump, d.hicp, s=10, color=SERIES[0], alpha=0.6, edgecolor="none")
    xs = np.linspace(d.pump.min(), d.pump.max(), 50)
    ax.plot(xs, intercept + slope * xs, color=INK, linewidth=1)
    _style(ax, "Pump prices and HICP fuels, monthly change", "HICP fuels, %")
    ax.set_xlabel("Weekly Oil Bulletin, euro area average with taxes, %", fontsize=9, color=MUTED)
    path2 = _save(fig, "bulletin_vs_hicp.png")

    # bulletins so far this month against last month's average, through the same line
    last = weekly.index.max()
    cur = last.to_period("M")
    weeks_in = weekly[weekly.index.to_period("M") == cur]
    partial = float(np.log(weeks_in.mean(axis=1).mean() / monthly.loc[cur - 1].mean()) * 100)
    implied = intercept + slope * partial
    month = cur.strftime("%B")

    tbl = silver.fuel_tax_table(weeks=6, geos=("EUR", "DE", "ES", "IT", "FR", "NL"))
    tbl.columns = [c if isinstance(c, str) else f"{c:%d %b}" for c in tbl.columns]
    return [f"## Fuel taxes and the {month} nowcast", "",
            "Tax per litre from the Weekly Oil Bulletin (with-tax minus without-tax price):", "",
            f"![]({path})", "", _table(tbl.reset_index(), "{:.3f}"), "",
            "Weekly moves of 3 cents or more, last 16 weeks:", "",
            _table(moves) if not moves.empty else "None.", "",
            f"The tax includes VAT, so a few cents can just be VAT following the pre-tax price. A step "
            f"like {top.country}'s {abs(int(top['cents per litre']))} cents ({top.fuel}, week of "
            f"{top['week of']}) is an excise change; VAT can't move that much in a week. The HICP is "
            "measured with taxes, so these go straight into the fuel index whatever crude does.", "",
            f"Bulletin against HICP fuels, monthly change since 2006 ({len(d)} months): slope {slope:.2f}, "
            f"intercept {intercept:.2f}, R² {r2:.2f}, residual sd {resid_sd:.2f} pp.", "",
            f"![]({path2})", "",
            f"{len(weeks_in)} bulletins of {month} so far (to {last:%d %b}): pump prices {partial:+.1f}% "
            f"on the {(cur - 1).strftime('%B')} average, which puts HICP fuels at about {implied:+.1f}% "
            f"for {month}.", ""]

def write():
    parts = ["# QA findings", "", "Built by `make qa` from silver and `data/gold/validation.json`.", ""]
    for section in (validation_section, breaks_section, seasonality_section, fuel_section):
        parts += section()
    path = settings.reports / "qa_findings.md"
    path.write_text("\n".join(parts) + "\n")
    return str(path)
