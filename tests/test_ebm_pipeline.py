"""
Test EBM Pipeline - MLOps Integration
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

from pathlib import Path
import hashlib
import json
import tempfile

import numpy as np
import polars as pl
import pytest

# Skip if interpret is not installed
try:
    from src.models.ebm_train import (
        build_dataset_provenance,
        train_ebm_pipeline,
        predict_with_pipeline,
        write_run_manifest,
        _canonical_manifest_body,
    )

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
        manifest_path = Path(results["paths"]["run_manifest"])
        assert manifest_path.exists()
        assert manifest_path.name.startswith("run_manifest_")
        assert manifest_path.name.endswith(".json")
        nested = Path(results["paths"]["run_manifest_nested"])
        assert nested.exists()
        pointer = Path(results["paths"]["run_manifest_latest"])
        assert pointer.exists()
        pointer_body = json.loads(pointer.read_text(encoding="utf-8"))
        assert pointer_body["run_id"] == results["run_id"]
        assert "non-authoritative" in pointer_body["note"].lower()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["run_id"] == results["run_id"]
        assert len(manifest["dataset"]["dataset_sha256"]) == 64
        assert manifest["dataset"]["file_size_bytes"] > 0
        assert manifest["dataset"]["row_count"] > 0
        assert len(manifest["dataset"]["schema_sha256"]) == 64
        expected_checksum = hashlib.sha256(
            _canonical_manifest_body(manifest).encode("utf-8")
        ).hexdigest()
        assert manifest["manifest_sha256"] == expected_checksum
        assert "NOT a cryptographic signature" in manifest["integrity_note"]

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


def test_dataset_provenance_synthetic_or_missing(tmp_path):
    """No train.csv → synthetic_or_missing marker; no invented file SHA."""
    df = pl.DataFrame({"a": [1, 2], "b": [0.1, 0.2], "target": [0, 1]})
    prov = build_dataset_provenance(str(tmp_path), sample_size=2, random_seed=1, df=df)
    assert prov["status"] == "synthetic_or_missing"
    assert prov["dataset_sha256"] is None
    assert prov["legacy_fingerprint"].startswith("synthetic_or_missing:")
    assert prov["schema_sha256"]
    assert "NOT" in prov["integrity_note"].upper() or "not" in prov["integrity_note"]


def test_run_manifest_does_not_overwrite_shared_file(tmp_path):
    """Two runs leave distinct manifest files; latest is pointer-only."""
    p1 = write_run_manifest(
        tmp_path,
        run_id="runA",
        dataset={"status": "synthetic_or_missing", "legacy_fingerprint": "x"},
        config={},
        metrics={"auc": 0.1},
        artifact_paths={},
    )
    p2 = write_run_manifest(
        tmp_path,
        run_id="runB",
        dataset={"status": "synthetic_or_missing", "legacy_fingerprint": "y"},
        config={},
        metrics={"auc": 0.2},
        artifact_paths={},
    )
    assert p1 != p2
    assert p1.exists() and p2.exists()
    assert not (tmp_path / "run_manifest.json").exists()
    latest = json.loads((tmp_path / "run_manifest_latest.json").read_text(encoding="utf-8"))
    assert latest["run_id"] == "runB"
    assert (tmp_path / "runA" / "run_manifest.json").exists()
    assert (tmp_path / "runB" / "run_manifest.json").exists()
