"""Tests for Polars-native drift monitoring and anti-leakage metrics."""

import pytest

pytest.importorskip("polars")
import polars as pl

from src.monitoring.drift_monitoring import detect_data_drift, detect_model_drift


def test_detect_data_drift_polars_native():
    ref = pl.DataFrame({"feat_a": [1.0, 2.0, 3.0, 4.0, 5.0]})
    curr = pl.DataFrame({"feat_a": [1.0, 2.0, 3.0, 4.0, 5.0]})
    result = detect_data_drift(ref, curr, threshold=0.5)
    assert "feat_a" in result["feature_drifts"]


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


def test_full_dataset_auc_not_used_in_threshold_script():
    """Document: full-dataset AUC must not be the reported production metric."""
    from src.models import find_optimal_threshold as fot

    assert "full_dataset_auc" not in fot.find_optimal_threshold.__code__.co_varnames
