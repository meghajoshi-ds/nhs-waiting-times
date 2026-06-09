"""
SQL-backed analysis functions. Each returns a tidy pandas DataFrame ready for
plotting. These are the queries referenced in the project README / notebooks.
"""

import pandas as pd

from . import database


def _q(sql, params=None):
    conn = database.connect()
    try:
        return pd.read_sql(sql, conn, params=params or {})
    finally:
        conn.close()


# ── National ──────────────────────────────────────────────────────────────────
def national_performance(start="2015-01-01"):
    """National monthly 4-hour performance + attendances from the time series."""
    df = _q(
        """SELECT period, att_total, att_type1, pct_within_4hrs
           FROM ae_national WHERE period >= :start ORDER BY period""",
        {"start": start})
    df["period"] = pd.to_datetime(df["period"])
    return df


def kpi_cards():
    """Headline numbers for the overview page (latest month + YoY change)."""
    df = national_performance("2010-01-01").dropna(subset=["pct_within_4hrs"])
    latest = df.iloc[-1]
    year_ago = df[df["period"] == latest["period"] - pd.DateOffset(years=1)]
    yoy = (latest["pct_within_4hrs"] - year_ago["pct_within_4hrs"].iloc[0]
           if len(year_ago) else None)
    best = df.loc[df["pct_within_4hrs"].idxmax()]
    worst = df.loc[df["pct_within_4hrs"].idxmin()]
    return {
        "latest_period": latest["period"].strftime("%B %Y"),
        "latest_pct": latest["pct_within_4hrs"],
        "latest_att": latest["att_total"],
        "yoy": yoy,
        "best": (best["period"].strftime("%b %Y"), best["pct_within_4hrs"]),
        "worst": (worst["period"].strftime("%b %Y"), worst["pct_within_4hrs"]),
    }


def seasonal_index():
    """Average attendances by calendar month (seasonality fingerprint)."""
    df = _q("""SELECT CAST(STRFTIME('%m', period) AS INTEGER) AS month,
                      AVG(att_total) AS avg_att
               FROM ae_national WHERE period >= '2015-01-01'
                 AND period < '2020-01-01'
               GROUP BY month ORDER BY month""")
    df["month_name"] = pd.to_datetime(df["month"], format="%m").dt.strftime("%b")
    df["index"] = 100 * df["avg_att"] / df["avg_att"].mean()
    return df


def covid_comparison():
    """Pre / during / post-COVID averages of performance and attendances."""
    return _q("""
        SELECT CASE
                 WHEN period < '2020-03-01' THEN '1 Pre-COVID'
                 WHEN period <= '2021-06-01' THEN '2 During COVID'
                 ELSE '3 Post-COVID' END AS phase,
               ROUND(AVG(pct_within_4hrs), 1) AS avg_4hr_performance,
               ROUND(AVG(att_total))          AS avg_monthly_attendances
        FROM ae_national
        WHERE period >= '2017-01-01'
        GROUP BY phase ORDER BY phase""")


# ── Trust level ───────────────────────────────────────────────────────────────
def trust_list():
    """All trusts that report Type 1 activity, alphabetical."""
    df = _q("""SELECT DISTINCT org_name FROM ae_monthly
               WHERE org_name IS NOT NULL AND att_type1 > 0
               ORDER BY org_name""")
    return df["org_name"].tolist()


def trust_timeseries(org_name):
    """One trust's monthly Type-1 performance and attendances."""
    df = _q("""SELECT period, att_type1, pct_within_4hrs_t1, emergency_admissions
               FROM ae_monthly WHERE org_name = :name AND att_type1 > 0
               ORDER BY period""", {"name": org_name})
    df["period"] = pd.to_datetime(df["period"])
    return df


def national_type1_monthly():
    """National Type-1 performance built up from trust rows (for trust compare)."""
    df = _q("""SELECT period,
                      100.0*SUM(att_type1 - over4hr_type1)/SUM(att_type1) AS pct
               FROM ae_monthly WHERE att_type1 > 0
               GROUP BY period ORDER BY period""")
    df["period"] = pd.to_datetime(df["period"])
    return df


