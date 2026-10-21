# Data quality

Built 2026-10-20T22:05:41+00:00 UTC by 'make data'.

## Checks

| layer | check | result | detail |
|---|---|---|---|
| eurostat | index: no duplicate keys | pass | 0 duplicates |
| eurostat | index: no missing months inside a series | pass | 0 series with gaps |
| eurostat | index: all values positive | pass | 0 non-positive values |
| eurostat | index: every requested series returned data | pass | 506 of 506 present |
| eurostat | index: every series reaches the latest month | pass | latest month 2026-09 |
| eurostat | weights: groups sum to 1000 in every complete year | pass | max deviation 0.08 over 627 geo-years; accepted exceptions: EL 1996 |
| eurostat | weights: divisions sum to 1000 in every complete year | pass | max deviation 0.03 over 679 geo-years |
| eurostat | country weights: sum to 1000 every year | pass | max deviation 0.03 over 31 years |
| eurostat | country weights: members match the euro area of each year | pass | membership correct for every year since 1999 |
| eurostat | codes: every configured code exists in Eurostat's code lists | pass | 45 codes checked |
| eurostat | contributions: available for the latest month | pass | latest 2026-09 |
| eurostat | first releases: final release up to the latest month | pass | 357 months, 1997-01 to 2026-09 |
| eurostat | surveys: all three series reach the latest HICP month | pass | industry_price_expectations 2026-09, retail_price_expectations 2026-09, services_price_expectations 2026-09 |
| external | external: brent_usd available | pass | 9,108 obs to 2026-10-14 |
| external | external: eurusd available | pass | 7,118 obs to 2026-10-20 |
| external | external: gas_eu_usd available | pass | 415 obs to 2026-07-01 |
| external | external: oil bulletin has euro area, DE and ES, with and without tax | pass | 30 geos, weeks to 2026-10-12 |

## Vintages

| source | last update |
|---|---|
| prc_hicp_minr | 2026-10-16 21:00:00+00:00 |
| prc_hicp_iw | 2026-10-16 21:00:00+00:00 |
| prc_hicp_cw | 2026-07-17 09:00:00+00:00 |
| prc_hicp_ctr | 2026-10-16 09:00:00+00:00 |
| prc_hicp_fpd | 2026-10-16 21:00:00+00:00 |
| business_surveys | 2026-09-29 09:00:00+00:00 |
| brent_usd | 2026-10-14 |
| eurusd | 2026-10-20 |
| gas_eu_usd | 2026-07-01 |
| oil_bulletin | 2026-10-12 |

## Accepted issues

- `EL/1996/groups`: Greece's back-calculated 1996 special-aggregate weights sum to 1014.83. Greece joined the euro area in 2001 and 1996 is never used.

## Coverage

Index from: first month with every series. Weights from: first year the weights add up to 1000

| geo | country | total_from | groups_index_from | groups_weights_from | divisions_index_from | divisions_weights_from | in_ea_weights_from | last_month | flagged_obs |
|---|---|---|---|---|---|---|---|---|---|
| EA | Euro area | 1996-01 | 1999-12 | 2001 | 1996-01 | 1996 | - | 2026-09 | 2154 |
| AT | Austria | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| BE | Belgium | 1996-01 | 1998-12 | 1999 | 1999-12 | 1996 | 1996 | 2026-09 | 2172 |
| BG | Bulgaria | 1996-12 | 1996-12 | 1997 | 1999-12 | 1997 | 2026 | 2026-09 | 2178 |
| CY | Cyprus | 1996-01 | 1996-01 | 1996 | 1996-01 | 1996 | 2008 | 2026-09 | 2277 |
| DE | Germany | 1996-01 | 1996-01 | 1996 | 1996-01 | 1996 | 1996 | 2026-09 | 2294 |
| EE | Estonia | 1996-01 | 2000-12 | 2001 | 1997-12 | 1996 | 2011 | 2026-09 | 2031 |
| EL | Greece | 1996-01 | 1996-01 | 1997 | 1996-01 | 1996 | 2001 | 2026-09 | 2277 |
| ES | Spain | 1996-01 | 2000-12 | 2001 | 1996-01 | 1996 | 1996 | 2026-09 | 3360 |
| FI | Finland | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| FR | France | 1996-01 | 1996-01 | 1996 | 1996-01 | 1996 | 1996 | 2026-09 | 5397 |
| HR | Croatia | 1997-12 | 1998-01 | 1998 | 1997-12 | 1998 | 2023 | 2026-09 | 2061 |
| IE | Ireland | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| IT | Italy | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| LT | Lithuania | 1996-01 | 1996-01 | 1996 | 1996-01 | 1996 | 2015 | 2026-09 | 2277 |
| LU | Luxembourg | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| LV | Latvia | 1996-01 | 1997-12 | 1996 | 1996-01 | 1996 | 2014 | 2026-09 | 2231 |
| MT | Malta | 1996-01 | 1996-01 | 1996 | 1996-01 | 1996 | 2008 | 2026-09 | 3117 |
| NL | Netherlands | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2138 |
| PT | Portugal | 1996-01 | 1999-12 | 2000 | 1996-01 | 1996 | 1996 | 2026-09 | 2136 |
| SI | Slovenia | 1996-01 | 2000-12 | 2001 | 1996-01 | 1996 | 2007 | 2026-09 | 1818 |
| SK | Slovakia | 1996-12 | 1996-01 | 1996 | 1996-12 | 1996 | 2009 | 2026-09 | 2277 |

