"""
Run compliance audits and persist results for the Streamlit Compliance hub.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import polars as pl

AUDIT_RESULTS_PATH = Path("docs/audit_results.json")
COMPLIANCE_REPORT_PATH = Path("docs/compliance_report.json")
ROBUSTNESS_RESULTS_PATH = Path("docs/robustness_results.json")
DRIFT_MONITORING_PATH = Path("docs/drift_monitoring_latest.json")


def _load_optimal_threshold() -> float:
    path = Path("models/artifacts/optimal_threshold.txt")
    if path.exists():
        return float(path.read_text().strip())
    results_path = Path("training_results.json")
    if results_path.exists():
        data = json.loads(results_path.read_text(encoding="utf-8"))
        return float(data.get("optimal_threshold", 0.5))
    return 0.5


def build_proxy_protected_attributes(X_raw: pl.DataFrame) -> Dict[str, np.ndarray]:
    """
    Proxy groups from anonymized Porto Seguro features (no real demographics in dataset).
    """
    attrs: Dict[str, np.ndarray] = {}
    if "ps_ind_03" in X_raw.columns:
        med = float(X_raw.select(pl.col("ps_ind_03").median()).item())
        attrs["risk_proxy_ps_ind_03"] = (
            X_raw.select(
                pl.when(pl.col("ps_ind_03") >= med)
                .then(pl.lit("above_median"))
                .otherwise(pl.lit("below_median"))
                .alias("g")
            )["g"]
            .to_numpy()
        )
    if "ps_reg_03" in X_raw.columns:
        q1, q2 = X_raw.select(
            pl.col("ps_reg_03").quantile(0.33).alias("q1"),
            pl.col("ps_reg_03").quantile(0.66).alias("q2"),
        ).row(0)
        attrs["region_proxy_ps_reg_03"] = (
            X_raw.select(
                pl.when(pl.col("ps_reg_03") <= q1)
                .then(pl.lit("low"))
                .when(pl.col("ps_reg_03") <= q2)
                .then(pl.lit("mid"))
                .otherwise(pl.lit("high"))
                .alias("g")
            )["g"]
            .to_numpy()
        )
    if "ps_car_13" in X_raw.columns:
        med = float(X_raw.select(pl.col("ps_car_13").median()).item())
        attrs["vehicle_proxy_ps_car_13"] = (
            X_raw.select(
                pl.when(pl.col("ps_car_13") >= med)
                .then(pl.lit("above_median"))
                .otherwise(pl.lit("below_median"))
                .alias("g")
            )["g"]
            .to_numpy()
        )
    return attrs


def _artifact_checks() -> Dict[str, bool]:
    return {
        "train_csv": Path("train.csv").exists(),
        "model": Path("models/artifacts/ebm_model_v1.pkl").exists()
        or Path("models/ebm_model.pkl").exists(),
        "feature_engineer": Path("models/artifacts/feature_engineer_v1.pkl").exists()
        or Path("models/feature_engineer.pkl").exists(),
        "training_results": Path("training_results.json").exists(),
        "optimal_threshold": Path("models/artifacts/optimal_threshold.txt").exists(),
        "robustness_results": ROBUSTNESS_RESULTS_PATH.exists(),
        "drift_monitoring": DRIFT_MONITORING_PATH.exists(),
    }


def _load_monitoring_passed() -> Optional[bool]:
    """Load post-market drift gate verdict (EU AI Act Art. 9 evidence)."""
    if not DRIFT_MONITORING_PATH.exists():
        return None
    try:
        data = json.loads(DRIFT_MONITORING_PATH.read_text(encoding="utf-8"))
        if "monitoring_passed" in data:
            return bool(data["monitoring_passed"])
        status = data.get("drift_report", {}).get("overall_status")
        if status is not None:
            return status == "healthy"
    except Exception:
        pass
    return None


def _load_robustness_passed() -> Optional[bool]:
    """Load adversarial robustness verdict from training pipeline artifacts."""
    if ROBUSTNESS_RESULTS_PATH.exists():
        try:
            data = json.loads(ROBUSTNESS_RESULTS_PATH.read_text(encoding="utf-8"))
            adv = data.get("adversarial_testing", {})
            if "overall_robust" in adv:
                return bool(adv["overall_robust"])
        except Exception:
            pass

    training_path = Path("training_results.json")
    if training_path.exists():
        try:
            data = json.loads(training_path.read_text(encoding="utf-8"))
            if "robustness_passed" in data:
                return bool(data["robustness_passed"])
        except Exception:
            pass
    return None


def build_training_data_info() -> Dict[str, Any]:
    """
    Article 10 traceability: full train.csv scope, feature count, target distribution.
    """
    from src.data_processing.load_data_polars import load_porto_seguro_data, validate_data_quality

    if not Path("train.csv").exists():
        return {
            "total_records": 0,
            "total_features": 0,
            "target_distribution": {},
            "quality_score": 0.0,
            "source_file": "train.csv",
        }

    df = load_porto_seguro_data(".", sample_size=None)
    validation = validate_data_quality(df)
    feature_cols = [c for c in df.columns if c not in ("id", "target")]

    target_dist: Dict[str, Any] = {}
    positive_rate = None
    if "target" in df.columns:
        total = df.height
        for row in df["target"].value_counts().iter_rows(named=True):
            label = str(row["target"])
            count = int(row["count"])
            target_dist[label] = {
                "count": count,
                "proportion": round(count / total, 6) if total else 0.0,
            }
            if label == "1":
                positive_rate = round(count / total, 6) if total else 0.0

    missing_cols = len(validation.get("missing_values", {}))
    if df.height == 0:
        quality_score = 0.0
    elif missing_cols == 0:
        quality_score = 1.0
    else:
        quality_score = round(max(0.5, 1.0 - missing_cols / max(len(df.columns), 1)), 4)

    return {
        "total_records": int(df.height),
        "total_features": len(feature_cols),
        "target_distribution": target_dist,
        "positive_class_rate": positive_rate,
        "quality_score": quality_score,
        "missing_value_columns": missing_cols,
        "source_file": "train.csv",
        "train_test_split": "80/20 stratified (hold-out test, seed=42)",
    }


def _load_drift_monitoring_payload() -> Optional[dict]:
    if not DRIFT_MONITORING_PATH.exists():
        return None
    try:
        return json.loads(DRIFT_MONITORING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_performance_metrics() -> dict:
    path = Path("training_results.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "roc_auc": data.get("test_auc", 0.0),
        "f1_score": data.get("test_f1", 0.0),
        "precision": data.get("test_precision", 0.0),
        "recall": data.get("test_recall", 0.0),
        "accuracy": data.get("test_accuracy", 0.0),
        "optimal_threshold": data.get("optimal_threshold", 0.5),
    }


def build_compliance_status(
    checks: Dict[str, bool],
    bias_audit: Dict[str, Any],
    governance_passed: Optional[bool] = None,
    robustness_passed: Optional[bool] = None,
    monitoring_passed: Optional[bool] = None,
) -> dict:
    """Map audit outputs to UI status strings (technical evidence, not a conformity decision)."""
    artifacts_ok = all(
        checks.get(k, False)
        for k in ("train_csv", "model", "feature_engineer", "training_results")
    )

    solvency = "✅ Evidence present" if artifacts_ok else "⚠️ Not Audited"

    if monitoring_passed is None:
        monitoring_passed = _load_monitoring_passed()
    if monitoring_passed is True:
        monitoring = "✅ Evidence present"
    elif monitoring_passed is False:
        monitoring = "⚠️ Review Required"
    else:
        monitoring = "⚠️ Not Audited"

    eu_ai_act_ok = (
        artifacts_ok
        and checks.get("optimal_threshold")
        and monitoring_passed is not None
        and monitoring_passed
    )
    eu_ai_act = "✅ Evidence present" if eu_ai_act_ok else (
        "⚠️ Review Required" if monitoring_passed is False or artifacts_ok else "⚠️ Not Audited"
    )

    demo = bias_audit.get("demographic_parity", {})
    bias_ok = bias_audit.get("overall_compliance", False)
    bias_evaluated = demo.get("overall_parity") is not None or demo.get("attribute_tests")

    if not bias_evaluated:
        fairness = "⚠️ Not Audited"
        responsible = "⚠️ Not Audited"
    elif bias_ok:
        fairness = "✅ Evidence present"
        responsible = "✅ Evidence present"
    else:
        fairness = "⚠️ Review Required"
        responsible = "⚠️ Review Required"

    transparency = "✅ Evidence present" if artifacts_ok else "⚠️ Not Audited"
    accountability = "✅ Evidence present" if artifacts_ok else "⚠️ Not Audited"

    if robustness_passed is None:
        robustness_passed = _load_robustness_passed()
    if robustness_passed is True:
        robustness = "✅ Evidence present"
    elif robustness_passed is False:
        robustness = "⚠️ Review Required"
    elif governance_passed is True:
        robustness = "✅ Evidence present"
    elif governance_passed is False:
        robustness = "⚠️ Review Required"
    else:
        robustness = "⚠️ Not Audited"

    # Demo Kaggle features are publisher-anonymised; not a Recital 26 / DPIA finding.
    privacy = "⚠️ Demo dataset — not a privacy determination"

    status = {
        "overall": "⚠️ Not Audited",
        "solvency_ii": solvency,
        "eu_ai_act": eu_ai_act,
        "responsible_ai": responsible,
        "fairness": fairness,
        "transparency": transparency,
        "accountability": accountability,
        "robustness": robustness,
        "monitoring": monitoring,
        "privacy": privacy,
        "last_audit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status_note": "Technical evidence labels only — not AEPD/GDPR/AI Act certification.",
    }

    pillars = [solvency, eu_ai_act, responsible, fairness, robustness, monitoring]
    if all("✅" in s for s in pillars):
        status["overall"] = "✅ Evidence present"
    elif any("⚠️" in s for s in pillars):
        status["overall"] = "⚠️ Review Required"
    else:
        status["overall"] = "❌ Gaps detected"
    return status


def _bias_audit_is_degenerate(bias_audit: dict) -> bool:
    """True when fairness metrics are vacuous (e.g. zero positive predictions everywhere)."""
    if bias_audit.get("audit_valid") is False:
        return True
    demo = bias_audit.get("demographic_parity", {}).get("attribute_tests", {})
    if not demo:
        return False
    total_positive_preds = 0
    for info in demo.values():
        for group in info.get("groups", {}).values():
            total_positive_preds += int(group.get("positive_count", 0))
    return total_positive_preds == 0


def bias_audit_to_dataframe(bias_audit: dict) -> pd.DataFrame:
    """Flatten bias audit attribute tests for Streamlit table."""
    rows = []
    demo = bias_audit.get("demographic_parity", {}).get("attribute_tests", {})
    eq = bias_audit.get("equalized_odds", {}).get("attribute_tests", {})
    degenerate = _bias_audit_is_degenerate(bias_audit)

    for attr_name, info in demo.items():
        eq_info = eq.get(attr_name, {})
        parity_ok = info.get("parity_met", False)
        eq_ok = eq_info.get("equality_met", False)
        if degenerate:
            status = "⚠️ Invalid (no positive predictions)"
        elif parity_ok and eq_ok:
            status = "✅ Pass"
        else:
            status = "⚠️ Review Required"
        rows.append(
            {
                "Protected Attribute": attr_name,
                "Demographic Parity Disparity": f"{info.get('max_difference', 0):.4f}",
                "Equal Opportunity Difference": (
                    f"TPR Δ {eq_info.get('tpr_difference', 0):.4f} / FPR Δ {eq_info.get('fpr_difference', 0):.4f}"
                ),
                "Status": status,
            }
        )

    if not rows:
        return pd.DataFrame(
            {
                "Protected Attribute": ["—"],
                "Demographic Parity Disparity": ["Not evaluated"],
                "Equal Opportunity Difference": ["—"],
                "Status": [bias_audit.get("status", "⚠️ No audit")],
            }
        )
    return pd.DataFrame(rows)


def run_full_compliance_audit(
    sample_size: int = 10000,
    run_governance_tests: bool = False,
) -> dict:
    """
    Execute bias audit + artifact checks and save docs/audit_results.json.
    """
    from src.data_processing.load_data_polars import load_porto_seguro_data
    from src.governance.bias_audit import comprehensive_bias_audit
    from src.governance.reporting_generator import generate_compliance_report
    from src.models.ebm_train import load_ebm_pipeline

    checks = _artifact_checks()
    if not checks["model"] or not checks["feature_engineer"] or not checks["train_csv"]:
        raise FileNotFoundError(
            "Missing artifacts. Run first: python run_training.py"
        )

    threshold = _load_optimal_threshold()
    model, feature_engineer = load_ebm_pipeline()
    expected_features = list(getattr(model, "feature_names_in_", []))
    if expected_features and expected_features[0].startswith("feature_"):
        raise RuntimeError(
            "Misaligned artifacts: the model expects synthetic columns "
            f"({expected_features[0]}, …) but data uses Porto Seguro (ps_*). "
            "Run `python run_training.py` to regenerate the model and feature engineer."
        )
    df = load_porto_seguro_data(".", sample_size=sample_size)

    if "target" not in df.columns:
        raise ValueError("Column 'target' not found in train.csv")

    y_series = df.select("target").to_series()
    id_cols = [c for c in ("id", "target") if c in df.columns]
    X_raw = df.drop(id_cols)
    protected = build_proxy_protected_attributes(X_raw)

    df_engineered = feature_engineer.transform(df)

    bias_audit = comprehensive_bias_audit(
        model=model,
        X_test=df_engineered,
        y_test=y_series,
        protected_attributes=protected,
        classification_threshold=threshold,
    )
    bias_audit["note"] = (
        "Audit uses proxies derived from anonymized features (Porto Seguro does not include "
        "real age/gender). Replace with real protected attributes in production."
    )
    bias_audit["classification_threshold"] = threshold
    bias_audit["proxy_attributes"] = True

    governance_passed = None
    if run_governance_tests:
        import subprocess

        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_governance.py", "-q"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        governance_passed = result.returncode == 0

    robustness_passed = _load_robustness_passed()
    monitoring_passed = _load_monitoring_passed()
    compliance_status = build_compliance_status(
        checks, bias_audit, governance_passed, robustness_passed, monitoring_passed
    )
    performance = _load_performance_metrics()
    training_data_info = build_training_data_info()
    drift_payload = _load_drift_monitoring_payload()

    conformity_report = generate_compliance_report(
        model_info={
            "name": "Porto Seguro Insurance Claim Prediction - EBM",
            "version": "1.0.0",
            "model_type": "Explainable Boosting Machine (EBM)",
            "framework": "Microsoft InterpretML",
            "architecture": "Polars + EBM",
        },
        performance_metrics=performance,
        training_data_info=training_data_info,
        explainability_report={
            "compliance_notes": {
                "global": "EBM native",
                "local": "EBM native",
                "interactions": "EBM native",
            }
        },
        data_quality_report={
            "quality_score": training_data_info.get("quality_score", 0.0),
            "records": training_data_info.get("total_records", 0),
            "target_distribution": training_data_info.get("target_distribution", {}),
        },
        bias_audit_results=bias_audit,
        drift_monitoring_results=drift_payload,
        validation_results={
            "governance_tests_passed": governance_passed,
            "robustness_passed": robustness_passed,
            "robustness_results": (
                json.loads(ROBUSTNESS_RESULTS_PATH.read_text(encoding="utf-8"))
                if ROBUSTNESS_RESULTS_PATH.exists()
                else None
            ),
        },
    )

    payload = {
        "audit_date": datetime.now().isoformat(),
        "compliance_status": compliance_status,
        "artifact_checks": checks,
        "bias_audit": bias_audit,
        "governance_tests_passed": governance_passed,
        "robustness_passed": robustness_passed,
        "monitoring_passed": monitoring_passed,
        "drift_monitoring": drift_payload,
        "conformity_report": conformity_report,
    }

    AUDIT_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    with open(COMPLIANCE_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(conformity_report, f, indent=2, default=str)

    return payload


def load_saved_audit_results() -> Optional[dict]:
    if not AUDIT_RESULTS_PATH.exists():
        return None
    with open(AUDIT_RESULTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
