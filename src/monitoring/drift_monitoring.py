"""
Drift Monitoring Module
Part of Insurance Claim Prediction - Responsible AI Architecture

Polars-native data processing; scipy KS only on exported numpy slices.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

import numpy as np
import polars as pl
from scipy import stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FrameLike = Union[pl.DataFrame, pl.LazyFrame]


def _ensure_dataframe(data: FrameLike) -> pl.DataFrame:
    if isinstance(data, pl.LazyFrame):
        return data.collect()
    return data


_NUMERIC_DTYPES = (
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
)


def _numeric_feature_columns(df: pl.DataFrame) -> List[str]:
    return [
        name
        for name, dtype in zip(df.columns, df.dtypes)
        if dtype in _NUMERIC_DTYPES and name not in {"id", "target"}
    ]


def detect_data_drift(
    reference_data: FrameLike,
    current_data: FrameLike,
    threshold: float = 0.1,
) -> Dict:
    """
    Detect data drift between reference and current data using Polars + KS test.

    Args:
        reference_data: Reference dataset (training or baseline)
        current_data: Current production data
        threshold: KS statistic threshold per feature (default: 0.1)

    Returns:
        dict: Data drift detection results
    """
    logger.info("Detecting data drift (Polars-native)")

    ref_df = _ensure_dataframe(reference_data)
    curr_df = _ensure_dataframe(current_data)

    results: Dict = {
        "drift_detected": False,
        "drift_score": 0.0,
        "feature_drifts": {},
        "overall_drift": False,
        "recommendations": [],
    }

    drift_scores: List[float] = []
    numerical_cols = _numeric_feature_columns(ref_df)

    for col in numerical_cols:
        if col not in curr_df.columns:
            continue

        ref_series = (
            ref_df.select(pl.col(col).cast(pl.Float64, strict=False))
            .filter(pl.col(col).is_not_null())
            .to_series()
        )
        curr_series = (
            curr_df.select(pl.col(col).cast(pl.Float64, strict=False))
            .filter(pl.col(col).is_not_null())
            .to_series()
        )

        if ref_series.len() == 0 or curr_series.len() == 0:
            continue

        try:
            ref_values = ref_series.to_numpy()
            curr_values = curr_series.to_numpy()
            ks_statistic, p_value = stats.ks_2samp(ref_values, curr_values)
            drift_score = float(ks_statistic)

            results["feature_drifts"][col] = {
                "drift_score": drift_score,
                "ks_statistic": drift_score,
                "p_value": float(p_value),
                "drift_detected": drift_score > threshold,
                "reference_n": int(ref_series.len()),
                "current_n": int(curr_series.len()),
            }
            drift_scores.append(drift_score)
        except Exception as exc:
            logger.warning("Error calculating drift for %s: %s", col, exc)

    if drift_scores:
        results["drift_score"] = float(np.mean(drift_scores))
        results["drift_detected"] = results["drift_score"] > threshold
        results["overall_drift"] = results["drift_detected"]

    if results["drift_detected"]:
        results["recommendations"].append(
            "Data drift detected. Consider: "
            "1) Retraining model with new data, "
            "2) Investigating cause of drift, "
            "3) Updating feature engineering pipeline"
        )

    return results


def detect_model_drift(
    reference_performance: Dict[str, float],
    current_performance: Dict[str, float],
    threshold: float = 0.05,
) -> Dict:
    """
    Detect model performance degradation (improvements do NOT trigger drift).

    Drift is raised only when a metric **drops** beyond the relative threshold.
    """
    logger.info("Detecting model performance drift (degradation-only)")

    results: Dict = {
        "drift_detected": False,
        "metric_changes": {},
        "recommendations": [],
    }

    key_metrics = ["roc_auc", "f1_score", "precision", "recall"]

    for metric in key_metrics:
        if metric not in reference_performance or metric not in current_performance:
            continue

        ref_val = float(reference_performance[metric])
        curr_val = float(current_performance[metric])

        if ref_val == 0:
            relative_change = 0.0 if curr_val == 0 else -1.0
        else:
            relative_change = (curr_val - ref_val) / ref_val

        # Degradation: current below reference by more than threshold (relative drop)
        degraded = relative_change < -threshold

        results["metric_changes"][metric] = {
            "reference": ref_val,
            "current": curr_val,
            "absolute_change": float(curr_val - ref_val),
            "relative_change": float(relative_change),
            "drift_detected": degraded,
            "direction": "degraded" if degraded else ("improved" if relative_change > 0 else "stable"),
        }

        if degraded:
            results["drift_detected"] = True

    if results["drift_detected"]:
        results["recommendations"].append(
            "Model performance degradation detected. Consider: "
            "1) Immediate model retraining, "
            "2) Investigating root cause, "
            "3) Reviewing data quality"
        )

    return results


def continuous_drift_monitoring(
    reference_data: FrameLike,
    reference_performance: Dict[str, float],
    current_data: FrameLike,
    current_performance: Dict[str, float],
    data_drift_threshold: float = 0.1,
    model_drift_threshold: float = 0.05,
) -> Dict:
    """Perform continuous drift monitoring (data + model)."""
    logger.info("Performing continuous drift monitoring")

    results: Dict = {
        "monitoring_date": datetime.now().isoformat(),
        "data_drift": {},
        "model_drift": {},
        "overall_status": "healthy",
        "alerts": [],
    }

    results["data_drift"] = detect_data_drift(
        reference_data,
        current_data,
        threshold=data_drift_threshold,
    )
    results["model_drift"] = detect_model_drift(
        reference_performance,
        current_performance,
        threshold=model_drift_threshold,
    )

    if results["data_drift"]["drift_detected"] or results["model_drift"]["drift_detected"]:
        results["overall_status"] = "drift_detected"
        results["alerts"].append("Drift detected - action required")
    else:
        results["overall_status"] = "healthy"

    return results
