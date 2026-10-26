"""
Test Model Evaluation Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import pytest
import polars as pl
import numpy as np
import tempfile
from pathlib import Path

# Skip tests if interpret is not installed
try:
    from src.models.evaluation import evaluate_model, calculate_business_metrics
    from src.models.ebm_train import train_ebm_pipeline
    from src.data_processing.feature_engineering import get_stratified_split, ResponsibleFeatureEngineer
    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False

pytestmark = pytest.mark.skipif(not INTERPRET_AVAILABLE, reason="interpret package not installed")


def test_evaluate_model():
    """Test model evaluation."""
    n_samples = 500
    n_features = 5
    data = {f"feature_{i}": np.random.randn(n_samples) for i in range(n_features)}
    data["target"] = (data["feature_0"] > 0).astype(int)
    data["id"] = range(n_samples)
    df = pl.DataFrame(data)

    with tempfile.TemporaryDirectory() as tmpdir:
        df.write_csv(Path(tmpdir) / "train.csv")
        pipeline = train_ebm_pipeline(
            data_path=tmpdir,
            target_col="target",
            test_size=0.2,
            random_seed=42,
            hyperparameters={"max_rounds": 50, "interactions": 2},
        )
        model = pipeline["model"]
        fe = pipeline["feature_engineer"]

    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2, random_seed=42)
    fe.fit(train_df)
    test_eng = fe.transform(test_df)
    X_test = test_eng.drop(["id", "target"])
    y_test = test_eng.select(["target"])
    
    # Evaluate
    metrics = evaluate_model(model, X_test, y_test, target_col="target")
    
    # Check all required metrics
    assert "roc_auc" in metrics
    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1_score" in metrics
    assert "confusion_matrix" in metrics
    assert "classification_report" in metrics
    assert "roc_curve" in metrics
    assert "pr_curve" in metrics
    
    # Check metric ranges
    assert 0 <= metrics["roc_auc"] <= 1
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1_score"] <= 1


def test_calculate_business_metrics():
    """Test business metrics calculation."""
    # Create synthetic predictions
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
    y_pred = np.array([0, 1, 1, 0, 0, 1, 0, 1])
    y_pred_proba = np.array([0.1, 0.6, 0.8, 0.4, 0.2, 0.9, 0.3, 0.7])
    
    business_metrics = calculate_business_metrics(
        y_true, y_pred, y_pred_proba,
        claim_cost=10000.0,
        premium=1000.0
    )
    
    assert "true_positives" in business_metrics
    assert "true_negatives" in business_metrics
    assert "false_positives" in business_metrics
    assert "false_negatives" in business_metrics
    assert "total_cost" in business_metrics
    assert "total_revenue" in business_metrics
    assert "net_profit" in business_metrics
    assert "cost_per_prediction" in business_metrics
    
    # Check that metrics are calculated
    assert business_metrics["true_positives"] >= 0
    assert business_metrics["true_negatives"] >= 0

