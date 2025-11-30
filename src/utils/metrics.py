"""
Metric helpers: grouping, rolling ROAS, percent change, outlier detection, confidence scoring.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List

def compute_group_metrics(df: pd.DataFrame, group_by: List[str], metrics: List[str] = None) -> pd.DataFrame:
    if metrics is None:
        metrics = ["impressions", "clicks", "spend", "revenue"]
    agg = {m: "sum" for m in metrics}
    grp = df.groupby(group_by).agg(agg).reset_index()
    # derived
    grp["ctr"] = grp.apply(lambda r: (r["clicks"] / r["impressions"]) if r["impressions"] > 0 else 0.0, axis=1)
    grp["roas"] = grp.apply(lambda r: (r["revenue"] / r["spend"]) if r["spend"] > 0 else 0.0, axis=1)
    return grp

def rolling_roas(df: pd.DataFrame, window: int = 7) -> pd.Series:
    # require date ordering
    if "date" not in df.columns:
        return pd.Series(dtype=float)
    ts = df.set_index("date").sort_index()
    daily = ts.resample("D").agg({"revenue": "sum", "spend": "sum"})
    daily["roas"] = daily.apply(lambda r: (r["revenue"] / r["spend"]) if r["spend"] > 0 else 0.0, axis=1)
    return daily["roas"].rolling(window=window, min_periods=1).mean().fillna(0.0)

def pct_change(a: float, b: float) -> float:
    # percent change from a -> b
    try:
        if a == 0:
            return float("inf") if b != 0 else 0.0
        return (b - a) / abs(a)
    except Exception:
        return 0.0

def detect_outliers(series: pd.Series, method: str = "iqr", z_thresh: float = 3.0, iqr_mul: float = 1.5) -> pd.Series:
    if series.dtype.kind not in "fi":
        try:
            series = pd.to_numeric(series, errors="coerce").fillna(0.0)
        except Exception:
            return pd.Series([False] * len(series), index=series.index)
    if method == "zscore":
        mean = series.mean()
        std = series.std(ddof=0) if series.std(ddof=0) > 0 else 1.0
        z = (series - mean) / std
        return abs(z) > z_thresh
    else:
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - iqr_mul * iqr
        upper = q3 + iqr_mul * iqr
        return (series < lower) | (series > upper)

def compute_confidence_score(evidence: Dict[str, Any]) -> float:
    """
    Convert numeric evidence into a 0-1 confidence score.
    Evidence dict can contain keys like:
    - pct_change_roas (float)
    - pct_change_ctr (float)
    - sample_size (int)
    - outlier_flag (bool)
    - consistency_score (0-1)
    This is a heuristic weighted function; tune via config.
    """
    score = 0.0
    weight_total = 0.0

    # stronger weight to roas change
    if "pct_change_roas" in evidence:
        w = 0.5
        val = min(abs(evidence.get("pct_change_roas", 0.0)), 2.0) / 2.0  # cap at 200%
        score += w * val
        weight_total += w

    if "pct_change_ctr" in evidence:
        w = 0.2
        val = min(abs(evidence.get("pct_change_ctr", 0.0)), 2.0) / 2.0
        score += w * val
        weight_total += w

    if "sample_size" in evidence:
        w = 0.15
        n = evidence.get("sample_size", 0)
        # logistic-ish mapping: >1000 -> full weight
        val = min(1.0, n / 1000.0)
        score += w * val
        weight_total += w

    if evidence.get("outlier_flag"):
        # penalize if outlier
        w = 0.15
        score += w * 0.2  # small positive if evidence exists but lower confidence
        weight_total += w

    if weight_total == 0:
        return 0.0
    final = score / weight_total
    # clamp
    return float(max(0.0, min(1.0, final)))
