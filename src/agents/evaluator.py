import os
import json
import math
from typing import Dict, Any
from src.utils.metrics import compute_confidence_score, pct_change, detect_outliers
from datetime import datetime

class Evaluator:
    """
    Enhanced Evaluator:
    - Uses richer numeric evidence (pct changes across windows, sample sizes, outlier checks).
    - Produces verdict: accepted | rejected | needs_review
    - Returns structured evidence and notes for provenance.
    """

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config or {}
        self.conf_min = float(self.cfg.get("confidence_min", 0.6))

    def evaluate(self, hypothesis: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        # Evidence expected keys: pct_change_roas, pct_change_ctr, sample_size, outlier_flag, other...
        ev = evidence.copy() if isinstance(evidence, dict) else {}
        # Compute base confidence via metric heuristic
        conf = compute_confidence_score(ev)

        # Heuristics to adjust confidence
        # - If pct_change_roas is infinite (division by zero) treat carefully
        pct_roas = ev.get("pct_change_roas", 0.0)
        if isinstance(pct_roas, float) and math.isinf(pct_roas):
            # If sample size small, lower confidence; if large, raise a bit
            n = ev.get("sample_size", 0)
            conf = min(1.0, conf + (0.15 if n > 200 else -0.1))

        # - Penalize when outlier_flag true (unless large sample)
        if ev.get("outlier_flag", False):
            n = ev.get("sample_size", 0)
            if n < 200:
                conf = conf * 0.6

        # Bound conf
        conf = float(max(0.0, min(1.0, conf)))

        # Decide verdict
        if conf >= self.conf_min:
            verdict = "accepted"
        elif conf < 0.25:
            verdict = "rejected"
        else:
            verdict = "needs_review"

        # Compose evaluator notes with provenance
        notes = {
            "computed_confidence": conf,
            "confidence_min": self.conf_min,
            "evidence_summary": ev,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        return {
            "verdict": verdict,
            "confidence": conf,
            "notes": str(notes),  # string-friendly notes for reports
            "evidence": ev
        }
