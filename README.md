# NHS England A&E and RTT Waiting Times — Analysis & Dashboard

![NHS waiting times dashboard](assets/dashboard.png)

An end-to-end data project on **NHS England's published A&E and Referral-to-Treatment
(RTT) waiting time statistics**. It ingests the raw NHS files into SQLite, runs
SQL + statistical analysis (seasonal decomposition, Mann-Kendall trend test,
correlation), and serves an interactive **Plotly Dash** dashboard.

> *Analysed 5+ years of NHS England A&E and RTT waiting-time data across 237 trusts
> using Python and SQL, identifying a statistically significant decline in 4-hour
> performance (Mann-Kendall p < 0.001) and a positive trust-level correlation
> between emergency-flow and elective-waiting performance — deployed as an
> interactive Plotly Dash dashboard.*

---

## What's in it

| Layer | Tool | File |
|---|---|---|
| Ingestion | `requests` + `BeautifulSoup` | `scrape_nhs_data.py` (download raw files) |
| Storage | SQLite | `src/database.py`, `src/ingest.py` |
| Analysis | SQL + `pandas` | `src/analysis.py` |
| Statistics | `statsmodels`, `scipy`, `numpy` | `src/stats.py` |
| Visualisation | Plotly | `src/charts.py` |
| Dashboard | Dash | `app.py` |

**Data loaded:** 12,403 trust-month A&E rows (237 trusts, 60 months, Apr 2020–Mar 2025),
187 months of national A&E time series (Aug 2010–Feb 2026), and 141,504 RTT
incomplete-pathway rows (36 months, by provider × specialty).

---

## Dashboard pages

1. **National overview** — 4-hour performance vs the 95% target with the COVID
   period shaded, attendance volumes, and headline KPI cards.
2. **Trends & statistics** — seasonal decomposition of the performance series,
   pre-COVID attendance seasonality, a pre/during/post-COVID comparison table,
   and the Mann-Kendall trend-test result.
3. **Trust explorer** — pick any trust; see its Type-1 performance vs the national
   line, monthly attendance volume, a 12-month data table, and the 15
   lowest-performing trusts.
4. **Regional** — a region × month heatmap and a latest-month ranking of the seven
   NHS England regions.
5. **RTT specialties** — national waiting-list size vs 18-week compliance, the worst
   specialties by 18-week breach, and a multi-select specialty trend explorer.
6. **A&E ↔ RTT correlation** — trust-level scatter of A&E 4-hour vs RTT 18-week
   performance with a fitted line and Pearson r / p-value.

---

## Quick start

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (optional) download the raw NHS files — already present in data/raw/
python scrape_nhs_data.py

# 3. build the SQLite database from the raw files
python -m src.ingest            # add --no-rtt for a faster A&E-only build

# 4. run the dashboard
python app.py                   # http://127.0.0.1:8050
```

---

## Key findings

- **4-hour A&E performance** fell from ~84% (2019) to the **low-to-mid 70s%** by
  2024–25 — a decline the **Mann-Kendall test confirms as statistically significant
  (z ≈ −10, p < 0.001)**, with Sen's slope ≈ −0.19 percentage points per month.
- **COVID-19** crashed April 2020 attendances by ~55% (to ~0.9m); performance
  briefly *rose* on the reduced footfall before deteriorating as activity returned.
- **Seasonality:** attendances peak in summer; winter brings the sharpest
  performance dips (the classic "winter pressures").
- **RTT backlog:** in the latest month several specialties — ENT, oral surgery,
  trauma & orthopaedics, gynaecology — have **only ~50% of patients seen within 18
  weeks**.
- **Cross-dataset:** across 124 trusts, A&E 4-hour and RTT 18-week performance are
  **positively correlated (r ≈ 0.37, p < 0.001)** — trusts that struggle on
  emergency flow tend to struggle on elective waits too.

*(Exact figures refresh automatically from whatever data is in the database.)*

---

## Deployment

The app exposes a gunicorn entrypoint (`app:server`) and ships with a `Procfile`,
so it deploys as-is to Render, Railway, or any Heroku-style host:

```bash
gunicorn app:server --bind 0.0.0.0:$PORT
```

Because the raw NHS files are large (the RTT set is ~360 MB) they are **git-ignored**.
For a hosted deploy, commit a pre-built `data/nhs_waiting.db` (a few MB) or run
`python -m src.ingest` as a build step.

---

## Project structure

```
nhs-waiting-times/
├── app.py                  Dash dashboard (gunicorn entrypoint: app:server)
├── scrape_nhs_data.py      Download raw A&E + RTT files from NHS England
├── src/
│   ├── database.py         SQLite schema + connection
│   ├── ingest.py           Parse raw files -> SQLite
│   ├── analysis.py         SQL-backed analysis functions
│   ├── stats.py            Mann-Kendall, seasonal decomposition, Pearson
│   └── charts.py           Plotly figure factories
├── notebooks/
│   └── analysis.ipynb      SQL + statistical walkthrough
├── assets/style.css        Dashboard styling (NHS palette)
├── data/raw/               Raw NHS files (git-ignored)
├── requirements.txt
└── Procfile
```

---

*Data source: [NHS England A&E waiting times](https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/)
and [RTT waiting times](https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/).
This project is for analysis/portfolio purposes and is not affiliated with NHS England.*
