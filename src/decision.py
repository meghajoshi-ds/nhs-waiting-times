"""
Decision-support layer on top of the RTT data.

Turns raw waiting numbers into answers to "what should I do with this?":
  - which providers are fastest for a given specialty (and region)
  - how each provider compares to the national average
  - whether a provider is improving or worsening (6 / 12-month trend)
  - the provider's percentile rank
  - estimated weeks saved by switching to a faster provider

All figures are derived from NHS England RTT "incomplete pathways" data;
the headline number is each provider's published *median* wait in weeks.
"""

import pandas as pd

from . import database

# NHS England region codes -> human names (verified against the data via the
# A&E join: see notebooks / README methodology).
REGION_NAMES = {
    "Y56": "London",
    "Y58": "South West",
    "Y59": "South East",
    "Y60": "Midlands",
    "Y61": "East of England",
    "Y62": "North West",
    "Y63": "North East and Yorkshire",
}


def _q(sql, params=None):
    conn = database.connect()
    try:
        return pd.read_sql(sql, conn, params=params or {})
    finally:
        conn.close()


# ── reference helpers ─────────────────────────────────────────────────────────
def periods():
    """Sorted list of available RTT month strings (oldest -> newest)."""
    return _q("""SELECT DISTINCT period FROM rtt_monthly
                 ORDER BY period""")["period"].tolist()


def latest_period():
    return periods()[-1]


def period_offset(months_back):
    """The RTT period `months_back` months before the latest (or None)."""
    ps = periods()
    idx = len(ps) - 1 - months_back
    return ps[idx] if idx >= 0 else None


def last_refresh():
    """Methodology metadata: latest data month + RTT coverage."""
    ps = periods()
    return {
        "latest_month": pd.to_datetime(ps[-1]).strftime("%B %Y"),
        "earliest_month": pd.to_datetime(ps[0]).strftime("%B %Y"),
        "months": len(ps),
    }


# Standing disclaimer shown wherever an estimated wait is presented.
DISCLAIMER = ("Estimated from recent NHS England RTT reporting (median waits). "
              "Actual waits vary by clinical priority, referral and individual "
              "circumstances — use as a guide, not a guarantee.")


def coverage():
    """Above-the-fold trust indicators: how much real data backs the tool."""
    P = latest_period()
    row = _q("""SELECT COUNT(DISTINCT provider_code) AS hospitals,
                       COUNT(DISTINCT treatment_function) AS specialties
                FROM rtt_monthly
                WHERE period = :p AND treatment_function != 'Total'""",
             {"p": P}).iloc[0]
    return {
        "hospitals": int(row["hospitals"]),
        "specialties": int(row["specialties"]),
        "regions": len(REGION_NAMES),
        "latest_month": pd.to_datetime(P).strftime("%B %Y"),
    }


def compare(specialty, name_a, name_b, region="ALL"):
    """
    Head-to-head: weeks saved by switching from the slower to the faster of two
    named providers for a specialty. Returns the faster/slower split and saving.
    """
    df = provider_recommendations(specialty, "ALL")
    if df.empty:
        return None
    df["title"] = df["provider_name"].str.title()
    picks = {}
    for label, name in (("a", name_a), ("b", name_b)):
        m = df[df["title"] == name]
        if not m.empty:
            picks[label] = m.iloc[0]
    if len(picks) < 2:
        return None
    a, b = picks["a"], picks["b"]
    faster, slower = (a, b) if a["median_wait_wks"] <= b["median_wait_wks"] else (b, a)
    return {
        "faster_name": faster["title"], "slower_name": slower["title"],
        "faster_wait": float(faster["median_wait_wks"]),
        "slower_wait": float(slower["median_wait_wks"]),
        "weeks_saved": round(float(slower["median_wait_wks"]
                                   - faster["median_wait_wks"]), 1),
        "faster_dir": faster["direction"], "slower_dir": slower["direction"],
    }


def specialties(min_waiting=100000):
    """Treatment functions with meaningful national volume (for dropdowns)."""
    df = _q("""SELECT treatment_function, SUM(total_waiting) tot
               FROM rtt_monthly
               WHERE period = :p AND treatment_function != 'Total'
               GROUP BY treatment_function HAVING tot > :m
               ORDER BY tot DESC""",
            {"p": latest_period(), "m": min_waiting})
    return df["treatment_function"].tolist()


def regions():
    """Region options as (label, code) including a national 'All' choice."""
    opts = [{"label": "All of England", "value": "ALL"}]
    opts += [{"label": name, "value": code}
             for code, name in sorted(REGION_NAMES.items(), key=lambda x: x[1])]
    return opts


def region_name(code):
    return "England" if code in (None, "ALL") else REGION_NAMES.get(code, code)


