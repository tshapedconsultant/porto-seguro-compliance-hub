"""
Test EBM Pipeline - MLOps Integration
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

from pathlib import Path
import tempfile

import numpy as np
import polars as pl
import pytest

# Skip if interpret is not installed
try:
    from src.models.ebm_train import train_ebm_pipeline, predict_with_pipeline

    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False

pytestmark = pytest.mark.skipif(not INTERPRET_AVAILABLE, reason="interpret package not installed")


@pytest.fixture
def synthetic_data_dir():
    """Fixture to generate synthetic data with a clear feature_0 signal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rng = np.random.default_rng(42)
        n_samples = 800
        n_features = 5
        data = {f"feature_{i}": rng.normal(0, 1, n_samples) for i in range(n_features)}
        # Stronger signal in feature_0 so AUC >> 0.65 under seed
        noise = rng.normal(0, 0.35, n_samples)
        data["target"] = (data["feature_0"] + noise > 0.0).astype(int)
        data["id"] = np.arange(n_samples)

        df = pl.DataFrame(data)
        df.write_csv(Path(tmpdir) / "train.csv")
        yield tmpdir


def test_full_ebm_pipeline_execution(synthetic_data_dir):
    """Test the production EBM pipeline end-to-end (No Data Leakage)."""
    with tempfile.TemporaryDirectory() as art_dir:
        results = train_ebm_pipeline(
            data_path=synthetic_data_dir,
            target_col="target",
            test_size=0.2,
            random_seed=42,
            hyperparameters={"max_rounds": 80, "interactions": 2, "outer_bags": 2},
            artifacts_dir=art_dir,
            write_legacy_copies=False,
            perform_cv=False,
            perform_adversarial=False,
        )

        assert "model" in results
        assert "feature_engineer" in results
        assert "metrics" in results
        assert Path(results["paths"]["run_manifest"]).exists()

        metrics = results["metrics"]
        assert "test_auc" in metrics
        assert "optimal_threshold" in metrics
        assert metrics["test_auc"] > 0.65

        rng = np.random.default_rng(0)
        new_data = pl.DataFrame(
            {f"feature_{i}": rng.normal(0, 1, 10) for i in range(5)}
        ).with_columns(pl.Series("id", range(10)))
        inference_results = predict_with_pipeline(
            model=results["model"],
            feature_engineer=results["feature_engineer"],
            new_data=new_data,
        )

        assert "predictions" in inference_results
        assert "probabilities" in inference_results
        assert len(inference_results["probabilities"]) == 10
        assert all(0.0 <= p <= 1.0 for p in inference_results["probabilities"])
