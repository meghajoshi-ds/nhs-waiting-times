# CLAUDE.md — NHS Waiting Times Analysis

## Project overview

An end-to-end data analysis and visualisation project using NHS England's publicly published A&E and referral-to-treatment (RTT) waiting time data. Covers data ingestion, SQL-based analysis, statistical modelling of trends, and an interactive Plotly Dash dashboard. Demonstrates real UK domain knowledge and strong analyst fundamentals.

**Target roles:** Data Analyst, Business Analyst, BI Analyst  
**Salary signal:** £25k–£35k UK mid-market, public sector, healthcare analytics, consultancy  
**Resume headline:** *"Analysed 5 years of NHS England A&E and RTT waiting time data using Python and SQL, identifying seasonal patterns and regional variation, deployed as an interactive Plotly Dash dashboard"*

---

## Dataset

- **Primary:** NHS England A&E Attendances and Emergency Admissions
  - URL: https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/
  - Monthly CSV files dating back to 2010
  - Columns: period, org_code, org_name, type_1_attendances, type_1_4hr_performance, admissions, etc.

- **Secondary:** NHS England Referral to Treatment (RTT) Waiting Times
  - URL: https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/
  - 18-week standard performance by trust and specialty

- **Why:** Real NHS data, publicly available, directly relevant to public sector and healthcare analytics roles in the UK. Shows awareness of UK-specific policy context (the 4-hour A&E target, 18-week RTT standard).

---

## Analysis questions to answer

1. How has A&E 4-hour performance changed nationally from 2019 to 2024?
2. Which NHS trusts consistently underperform vs the 95% 4-hour target?
3. What seasonal patterns exist in A&E attendance volumes?
4. How did COVID-19 (2020–2021) affect attendance and performance metrics?
5. Which specialties have the longest RTT waits, and has this worsened post-pandemic?
6. Is there a correlation between A&E admission rate and RTT performance at trust level?

---

## Tech stack

| Layer | Tool | Purpose |
|---|---|---|
| Data ingestion | Python `requests` + `pandas` | Download and parse NHS CSVs |
| Storage | SQLite (local) or PostgreSQL | Structured query layer |
| Analysis | Python, SQL, `pandas`, `scipy` | EDA, trend analysis, stats tests |
| Visualisation | Plotly + Dash | Interactive dashboard |
| Statistical modelling | `statsmodels` | Time series decomposition, trend detection |
| Deployment | Render.com or Railway (free tier) | Public dashboard link for CV |
| Version control | Git + GitHub | All code and notebooks |

---

## SQL analysis — key queries to include

### 1. National 4-hour performance trend
```sql
SELECT
  period,
  SUM(type_1_attendances) AS total_attendances,
  SUM(type_1_4hr_attendances) AS within_4hrs,
  ROUND(100.0 * SUM(type_1_4hr_attendances) / SUM(type_1_attendances), 1) AS pct_within_4hrs
FROM ae_monthly
WHERE type = 'Type 1'
GROUP BY period
ORDER BY period;
```

### 2. Bottom 10 trusts by 4-hour performance (latest 12 months)
```sql
SELECT
  org_name,
  AVG(pct_within_4hrs) AS avg_performance,
  COUNT(*) AS months_reported
FROM ae_monthly
WHERE period >= DATE('now', '-12 months')
GROUP BY org_name
HAVING months_reported >= 10
ORDER BY avg_performance ASC
LIMIT 10;
```

### 3. Seasonal index by month
```sql
SELECT
  STRFTIME('%m', period) AS month,
  AVG(type_1_attendances) AS avg_attendances
FROM ae_monthly
GROUP BY month
ORDER BY month;
```

### 4. Pre/post COVID comparison
```sql
SELECT
  CASE
    WHEN period < '2020-03-01' THEN 'Pre-COVID'
    WHEN period BETWEEN '2020-03-01' AND '2021-06-30' THEN 'During COVID'
    ELSE 'Post-COVID'
  END AS period_group,
  AVG(pct_within_4hrs) AS avg_4hr_performance,
  AVG(type_1_attendances) AS avg_monthly_attendances
FROM ae_monthly
GROUP BY period_group;
```

---

## Statistical analysis

### Time series decomposition
- Use `statsmodels.tsa.seasonal.seasonal_decompose` on national monthly attendance
- Extract trend, seasonal, and residual components
- Plot all three components — shows methodology in notebook