# ── core: provider recommendations ────────────────────────────────────────────
def provider_recommendations(specialty, region="ALL", min_waiting=200):
    """
    Ranked table of providers for a specialty, fastest first.

    Columns: provider_name, region, median_wait_wks, total_waiting,
             pct_within_18wk, vs_national_pct, trend_6m, direction, percentile.
    `vs_national_pct` is the % difference from the national patient-weighted
    average median wait (negative = faster than average).
    """
    P = latest_period()
    P6 = period_offset(6)

    cur = _q("""SELECT provider_code, provider_name, region_code,
                       median_wait_wks, total_waiting, pct_within_18wk
                FROM rtt_monthly
                WHERE period = :p AND treatment_function = :s
                  AND median_wait_wks IS NOT NULL AND total_waiting >= :m""",
             {"p": P, "s": specialty, "m": min_waiting})
    if cur.empty:
        return cur

    # national patient-weighted average median (across ALL providers)
    national = (cur["median_wait_wks"] * cur["total_waiting"]).sum() / \
               cur["total_waiting"].sum()

    # percentile across all providers (faster = higher percentile)
    cur["percentile"] = (100 * (1 - cur["median_wait_wks"].rank(method="min",
                         ascending=True) / len(cur))).round(0).clip(0, 99)

    # 6-month trend
    if P6:
        prev = _q("""SELECT provider_code, median_wait_wks AS median_6m
                     FROM rtt_monthly
                     WHERE period = :p AND treatment_function = :s""",
                  {"p": P6, "s": specialty})
        cur = cur.merge(prev, on="provider_code", how="left")
        cur["trend_6m"] = cur["median_wait_wks"] - cur["median_6m"]
    else:
        cur["trend_6m"] = pd.NA

    cur["direction"] = cur["trend_6m"].map(
        lambda d: "improving" if pd.notna(d) and d < -0.5
        else "worsening" if pd.notna(d) and d > 0.5
        else "stable")
    cur["vs_national_pct"] = (100 * (cur["median_wait_wks"] - national)
                              / national).round(0)
    cur["region"] = cur["region_code"].map(REGION_NAMES).fillna(cur["region_code"])
    cur["national_avg"] = round(national, 1)

    if region and region != "ALL":
        cur = cur[cur["region_code"] == region]

    cur = cur.sort_values("median_wait_wks").reset_index(drop=True)
    return cur


def recommendation_summary(specialty, region="ALL"):
    """
    Plain-language decision support for a specialty/region:
    national + regional average, fastest provider, and weeks saved by switching.
    """
    full = provider_recommendations(specialty, "ALL")
    if full.empty:
        return None
    national_avg = float(full["national_avg"].iloc[0])

    scope = full if region in (None, "ALL") else \
        full[full["region_code"] == region]
    if scope.empty:
        scope = full

    fastest = scope.iloc[0]
    scope_avg = (scope["median_wait_wks"] * scope["total_waiting"]).sum() / \
                scope["total_waiting"].sum()
    saved = max(0.0, scope_avg - fastest["median_wait_wks"])

    return {
        "specialty": specialty,
        "region": region_name(region),
        "national_avg": round(national_avg, 1),
        "scope_avg": round(float(scope_avg), 1),
        "fastest_name": fastest["provider_name"].title(),
        "fastest_wait": float(fastest["median_wait_wks"]),
        "weeks_saved": round(float(saved), 1),
        "n_providers": int(len(scope)),
        "fastest_vs_national": int(fastest["vs_national_pct"]),
        "latest_month": pd.to_datetime(latest_period()).strftime("%B %Y"),
    }


def provider_trend(provider_code, specialty):
    """Median-wait time series for one provider + specialty (for sparkline)."""
    df = _q("""SELECT period, median_wait_wks, total_waiting, pct_within_18wk
               FROM rtt_monthly
               WHERE provider_code = :pc AND treatment_function = :s
               ORDER BY period""",
            {"pc": provider_code, "s": specialty})
    df["period"] = pd.to_datetime(df["period"])
    return df


def specialty_national_trend(specialty):
    """National patient-weighted median wait over time for a specialty."""
    df = _q("""SELECT period,
                      SUM(median_wait_wks*total_waiting)/SUM(total_waiting) AS median_wait,
                      100.0*SUM(within_18wk)/SUM(total_waiting) AS pct_within_18wk,
                      SUM(total_waiting) AS waiting
               FROM rtt_monthly
               WHERE treatment_function = :s AND median_wait_wks IS NOT NULL
               GROUP BY period ORDER BY period""", {"s": specialty})
    df["period"] = pd.to_datetime(df["period"])
    return df
