# Euro area inflation: pipeline, forecast and shock simulator

A take-home case study from October 2026. It pulls the euro area HICP from the Eurostat API, checks it against
the official figures, forecasts headline inflation three months ahead and simulates price shocks by country
and group. The results are in a Streamlit dashboard and in five slides (`slides/`).

Dashboard: https://euro-area-inflation.streamlit.app (if nobody has opened it for a while it takes about half
a minute to wake up).

Numbers in this file come from the run of 21 October 2026, with HICP up to September 2026.

## Running it

Python 3.13.

```bash
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard/app.py
```

`data/silver` and `data/gold` are committed, so the dashboard opens straight away without downloading
anything. Run it from the repo root, where `.streamlit/config.toml` sets the light theme. To pull fresh data
and rebuild everything:

```bash
python -m src all
pytest
```

`all` takes a few minutes. Most of it is the backtest, about a minute and a half on 10 cores. It stops before
any modelling if a data check or a validation gate fails. The steps can also be run one at a time:

- `python -m src data` downloads Eurostat and the external series, builds the silver tables and runs the data
  checks. `--refresh` ignores files already fetched today, `--no-external` pulls Eurostat only.
- `python -m src validate` rebuilds the euro area index from its parts and compares it with Eurostat.
- `python -m src qa` writes `reports/qa_findings.md` (breaks, seasonality, fuel taxes).
- `python -m src backtest` runs every model in the real-time backtest. `--no-ablations` skips the runs
  without each source.
- `python -m src evaluate` scores the backtest and picks the model.
- `python -m src forecast` makes the forecast for the next three months.
- `python -m src passthrough` estimates how oil, gas and energy feed into each group.
- `python -m src shocks` runs the shock presets.

The tests (33, no network needed) cover the real-time snapshots and the shock engine.

## Data

From Eurostat, all in the new ECOICOP ver.2 tables. The old ones (`prc_hicp_midx`, `prc_hicp_inw`,
`prc_hicp_cow`) stop in December 2025.

- `prc_hicp_minr`: monthly indices, 2025 = 100, for the euro area and its 21 countries
- `prc_hicp_iw` and `prc_hicp_cw`: item weights and country weights
- `prc_hicp_ctr`: Eurostat's own contributions to the euro area rate
- `prc_hicp_fpd`: flash and final releases
- `ei_bsrt_m_r2`, `ei_bsse_m_r2`, `ei_bsin_m_r2`: selling price expectations in retail, services and industry

The forecast also uses Brent (FRED), EUR/USD (ECB), European natural gas (FRED, monthly and about two months
late) and pump prices from the European Commission's Weekly Oil Bulletin.

Data goes through three folders. `data/bronze` keeps every raw response as it came back, with a new copy only
when the content changes (SHA-256) and a fetch log. If an API is down the run falls back to the last copy.
Bronze isn't committed, it is rebuilt by `python -m src data`. `data/silver` has the tidy monthly tables and
`data/gold` the model outputs.

## Checks

The data step runs 17 checks (no gaps or duplicates, weights adding up to 1000, every series reaching the
latest month and so on, see `reports/data_quality.md`). The euro area changes composition, so one of them
checks each year's country weights against who was in the euro that year: 11 countries in 1999, 12 from 2001,
up to 21 in 2026 with Bulgaria.

Then the euro area index is rebuilt with Eurostat's chain-linking, each component against its own December with
that year's weights (and, from the country indices, that year's members), and compared with the official annual
rate:

| euro area rebuilt from | months | largest gap, pp |
|---|---|---|
| the 6 main groups | 298 | 0.030 |
| the 13 COICOP divisions | 346 | 0.019 |
| the 21 country indices | 346 | 0.038 |
| groups within each country | 298 | 0.032 |
| divisions within each country | 346 | 0.026 |
| group contributions, against Eurostat's | 297 | 0.009 |

The limit is 0.05 pp (0.02 for contributions). What is left is rounding, since the published indices have two
decimals. The same chain-linking code is used by the forecast and the shock engine.

A few things the checks turned up, more in `reports/qa_findings.md`:

- Headline rates aren't revised after the final release. All 321 months since 2000 match today's figures, so
  scoring a backtest against today's data is fair.
- Pump prices from the Oil Bulletin explain 97% of the monthly moves in HICP fuels since 2006.
- Germany cut fuel tax by about 17 cents a litre in the week of 5 October and Spain cut petrol tax too. Pump
  prices in early October were down 1.7% while Brent was up 14%.
- Easter moves about 0.5 pp of services inflation between March and April, so the regressions have an Easter term.

## Forecast

Three months out, the only unknowns in the annual rate are the new monthly changes, because the year-ago months
that drop out are already known. So the models forecast monthly changes and chain them back into the annual
rate.

Six models, simplest first: no change, seasonal (the median change of the same month over the last five years),
a direct regression on the headline, a bottom-up regression per group (6 groups chained with this year's
weights), the average of those two, and the bottom-up model with a ridge penalty on lags of all six groups plus
oil, pump prices, gas, surveys and Easter. The rule for picking one was set before running the backtest: lowest
RMSE averaged over the three horizons, and a simpler model within 2% of the best one wins.