### Mann-Kendall trend test
- Apply to 4-hour performance time series
- Test whether decline in performance is statistically significant
- Report: test statistic, p-value, trend direction

### Correlation analysis
- Pearson correlation between A&E admission rate and RTT 18-week performance at trust level
- Hypothesis: trusts with higher A&E admission rates tend to have worse RTT performance
- Plot scatter with trust labels, add regression line

---

## Plotly Dash dashboard — pages spec

### Page 1: National overview
- Line chart: monthly 4-hour performance 2019–2024 with target line at 95%
- Shaded region marking COVID period (March 2020 – June 2021)
- KPI cards: current performance %, YoY change, best/worst month

### Page 2: Trust-level explorer
- Dropdown: select NHS trust
- Line chart: selected trust's 4-hour performance vs national average
- Bar chart: attendance volume by month
- Data table: last 12 months raw data

### Page 3: Regional heatmap
- Choropleth map of England by NHS region — colour = average 4-hour performance
- Slider: select year
- Click region to drill into trust list

### Page 4: RTT waiting times
- Bar chart: top 10 specialties by median wait (weeks)
- Line chart: % waiting > 18 weeks over time by specialty
- Slicer: trust, specialty, time range

---

## Project folder structure

```
nhs-waiting-times/
├── CLAUDE.md
├── README.md
├── app.py                       ← Dash app entry point
├── src/
│   ├── ingest.py                ← Download and parse NHS CSVs
│   ├── database.py              ← SQLite schema + load functions
│   ├── analysis.py              ← SQL queries + pandas analysis
│   ├── stats.py                 ← Trend tests, decomposition
│   └── charts.py                ← Plotly figure factories
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_sql_analysis.ipynb
│   └── 03_statistical_modelling.ipynb
├── data/
│   ├── raw/                     ← Downloaded NHS CSVs
│   └── nhs_waiting.db           ← SQLite database
├── assets/
│   └── style.css                ← Dash custom styles
└── requirements.txt
```

---

## Implementation steps

1. **Data collection** — write `ingest.py` to download all monthly A&E and RTT CSVs programmatically
2. **Database setup** — create SQLite schema, load all CSVs into tables with consistent column names
3. **EDA notebook** — shape, nulls, date ranges, trust counts, basic summary stats
4. **SQL analysis notebook** — run all key queries, export results to dataframes for plotting
5. **Statistical analysis** — time series decomposition, Mann-Kendall test, correlation analysis
6. **Build Dash app** — layout, callbacks for interactivity, responsive charts
7. **Regional map** — source NHS England region shapefiles or GeoJSON for choropleth
8. **Deploy** — push to GitHub, deploy on Render.com free tier, add live URL to README
9. **Write README** — key findings summary, methodology, setup instructions, screenshots

---

## Key findings to highlight in README (expected)

- National 4-hour performance dropped from ~85% in 2019 to ~55–60% in 2023–2024
- Clear seasonal pattern: attendance peaks in winter (Dec–Jan), performance dips correspondingly
- COVID period shows attendance drop of ~25% in April 2020 but performance paradoxically improved briefly due to reduced footfall, then collapsed
- Post-COVID RTT backlog: several specialties (orthopaedics, ophthalmology) show >40% of patients waiting beyond 18 weeks

---

## Resume bullet points (use these)

- Analysed 5 years of NHS England A&E and RTT waiting time data across 200+ trusts using Python and SQL, identifying a statistically significant decline in 4-hour performance (Mann-Kendall p < 0.001)
- Built a seasonal decomposition model revealing consistent winter demand spikes and quantified the COVID-19 impact on attendance volumes and performance metrics
- Deployed an interactive Plotly Dash dashboard with trust-level drill-down, regional choropleth map, and RTT specialty explorer — publicly accessible via Render
- Demonstrated UK healthcare domain knowledge and awareness of NHS operational targets (4-hour A&E standard, 18-week RTT) relevant to public sector and health analytics roles

---

## Stretch goals (add if time allows)

- Add Prophet forecasting for next 12 months of attendance volumes
- Scrape and join NHS workforce data (vacancy rates by trust) to test staffing correlation
- Add a "trust comparison" feature — select two trusts and compare head to head
- Export filtered data to CSV/Excel from the dashboard
