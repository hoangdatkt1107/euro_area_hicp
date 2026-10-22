"""The shock engine: exact against a full chain rerun, and the behaviour a shock should have"""
import json
import numpy as np
import pandas as pd
import pytest
from src import chain as ch
from src.config import settings
from src.forecast import realtime as rt
from src.shocks import engine as en

GROUPS = settings.groups
OTHERS = [g for g in GROUPS if g not in settings.energy_groups]

def make_tables(start="2018-01", end="2026-09"):
    """Fake index and weights for every country and group, plus a euro area headline"""
    rng = np.random.default_rng(1)
    months = pd.period_range(start, end, freq="M").to_timestamp()
    years = range(months[0].year, months[-1].year + 1)
    season = rng.normal(0, 0.004, (12, len(GROUPS)))

    rows, weights = [], []
    for geo in [settings.euro_area, *settings.countries]:
        growth = 1 + 0.002 + season[months.month - 1] + rng.normal(0, 0.002, (len(months), len(GROUPS)))
        levels = 100 * np.cumprod(growth, axis=0)
        for i, g in enumerate(GROUPS):
            rows.append(pd.DataFrame({"geo": geo, "coicop": g, "month": months, "value": levels[:, i],
                                      "flag": None}))
        w = rng.uniform(30, 300, len(GROUPS))
        weights += [{"geo": geo, "coicop": g, "year": y, "weight": 1000 * w[i] / w.sum(), "flag": None}
                    for y in years for i, g in enumerate(GROUPS)]
    total = rows[0].assign(coicop="TOTAL", value=100 * np.cumprod(1 + rng.normal(0.002, 0.002, len(months))))
    cw = rng.uniform(1, 50, len(settings.countries))
    return {
        "index": pd.concat([*rows, total]),
        "item_weights": pd.DataFrame(weights),
        "country_weights": pd.DataFrame([{"geo": c, "year": y, "weight": 1000 * cw[j] / cw.sum(),
                                          "flag": None}
                                         for y in years for j, c in enumerate(settings.countries)])}


def flat(value):
    return [value] * (settings.lp_horizon + 1)

@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    gold = tmp_path_factory.mktemp("gold")
    # simple made-up pass-through so oil and second-round results can be checked by hand
    brent = {g: {"elasticity": flat(0.3), "elasticity_ex": flat(0.2)} if g == "FUEL"
             else {"elasticity": flat(0.1), "elasticity_ex": flat(0.05)} for g in GROUPS}
    lp = {"brent": brent,
          "gas": {g: {"elasticity": flat(0.1), "elasticity_ex": flat(0.1)} for g in GROUPS},
          "energy": {g: {"elasticity": flat(0.2), "elasticity_ex": flat(0.1)} for g in OTHERS}}
    (gold / "passthrough.json").write_text(json.dumps(lp))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "gold", gold) 
        tables = make_tables()
        yield tables, en.baseline(tables)

def full_chain(tables, base, x):
    """Euro area index from the full two-level chain, with level shocks x on the seasonal paths"""
    snap = rt.snapshot(tables, base.months[0] - 1)
    levels, item = {}, {}
    for j, c in enumerate(base.countries):
        lv = en._seasonal_path(ch.wide(snap["index"], c, base.codes), base.months)
        lv.loc[base.months] = lv.loc[base.months].to_numpy() * (1 + x[:, j, :])
        levels[c] = lv
        item[c] = en._weights(snap["item_weights"], range(2018, base.months[-1].year + 1), geo=c,
                              codes=base.codes)
    cw = en._weights(snap["country_weights"], range(2018, base.months[-1].year + 1))
    return ch.two_level(levels, item, cw)[0]

def shocks_to_x(base, shocks):
    x = np.zeros(base.theta.shape)
    for s in shocks:
        p = en.shape(s["size"], s["start"], base.months, s.get("kind", "step"), s.get("half_life", 6),
                     s.get("ramp", 6), s.get("path"))
        everyone = s["countries"] == "EA"
        cs = range(len(base.countries)) if everyone else [base.countries.index(c) for c in s["countries"]]
        for c in cs:
            for g in s["components"]:
                x[:, c, base.codes.index(g)] += p / 100
    return x

CASES = {
    "step across the new year": [{"countries": ["DE"], "components": ["FUEL"], "size": 8.5,
                                  "start": "2027-01"}],
    "fading": [{"countries": ["DE", "FR"], "components": ["FOOD_P", "FOOD_NP"], "size": 5, "start": "2026-11",
                "kind": "fade", "half_life": 4}],
    "ramp over a December": [{"countries": "EA", "components": GROUPS, "size": 20, "start": "2026-12",
                              "kind": "ramp", "ramp": 10}],
    "path and two shocks": [{"countries": ["ES"], "components": ["SERV"], "size": 0, "start": "2027-03",
                             "kind": "path", "path": [-3, -2, 4, 1]},
                            {"countries": ["IT"], "components": ["FUEL", "ELC_GAS"], "size": 15,
                             "start": "2026-10", "kind": "fade", "half_life": 9}]}


