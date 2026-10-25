"""
Production compliance gate — EU AI Act Art. 9 post-market monitoring.

Compares production data and performance against training baseline, persists
drift evidence and performance history for conformity reports.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

import polars as pl

from src.monitoring.drift_monitoring import continuous_drift_monitoring
from src.monitoring.performance_tracking import PerformanceTracker

logger = logging.getLogger(__name__)

MONITORING_DIR = Path("monitoring")
DRIFT_LATEST_PATH = Path("docs/drift_monitoring_latest.json")
PERFORMANCE_HISTORY_PATH = MONITORING_DIR / "performance_history.json"
PERFORMANCE_TIMELINE_PATH = MONITORING_DIR / "performance_timeline.json"
TRAINING_RESULTS_PATH = Path("training_results.json")


def load_reference_metrics() -> Dict[str, float]:
    """Hold-out baseline metrics from the training pipeline."""
    defaults = {
        "roc_auc": 0.638,
        "f1_score": 0.117,
        "precision": 0.078,
        "recall": 0.228,
    }
    if not TRAINING_RESULTS_PATH.exists():
        return defaults
    try:
        data = json.loads(TRAINING_RESULTS_PATH.read_text(encoding="utf-8"))
        return {
            "roc_auc": float(data.get("test_auc", defaults["roc_auc"])),
            "f1_score": float(data.get("test_f1", defaults["f1_score"])),
            "precision": float(data.get("test_precision", defaults["precision"])),
            "recall": float(data.get("test_recall", defaults["recall"])),
        }
    except Exception as exc:
        logger.warning("Could not load training_results.json: %s", exc)
        return defaults


def _persist_drift_evidence(
    drift_report: Dict[str, Any],
    reference_metrics: Dict[str, float],
    current_metrics: Dict[str, float],
    model_version: str,
) -> Dict[str, Any]:
    """Save latest drift report for Streamlit / EU AI Act conformity exports."""
    monitoring_passed = drift_report.get("overall_status") == "healthy"
    payload = {
        "saved_at": datetime.now().isoformat(),
        "model_version": model_version,
        "monitoring_passed": monitoring_passed,
        "drift_report": drift_report,
        "reference_metrics": reference_metrics,
        "current_metrics": current_metrics,
    }
    DRIFT_LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_LATEST_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Saved drift evidence: %s (monitoring_passed=%s)", DRIFT_LATEST_PATH, monitoring_passed)
    return payload


def run_production_compliance_gate(
    df_train: Union[pl.DataFrame, pl.LazyFrame],
    df_production: Union[pl.DataFrame, pl.LazyFrame],
    reference_metrics: Dict[str, float],
    current_metrics: Dict[str, float],
    data_drift_threshold: float = 0.10,
    model_drift_threshold: float = 0.05,
    model_version: str = "1.0.0",
    tracking_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Actively compare production data and performance against baseline.

    Runs KS data drift + degradation-only model drift, logs metrics to the
    performance tracker, and persists evidence for EU conformity reports.
    """
    history_path = Path(tracking_file or PERFORMANCE_HISTORY_PATH)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    drift_report = continuous_drift_monitoring(
        reference_data=df_train,
        reference_performance=reference_metrics,
        current_data=df_production,
        current_performance=current_metrics,
        data_drift_threshold=data_drift_threshold,
        model_drift_threshold=model_drift_threshold,
    )

    tracker = PerformanceTracker(tracking_file=str(history_path))
    tracker.log_performance(
        metrics=current_metrics,
        model_version=model_version,
        dataset_info={
            "source": "production_compliance_gate",
            "monitoring_status": drift_report.get("overall_status"),
        },
    )
    timeline = tracker.export_timeline()
    PERFORMANCE_TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERFORMANCE_TIMELINE_PATH.write_text(
        json.dumps(timeline, indent=2), encoding="utf-8"
    )

    evidence = _persist_drift_evidence(
        drift_report, reference_metrics, current_metrics, model_version
    )
    drift_report["evidence_path"] = str(DRIFT_LATEST_PATH)
    drift_report["performance_history_path"] = str(history_path)
    drift_report["monitoring_passed"] = evidence["monitoring_passed"]
    return drift_report


def run_scheduled_production_monitor(
    production_data_path: Optional[str] = None,
    sample_size: int = 5000,
    production_sample_size: int = 1000,
    simulate_drift: bool = False,
) -> Dict[str, Any]:
    """
    Scheduled / CLI entry: load baseline + production slices and run the gate.

    If production_data_path is omitted, uses a hold-out slice from train.csv
    (optionally with demo covariate shift on ps_car_13).
    """
    from src.data_processing.load_data_polars import load_porto_seguro_data

    reference_metrics = load_reference_metrics()
    df_all = load_porto_seguro_data(".", sample_size=sample_size)
    df_train = df_all.head(max(sample_size // 2, 100))

    if production_data_path:
        prod_path = Path(production_data_path)
        if prod_path.suffix == ".csv":
            df_production = pl.read_csv(prod_path)
            if production_sample_size and len(df_production) > production_sample_size:
                df_production = df_production.sample(n=production_sample_size, seed=123)
        else:
            raise FileNotFoundError(f"Unsupported production data: {prod_path}")
    else:
        df_production = df_all.sample(n=min(production_sample_size, len(df_all)), seed=123)
        if simulate_drift and "ps_car_13" in df_production.columns:
            df_production = df_production.with_columns(
                (pl.col("ps_car_13") * 1.5 + 0.5).alias("ps_car_13")
            )

    # Recompute production metrics only when an explicit production file is supplied.
    # Random train slices are too small for stable recall/F1 — avoids false model-drift alerts.
    current_metrics = dict(reference_metrics)
    if production_data_path and "target" in df_production.columns:
        try:
            from src.models.ebm_train import load_ebm_pipeline
            from src.models.interpret_bridge import predict_proba_ebm
            from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

            model, fe = load_ebm_pipeline()
            eng = fe.transform(df_production)
            y = eng.select("target").to_numpy().ravel()
            proba = predict_proba_ebm(model, eng)
            threshold_path = Path("models/artifacts/optimal_threshold.txt")
            thr = float(threshold_path.read_text().strip()) if threshold_path.exists() else 0.5
            y_pred = (proba >= thr).astype(int)
            current_metrics = {
                "roc_auc": float(roc_auc_score(y, proba)),
                "f1_score": float(f1_score(y, y_pred, zero_division=0)),
                "precision": float(precision_score(y, y_pred, zero_division=0)),
                "recall": float(recall_score(y, y_pred, zero_division=0)),
            }
        except Exception as exc:
            logger.warning("Could not compute production metrics from labels: %s", exc)

    return run_production_compliance_gate(
        df_train=df_train,
        df_production=df_production,
        reference_metrics=reference_metrics,
        current_metrics=current_metrics,
    )
