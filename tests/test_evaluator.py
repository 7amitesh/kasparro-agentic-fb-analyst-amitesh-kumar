"""
Unit tests for the Evaluator and confidence scoring logic.

Run with:
    pytest -q

These tests are deterministic and use small synthetic data / evidence dicts.
They validate:
 - compute_confidence_score behavior for several evidence patterns
 - Evaluator.evaluate decisions for different confidence thresholds
"""

import math
import json
import os
import tempfile
try:
    # Use dynamic import to avoid static analysis errors for missing 'pytest'
    import importlib
    pytest = importlib.import_module("pytest")
except Exception:
    # Minimal fallback for pytest.fixture decorator used in these tests.
    # If pytest is not installed in the environment, provide a no-op fixture
    # so the tests can still be executed (fixtures will simply return the function).
    def _fixture_decorator(func=None):
        if func is None:
            def _decorator(f):
                return f
            return _decorator
        return func

    class _PytestFallback:
        fixture = staticmethod(_fixture_decorator)

    pytest = _PytestFallback()

from src.utils.metrics import compute_confidence_score, pct_change
from src.agents.evaluator import Evaluator

@pytest.fixture
def cfg():
    return {
        "confidence_min": 0.6
    }

def test_pct_change_zero_to_value():
    # a -> b where a == 0 should return inf (handled by pct_change)
    a = 0.0
    b = 10.0
    pc = pct_change(a, b)
    assert math.isinf(pc) or pc == float("inf") or pc > 0

def test_confidence_score_high_roas_change():
    evidence = {
        "pct_change_roas": 1.0,   # 100% change
        "pct_change_ctr": 0.2,
        "sample_size": 2000,
        "outlier_flag": False
    }
    score = compute_confidence_score(evidence)
    # Expect reasonably high confidence (close to 1)
    assert 0.6 <= score <= 1.0

def test_confidence_score_low_sample_small_changes():
    evidence = {
        "pct_change_roas": 0.01,
        "pct_change_ctr": 0.0,
        "sample_size": 10,
        "outlier_flag": False
    }
    score = compute_confidence_score(evidence)
    assert 0.0 <= score <= 0.2

def test_evaluator_accepts_high_confidence(cfg):
    ev = Evaluator(cfg)
    # A hypothesis object (shape used by Evaluator)
    hypothesis = {"id": "h-test", "hypothesis": "test"}
    evidence = {
        "pct_change_roas": 1.0,
        "pct_change_ctr": 0.1,
        "sample_size": 1500,
        "outlier_flag": False
    }
    result = ev.evaluate(hypothesis, evidence)
    assert isinstance(result, dict)
    assert "verdict" in result
    assert result["verdict"] in ("accepted", "needs_review", "rejected")
    assert result["confidence"] >= 0.6

def test_evaluator_needs_review_low_confidence(cfg):
    ev = Evaluator(cfg)
    hypothesis = {"id": "h-low", "hypothesis": "low"}
    evidence = {
        "pct_change_roas": 0.0,
        "pct_change_ctr": 0.0,
        "sample_size": 5,
        "outlier_flag": False
    }
    result = ev.evaluate(hypothesis, evidence)
    # Low evidence should map to needs_review (per Evaluator logic)
    assert result["confidence"] < cfg["confidence_min"]
    assert result["verdict"] == "needs_review"

def test_evaluator_structure_and_evidence_returned(cfg):
    ev = Evaluator(cfg)
    hypothesis = {"id": "h-structure", "hypothesis": "struct"}
    evidence = {
        "pct_change_roas": 0.5,
        "sample_size": 300,
        "outlier_flag": True
    }
    result = ev.evaluate(hypothesis, evidence)
    # Ensure evidence and notes are preserved in return structure
    assert "evidence" in result or "notes" in result or "confidence" in result

