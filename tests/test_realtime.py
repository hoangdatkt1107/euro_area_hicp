"""Snapshots and feature tables only use what was published on the forecast day"""
import numpy as np
import pandas as pd
import pytest
from src.config import settings
from src.forecast import features as ft
from src.forecast import realtime as rt

CODES = ["TOTAL", *settings.groups]

def make_tables(start="2023-01", end="2027-06"):
    """Small fake silver tables, same columns as the real ones, running well past any origin"""
    months = pd.period_range(start, end, freq="M").to_timestamp()
    days = pd.bdate_range(months[0], months[-1] + pd.offsets.MonthEnd(0))
    mondays = pd.date_range(months[0], months[-1] + pd.offsets.MonthEnd(0), freq="W-MON")
    years = range(months[0].year, months[-1].year + 1)
    rng = np.random.default_rng(0)

    def monthly(**cols):
        return pd.DataFrame({"month": months, "value": rng.normal(1, 0.1, len(months)), "flag": None, **cols})

    index = pd.concat([pd.DataFrame({"geo": "EA", "coicop": c, "month": months, "flag": None,
                                     "value": 100 * np.cumprod(1 + rng.normal(0.002, 0.003, len(months)))})
                       for c in CODES])
    weights = pd.DataFrame([{"geo": "EA", "coicop": c, "year": y, "weight": 1000 / 6, "flag": None}
                            for c in settings.groups for y in years])
    bulletin = pd.DataFrame([{"date": d, "geo": "EUR", "product": p, "tax": t, "price": 1.8} for d in mondays
                             for p in ("euro95", "diesel") for t in ("with_tax", "without_tax")])
    return {
        "index": index,
        "official_rates": monthly(coicop="TOTAL"),
        "item_weights": weights,
        "country_weights": pd.DataFrame({"geo": "DE", "year": list(years), "weight": 1000.0, "flag": None}),
        "contributions": monthly(coicop="SERV").rename(columns={"value": "pp"}),
        "first_release": monthly(coicop="TOTAL", release="FIN"),
        "surveys": pd.concat([monthly(series=name) for _, _, name in settings.surveys]),
        "brent_usd": pd.DataFrame({"date": days, "value": 80 + rng.normal(0, 1, len(days))}),
        "eurusd": pd.DataFrame({"date": days, "value": 1.1}),
        "gas_eu_usd": pd.DataFrame({"date": months, "value": 10.0}),
        "oil_bulletin": bulletin}

def poison(tables, day):
    """Overwrite everything that didn't exist yet on `day` with nonsense."""
    out = {}
    for name, df in tables.items():
        df = df.copy()
        value = next(c for c in ("value", "weight", "pp", "price") if c in df)
        if "month" in df or name == "gas_eu_usd":
            month = df["month" if "month" in df else "date"].dt.to_period("M")
            future = month.dt.end_time > day  
        elif "year" in df:
            future = df.year > day.year
        else:
            future = df.date > day
        assert future.any(), name  
        df.loc[future, value] = 1e6
        out[name] = df
    return out

@pytest.mark.parametrize("month,day", [("2026-09", "2026-10-20"), ("2025-12", "2026-01-20"),
                                       ("2026-01", "2026-02-28"), ("2024-01", "2024-02-29")])
def test_origin_is_the_20th_except_after_january(month, day):
    assert rt.origin_date(month) == pd.Timestamp(day)

def test_each_source_stops_where_it_did_on_20_october_2026():
    last = rt.last_dates(rt.snapshot(make_tables(), "2026-09"))
    assert last["index"] == last["surveys"] == last["first_release"] == "2026-09"
    assert last["item_weights"] == "2026"
    assert last["brent_usd"] == "2026-10-14"   
    assert last["eurusd"] == "2026-10-19"
    assert last["oil_bulletin"] == "2026-10-12"  
    assert last["gas_eu_usd"] == "2026-07-01"

def test_next_years_weights_wait_for_its_january_final():
    tables = make_tables()
    assert rt.last_dates(rt.snapshot(tables, "2025-12"))["item_weights"] == "2025"
    assert rt.last_dates(rt.snapshot(tables, "2026-01"))["item_weights"] == "2026"

@pytest.mark.parametrize("month", ["2024-03", "2025-12", "2026-01", "2026-09"])
def test_poisoned_future_changes_neither_snapshot_nor_features(month):
    tables = make_tables()
    dirty = poison(tables, rt.origin_date(month))
    a, b = rt.snapshot(tables, month), rt.snapshot(dirty, month)
    assert all(a[n].equals(b[n]) for n in a)
    pd.testing.assert_frame_equal(ft.build(a), ft.build(b))

def test_a_source_without_a_release_rule_is_refused():
    with pytest.raises(KeyError, match="no release rule"):
        rt.snapshot({"labels": pd.DataFrame()}, "2026-09")

def test_feature_rows_after_the_last_hicp_month():
    f = ft.build(rt.snapshot(make_tables(), "2026-09"))
    assert f.attrs["last_hicp"] == pd.Period("2026-09", freq="M")
    assert f.index[-1] == pd.Period("2026-12", freq="M")
    oct_ = f.loc["2026-10"]
    assert np.isnan(oct_.mom_TOTAL) and np.isnan(oct_.pump) and np.isnan(oct_.brent)
    assert not np.isnan(oct_.pump_early_chg) and not np.isnan(oct_.brent_early_chg)
    assert f.loc["2026-11":, "brent_early_chg"].isna().all()

def test_monthly_changes_are_percent_not_log():
    tables = make_tables()
    f = ft.build(rt.snapshot(tables, "2026-09"))
    total = tables["index"].query("coicop == 'TOTAL'").set_index("month").value
    expected = (total.loc["2026-09-01"] / total.loc["2026-08-01"] - 1) * 100
    assert f.loc["2026-09", "mom_TOTAL"] == pytest.approx(expected)

def test_early_change_only_sees_the_first_two_weeks():
    tables = make_tables()
    wob = tables["oil_bulletin"]
    in_sep = wob.date.dt.to_period("M") == pd.Period("2026-09", freq="M")
    wob.loc[in_sep, "price"] = np.where(wob.loc[in_sep, "date"].dt.day <= 14, 3.6, 9.0)
    f = ft.build(rt.snapshot(tables, "2026-09"))
    assert f.loc["2026-09", "pump_early_chg"] == pytest.approx(100.0) 

def test_easter_share_follows_the_week_before_easter():
    f = ft.build(rt.snapshot(make_tables(start="2015-01"), "2026-09"))
    assert f.loc["2026-03", "easter"] == 0.375 and f.loc["2026-04", "easter"] == 0.625  
    assert f.loc["2016-03", "easter"] == 1.0 and f.loc["2016-04", "easter"] == 0.0     
    assert f.loc[f.month.isin([1, 2, 5, 6, 7, 8, 9, 10, 11, 12]), "easter"].eq(0).all()


@pytest.mark.skipif(not (settings.silver / "index.parquet").exists(), reason="needs data/silver")
def test_real_data_on_20_october_2026():
    last = rt.last_dates(rt.snapshot(rt.load(), "2026-09"))
    assert last["index"] == last["surveys"] == "2026-09"
    assert last["brent_usd"] <= "2026-10-14" and last["oil_bulletin"] <= "2026-10-17"
    assert last["gas_eu_usd"] <= "2026-07-01"