The backtest is real time. For each month from 2012 the forecast is made on the day the HICP came out (the 20th
of the next month, end of February for January) and only sees what was published by then, with a release lag
for each external series. A test feeds the snapshot poisoned future data to make sure none of it gets through.
Scores below are on the 138 forecasts from 2015 to 2026.

| RMSE, pp | 1 month | 2 months | 3 months |
|---|---|---|---|
| No change | 0.42 | 0.68 | 0.92 |
| Direct regression | 0.27 | 0.51 | 0.71 |
| Bottom-up | 0.25 | 0.47 | 0.64 |
| Bottom-up ridge (chosen) | 0.25 | 0.43 | 0.59 |

The chosen model has about 40% less error than no change, and the Diebold-Mariano test rejects equal accuracy
at every horizon (p < 0.01). Against the plain bottom-up model the difference is not significant. When the rule
only sees 2015-19 it still picks the ridge model, and the ridge model still comes first on the 78 forecasts
after that.
Leaving out the surveys raises its error by 11%, leaving out pump prices by 8%. Gas doesn't help.

The bands come from the model's own past errors. Outside 2021-23 the 90% band caught 88 to 94% of outcomes,
during the surge only 56 to 67%.

The forecast made on 20 October 2026:

| month | annual rate | 90% band |
|---|---|---|
| October 2026 | 3.85% | 3.5 to 4.2 |
| November 2026 | 3.88% | 3.4 to 4.6 |
| December 2026 | 3.98% | 3.3 to 4.9 |

So Q4 averages 3.90%. The ECB's September projection has 3.6% with oil at about $88, while Brent averaged
$127 in the first half of October. With Brent at $90 the same model gives 3.67%, and it needs Brent near $81
to land on 3.6%, so most of the gap is oil.

Details in `reports/forecast_evaluation.md` and `reports/forecast.md`.

## Shocks

A shock is a change in the price level of any groups (the 6 main ones or the 13 COICOP divisions) in any set
of countries, from a given month, and it can stay, fade or build up. The direct effect on the euro area rate
goes through each country's and group's weight with the December chain-linking, so it is exact. The tests
check it against a full rebuild of the index.

Oil and gas shocks pass through to fuels and to electricity and gas with responses estimated by local
projections. The energy move then feeds food, goods and services over the following year. Brent up 10% for
good lifts the all-items price level by about 0.3% after a year, or 0.4% with 2020-23 in the estimation. The
second round is where the period matters most: processed food moves 0.06% for 1% on energy without 2020-23
and 0.17% with it. The dashboard lets you choose between the two.

The presets, as the change in the 2027 average annual rate (pp):

| preset | normal times | second round as in 2022 |
|---|---|---|
| Brent back to $90 | -0.78 | -0.99 |
| Brent up 20% | +0.41 | +0.51 |
| Wholesale gas up 50% | +0.13 | +0.25 |
| Germany ends its fuel tax cut in January 2027 | +0.09 | +0.11 |
| Food up 5% in Germany and France | +0.27 | +0.27 |

The German preset is sized from the Oil Bulletin: 16.7 cents a litre on a pump price of 2.24 EUR. More in
`reports/passthrough.md` and `reports/shocks.md`.

## Dashboard

Four tabs:

- Today: the latest rates, what each group adds to the headline, and a heatmap by country and group.
- Outlook: the forecast with its bands, a Brent slider that reruns it, how December is built from the base
  effect and the new months, and the backtest scores.
- What if: the shock simulator, with the presets above and a CSV download.
- How it's built: the checks, the data vintages, the formulas and the limits.

## Layout

```
src/
  sources/      Eurostat, FRED, ECB and Oil Bulletin downloads, with retries and the bronze cache
  silver.py     tidy tables and the data checks
  chain.py      chain-linking, annual and monthly rates, contributions
  validate.py   the rebuild checks
  report.py     reports/data_quality.md
  qa.py         reports/qa_findings.md and its figures
  forecast/     real-time snapshots, features, one file per model, backtest, evaluation, live forecast
  shocks/       pass-through, the shock engine, presets
  config.py     every setting in one place
  cli.py        python -m src <command>
dashboard/      the Streamlit app, one file per tab
tests/          real-time snapshots and the shock engine
reports/        written by the pipeline, with figures
slides/         the five slides, PPTX and PDF
```

## Limits

- The bands come from past errors, so they were far too narrow in 2021-23 and would be again in a sudden shift.
- No spillover between countries, and next year's weights are taken equal to this year's.
- National flash CPIs, oil futures and inflation swaps aren't used. Without the flash CPIs the model probably
  trails the consensus one month ahead.
- For October the model has fuels at +0.1% while pump prices alone say -1.7%, a gap worth about 0.1 pp
  on the headline. The October flash will show which one was closer.
- Gas prices arrive about two months late, which may be why they don't help.