@pytest.mark.parametrize("name", CASES)
def test_engine_is_exact_against_a_full_chain_rerun(setup, name):
    tables, base = setup
    x = shocks_to_x(base, CASES[name])
    exact = (full_chain(tables, base, x) / full_chain(tables, base, np.zeros_like(x)))[base.months]
    assert np.abs(en.multiplier(base, x) - exact.to_numpy()).max() < 1e-12

def test_theta_sums_to_one_every_month(setup):
    _, base = setup
    assert np.allclose(base.theta.sum(axis=(1, 2)), 1)
    assert base.theta.shape == (settings.shock_months, len(settings.countries), len(GROUPS))

def test_no_shock_no_impact(setup):
    _, base = setup
    r = en.simulate(base, indirect=False)
    assert np.abs(r["impact"]).max() < 1e-12  

def test_one_percent_on_everything_lasts_exactly_twelve_months(setup):
    _, base = setup
    everything = {"countries": "EA", "components": GROUPS, "size": 1, "start": "2026-11"}
    r = en.simulate(base, [everything], indirect=False)
    on = (base.months >= pd.Period("2026-11", freq="M")) & (base.months < pd.Period("2027-11", freq="M"))
    expected = 0.01 * (100 + base.yoy[on]) 
    assert np.allclose(r["impact"][on], expected) and np.abs(r["impact"][~on]).max() < 1e-9

def test_separate_shocks_add_up(setup):
    _, base = setup
    a = {"countries": ["DE"], "components": ["SERV"], "size": 3, "start": "2026-11"}
    b = {"countries": ["IT", "NL"], "components": ["FOOD_P"], "size": -4, "start": "2027-02", "kind": "fade"}
    both = en.simulate(base, [a, b], indirect=False)["impact"]
    apart = sum(en.simulate(base, [s], indirect=False)["impact"] for s in (a, b))
    assert np.abs(both - apart).max() < 1e-3  
    parts = en.simulate(base, [a, b], indirect=False)["by_country"].sum(axis=1)
    assert np.abs(parts - both).max() < 1e-3

def test_a_country_moves_the_headline_by_its_share(setup):
    _, base = setup
    r = en.simulate(base, [{"countries": ["DE"], "components": GROUPS, "size": 1, "start": "2026-11"}],
                    indirect=False)
    share = base.theta[1, base.countries.index("DE"), :].sum()
    assert r["impact"].iloc[1] == pytest.approx(share * (1 + base.yoy.iloc[1] / 100), rel=1e-9)

@pytest.mark.parametrize("kind,expected", [("step", [0, 0, 4, 4, 4, 4]), ("fade", [0, 0, 4, 2, 1, 0.5]),
                                           ("ramp", [0, 0, 1, 2, 3, 4]), ("path", [0, 0, 1, 5, 5, 5])])
def test_shapes(kind, expected):
    months = pd.period_range("2026-10", periods=6, freq="M")
    x = en.shape(4, "2026-12", months, kind, half_life=1, ramp=4, path=[1, 5])
    assert np.allclose(x, expected)

def test_oil_splits_into_direct_energy_and_indirect_rest(setup):
    _, base = setup
    oil = {"size": -10, "start": "2026-11"}
    r = en.simulate(base, oil=oil, regime="2022")
    k = 1  # first month of the shock
    fuel = base.theta[k, :, GROUPS.index("FUEL")].sum()
    rest = base.theta[k][:, [GROUPS.index(g) for g in GROUPS if g != "FUEL"]].sum()
    scale = 1 + base.yoy.iloc[k] / 100
    elc = base.theta[k, :, GROUPS.index("ELC_GAS")].sum()
    assert r["direct"].iloc[k] == pytest.approx(-(3 * fuel + elc) * scale, rel=1e-9)
    assert r["indirect"].iloc[k] == pytest.approx(-1 * (rest - elc) * scale, rel=1e-9)
    assert en.simulate(base, oil=oil, indirect=False, regime="2022")["indirect"].abs().max() < 1e-12

def test_second_round_stays_in_the_shocked_country(setup):
    _, base = setup
    r = en.simulate(base, [{"countries": ["DE"], "components": ["FUEL"], "size": 10, "start": "2026-11"}])
    assert list(r["by_country"].columns) == ["DE"]
    assert r["indirect"].iloc[1] > 0 and set(r["by_component"].columns) == {"FUEL", *OTHERS}

def test_oil_needs_the_six_groups(setup):
    _, base = setup
    divisions = en.Baseline("divisions", base.months, base.countries, base.codes, base.theta, base.level,
                            base.yoy)
    with pytest.raises(ValueError, match="six-group"):
        en.simulate(divisions, oil={"size": -10, "start": "2026-11"})

@pytest.mark.skipif(not (settings.silver / "index.parquet").exists(), reason="needs data/silver")
def test_real_data_shares():
    base = en.baseline()
    by_country = pd.Series(base.theta[0].sum(axis=1), index=base.countries)
    assert by_country.idxmax() == "DE" and 0.25 < by_country["DE"] < 0.30
    assert np.allclose(base.theta.sum(axis=(1, 2)), 1)
