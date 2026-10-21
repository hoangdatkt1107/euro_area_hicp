""" G(t) = sum_ci theta_ci(t) * (1 + x_ci(t)) / (1 + x_ci(Dec before t))
    M(t) = M(Dec before t) * G(t) """
import json
from dataclasses import dataclass
import numpy as np
import pandas as pd
from src import chain as ch
from src.config import settings
from src.forecast import realtime as rt

@dataclass
class Baseline:
    partition: str
    months: pd.PeriodIndex
    countries: list[str]
    codes: list[str]
    theta: np.ndarray      
    level: pd.Series       
    yoy: pd.Series         

def _seasonal_path(lv: pd.DataFrame, months) -> pd.DataFrame:
    """Each component carried forward with the median change of the same month in past years"""
    lv = lv.copy()
    for t in months:
        same = [t - 12 * k for k in range(1, settings.seasonal_years + 1)]
        growth = pd.concat([lv.loc[s] / lv.loc[s - 1] for s in same], axis=1).median(axis=1)
        lv.loc[t] = lv.loc[t - 1] * growth
    return lv

def _weights(table, years, geo=None, codes=None):
    """year x code (or geo) weights, later years copying the latest one published"""
    if codes is None:
        w = table.pivot_table(index="year", columns="geo", values="weight")
    else:
        w = ch.weight_table(table, codes, geo=geo)
    return w.reindex(range(w.index.min(), max(years) + 1)).ffill().loc[list(years)].fillna(0)

def _relatives(levels, months):
    """Each level relative to the December before its month"""
    decs = pd.PeriodIndex([pd.Period(year=t.year - 1, month=12, freq="M") for t in months])
    return levels.loc[months].to_numpy() / levels.loc[decs].to_numpy()

def baseline(tables=None, partition="groups") -> Baseline:
    tables = tables or rt.load()
    last = tables["index"].month.max().to_period("M")
    snap = rt.snapshot(tables, last)
    codes, countries = settings.partitions[partition], settings.countries
    months = pd.period_range(last + 1, periods=settings.shock_months, freq="M")
    span = months.insert(0, last)  # the last actual month too, for the first monthly change
    years = sorted(set(span.year))
    cw = _weights(snap["country_weights"], years)

    # country weight x item weight x relative price, for every country and component
    shares = np.zeros((len(span), len(countries), len(codes)))
    for j, c in enumerate(countries):
        lv = _seasonal_path(ch.wide(snap["index"], c, codes).reindex(columns=codes), months)
        w = _weights(snap["item_weights"], years, geo=c, codes=codes).loc[span.year].to_numpy()
        total_w = w.sum(axis=1, keepdims=True)
        rel = np.nan_to_num(_relatives(lv, span))
        shares[:, j, :] = cw.loc[span.year, c].to_numpy()[:, None] * np.divide(
            w, total_w, out=np.zeros_like(w), where=total_w > 0) * rel
    theta = shares[1:] / shares[1:].sum(axis=(1, 2))[:, None, None]

    # headline: history, the live forecast for its months, then the components' seasonal path
    ea = shares.sum(axis=(1, 2)) / cw.loc[span.year].sum(axis=1).to_numpy()  # relative to December
    mom = pd.Series([(ea[k] if t.month == 1 else ea[k] / ea[k - 1]) - 1 for k, t in enumerate(span)][1:],
                    index=months) * 100
    live = settings.gold / "forecast.json"
    if live.exists():
        r = json.loads(live.read_text())
        if r["last_hicp"] == str(last):
            for f in r["forecast"]:
                mom[pd.Period(f["month"], freq="M")] = f["mom"]
    total = ch.wide(snap["index"], settings.euro_area, ["TOTAL"])["TOTAL"]
    level = ch.extend(total, mom.to_numpy())
    return Baseline(partition, months, countries, codes, theta, level, ch.yoy(level)[months])

def shape(size, start, months, kind="step", half_life=6, ramp=6, path=None) -> np.ndarray:
    """A shock's path in % over the months ahead: step (stays), fade (halves every half_life months), 
    ramp (builds up over `ramp` months) or a path given month by month (last value held)"""
    k = np.array([(t - pd.Period(start, freq="M")).n for t in months])
    on = k >= 0
    if kind == "step":
        x = np.full(len(k), float(size))
    elif kind == "fade":
        x = size * 0.5 ** (np.maximum(k, 0) / half_life)
    elif kind == "ramp":
        x = size * np.minimum(1, (np.maximum(k, 0) + 1) / ramp)
    elif kind == "path":
        p = np.asarray(path, dtype=float)
        x = p[np.clip(k, 0, len(p) - 1)]
    else:
        raise ValueError(f"unknown shock shape {kind}")
    return np.where(on, x, 0.0)

