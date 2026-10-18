import numpy as np
import pandas as pd
import hashlib
import json
import httpx

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