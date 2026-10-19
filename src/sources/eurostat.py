import numpy as np
import pandas as pd
import hashlib
import json
import httpx
from src.config import settings
# responses seen in this run, so the label table can be built at the end
_responses = {}

def codes(category: dict) -> list[str]:
    """take catagory by building fall-back wheather it's list or dict"""
    idx = category["index"]
    if isinstance(idx, list):
        return idx
    return [code for code, _ in sorted(idx.items(), key=lambda kv: kv[1])]

def parse(js: dict) -> pd.DataFrame:
    """JSON-stat dataset to a long frame: one column per dimension, then time_period, obs_value, obs_flag and last_update"""
    if "error" in js:
        raise RuntimeError(f"Eurostat error: {js['error']}")
    dims, size = js["id"], js["size"]
    values = js.get("value", {})
    if isinstance(values, list):
        pos = np.array([i for i, v in enumerate(values) if v is not None], dtype=np.int64)
        vals = np.array([values[i] for i in pos], dtype=float)
    else:
        pos = np.array([int(k) for k in values], dtype=np.int64)
        vals = np.array(list(values.values()), dtype=float)
    status = js.get("status", {})
    if isinstance(status, list):
        flags = [status[i] if i < len(status) else None for i in pos]
    else:
        flags = [status.get(str(i)) for i in pos]

    coords = np.unravel_index(pos, size) if len(pos) else [np.array([], dtype=int)] * len(dims)
    out = {}
    for d, c in zip(dims, coords, strict=True):
        codes = np.array(codes(js["dimension"][d]["category"]), dtype=object)
        out["time_period" if d == "time" else d] = codes[c]
    out["obs_value"] = vals
    out["obs_flag"] = pd.array(flags, dtype="string")
    out["last_update"] = js.get("updated")
    return pd.DataFrame(out)

def labels(js):
    rows = []
    for dim in js["id"]:
        if dim == "time":
            continue
        names = js["dimension"][dim]["category"].get("label", {})
        rows += [(dim, code, names.get(code, code)) for code in codes_of(js, dim)]
    return pd.DataFrame(rows, columns=["dimension", "code", "label"])


def all_labels():
    if not _responses:
        return pd.DataFrame(columns=["dimension", "code", "label"])
    return pd.concat(labels(js) for js in _responses.values()).drop_duplicates(["dimension", "code"])


def fetch(flow, filters, start=None, refresh=False):
    params = [("format", "JSON"), ("lang", "EN")]
    for dim, value in filters.items():
        params += [(dim, v) for v in ([value] if isinstance(value, str) else value)]
    if start:
        params.append(("sinceTimePeriod", start))

    # one bronze folder per distinct query
    name = f"{flow}-{hashlib.sha1(json.dumps(params).encode()).hexdigest()[:10]}"
    raw = net.fetch(f"{settings.eurostat_url}/{flow}", params, source="eurostat", name=name,
                    ext="json", refresh=refresh)
    js = json.loads(raw)
    _responses[name] = js
    return parse(js)


def indices(refresh=False):
    # euro area and countries separately; the countries alone are about 3 MB
    frames = [fetch("prc_hicp_minr", {"freq": "M", "unit": "I25", "coicop18": settings.codes, "geo": geo},
                    start=settings.start, refresh=refresh)
              for geo in (settings.euro_area, settings.countries)]
    return pd.concat(frames, ignore_index=True)


def official_rates(refresh=False):
    # only used to cross-check the rates we compute ourselves
    filters = {"freq": "M", "unit": "RCH_A", "coicop18": settings.codes, "geo": settings.euro_area}
    return fetch("prc_hicp_minr", filters, start="2000-01", refresh=refresh)


def item_weights(refresh=False):
    filters = {"coicop18": settings.codes, "statinfo": "IW", "geo": [settings.euro_area, *settings.countries]}
    return fetch("prc_hicp_iw", filters, refresh=refresh)


def country_weights(refresh=False):
    return fetch("prc_hicp_cw", {"statinfo": "COWEA", "geo": settings.countries}, refresh=refresh)


def contributions(refresh=False):
    codes = settings.contribution_codes + settings.divisions
    return fetch("prc_hicp_ctr", {"unit": "PC_PNT", "coicop18": codes, "geo": settings.euro_area},
                 refresh=refresh)


def first_release(refresh=False):
    # final releases go back to 1997, flash ones only to 2026-01
    filters = {"unit": "RCH_A", "coicop18": ["TOTAL", "TOT_X_NRG_FOOD", "NRG", "SERV"],
               "release": ["FIN", "FLS"], "geo": settings.euro_area}
    return fetch("prc_hicp_fpd", filters, refresh=refresh)


def surveys(refresh=False):
    frames = []
    for flow, indic, name in settings.surveys:
        filters = {"indic": indic, "s_adj": "SA", "unit": "BAL", "geo": settings.survey_geo}
        frames.append(fetch(flow, filters, start="1990-01", refresh=refresh).assign(series=name))
    return pd.concat(frames, ignore_index=True)