def _respond(driver, elasticity) -> np.ndarray:
    """Level response (%) to a driver path (%): every change in the driver sets off the estimated
    response from that month on, held at its last value after the horizon"""
    e = np.asarray(elasticity)
    steps = np.diff(np.r_[0.0, driver])
    out = np.zeros(len(driver))
    for k, s in enumerate(steps):
        if s:
            h = np.arange(len(driver) - k)
            out[k:] += s * e[np.minimum(h, len(e) - 1)]
    return out

def multiplier(base: Baseline, x: np.ndarray) -> np.ndarray:
    """Headline with the shocks over the baseline headline, month by month (x as fractions)"""
    M = np.ones(len(base.months))
    for k, t in enumerate(base.months):
        dec = k - t.month if k - t.month >= 0 else None  # the December before t, if it's ahead
        x_dec = x[dec] if dec is not None else 0.0
        m_dec = M[dec] if dec is not None else 1.0
        M[k] = m_dec * (base.theta[k] * (1 + x[k]) / (1 + x_dec)).sum()
    return M

def _impact(base, x) -> np.ndarray:
    level = base.level.copy()
    level[base.months] = level[base.months] * multiplier(base, x)
    return (ch.yoy(level)[base.months] - base.yoy).to_numpy()

def simulate(base: Baseline, shocks=(), oil=None, gas=None, indirect=True, regime="normal") -> dict:
    """cshocks: dicts with countries (list or "EA"), components, size (%), start, and optionally kind,
    half_life, ramp, path as in shape(). oil, gas: same, without countries and components; they
    hit every country. regime: "normal" uses pass-through estimated without 2020-23, "2022" all of it"""
    n, nc, ni = base.theta.shape
    direct = np.zeros((n, nc, ni))
    second = np.zeros((n, nc, ni))
    for s in shocks:
        cs = range(nc) if s["countries"] == "EA" else [base.countries.index(c) for c in s["countries"]]
        comps = [base.codes.index(c) for c in s["components"]]
        p = shape(s["size"], s["start"], base.months, s.get("kind", "step"), s.get("half_life", 6),
                  s.get("ramp", 6), s.get("path"))
        for c in cs:
            direct[:, c, comps] += p[:, None]
    # energy shocks whose second round still has to be added: the user's and gas. Oil's estimated
    # responses already include it
    push = direct.copy()

    groups = base.partition == "groups"
    if (oil or gas or indirect) and groups:
        lp = json.loads((settings.gold / "passthrough.json").read_text())
        key = "elasticity_ex" if regime == "normal" else "elasticity"
        energy = [base.codes.index(g) for g in settings.energy_groups]
        others = [i for i in range(ni) if i not in energy]
        for driver, s in (("brent", oil), ("gas", gas)):
            if not s:
                continue
            p = shape(s["size"], s["start"], base.months, s.get("kind", "step"), s.get("half_life", 6),
                      s.get("ramp", 6), s.get("path"))
            for i, g in enumerate(base.codes):
                if g not in lp[driver]:
                    continue
                r = _respond(p, lp[driver][g][key])[:, None]
                if i in energy:
                    direct[:, :, i] += r
                    if driver == "gas":
                        push[:, :, i] += r
                elif indirect:
                    second[:, :, i] += r
        if indirect and np.any(push[:, :, energy]):
            # second round inside each country from its own energy shock
            w = base.theta[:, :, energy]
            share = w.sum(axis=2)
            shock_energy = (w * push[:, :, energy]).sum(axis=2) / np.where(share > 0, share, 1)
            for i in others:
                e = lp["energy"][base.codes[i]][key]
                for c in range(nc):
                    second[:, c, i] += _respond(shock_energy[:, c], e)
    elif oil or gas:
        raise ValueError("oil and gas shocks need the six-group partition")

    total = _impact(base, (direct + second) / 100)
    only_direct = _impact(base, direct / 100)

    # one country or component at a time; the parts add up to the total up to tiny cross terms
    x = (direct + second) / 100
    by_country = {c: _impact(base, np.where(np.arange(nc)[None, :, None] == j, x, 0))
                  for j, c in enumerate(base.countries) if np.any(x[:, j, :])}
    by_component = {g: _impact(base, np.where(np.arange(ni)[None, None, :] == i, x, 0))
                    for i, g in enumerate(base.codes) if np.any(x[:, :, i])}
    idx = base.months
    return {
        "baseline": base.yoy, "yoy": base.yoy + total,
        "impact": pd.Series(total, index=idx), "direct": pd.Series(only_direct, index=idx),
        "indirect": pd.Series(total - only_direct, index=idx),
        "by_country": pd.DataFrame(by_country, index=idx),
        "by_component": pd.DataFrame(by_component, index=idx)}
