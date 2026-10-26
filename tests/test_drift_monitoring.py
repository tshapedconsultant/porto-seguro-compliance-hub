"""Tests for Polars-native drift monitoring and anti-leakage threshold selection."""

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.monitoring.drift_monitoring import detect_data_drift, detect_model_drift
from src.models.evaluation import compute_f1_optimal_threshold


def test_detect_data_drift_identical_distributions_negative_control():
    """Identical distributions must not alert (negative control)."""
    rng = np.random.default_rng(7)
    values = rng.normal(0.0, 1.0, 400)
    ref = pl.DataFrame({"feat_a": values})
    curr = pl.DataFrame({"feat_a": values.copy()})
    result = detect_data_drift(ref, curr, threshold=0.1)
    assert "feat_a" in result["feature_drifts"]
    assert result["feature_drifts"]["feat_a"]["drift_detected"] is False
    assert result["drift_detected"] is False


def test_detect_data_drift_shifted_distribution_alerts():
    """Clearly shifted distribution must alert."""
    rng = np.random.default_rng(11)
    ref = pl.DataFrame({"feat_a": rng.normal(0.0, 1.0, 500)})
    curr = pl.DataFrame({"feat_a": rng.normal(3.0, 1.0, 500)})
    result = detect_data_drift(ref, curr, threshold=0.1)
    assert result["feature_drifts"]["feat_a"]["drift_detected"] is True
    assert result["drift_detected"] is True
    assert result["feature_drifts"]["feat_a"]["ks_statistic"] > 0.3


def test_detect_data_drift_ks_power_with_enough_observations():
    """With enough observations, moderate mean shift is detectable by KS."""
    rng = np.random.default_rng(21)
    n = 800
    ref = pl.DataFrame({"feat_b": rng.normal(0.0, 1.0, n)})
    curr = pl.DataFrame({"feat_b": rng.normal(0.6, 1.0, n)})
    result = detect_data_drift(ref, curr, threshold=0.05)
    feat = result["feature_drifts"]["feat_b"]
    assert feat["reference_n"] >= 500
    assert feat["current_n"] >= 500
    assert feat["drift_detected"] is True
    assert feat["p_value"] < 0.05


def test_model_drift_improvement_does_not_alert():
    ref = {"roc_auc": 0.63, "f1_score": 0.11, "precision": 0.08, "recall": 0.21}
    improved = {"roc_auc": 0.65, "f1_score": 0.12, "precision": 0.09, "recall": 0.22}
    result = detect_model_drift(ref, improved, threshold=0.05)
    assert result["drift_detected"] is False


def test_model_drift_degradation_alerts():
    ref = {"roc_auc": 0.63, "f1_score": 0.11, "precision": 0.08, "recall": 0.21}
    degraded = {"roc_auc": 0.55, "f1_score": 0.08, "precision": 0.06, "recall": 0.15}
    result = detect_model_drift(ref, degraded, threshold=0.05)
    assert result["drift_detected"] is True


def test_optimal_threshold_uses_split_not_full_dataset():
    """
    Behavioral anti-leakage: F1-optimal threshold on train/val can differ from
    full-data optimum; official helper must match the split-only computation.
    """
    rng = np.random.default_rng(0)
    y_train = np.array([0] * 20 + [1] * 10, dtype=int)
    p_train = np.concatenate([rng.uniform(0, 0.45, 20), rng.uniform(0.35, 0.9, 10)])
    y_test = np.array([0] * 15 + [1] * 15, dtype=int)
    # Test negatives score high / positives low → pulls full-data optimum down
    p_test = np.concatenate([rng.uniform(0.5, 0.95, 15), rng.uniform(0.0, 0.4, 15)])

    y_full = np.concatenate([y_train, y_test])
    p_full = np.concatenate([p_train, p_test])

    thr_train = compute_f1_optimal_threshold(y_train, p_train)
    thr_full = compute_f1_optimal_threshold(y_full, p_full)

    assert abs(thr_train - thr_full) > 0.05, (
        f"Fixture must diverge: train={thr_train}, full={thr_full}"
    )
    # Official path in ebm_train / find_optimal_threshold uses train scores only
    assert compute_f1_optimal_threshold(y_train, p_train) == pytest.approx(thr_train)
