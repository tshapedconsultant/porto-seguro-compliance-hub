"""
Data loading utilities for Streamlit multi-page app.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st


def _resolve_model_paths() -> tuple[Path, Path]:
    model_path = Path("models/artifacts/ebm_model_v1.pkl")
    feature_engineer_path = Path("models/artifacts/feature_engineer_v1.pkl")
    if not model_path.exists():
        model_path = Path("models/ebm_model.pkl")
    if not feature_engineer_path.exists():
        feature_engineer_path = Path("models/feature_engineer.pkl")
    return model_path, feature_engineer_path


@st.cache_data
def load_model_info() -> dict:
    current_date = datetime.now().strftime("%Y-%m-%d")
    model_info = {
        "model_type": "Explainable Boosting Machine (EBM)",
        "version": "1.0.0",
        "framework": "Microsoft InterpretML",
        "training_date": current_date,
        "architecture": "Polars (data processing) + EBM (modeling)",
    }

    try:
        model_card_path = Path("docs/model_card.json")
        if model_card_path.exists():
            with open(model_card_path, "r", encoding="utf-8") as f:
                loaded_info = json.load(f)
            if "model_details" in loaded_info:
                model_info.update(loaded_info["model_details"])
                if "date" in loaded_info["model_details"]:
                    model_info["training_date"] = loaded_info["model_details"]["date"]
    except Exception:
        pass

    try:
        model_path, _ = _resolve_model_paths()
        if model_path.exists():
            mod_time = os.path.getmtime(model_path)
            model_info["training_date"] = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d")
    except Exception:
        pass

    return model_info


def training_results_mtime() -> float:
    """Modification time of training_results.json for Streamlit cache busting."""
    path = Path("training_results.json")
    return path.stat().st_mtime if path.exists() else 0.0


def threshold_optimization_mtime() -> float:
    """Modification time of threshold_optimization_results.json (confusion matrix source)."""
    path = Path("threshold_optimization_results.json")
    return path.stat().st_mtime if path.exists() else 0.0


def performance_metrics_mtime() -> float:
    """Combined mtime so cache refreshes when either metrics or threshold CM file changes."""
    return max(training_results_mtime(), threshold_optimization_mtime())


@st.cache_data
def load_performance_metrics(_cache_key: float = 0.0) -> dict:
    """
    Load hold-out test metrics from training_results.json (single source of truth).

    Confusion matrix (tn/fp/fn/tp) is loaded from threshold_optimization_results.json
    when present — same hold-out test and optimal threshold as find_optimal_threshold.py.

    _cache_key must be performance_metrics_mtime() so Streamlit refreshes after retrain
    or re-running threshold optimization.
    """
    _ = _cache_key
    metrics = {
        "roc_auc": 0.5,
        "f1_score": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "accuracy": 0.96,
        "optimal_threshold": 0.5,
        "source_file": None,
        "source_mtime": None,
    }

    results_path = Path("training_results.json")
    if results_path.exists():
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            test_f1 = data.get("test_f1", 0.0)
            test_precision = data.get("test_precision", 0.0)
            test_recall = data.get("test_recall", 0.0)
            if test_f1 == 0.0 and test_precision > 0 and test_recall > 0:
                test_f1 = 2 * (test_precision * test_recall) / (test_precision + test_recall)

            metrics.update(
                {
                    "roc_auc": data.get("test_auc", 0.5),
                    "f1_score": test_f1,
                    "precision": test_precision,
                    "recall": test_recall,
                    "train_auc": data.get("train_auc", 0.5),
                    "optimal_threshold": data.get("optimal_threshold", 0.5),
                    "f1_score_default_threshold": data.get("test_f1_default", 0.0),
                    "brier_score": data.get("brier_score"),
                    "calibration_plot": data.get("paths", {}).get("calibration_plot")
                    if isinstance(data.get("paths"), dict)
                    else None,
                    "source_file": str(results_path),
                    "source_mtime": datetime.fromtimestamp(
                        results_path.stat().st_mtime
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            if data.get("test_accuracy") is not None:
                metrics["accuracy"] = data["test_accuracy"]
        except Exception as exc:
            st.warning(f"Error loading training_results.json: {exc}")

    threshold_path = Path("threshold_optimization_results.json")
    if threshold_path.exists():
        try:
            with open(threshold_path, "r", encoding="utf-8") as f:
                threshold_data = json.load(f)
            cm = threshold_data.get("confusion_matrix")
            if isinstance(cm, dict) and all(k in cm for k in ("tn", "fp", "fn", "tp")):
                metrics["confusion_matrix"] = {
                    "tn": int(cm["tn"]),
                    "fp": int(cm["fp"]),
                    "fn": int(cm["fn"]),
                    "tp": int(cm["tp"]),
                }
                metrics["confusion_matrix_source"] = str(threshold_path)
        except Exception as exc:
            st.warning(f"Error loading threshold_optimization_results.json: {exc}")

    return metrics


def audit_results_mtime() -> float:
    path = Path("docs/audit_results.json")
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data
def load_compliance_status(_cache_key: float = 0.0) -> dict:
    """Load persisted compliance status from docs/audit_results.json."""
    _ = _cache_key
    default_status = {
        "overall": "⚠️ Not Audited",
        "solvency_ii": "⚠️ Not Audited",
        "eu_ai_act": "⚠️ Not Audited",
        "responsible_ai": "⚠️ Not Audited",
        "fairness": "⚠️ Not Audited",
        "transparency": "⚠️ Not Audited",
        "accountability": "⚠️ Not Audited",
        "robustness": "⚠️ Not Audited",
        "monitoring": "⚠️ Not Audited",
        "privacy": "⚠️ Not Audited",
        "last_audit": None,
        "audit_pending": True,
    }

    audit_file = Path("docs/audit_results.json")
    if audit_file.exists():
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                audit_data = json.load(f)
            if "compliance_status" in audit_data:
                default_status.update(audit_data["compliance_status"])
                default_status["audit_pending"] = False
        except Exception as exc:
            st.warning(f"Could not read audit_results.json: {exc}")

    # Overlay robustness / monitoring from persisted pipeline artifacts
    from utils.compliance_audit import _load_monitoring_passed, _load_robustness_passed

    robustness_passed = _load_robustness_passed()
    if robustness_passed is True:
        default_status["robustness"] = "✅ Evidence present"
    elif robustness_passed is False:
        default_status["robustness"] = "⚠️ Review Required"

    monitoring_passed = _load_monitoring_passed()
    if monitoring_passed is True:
        default_status["monitoring"] = "✅ Evidence present"
        if default_status.get("eu_ai_act", "").startswith("⚠️"):
            default_status["eu_ai_act"] = "✅ Evidence present"
    elif monitoring_passed is False:
        default_status["monitoring"] = "⚠️ Review Required"

    # Never surface legacy "Compliant" strings as a conformity decision.
    for key, value in list(default_status.items()):
        if isinstance(value, str) and "Compliant" in value:
            default_status[key] = value.replace("Non-Compliant", "Gaps detected").replace(
                "Compliant", "Evidence present"
            )

    default_status.setdefault(
        "status_note",
        "Technical evidence labels only — not AEPD/GDPR/AI Act certification.",
    )
    return default_status


@st.cache_data
def load_bias_audit_results() -> dict | None:
    audit_file = Path("docs/audit_results.json")
    if not audit_file.exists():
        return None
    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("bias_audit")
    except Exception:
        return None


@st.cache_data
def resolve_shadow_monitor_paths() -> dict:
    model_path, feature_engineer_path = _resolve_model_paths()
    return {
        "train_csv": Path("train.csv"),
        "model_path": model_path,
        "feature_engineer_path": feature_engineer_path,
        "performance_history_path": Path("monitoring/performance_timeline.json"),
    }
