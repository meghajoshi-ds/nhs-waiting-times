"""
Statistical analysis: Mann-Kendall trend test, seasonal decomposition, and
Pearson correlation. Kept dependency-light (numpy/scipy/statsmodels).
"""

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.tsa.seasonal import seasonal_decompose


def mann_kendall(values):
    """
    Non-parametric Mann-Kendall trend test.

    Returns a dict with the trend direction, normalised test statistic z,
    two-sided p-value, and Sen's slope (median pairwise slope per step).
    """
    x = np.asarray(pd.Series(values).dropna(), dtype=float)
    n = len(x)
    if n < 8:
        return {"trend": "insufficient data", "n": n}

    s = sum(np.sign(x[j] - x[i]) for i in range(n - 1) for j in range(i + 1, n))

    # variance with tie correction
    _, counts = np.unique(x, return_counts=True)
    tie = sum(c * (c - 1) * (2 * c + 5) for c in counts)
    var_s = (n * (n - 1) * (2 * n + 5) - tie) / 18.0

    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0
    p = 2 * (1 - scipy_stats.norm.cdf(abs(z)))

    slopes = [(x[j] - x[i]) / (j - i)
              for i in range(n - 1) for j in range(i + 1, n)]
    sen = float(np.median(slopes))

    if p < 0.05:
        trend = "increasing" if z > 0 else "decreasing"
    else:
        trend = "no significant trend"

    return {"trend": trend, "z": float(z), "p_value": float(p),
            "sen_slope": sen, "s": int(s), "n": n}


def decompose(df, value_col="pct_within_4hrs", period_col="period", freq=12):
    """
    Additive seasonal decomposition of a monthly series.

    `df` must be sorted by date. Returns a DataFrame indexed by period with
    observed / trend / seasonal / residual columns.
    """
    s = (df.dropna(subset=[value_col])
           .set_index(period_col)[value_col].astype(float).asfreq("MS"))
    s = s.interpolate(limit_direction="both")
    result = seasonal_decompose(s, model="additive", period=freq)
    return pd.DataFrame({
        "observed": result.observed,
        "trend": result.trend,
        "seasonal": result.seasonal,
        "residual": result.resid,
    })


def pearson(x, y):
    """Pearson correlation with p-value and a fitted regression line."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return {"r": None, "n": len(x)}
    r, p = scipy_stats.pearsonr(x, y)
    slope, intercept = np.polyfit(x, y, 1)
    return {"r": float(r), "p_value": float(p), "n": int(len(x)),
            "slope": float(slope), "intercept": float(intercept)}
