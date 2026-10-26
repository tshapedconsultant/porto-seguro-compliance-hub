"""
Fairness subgroup tests on synthetic group attributes.

Technical detection only — not a legal fairness certification or GDPR claim.
"""

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.governance.bias_audit import (
    _build_audit_frame,
    demographic_parity_test,
    equalized_odds_test,
)


def test_demographic_parity_detects_group_difference():
    """Biased positive rates across groups must fail demographic parity."""
    n = 200
    group = np.array([0] * 100 + [1] * 100)
    # Group 0 rarely predicted positive; group 1 often
    y_pred_proba = np.concatenate([np.full(100, 0.1), np.full(100, 0.9)])
    y_true = pl.Series("y_true", np.concatenate([np.zeros(100, dtype=int), np.ones(100, dtype=int)]))
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = demographic_parity_test(audit_df, protected, threshold=0.1)
    assert result["overall_parity"] is False
    assert result["attribute_tests"]["proxy_group"]["max_difference"] > 0.5
    assert len(result["violations"]) >= 1


def test_demographic_parity_passes_when_rates_match():
    n = 200
    group = np.array([0] * 100 + [1] * 100)
    y_pred_proba = np.tile([0.2, 0.8], 100)  # same pattern both groups
    y_true = pl.Series("y_true", np.tile([0, 1], 100))
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = demographic_parity_test(audit_df, protected, threshold=0.1)
    assert result["overall_parity"] is True
    assert result["attribute_tests"]["proxy_group"]["max_difference"] < 0.1


def test_equalized_odds_detects_tpr_fpr_gap():
    """Construct groups with clearly different TPR/FPR."""
    # Group A: perfect predictions; Group B: inverted
    y_true = pl.Series(
        "y_true",
        np.array([0, 0, 0, 0, 1, 1, 1, 1] * 10, dtype=int),
    )
    group = np.array([0] * 40 + [1] * 40)
    # First 40 (group 0): scores match labels; last 40 (group 1): anti-aligned
    scores_a = np.array([0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9] * 5)
    scores_b = np.array([0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1] * 5)
    y_pred_proba = np.concatenate([scores_a, scores_b])
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = equalized_odds_test(audit_df, protected, threshold=0.1)
    assert result["overall_equality"] is False
    attr = result["attribute_tests"]["proxy_group"]
    assert attr["tpr_difference"] > 0.5 or attr["fpr_difference"] > 0.5
    assert len(result["violations"]) >= 1