def worst_trusts(months=12, min_reports=10, limit=15):
    """Bottom trusts by average Type-1 performance over the latest N months."""
    return _q("""
        WITH latest AS (
            SELECT DISTINCT period FROM ae_monthly ORDER BY period DESC LIMIT :months)
        SELECT org_name,
               ROUND(AVG(pct_within_4hrs_t1), 1) AS avg_performance,
               ROUND(AVG(att_type1))             AS avg_type1_attendances,
               COUNT(*)                          AS months_reported
        FROM ae_monthly
        WHERE period IN (SELECT period FROM latest) AND att_type1 > 0
        GROUP BY org_name HAVING months_reported >= :min_reports
        ORDER BY avg_performance ASC LIMIT :limit""",
        {"months": months, "min_reports": min_reports, "limit": limit})


# ── Regional ──────────────────────────────────────────────────────────────────
def regional_heatmap():
    """Region x month matrix of Type-1 4-hour performance (last 24 months)."""
    df = _q("""
        WITH latest AS (
            SELECT DISTINCT period FROM ae_monthly ORDER BY period DESC LIMIT 24)
        SELECT period, region,
               100.0*SUM(att_type1 - over4hr_type1)/SUM(att_type1) AS pct
        FROM ae_monthly
        WHERE region IS NOT NULL AND att_type1 > 0
          AND period IN (SELECT period FROM latest)
        GROUP BY period, region ORDER BY period""")
    df["period"] = pd.to_datetime(df["period"])
    return df


# ── RTT ───────────────────────────────────────────────────────────────────────
def rtt_specialty_latest(limit=12):
    """Worst specialties in the latest RTT month by median wait + % > 18 weeks."""
    latest = _q("SELECT MAX(period) AS p FROM rtt_monthly")["p"].iloc[0]
    df = _q("""
        SELECT treatment_function,
               SUM(total_waiting) AS waiting,
               ROUND(100.0*SUM(within_18wk)/SUM(total_waiting), 1) AS pct_within_18wk,
               ROUND(100.0*SUM(over_52wk)/SUM(total_waiting), 1)   AS pct_over_52wk
        FROM rtt_monthly WHERE period = :p AND treatment_function != 'Total'
        GROUP BY treatment_function
        HAVING waiting > 20000
        ORDER BY pct_within_18wk ASC LIMIT :limit""",
        {"p": latest, "limit": limit})
    df["pct_over_18wk"] = (100 - df["pct_within_18wk"]).round(1)
    df["latest_period"] = pd.to_datetime(latest).strftime("%B %Y")
    return df


def rtt_specialty_trend(specialties=None):
    """% waiting over 18 weeks over time, by specialty (national)."""
    df = _q("""
        SELECT period, treatment_function,
               100.0*(SUM(total_waiting)-SUM(within_18wk))/SUM(total_waiting) AS pct_over_18wk,
               SUM(total_waiting) AS waiting
        FROM rtt_monthly WHERE treatment_function != 'Total'
        GROUP BY period, treatment_function ORDER BY period""")
    df["period"] = pd.to_datetime(df["period"])
    if specialties:
        df = df[df["treatment_function"].isin(specialties)]
    return df


def rtt_specialties():
    """List of treatment functions with meaningful volume, for dropdowns."""
    df = _q("""SELECT treatment_function, SUM(total_waiting) tot
               FROM rtt_monthly WHERE treatment_function != 'Total'
               GROUP BY treatment_function HAVING tot > 100000
               ORDER BY tot DESC""")
    return df["treatment_function"].tolist()


def rtt_national_trend():
    """National total waiting list size and 18-week compliance over time."""
    df = _q("""
        SELECT period, SUM(total_waiting) AS total_waiting,
               100.0*SUM(within_18wk)/SUM(total_waiting) AS pct_within_18wk
        FROM rtt_monthly WHERE treatment_function != 'Total'
        GROUP BY period ORDER BY period""")
    df["period"] = pd.to_datetime(df["period"])
    return df


# ── Scotland (Public Health Scotland A&E) ─────────────────────────────────────
def scotland_national(start="2012-01-01"):
    """Scotland-wide monthly A&E performance, aggregated across health boards."""
    df = _q("""SELECT period,
                      SUM(att_total) AS att_total,
                      100.0*SUM(within4hr_total)/SUM(att_total) AS pct_within_4hrs,
                      100.0*SUM(within4hr_type1)/SUM(att_type1) AS pct_within_4hrs_t1,
                      SUM(over12hr_total) AS over12hr
               FROM scotland_ae_monthly WHERE period >= :s
               GROUP BY period ORDER BY period""", {"s": start})
    df["period"] = pd.to_datetime(df["period"])
    return df


