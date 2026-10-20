import numpy as np
import pandas as pd

def _december(year):
    return pd.Period(year=year, month=12, freq="M")

def to_periods(index):
    return index if isinstance(index, pd.PeriodIndex) else pd.PeriodIndex(index, freq="M")

def full_months(obj):
    # no silent holes: a missing month shows up as NaN
    return obj.reindex(pd.period_range(obj.index.min(), obj.index.max(), freq="M"))

def wide(index_long, geo, codes):
    """Silver index table to month x component for one geography"""
    d = index_long[(index_long.geo == geo) & index_long.coicop.isin(codes)]
    out = d.pivot_table(index="month", columns="coicop", values="value")
    out.index = to_periods(out.index)
    return out.reindex(columns=[c for c in codes if c in out.columns]).sort_index()

def weight_table(weights_long, codes, geo=None):
    """Silver weights to year x component. Any scale, they get normalised where used"""
    d = weights_long if geo is None else weights_long[weights_long.geo == geo]
    d = d[d.coicop.isin(codes)]
    return d.pivot_table(index="year", columns="coicop", values="weight").reindex(columns=codes)

def _year_weights(weights, year):
    w = weights.loc[year].dropna()
    return w[w > 0]

def _inputs(levels, weights, year, require_all):
    """The year's weights and the December levels they apply to, or None if the year can't be built"""
    dec = _december(year - 1)
    if year not in weights.index or dec not in levels.index:
        return None
    if require_all and weights.loc[year].isna().any():
        return None
    w = _year_weights(weights, year)
    missing = w.index.difference(levels.columns)
    if len(missing):
        # a weight with no data behind it is a config mistake, not a gap in the data
        raise ValueError(f"{year}: weight but no level data for {list(missing)}")
    base = levels.loc[dec, w.index]
    if w.empty or base.isna().any():
        return None
    return w, base

def chain(levels, weights, anchor=100.0, require_all=False):
    levels = levels.sort_index()
    out = {}
    for year in sorted(set(levels.index.year)):
        inputs = _inputs(levels, weights, year, require_all)
        if inputs is None:
            if out:
                break
            continue
        w, base = inputs
        dec = _december(year - 1)
        if not out:
            out[dec] = anchor

        rel = levels.loc[levels.index.year == year, w.index].div(base)
        s = rel.mul(w / w.sum()).sum(axis=1, min_count=len(w)).dropna()
        for month, v in s.items():
            out[month] = out[dec] * v
        if _december(year) not in s.index:
            break  
    return pd.Series(out, dtype=float).sort_index()

def _change(level, months):
    s = full_months(level)
    return (s / s.shift(months) - 1) * 100

def yoy(level):
    """Annual rate, %."""
    return _change(level, 12)

def mom(level):
    """Monthly rate, %."""
    return _change(level, 1)

def contributions(levels, weights):
    levels = full_months(levels)
    rows = {}
    for month in levels.index:
        y = month.year
        if y not in weights.index or y - 1 not in weights.index or _december(y - 2) not in levels.index:
            continue
        w1, w2 = _year_weights(weights, y - 1), _year_weights(weights, y)
        w1, w2 = w1 / w1.sum(), w2 / w2.sum()
        lv = levels.reindex(columns=w1.index.union(w2.index))

        # the three relatives, each against the December it is linked on
        a_year_ago = lv.loc[month - 12] / lv.loc[_december(y - 2)]
        last_dec = lv.loc[_december(y - 1)] / lv.loc[_december(y - 2)]
        now = lv.loc[month] / lv.loc[_december(y - 1)]
        gaps = a_year_ago[w1.index].isna().any() or last_dec[w1.index].isna().any()
        if gaps or now[w2.index].isna().any():
            continue

        w1, w2 = w1.reindex(lv.columns, fill_value=0.0), w2.reindex(lv.columns, fill_value=0.0)
        p1 = (w1 * (last_dec - a_year_ago) / (w1 * a_year_ago.fillna(0)).sum()).fillna(0)
        p2 = (w2 * (now - 1)).fillna(0)
        rows[month] = (p1 + (1 + p1.sum()) * p2) * 100
    return pd.DataFrame(rows).T.sort_index() if rows else pd.DataFrame(columns=weights.columns)

def extend(level, mom_path):
    """Append future months to an index, given their monthly rates in %"""
    out = full_months(level).copy()  
    last, value = out.index[-1], out.iloc[-1]
    for k, r in enumerate(np.asarray(mom_path, dtype=float), start=1):
        value *= 1 + r / 100
        out.loc[last + k] = value
    return out

def base_effect_split(level, mom_path, origin=None):
    level = full_months(level if origin is None else level.loc[:origin])
    t = level.index[-1]
    path = extend(level, mom_path)
    now = level.loc[t] / level.loc[t - 12]
    rows = []
    for h in range(1, len(mom_path) + 1):
        new = path.loc[t + h] / path.loc[t]
        old = path.loc[t + h - 12] / path.loc[t - 12]
        ahead = now * new / old
        rows.append({"month": t + h, "yoy": (ahead - 1) * 100, "yoy_now": (now - 1) * 100,
                     "new_months": (now * new - now) * 100, "dropping_out": (ahead - now * new) * 100})
    return pd.DataFrame(rows).set_index("month")

def two_level(levels, item_weights, country_weights, anchors=None, anchor=100.0):
    anchors = anchors or {}
    countries = pd.DataFrame({
        geo: chain(levels[geo], item_weights[geo], anchors.get(geo, 100.0), require_all=True)
        for geo in levels
    })
    countries.index = to_periods(countries.index)
    return chain(countries.sort_index(), country_weights, anchor), countries
