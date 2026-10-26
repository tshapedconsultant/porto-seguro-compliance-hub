"""
Test Explainability Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import pytest
import polars as pl
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile

# Skip tests if interpret is not installed
try:
    from src.models.explainability import (
        explain_ebm_global,
        explain_ebm_local,
        explain_ebm_interactions,
        generate_explainability_report
    )
    from src.models.ebm_train import train_ebm_pipeline
    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False

pytestmark = pytest.mark.skipif(not INTERPRET_AVAILABLE, reason="interpret package not installed")


@pytest.fixture
def trained_pipeline_and_sample():
    """Train pipeline using production path and return model + sample."""
    with tempfile.TemporaryDirectory() as tmpdir:
        n_samples = 400
        n_features = 5
        data = {f"feature_{i}": np.random.randn(n_samples) for i in range(n_features)}
        data["target"] = (data["feature_0"] > 0).astype(int)
        data["id"] = range(n_samples)
        df = pl.DataFrame(data)
        df.write_csv(Path(tmpdir) / "train.csv")

        results = train_ebm_pipeline(
            data_path=tmpdir,
            target_col="target",
            test_size=0.2,
            random_seed=42,
            hyperparameters={"max_rounds": 30, "interactions": 3},
        )
        X_sample = pd.DataFrame({f"feature_{i}": np.random.randn(5) for i in range(n_features)})
        yield results["model"], X_sample


def test_explain_ebm_global(trained_pipeline_and_sample):
    """Test global explanation generation."""
    model, _ = trained_pipeline_and_sample
    global_explanation = explain_ebm_global(model)
    
    assert "feature_importance" in global_explanation
    assert len(global_explanation["feature_importance"]) > 0
    assert "explanation_object" in global_explanation


def test_explain_ebm_local(trained_pipeline_and_sample):
    """Test local explanation generation."""
    model, X_sample = trained_pipeline_and_sample
    local_explanation = explain_ebm_local(model, X_sample)
    
    assert "local_explanations" in local_explanation
    assert "explanation_object" in local_explanation


def test_explain_ebm_interactions(trained_pipeline_and_sample):
    """Test feature interaction explanation."""
    model, _ = trained_pipeline_and_sample
    interactions = explain_ebm_interactions(model)
    
    assert "interactions" in interactions
    assert "explanation_object" in interactions


def test_generate_explainability_report(trained_pipeline_and_sample):
    """Test comprehensive explainability report generation."""
    model, X_sample = trained_pipeline_and_sample
    report = generate_explainability_report(model, X_sample)
    
    assert "global_explanation" in report
    assert "local_explanation" in report
    assert "interactions" in report
    assert "compliance_notes" in report
    
    # Check compliance notes
    assert "model_type" in report["compliance_notes"]
    assert "explainability_method" in report["compliance_notes"]
    assert "compliance_standards" in report["compliance_notes"]

