# Niche Alpha: China PMI vs LATAM markets

Does China's factory activity give an early hint about copper and Latin American currencies?

This project matches China's official PMI with COMEX copper and three LATAM currencies
(Chilean peso, Mexican peso, Brazilian real) month by month, tests same-month and
one-month-lead correlations, and presents the results in an interactive Streamlit dashboard.

## Key findings (Nov 2016 – Oct 2026, 118–119 months)

| China indicator | Copper | CLP | MXN | BRL |
|---|---|---|---|---|
| Manufacturing PMI change, same month | −0.14 | −0.03 | −0.19* | −0.17 |
| Manufacturing PMI change, previous month | 0.20* | 0.03 | 0.21* | 0.11 |
| Non-manufacturing PMI change, same month | −0.14 | −0.02 | −0.13 | −0.17 |
| Non-manufacturing PMI change, previous month | 0.16 | 0.04 | 0.22* | 0.13 |

Pearson r between the monthly PMI change and each market's monthly return
(currencies: positive = stronger vs USD). \* p < 0.05, approximate, not adjusted for multiple tests.

- A rise in China's PMI is followed **the next month** by slightly better copper returns and a slightly stronger Mexican peso.
- Same-month links are near zero.
- The Chilean peso shows almost no link (its data is a monthly average rate, which may weaken it).

**Caveat:** these are weak relationships (PMI explains about 4% of next month's moves) and 16 combinations
were tested, so they are hints worth investigating, not trading signals.

## Data sources

| Series | Source |
|---|---|
| China manufacturing and non-manufacturing PMI | National Bureau of Statistics, via [AkShare](https://github.com/akfamily/akshare) |
| COMEX copper futures (HG), month-end close, US cents/lb | Sina Finance, via AkShare |
| MXN, BRL per USD (daily, month-end) | FRED: DEXMXUS, DEXBZUS |
| CLP per USD (monthly average) | FRED: CCUSMA02CLM618N (OECD) |

## Files

| File | Purpose |
|---|---|
| `data_fetcher_v2.py` | Downloads PMI and copper; builds `pmi_copper_matched.csv`. Stops if a download fails (no substituted data). |
| `analyzer_v2.py` | Same-month and one-month-lead correlations; saves `lag_results.csv` and two charts. |
| `latam_heatmap.py` | Adds currencies and non-manufacturing PMI; saves `latam_monthly.csv`, `heatmap_results.csv`, `correlation_heatmap.png`. |
| `app.py` | Streamlit dashboard (reads the saved CSVs; no live data). |

## Run it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt akshare
python data_fetcher_v2.py
python analyzer_v2.py
python latam_heatmap.py
streamlit run app.py
```

## Method notes

- Monthly returns are calculated from month-end values (CLP: monthly average).
- NBS publishes PMI at month-end, so pairing month *t*'s PMI change with month *t+1*'s return uses only information public at the time.
- p-values use a normal approximation.

## Development

Built with AI coding assistance (Claude). Data choices, checks and interpretation by the author.