Per series: `series_coverage.csv`.

## Series starting after all-items

| geo | coicop | series | start | total_start |
|---|---|---|---|---|
| AT | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| AT | SERV | Services | 1999-12 | 1996-01 |
| AT | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| BE | CP10 | Education | 1999-12 | 1996-01 |
| BE | IGD_NNRG | Non-energy industrial goods | 1998-12 | 1996-01 |
| BE | SERV | Services | 1998-12 | 1996-01 |
| BE | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1998-12 | 1996-01 |
| BG | CP12 | Insurance and financial services | 1999-12 | 1996-12 |
| EA | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| EA | SERV | Services | 1999-12 | 1996-01 |
| EA | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| EE | CP12 | Insurance and financial services | 1997-12 | 1996-01 |
| EE | ELC_GAS | Electricity, gas and heat | 1997-12 | 1996-01 |
| EE | FUEL | Liquid and transport fuels | 1997-12 | 1996-01 |
| EE | IGD_NNRG | Non-energy industrial goods | 2000-12 | 1996-01 |
| EE | NRG | Energy | 1997-12 | 1996-01 |
| EE | SERV | Services | 2000-12 | 1996-01 |
| EE | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 2000-12 | 1996-01 |
| ES | IGD_NNRG | Non-energy industrial goods | 2000-12 | 1996-01 |
| ES | SERV | Services | 2000-12 | 1996-01 |
| ES | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 2000-12 | 1996-01 |
| FI | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| FI | SERV | Services | 1999-12 | 1996-01 |
| FI | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| HR | ELC_GAS | Electricity, gas and heat | 1998-01 | 1997-12 |
| HR | FOOD | Food, alcohol and tobacco | 1998-01 | 1997-12 |
| HR | FOOD_NP | Unprocessed food | 1998-01 | 1997-12 |
| HR | FOOD_P | Processed food | 1998-01 | 1997-12 |
| HR | FUEL | Liquid and transport fuels | 1998-01 | 1997-12 |
| HR | IGD_NNRG | Non-energy industrial goods | 1998-01 | 1997-12 |
| HR | NRG | Energy | 1998-01 | 1997-12 |
| HR | SERV | Services | 1998-01 | 1997-12 |
| HR | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1998-01 | 1997-12 |
| IE | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| IE | SERV | Services | 1999-12 | 1996-01 |
| IE | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| IT | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| IT | SERV | Services | 1999-12 | 1996-01 |
| IT | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| LU | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| LU | SERV | Services | 1999-12 | 1996-01 |
| LU | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| LV | SERV | Services | 1997-12 | 1996-01 |
| LV | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1997-12 | 1996-01 |
| NL | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| NL | SERV | Services | 1999-12 | 1996-01 |
| NL | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| PT | IGD_NNRG | Non-energy industrial goods | 1999-12 | 1996-01 |
| PT | SERV | Services | 1999-12 | 1996-01 |
| PT | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 1999-12 | 1996-01 |
| SI | ELC_GAS | Electricity, gas and heat | 1999-12 | 1996-01 |
| SI | FOOD | Food, alcohol and tobacco | 1999-12 | 1996-01 |
| SI | FOOD_NP | Unprocessed food | 1999-12 | 1996-01 |
| SI | FOOD_P | Processed food | 1999-12 | 1996-01 |
| SI | FUEL | Liquid and transport fuels | 1999-12 | 1996-01 |
| SI | IGD_NNRG | Non-energy industrial goods | 2000-12 | 1996-01 |
| SI | NRG | Energy | 1999-12 | 1996-01 |
| SI | SERV | Services | 2000-12 | 1996-01 |
| SI | TOT_X_NRG_FOOD | Core (excl. energy, food, alcohol, tobacco) | 2000-12 | 1996-01 |