def scotland_kpis():
    df = scotland_national("2007-01-01").dropna(subset=["pct_within_4hrs"])
    latest = df.iloc[-1]
    year_ago = df[df["period"] == latest["period"] - pd.DateOffset(years=1)]
    yoy = (latest["pct_within_4hrs"] - year_ago["pct_within_4hrs"].iloc[0]
           if len(year_ago) else None)
    rank = scotland_board_ranking()
    return {
        "latest_period": latest["period"].strftime("%B %Y"),
        "latest_pct": latest["pct_within_4hrs"],
        "latest_att": latest["att_total"],
        "yoy": yoy,
        "best_board": (rank.iloc[0]["hb_name"], rank.iloc[0]["avg_performance"]),
        "worst_board": (rank.iloc[-1]["hb_name"], rank.iloc[-1]["avg_performance"]),
        "n_boards": len(rank),
    }


def scotland_board_list():
    df = _q("""SELECT DISTINCT hb_name FROM scotland_ae_monthly
               WHERE hb_name IS NOT NULL ORDER BY hb_name""")
    return df["hb_name"].tolist()


def scotland_board_timeseries(hb_name):
    df = _q("""SELECT period, att_total, pct_within_4hrs, pct_within_4hrs_t1
               FROM scotland_ae_monthly WHERE hb_name = :n AND att_total > 0
               ORDER BY period""", {"n": hb_name})
    df["period"] = pd.to_datetime(df["period"])
    return df


def scotland_board_ranking(months=12):
    """Average all-type 4-hour performance by board over the latest N months."""
    df = _q("""
        WITH latest AS (
            SELECT DISTINCT period FROM scotland_ae_monthly
            ORDER BY period DESC LIMIT :months)
        SELECT hb_name,
               ROUND(100.0*SUM(within4hr_total)/SUM(att_total), 1) AS avg_performance,
               ROUND(AVG(att_total))                               AS avg_attendances
        FROM scotland_ae_monthly
        WHERE period IN (SELECT period FROM latest) AND att_total > 0
        GROUP BY hb_name ORDER BY avg_performance DESC""", {"months": months})
    return df


def scotland_board_heatmap(months=24):
    df = _q("""
        WITH latest AS (
            SELECT DISTINCT period FROM scotland_ae_monthly
            ORDER BY period DESC LIMIT :months)
        SELECT period, hb_name, pct_within_4hrs AS pct
        FROM scotland_ae_monthly
        WHERE period IN (SELECT period FROM latest) AND att_total > 0
        ORDER BY period""", {"months": months})
    df["period"] = pd.to_datetime(df["period"])
    return df


def nations_comparison(start="2012-01-01"):
    """England vs Scotland national all-type 4-hour performance, aligned monthly."""
    eng = _q("""SELECT period, pct_within_4hrs AS england
                FROM ae_national WHERE period >= :s""", {"s": start})
    sco = _q("""SELECT period,
                       100.0*SUM(within4hr_total)/SUM(att_total) AS scotland
                FROM scotland_ae_monthly WHERE period >= :s
                GROUP BY period""", {"s": start})
    df = eng.merge(sco, on="period", how="inner")
    df["period"] = pd.to_datetime(df["period"])
    return df.sort_values("period")


# ── Cross-dataset correlation ─────────────────────────────────────────────────
def admission_vs_rtt():
    """
    Trust-level join: A&E emergency-admission rate vs RTT 18-week performance,
    averaged over the overlapping period. One row per trust.
    """
    return _q("""
        WITH ae AS (
            SELECT org_code,
                   MAX(org_name) AS org_name,
                   AVG(100.0*emergency_admissions/NULLIF(att_total,0)) AS admit_rate,
                   AVG(pct_within_4hrs_t1) AS ae_perf
            FROM ae_monthly WHERE period >= '2023-01-01' AND att_type1 > 0
            GROUP BY org_code),
        rtt AS (
            SELECT provider_code,
                   100.0*SUM(within_18wk)/SUM(total_waiting) AS rtt_perf,
                   SUM(total_waiting) AS waiting
            FROM rtt_monthly WHERE period >= '2023-01-01'
              AND treatment_function != 'Total'
            GROUP BY provider_code)
        SELECT ae.org_name, ae.admit_rate, ae.ae_perf, rtt.rtt_perf, rtt.waiting
        FROM ae JOIN rtt ON ae.org_code = rtt.provider_code
        WHERE ae.admit_rate IS NOT NULL AND rtt.rtt_perf IS NOT NULL
          AND rtt.waiting > 20000""")
