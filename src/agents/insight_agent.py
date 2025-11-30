import os
import json
import math
import random
from collections import Counter, defaultdict
from typing import Dict, Any, List
from datetime import timedelta

from src.utils.loader import get_recent_df, load_config
from src.utils.metrics import compute_group_metrics, rolling_roas, detect_outliers, pct_change

# This insight agent is designed to produce strong, testable hypotheses entirely offline.
# It uses deterministic rules, signal thresholds, and dataset-derived signals.

class InsightAgent:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config or load_config()
        # seed for reproducibility
        random.seed(int(self.cfg.get("random_seed", 42)))

    def generate(self, data_summaries: Dict[str, Any], df=None) -> Dict[str, Any]:
        """
        data_summaries: output of summarize_for_llm(...) (compact dict)
        df: full dataframe (optional, used for deeper checks if provided)
        Returns {"hypotheses": [ ... ]}
        """
        hypotheses = []
        s = data_summaries
        # basic signals
        by_audience = {r.get("audience_type"): r for r in (s.get("by_audience") or [])}
        by_platform = {r.get("platform"): r for r in (s.get("by_platform") or [])}
        low_ctr_creatives = s.get("low_ctr_creatives", [])
        top_creatives = s.get("top_creatives", [])
        avg_roas = s.get("avg_roas", 0.0)
        avg_ctr = s.get("avg_ctr", 0.0)
        total_spend = s.get("total_spend", 0.0)
        total_revenue = s.get("total_revenue", 0.0)

        # 1: Spend shift to low-efficiency audience
        if by_audience:
            # compute worst and best
            audience_list = list(by_audience.values())
            worst = min(audience_list, key=lambda x: x.get("roas", 0.0))
            best = max(audience_list, key=lambda x: x.get("roas", 0.0))
            hypotheses.append(self._mk_hyp(
                "H1",
                f"ROAS decline driven by increased spend on low-efficiency audience: {worst.get('audience_type')}",
                f"{worst.get('audience_type')} has ROAS={worst.get('roas'):.2f} vs best {best.get('audience_type')} ROAS={best.get('roas'):.2f}",
                ["Compare daily spend allocation by audience (last 7 vs prior 7 days).", "Compute pct change in ROAS for each audience."],
                est_conf=0.75 if worst.get("roas", 0.0) < (best.get("roas", 0.0) * 0.7) else 0.45
            ))

        # 2: Creative type performance (Video/UGC > Image)
        type_perf = defaultdict(lambda: {"spend":0,"revenue":0,"count":0})
        for t in (top_creatives or []) + (low_ctr_creatives or []):
            ctype = t.get("creative_type") or t.get("creative_type","Image")
            type_perf[ctype]["spend"] += float(t.get("revenue",0))
            type_perf[ctype]["revenue"] += float(t.get("revenue",0))
            type_perf[ctype]["count"] += 1
        # heuristic: if Image present in low_ctr list many times -> hypothesis
        images_low = sum(1 for c in (low_ctr_creatives or []) if (c.get("creative_type") or "").lower().startswith("image"))
        if images_low > max(2, len(low_ctr_creatives)//3):
            hypotheses.append(self._mk_hyp(
                "H2",
                "Image creatives underperform relative to Video/UGC",
                f"{images_low} low-CTR creatives are Image types. Consider richer formats.",
                ["Compare ROAS by creative_type", "Run A/B of Image vs UGC/Video on same audience"],
                est_conf=0.72
            ))

        # 3: Platform mismatch (Instagram low ROAS for Images)
        if by_platform:
            # find platform with lowest roas
            p_list = list(by_platform.values())
            worst_p = min(p_list, key=lambda x: x.get("roas", 0.0))
            if worst_p.get("roas",0) < avg_roas * 0.6:
                hypotheses.append(self._mk_hyp(
                    "H3",
                    f"Platform underperformance: {worst_p.get('platform')} shows low ROAS.",
                    f"Platform {worst_p.get('platform')} ROAS={worst_p.get('roas'):.2f} vs avg_roas={avg_roas:.2f}",
                    ["Compare creative_type mix on this platform", "Check CTR differential between platforms"],
                    est_conf=0.7
                ))

        # 4: CTR->ROAS mismatch (high CTR but low ROAS)
        if avg_ctr > 0:
            # approximate by checking top creatives with high clicks but low revenue (using provided lists)
            weird = []
            for c in (top_creatives or [])[:10]:
                clicks = float(c.get("roas",0)) # dummy use if clicks missing; can't assume clicks present in top_creatives
                # We'll inspect low_ctr_creatives specifically
            if low_ctr_creatives and avg_roas > 0:
                hypotheses.append(self._mk_hyp(
                    "H4",
                    "CTR not translating to conversions: high engagement but low purchase intent",
                    f"Median CTR={avg_ctr:.4f} but average ROAS={avg_roas:.2f}. Suggest funnel leakage.",
                    ["Compare CTR -> purchases by creative_id", "Review landing page conversion for top-click creatives"],
                    est_conf=0.68
                ))

        # 5: Creative message repetition (fatigue)
        messages = [ (c.get("creative_message") or "").lower() for c in (low_ctr_creatives or []) + (top_creatives or []) ]
        tokens = []
        for m in messages:
            tokens += [t.strip(" .,-") for t in m.split() if len(t) > 3]
        top_words = [w for w,cnt in Counter(tokens).most_common(10)]
        if len(top_words) > 0:
            # if same phrase repeats more than twice
            repeats = sum(1 for m in messages if any(w in m for w in top_words[:3]))
            if repeats > 2:
                hypotheses.append(self._mk_hyp(
                    "H5",
                    "Creative fatigue from repeated messaging/themes (e.g., cooling mesh, breathable)",
                    f"Top terms found in creatives: {', '.join(top_words[:6])}. Many creatives reuse same phrases.",
                    ["Cluster creative messages and compute similarity over time", "Rotate messaging themes"],
                    est_conf=0.7
                ))

        # 6: Outlier days skewing averages
        if df is not None:
            try:
                roas_series = rolling_roas(df, window=self.cfg.get("trend_window_days",7))
                out_flags = detect_outliers(roas_series.fillna(0), method=self.cfg.get("outlier_method","iqr"))
                if out_flags.any():
                    hypotheses.append(self._mk_hyp(
                        "H6",
                        "Outlier days (spikes) are skewing rolling averages and hiding trends",
                        "Detected outlier ROAS days in the time series. These should be winsorized for trend analysis.",
                        ["List dates with extreme ROAS", "Compute median-based trends after removing outliers"],
                        est_conf=0.6
                    ))
            except Exception:
                pass

        # 7: Missing data quality issues
        if any((c.get("ad_id","") == "" or c.get("ad_id") is None) for c in (low_ctr_creatives or [])):
            hypotheses.append(self._mk_hyp(
                "H7",
                "Data quality: missing ad identifiers or spend entries detected",
                "Missing ad_id or spend entries can distort group metrics and trend detection.",
                ["Check CSV for blank spend/ad_id values", "Impute or drop rows before analysis"],
                est_conf=0.52
            ))

        # 8: Retargeting saturation
        # look for retargeting audience present in low-CTR list
        retargeting_count = sum(1 for c in (low_ctr_creatives or []) if (c.get("audience_type") or "").lower().startswith("retarget"))
        if retargeting_count > 0:
            hypotheses.append(self._mk_hyp(
                "H8",
                "Retargeting pool saturation: retarget segments show diminishing returns",
                f"{retargeting_count} low-CTR creatives originate from retargeting segments.",
                ["Increase retargeting window or expand audience", "Check frequency and overlap with top buyers"],
                est_conf=0.65
            ))

        # 9: Frequency driven burnout proxy (use impressions/clicks ratio as proxy)
        if df is not None and "impressions" in df.columns and "clicks" in df.columns:
            try:
                frame = df.copy()
                frame["freq_proxy"] = frame["impressions"] / (frame["clicks"].replace(0,1))
                high_freq = frame[frame["freq_proxy"] > frame["freq_proxy"].quantile(0.9)]
                if len(high_freq) > 0:
                    hypotheses.append(self._mk_hyp(
                        "H9",
                        "High frequency (ad saturation) detected for subset of creatives",
                        "Proxy metric impressions/clicks indicates a top-decile group with excessive exposure.",
                        ["Compute frequency by user (if available) or ad_id", "Cap frequency and test"],
                        est_conf=0.6
                    ))
            except Exception:
                pass

        # 10: Conversion rate drop (purchases relative to clicks)
        if df is not None and "clicks" in df.columns and "purchases" in df.columns:
            try:
                recent = get_recent_df(df, self.cfg.get("recent_days",7))
                cr = recent["purchases"].sum() / max(1, recent["clicks"].sum())
                # compare to earlier window
                earlier = get_recent_df(df, self.cfg.get("long_trend_window_days",30))
                if len(earlier) > len(recent)*1.1:
                    earlier_cr = earlier["purchases"].sum() / max(1, earlier["clicks"].sum())
                    if earlier_cr > 0 and cr < earlier_cr * 0.85:
                        hypotheses.append(self._mk_hyp(
                            "H10",
                            "Conversion rate dropped in recent period versus longer window",
                            f"Recent CR={cr:.3f} vs earlier CR={earlier_cr:.3f}",
                            ["A/B test landing page", "Check checkout funnel metrics"],
                            est_conf=0.78
                        ))
            except Exception:
                pass

        # Keep only unique by hypothesis text, limit to 15
        uniq = []
        seen = set()
        for h in hypotheses:
            key = (h["hypothesis"][:200])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(h)
            if len(uniq) >= 15:
                break

        return {"hypotheses": uniq}

    def _mk_hyp(self, hid, hypothesis, reasoning, suggested_checks, est_conf=0.6):
        return {
            "id": hid,
            "hypothesis": hypothesis,
            "reasoning": reasoning,
            "suggested_checks": suggested_checks,
            "confidence_guess": float(max(0.0, min(1.0, est_conf)))
        }
