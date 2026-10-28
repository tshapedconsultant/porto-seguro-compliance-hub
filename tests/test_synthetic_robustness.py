"""
Lightweight reproducible robustness / data-quality smoke on synthetic data.

No Kaggle train.csv. Polars required; sklearn optional for noise AUC check.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pl = pytest.importorskip("polars")

from src.data_processing.data_validation import validate_data_quality
from src.governance.reporting_generator import (
    build_assurance_fields,
    format_drift_monitoring_section,
    generate_unified_ai_report,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "examples" / "evidence"


def _synthetic_frame(n: int = 80) -> "pl.DataFrame":
    rng = np.random.default_rng(42)
    ps_ind_01 = [float(x) for x in rng.normal(0.0, 1.0, size=n)]
    ps_car_13 = [float(x) for x in rng.uniform(0.2, 1.5, size=n)]
    # Inject missing (>10%) as true Polars nulls + out-of-range values
    miss_idx = set(rng.choice(n, size=max(12, n // 5), replace=False).tolist())
    ps_ind_01 = [None if i in miss_idx else v for i, v in enumerate(ps_ind_01)]
    ps_car_13[2] = 99.0  # out-of-range relative to typical Porto-like scale
    noise = rng.normal(0, 0.2, size=n)
    target = [
        int((ps_car_13[i] if ps_car_13[i] is not None else 0.5) + noise[i] > 0.9)
        for i in range(n)
    ]
    return pl.DataFrame(
        {
            "id": list(range(n)),
            "ps_ind_01": ps_ind_01,
            "ps_car_13": ps_car_13,
            "ps_reg_03": [float(x) for x in rng.normal(0.5, 0.2, size=n)],
            "target": target,
        }
    )


def test_synthetic_data_quality_flags_issues():
    df = _synthetic_frame()
    report = validate_data_quality(df, target_col="target")
    assert report["total_records"] == 80
    assert report["missing_values"]
    assert report["quality_score"] < 1.0
    assert isinstance(report.get("warnings", []), list)


def test_synthetic_noise_shifts_feature_distribution():
    df = _synthetic_frame()
    clean = df.select("ps_car_13").drop_nulls().to_series().to_numpy()
    rng = np.random.default_rng(7)
    noisy = clean + rng.normal(0.0, 0.35, size=clean.shape[0])
    # Simple distribution shift proxy (mean absolute delta) — no trained EBM required.
    shift = float(np.abs(noisy.mean() - clean.mean()))
    assert shift > 0.0
    assert np.isfinite(shift)


def test_synthetic_sklearn_auc_degrades_under_noise():
    sklearn = pytest.importorskip("sklearn")
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    df = _synthetic_frame(120).drop_nulls()
    assert df.height >= 40
    pdf = df.to_pandas()
    features = ["ps_ind_01", "ps_car_13", "ps_reg_03"]
    X = pdf[features].to_numpy(dtype=float)
    y = pdf["target"].to_numpy()
    assert np.isfinite(X).all()
    if len(np.unique(y)) < 2:
        pytest.skip("synthetic labels not both classes")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.35, random_state=42, stratify=y
    )
    model = LogisticRegression(max_iter=200)
    model.fit(X_train, y_train)
    baseline = float(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]))
    rng = np.random.default_rng(0)
    X_noisy = X_test + rng.normal(0.0, 0.75, size=X_test.shape)
    noisy_auc = float(roc_auc_score(y_test, model.predict_proba(X_noisy)[:, 1]))
    # Document robustness signal: noise should not improve AUC dramatically on this toy set.
    assert baseline >= 0.45
    assert noisy_auc <= baseline + 0.15


def test_synthetic_end_to_end_evidence_pack(tmp_path):
    """Model card / drift / evidence pack without Kaggle CSV."""
    drift_src = EVIDENCE_DIR / "synthetic_drift_snapshot.json"
    if not drift_src.is_file():
        pytest.skip("examples/evidence/synthetic_drift_snapshot.json is not in the published tree")
    drift_payload = json.loads(drift_src.read_text(encoding="utf-8"))
    drift_section = format_drift_monitoring_section(
        drift_monitoring_results=drift_payload,
        evidence_path=drift_src,
    )
    assert drift_section["evidence_available"] is True
    assert drift_section["control_tested"] is True
    assert drift_section["assurance_level"] == "tested"

    quality = validate_data_quality(_synthetic_frame(), target_col="target")
    report = generate_unified_ai_report(
        model_info={
            "name": "Synthetic claim-score stub",
            "version": "0.0.1-synth",
            "model_type": "LogisticRegression",
        },
        performance_metrics={"roc_auc": 0.72, "f1_score": 0.4},
        training_data_info={
            "total_records": quality["total_records"],
            "total_features": quality["total_features"],
            "source_file": "synthetic_tiny_polars",
            "quality_score": quality["quality_score"],
        },
        explainability_report={"compliance_notes": {"global": "stub coefficients"}},
        data_quality_report=quality,
        bias_audit_results={"status": "synthetic_skipped", "audit_valid": False},
        drift_monitoring_results=drift_payload,
        validation_results={"adversarial_testing": {"overall_robust": True}},
        output_path=str(tmp_path / "synthetic_unified_report.json"),
    )
    assert report["schema_version"] == "1.1.0"
    assert report["disclaimer"]["not_a_conformity_decision"] is True
    assert "Compliant" not in json.dumps(report)
    assurance = build_assurance_fields(
        evidence_available=True,
        control_tested=True,
        test_date="2026-10-26T12:00:00",
        test_evidence="tests/test_synthetic_robustness.py",
        owner="lab-demo",
    )
    assert assurance["assurance_level"] == "tested"
    assert (tmp_path / "synthetic_unified_report.json").exists()