## Flags

Index: 52,875 of 183,502 observations flagged

| flag | meaning | observations | months | geographies | main series |
|---|---|---|---|---|---|
| d | definition differs | 47420 | 1996-01 to 2016-12 | all 22 | FOOD, FOOD_NP, FOOD_P, ELC_GAS |
| e | estimated | 5220 | 1996-01 to 2016-12 | ES, FR, MT | CP07, CP08, CP09, CP12 |
| b | break in series | 198 | 2017-01 to 2017-01 | all 22 | ELC_GAS, FOOD, FOOD_NP, FOOD_P |
| u | low reliability | 37 | 2020-04 to 2021-05 | DE, EA, NL | CP11, CP03, CP05, CP09 |

### official_rates

| flag | meaning | observations | months | geographies | main series |
|---|---|---|---|---|---|
| d | definition differs | 1902 | 2000-01 to 2017-12 | EA | ELC_GAS, FOOD, FOOD_NP, FOOD_P |
| u | low reliability | 34 | 2020-04 to 2022-05 | EA | CP11, CP03, CP05, CP09 |
| b | break in series | 18 | 2017-01 to 2018-01 | EA | ELC_GAS, FOOD, FOOD_NP, FOOD_P |

### item_weights

| flag | meaning | observations | years | geographies | main series |
|---|---|---|---|---|---|
| d | definition differs | 3948 | 1996 to 2016 | all 22 | FOOD, FOOD_NP, FOOD_P, ELC_GAS |
| e | estimated | 280 | 1996 to 2015 | FR | CP01, CP02, CP03, CP04 |

### first_release

| flag | meaning | observations | months | geographies | main series | release |
|---|---|---|---|---|---|---|
| d | definition differs | 753 | 1997-01 to 2017-12 | EA | NRG, SERV, TOT_X_NRG_FOOD | FIN |
| e | estimated | 36 | 2026-01 to 2026-09 | EA | NRG, SERV, TOTAL, TOT_X_NRG_FOOD | FLS |
| b | break in series | 6 | 2017-01 to 2018-01 | EA | NRG, SERV, TOT_X_NRG_FOOD | FIN |

## Fuel tax per litre, last 6 bulletins (EUR)

With-tax minus without-tax price. EUR = euro area average.

| geo | product | 07 Sep | 14 Sep | 21 Sep | 28 Sep | 05 Oct | 12 Oct | change |
|---|---|---|---|---|---|---|---|---|
| DE | diesel | 1.004 | 1.02 | 1.024 | 1.021 | 0.852 | 0.854 | -0.15 |
| DE | euro95 | 1.175 | 1.179 | 1.178 | 1.177 | 1.013 | 1.016 | -0.159 |
| ES | diesel | 0.491 | 0.497 | 0.512 | 0.515 | 0.512 | 0.507 | 0.016 |
| ES | euro95 | 0.738 | 0.747 | 0.757 | 0.759 | 0.636 | 0.583 | -0.155 |
| EUR | diesel | 0.858 | 0.866 | 0.884 | 0.886 | 0.85 | 0.855 | -0.002 |
| EUR | euro95 | 1.026 | 1.031 | 1.036 | 1.038 | 0.97 | 0.964 | -0.062 |
| FR | diesel | 0.984 | 0.989 | 1.005 | 1.003 | 1 | 0.996 | 0.012 |
| FR | euro95 | 1.043 | 1.052 | 1.06 | 1.059 | 1.059 | 1.059 | 0.016 |
| IT | diesel | 0.919 | 0.928 | 0.984 | 0.997 | 1.033 | 1.077 | 0.158 |
| IT | euro95 | 1.04 | 1.049 | 1.059 | 1.062 | 1.047 | 1.037 | -0.002 |
| NL | diesel | 0.982 | 0.991 | 1.006 | 0.996 | 0.993 | 0.989 | 0.007 |
| NL | euro95 | 1.276 | 1.27 | 1.273 | 1.276 | 1.27 | 1.275 | -0.001 |
