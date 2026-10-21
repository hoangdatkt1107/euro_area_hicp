from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    project_root: Path = PROJECT_ROOT
    # Important paths for Medallion Architecture (hierarchical data layout)
    data: Path = PROJECT_ROOT / "data"
    bronze: Path = PROJECT_ROOT / "data" / "bronze"
    silver: Path = PROJECT_ROOT / "data" / "silver"
    gold: Path = PROJECT_ROOT / "data" / "gold"

    dashboard_data: Path = PROJECT_ROOT / "dashboard" / "data"
    reports: Path = PROJECT_ROOT / "reports"
    logs: Path = PROJECT_ROOT / "data" / "logs"

    # For httpx pipeline
    retry_status: set[int] = {429, 500, 502, 503, 504}
    max_attempts: int = 5
    backoff_seconds: int = 2

    # Eurostat
    eurostat_url: str = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    start: str = "1996-01"

    euro_area: str = "EA"
    countries: list[str] = ["AT", "BE", "BG", "CY", "DE", "EE", "EL", "ES", "FI", "FR", "HR",
                            "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK"]

    # when each country joined the euro, to check Eurostat's country weights against
    euro_join: dict[str, int] = {
        "BE": 1999, "DE": 1999, "IE": 1999, "ES": 1999, "FR": 1999, "IT": 1999, "LU": 1999,
        "NL": 1999, "AT": 1999, "PT": 1999, "FI": 1999, "EL": 2001, "SI": 2007, "CY": 2008,
        "MT": 2008, "SK": 2009, "EE": 2011, "LV": 2014, "LT": 2015, "HR": 2023, "BG": 2026,
    }

    # two ways to split the basket, each adding up to 1000 per mille; never mix them
    groups: list[str] = ["FOOD_P", "FOOD_NP", "FUEL", "ELC_GAS", "IGD_NNRG", "SERV"]
    divisions: list[str] = ["CP01", "CP02", "CP03", "CP04", "CP05", "CP06", "CP07",
                            "CP08", "CP09", "CP10", "CP11", "CP12", "CP13"]

    # pulled for display and cross-checks only
    extra_codes: list[str] = ["TOTAL", "NRG", "FOOD", "TOT_X_NRG_FOOD"]

    # prc_hicp_ctr has energy as a whole, not split into FUEL and ELC_GAS
    contribution_codes: list[str] = ["FOOD_P", "FOOD_NP", "NRG", "IGD_NNRG", "SERV"]

    # (dataset, indicator, name): price expectations over the next three months, seasonally adjusted
    surveys: list[tuple[str, str, str]] = [
        ("ei_bsrt_m_r2", "BS-RPE", "retail_price_expectations"),
        ("ei_bsse_m_r2", "BS-PE3M", "services_price_expectations"),
        ("ei_bsin_m_r2", "BS-ISPE", "industry_price_expectations"),
    ]
    survey_geo: str = "EA21"  # EA20 stops at 2025-12

    # things we looked at in Eurostat's data and decided to live with
    known_gaps: dict[str, str] = {}
    known_weight_issues: dict[str, str] = {
        "EL/1996/groups": "Greece's back-calculated 1996 special-aggregate weights sum to 1014.83. "
                          "Greece joined the euro area in 2001 and 1996 is never used.",
    }

    # Other sources, all free and keyless
    brent_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
    gas_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PNGASEUUSDM"
    eurusd_url: str = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    oil_bulletin_page: str = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"

    # Checks
    yoy_tolerance_pp: float = 0.05           # rebuilt vs official annual rate
    contribution_tolerance_pp: float = 0.02  # own vs published contributions
    weight_sum_tolerance: float = 0.6        # per mille, published weights are rounded
    freshness_days: dict[str, int] = {"brent_usd": 10, "eurusd": 7, "oil_bulletin": 14, "gas_eu_usd": 150}
    # final HICP for a month comes out around the 17th of the next one
    hicp_release_lag_days: int = 20

    # Forecast
    # days between an observation and its release; on 20 Oct FRED had Brent to 14 Oct,
    # and the bulletin prices Mondays and is out by Thursday
    release_lag_days: dict[str, int] = {"brent_usd": 6, "eurusd": 1, "oil_bulletin": 3}
    gas_lag_months: int = 2  # IMF gas, July was the latest one in mid October
    forecast_horizon: int = 3
    early_day: int = 14  # first two weeks of a month, always out by the 20th
    window_months: int = 120  # rolling estimation window
    min_obs: int = 60         # a regressor with less history than this is left out
    seasonal_years: int = 5   # seasonal model: median of the same month over this many years
    # simplest first; called M0, M1, M3, M2, M5, M4 in the plan written on 17 Oct
    models: list[str] = ["no_change", "seasonal", "direct", "bottom_up", "average", "bottom_up_ridge"]
    backtest_start: str = "2012-01"
    # model choice, written down on 17 Oct before any backtest ran: lowest RMSE averaged over the
    # horizons from eval_start on; a simpler model within 2% of the best one wins
    eval_start: str = "2015-01"
    selection_tolerance: float = 0.02
    interval_errors: int = 120  # past errors the forecast intervals are built from
    interval_min_errors: int = 24
    # oil paths for the live forecast, (kind, value); no kind means Brent stays where it was in the
    # first half of the month after the last HICP
    oil_scenarios: dict[str, tuple[str | None, float | None]] = {
        "Brent flat": (None, None), "Brent back to $90": ("usd", 90.0), "Brent up 20%": ("pct", 20.0)}
    ecb_reference: str = "ECB staff projections (September 2026): 3.6% in Q4 2026, with oil at about $88"

    # Shocks
    lp_horizon: int = 18  # months the pass-through is traced for
    lp_lags: int = 3
    lp_exclude: tuple[str, str] = ("2020-01", "2023-12")  # robustness run without the pandemic and the surge
    shock_months: int = 24
    energy_groups: list[str] = ["FUEL", "ELC_GAS"]

    # Display
    group_order: list[str] = ["SERV", "FUEL", "FOOD_P", "ELC_GAS", "IGD_NNRG", "FOOD_NP"]
    colors: dict[str, str] = {
        "SERV": "#2a78d6", "FUEL": "#eb6834", "FOOD_P": "#1baf7a",
        "ELC_GAS": "#eda100", "IGD_NNRG": "#e87ba4", "FOOD_NP": "#008300",
    }

    # short names for charts; Eurostat's full labels are in silver/labels.parquet
    labels: dict[str, str] = {
        "no_change": "No change", "seasonal": "Seasonal", "direct": "Direct regression",
        "bottom_up": "Bottom-up", "average": "Average", "bottom_up_ridge": "Bottom-up ridge",
        "TOTAL": "All items",
        "TOT_X_NRG_FOOD": "Core (excl. energy, food, alcohol, tobacco)",
        "NRG": "Energy",
        "FOOD": "Food, alcohol and tobacco",
        "FOOD_P": "Processed food",
        "FOOD_NP": "Unprocessed food",
        "FUEL": "Liquid and transport fuels",
        "ELC_GAS": "Electricity, gas and heat",
        "IGD_NNRG": "Non-energy industrial goods",
        "SERV": "Services",
        "CP01": "Food and non-alcoholic beverages",
        "CP02": "Alcoholic beverages and tobacco",
        "CP03": "Clothing and footwear",
        "CP04": "Housing, water, electricity, gas",
        "CP05": "Furnishings and household equipment",
        "CP06": "Health",
        "CP07": "Transport",
        "CP08": "Information and communication",
        "CP09": "Recreation, sport and culture",
        "CP10": "Education",
        "CP11": "Restaurants and accommodation",
        "CP12": "Insurance and financial services",
        "CP13": "Personal care and miscellaneous",
        "EA": "Euro area", "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus",
        "DE": "Germany", "EE": "Estonia", "EL": "Greece", "ES": "Spain", "FI": "Finland",
        "FR": "France", "HR": "Croatia", "IE": "Ireland", "IT": "Italy", "LT": "Lithuania",
        "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta", "NL": "Netherlands", "PT": "Portugal",
        "SI": "Slovenia", "SK": "Slovakia",
    }

    @property
    def partitions(self) -> dict[str, list[str]]:
        return {"groups": self.groups, "divisions": self.divisions}

    @property
    def codes(self) -> list[str]:
        # every index series we pull from prc_hicp_minr
        return list(dict.fromkeys(self.groups + self.divisions + self.extra_codes))

    def label(self, code: str) -> str:
        return self.labels.get(code, code)

settings = Settings()