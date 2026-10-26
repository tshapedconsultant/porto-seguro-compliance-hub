"""
Test Model Evaluation Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression

from src.models.evaluation import (
    calculate_business_metrics,
    compute_brier_score,
    compute_f1_optimal_threshold,
    expected_calibration_error,
    stratified_cross_validation,
)

# Skip EBM-backed tests if interpret is not installed
try:
    from src.models.evaluation import evaluate_model
    from src.models.ebm_train import train_ebm_pipeline
    from src.data_processing.feature_engineering import get_stratified_split, ResponsibleFeatureEngineer

    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False


def test_calculate_business_metrics():
    """Test business metrics calculation."""
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
    y_pred = np.array([0, 1, 1, 0, 0, 1, 0, 1])
    y_pred_proba = np.array([0.1, 0.6, 0.8, 0.4, 0.2, 0.9, 0.3, 0.7])

    business_metrics = calculate_business_metrics(
        y_true, y_pred, y_pred_proba, claim_cost=10000.0, premium=1000.0
    )

    assert "true_positives" in business_metrics
    assert "true_negatives" in business_metrics
    assert "false_positives" in business_metrics
    assert "false_negatives" in business_metrics
    assert "total_cost" in business_metrics
    assert "total_revenue" in business_metrics
    assert "net_profit" in business_metrics
    assert "cost_per_prediction" in business_metrics
    assert business_metrics["illustrative_only"] is True
    assert business_metrics["true_positives"] >= 0
    assert business_metrics["true_negatives"] >= 0


def test_brier_and_ece_well_vs_poorly_calibrated():
    """Technical calibration metrics: aligned probs beat anti-aligned / constant ones."""
    rng = np.random.default_rng(42)
    n = 2000
    y_true = rng.integers(0, 2, size=n).astype(float)

    # Well-calibrated-ish: probs near the true label
    well = np.clip(y_true * 0.75 + (1.0 - y_true) * 0.25 + rng.normal(0, 0.03, n), 0.0, 1.0)
    # Poor: systematically inverted probabilities
    poor = 1.0 - y_true
    # Also poorly calibrated: constant high confidence unrelated to labels
    constant = np.full(n, 0.9)

    brier_well = compute_brier_score(y_true, well)
    brier_poor = compute_brier_score(y_true, poor)
    ece_well = expected_calibration_error(y_true, well, n_bins=10)
    ece_constant = expected_calibration_error(y_true, constant, n_bins=10)

    assert 0.0 <= brier_well <= 1.0
    assert 0.0 <= ece_well <= 1.0
    assert brier_well < brier_poor
    assert ece_well < ece_constant


def test_compute_f1_optimal_threshold_matches_manual():
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.4, 0.45, 0.7, 0.9])
    thr = compute_f1_optimal_threshold(y_true, y_prob)
    assert 0.0 < thr < 1.0


def test_stratified_cv_mean_std_on_synthetic():
    """Unit-level stratified 5-fold CV with mean±std for AUC/recall/F1."""
    rng = np.random.default_rng(0)
    n = 400
    X = rng.normal(size=(n, 4))
    y = (X[:, 0] + rng.normal(0, 0.4, n) > 0).astype(int)
    model = LogisticRegression(max_iter=500, random_state=0)
    results = stratified_cross_validation(model, X, y, n_splits=5)

    assert results["n_splits"] == 5
    for metric in ("roc_auc", "f1", "recall"):
        block = results["metrics"][metric]
        assert "test_mean" in block and "test_std" in block
        assert len(block["test_scores"]) == 5
        assert 0.0 <= block["test_mean"] <= 1.0
    assert results["metrics"]["roc_auc"]["test_mean"] > 0.65


@pytest.mark.skipif(not INTERPRET_AVAILABLE, reason="interpret package not installed")
def test_evaluate_model():
    """Test model evaluation via EBM pipeline."""
    rng = np.random.default_rng(42)
    n_samples = 500
    n_features = 5
    data = {f"feature_{i}": rng.normal(0, 1, n_samples) for i in range(n_features)}
    data["target"] = (data["feature_0"] > 0).astype(int)
    data["id"] = np.arange(n_samples)
    df = pl.DataFrame(data)

    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as art_dir:
        df.write_csv(Path(tmpdir) / "train.csv")
        pipeline = train_ebm_pipeline(
            data_path=tmpdir,
            target_col="target",
            test_size=0.2,
            random_seed=42,
            hyperparameters={"max_rounds": 50, "interactions": 2, "outer_bags": 2},
            artifacts_dir=art_dir,
            write_legacy_copies=False,
            perform_cv=False,
            perform_adversarial=False,
        )
        model = pipeline["model"]
        fe = pipeline["feature_engineer"]

        train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2, random_seed=42)
        # Reuse fitted FE from pipeline (do not refit)
        test_eng = fe.transform(test_df)
        X_test = test_eng.drop(["id", "target"])
        y_test = test_eng.select(["target"])

        metrics = evaluate_model(model, X_test, y_test, target_col="target")

    assert "roc_auc" in metrics
    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1_score" in metrics
    assert "confusion_matrix" in metrics
    assert "classification_report" in metrics
    assert "roc_curve" in metrics
    assert "pr_curve" in metrics
    assert 0 <= metrics["roc_auc"] <= 1
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1_score"] <= 1

