"""
Robust data loader and small EDA helpers.
Functions:
- load_config(path)
- load_data(cfg)
- get_recent_df(df, days)
- summarize_for_llm(df, recent_days, top_n)
- save_sample_csv(path, n=100)
"""

import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def load_config(path: str = None) -> Dict[str, Any]:
    if path is None:
        path = os.path.join(ROOT, "config", "config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg

def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Common columns expected
    expected = [
        "campaign_name", "adset_name", "date", "spend", "impressions", "clicks",
        "ctr", "purchases", "revenue", "roas", "creative_type", "creative_message",
        "audience_type", "platform", "country", "ad_id"
    ]
    for c in expected:
        if c not in df.columns:
            if c in ["spend", "impressions", "clicks", "purchases"]:
                df[c] = 0
            elif c in ["revenue", "ctr", "roas"]:
                df[c] = 0.0
            else:
                df[c] = ""
    # parse date
    if "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        except Exception:
            pass
    # normalize types
    numeric_cols = ["spend", "impressions", "clicks", "purchases", "revenue", "ctr", "roas"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    # compute derived metrics
    # avoid division by zero
    df["ctr"] = df.apply(lambda r: (r["clicks"] / r["impressions"]) if r["impressions"] > 0 else 0.0, axis=1)
    df["roas"] = df.apply(lambda r: (r["revenue"] / r["spend"]) if r["spend"] > 0 else 0.0, axis=1)
    return df

def load_data(cfg: Dict[str, Any] = None) -> pd.DataFrame:
    if cfg is None:
        cfg = load_config()
    path = cfg.get("data_path")
    use_sample = cfg.get("use_sample_data", False)
    if use_sample and cfg.get("sample_data_path"):
        path = cfg.get("sample_data_path")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"CSV file not found at path: {path}")
    df = pd.read_csv(path)
    df = _ensure_columns(df)
    return df

def get_recent_df(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    if "date" not in df.columns or df["date"].isnull().all():
        return df.copy()
    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=days)
    return df[df["date"] > cutoff].copy()

def summarize_for_llm(df: pd.DataFrame, recent_days: int = 7, top_n: int = 5) -> Dict[str, Any]:
    """Return a compact JSON-serializable summary aimed for LLM prompts."""
    out = {}
    recent = get_recent_df(df, recent_days)
    out["recent_period_days"] = recent_days
    out["total_impressions"] = int(recent["impressions"].sum())
    out["total_clicks"] = int(recent["clicks"].sum())
    out["total_spend"] = float(recent["spend"].sum())
    out["total_revenue"] = float(recent["revenue"].sum())
    out["avg_ctr"] = float(recent["ctr"].mean()) if len(recent) > 0 else 0.0
    out["avg_roas"] = float(recent["roas"].mean()) if len(recent) > 0 else 0.0

    # by audience summary
    if "audience_type" in recent.columns:
        grp = recent.groupby("audience_type").agg({
            "impressions": "sum", "clicks": "sum", "spend": "sum", "revenue": "sum"
        }).reset_index()
        grp["ctr"] = grp.apply(lambda r: (r["clicks"] / r["impressions"]) if r["impressions"] > 0 else 0.0, axis=1)
        grp["roas"] = grp.apply(lambda r: (r["revenue"] / r["spend"]) if r["spend"] > 0 else 0.0, axis=1)
        out["by_audience"] = grp.to_dict(orient="records")
    else:
        out["by_audience"] = []

    # by platform summary
    if "platform" in recent.columns:
        pgrp = recent.groupby("platform").agg({
            "impressions": "sum", "clicks": "sum", "spend": "sum", "revenue": "sum"
        }).reset_index()
        pgrp["ctr"] = pgrp.apply(lambda r: (r["clicks"] / r["impressions"]) if r["impressions"] > 0 else 0.0, axis=1)
        pgrp["roas"] = pgrp.apply(lambda r: (r["revenue"] / r["spend"]) if r["spend"] > 0 else 0.0, axis=1)
        out["by_platform"] = pgrp.to_dict(orient="records")
    else:
        out["by_platform"] = []

    # low-CTR creatives
    median_ctr = df["ctr"].median() if len(df) > 0 else 0.0
    low = df[df["ctr"] < median_ctr].sort_values("ctr").head(top_n)
    out["low_ctr_creatives"] = low[["ad_id", "creative_message", "ctr", "creative_type", "audience_type", "platform"]].to_dict(orient="records")

    # top creatives by revenue
    top = recent.sort_values("revenue", ascending=False).head(top_n)
    out["top_creatives"] = top[["ad_id", "creative_message", "revenue", "roas", "creative_type", "audience_type", "platform"]].to_dict(orient="records")

    return out

def save_sample_csv(path: str, n: int = 200):
    """Save a sample of the main CSV to the given path for reproducibility/testing."""
    cfg = load_config()
    df = load_data(cfg)
    sample = df.sample(n=n, random_state=cfg.get("random_seed", 42))
    sample.to_csv(path, index=False)
    return path
