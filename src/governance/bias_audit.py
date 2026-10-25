"""
Bias Audit Module — Polars-segregated confusion matrices; chi-square only when valid.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import polars as pl
from scipy import stats

from src.models.interpret_bridge import predict_proba_ebm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_CHI2_CELL_COUNT = 5


def _chi2_test_if_valid(contingency_rows: List[List[int]]) -> Dict[str, Any]:
    """Run chi-square only when all marginal cell counts are statistically adequate."""
    if len(contingency_rows) < 2:
        return {"skipped": True, "reason": "fewer than two groups"}

    for row in contingency_rows:
        if sum(row) < MIN_CHI2_CELL_COUNT:
            return {"skipped": True, "reason": "insufficient group sample size"}

    try:
        chi2, p_value, _dof, expected = stats.chi2_contingency(contingency_rows)
        if np.any(expected < MIN_CHI2_CELL_COUNT):
            return {"skipped": True, "reason": "expected cell frequencies below minimum"}
        return {
            "skipped": False,
            "chi2_statistic": float(chi2),
            "p_value": float(p_value),
            "significant": bool(p_value < 0.05),
        }
    except Exception as exc:
        logger.warning("Chi-square test failed: %s", exc)
        return {"skipped": True, "reason": str(exc)}


def _build_audit_frame(
    y_true: pl.Series,
    y_pred_proba: np.ndarray,
    protected_attributes: Dict[str, np.ndarray],
    classification_threshold: float,
) -> pl.DataFrame:
    y_pred_bin = (y_pred_proba >= classification_threshold).astype(np.int8)
    data: Dict[str, Any] = {
        "y_true": y_true.to_numpy().ravel().astype(np.int8),
        "y_pred": y_pred_bin,
        "y_score": y_pred_proba.astype(np.float64),
    }
    for name, values in protected_attributes.items():
        data[name] = values
    return pl.DataFrame(data)


def _group_confusion_metrics(audit_df: pl.DataFrame, group_col: str) -> pl.DataFrame:
    return audit_df.group_by(group_col).agg(
        pl.len().alias("n"),
        ((pl.col("y_pred") == 1) & (pl.col("y_true") == 1)).sum().alias("tp"),
        ((pl.col("y_pred") == 1) & (pl.col("y_true") == 0)).sum().alias("fp"),
        ((pl.col("y_pred") == 0) & (pl.col("y_true") == 0)).sum().alias("tn"),
        ((pl.col("y_pred") == 0) & (pl.col("y_true") == 1)).sum().alias("fn"),
        (pl.col("y_pred") == 1).sum().alias("pred_positive"),
    )


def demographic_parity_test(
    audit_df: pl.DataFrame,
    protected_attributes: Dict[str, np.ndarray],
    threshold: float = 0.1,
) -> Dict[str, Any]:
    """Demographic parity using Polars group aggregations."""
    logger.info("Performing demographic parity test (Polars)")

    results: Dict[str, Any] = {
        "overall_parity": True,
        "attribute_tests": {},
        "violations": [],
        "recommendations": [],
    }

    for attr_name in protected_attributes:
        grouped = _group_confusion_metrics(audit_df, attr_name)
        attr_results: Dict[str, Any] = {
            "attribute": attr_name,
            "groups": {},
            "parity_met": True,
            "max_difference": 0.0,
            "statistical_test": {},
        }
        contingency: List[List[int]] = []
        rates: List[float] = []

        for row in grouped.iter_rows(named=True):
            group_key = str(row[attr_name])
            n = int(row["n"])
            pred_pos = int(row["pred_positive"])
            positive_rate = pred_pos / n if n else 0.0
            attr_results["groups"][group_key] = {
                "positive_rate": float(positive_rate),
                "sample_size": n,
                "positive_count": pred_pos,
            }
            rates.append(positive_rate)
            contingency.append([pred_pos, n - pred_pos])

        if len(rates) > 1:
            max_diff = max(rates) - min(rates)
            attr_results["max_difference"] = float(max_diff)
            if max_diff > threshold:
                attr_results["parity_met"] = False
                results["overall_parity"] = False
                results["violations"].append(
                    {"attribute": attr_name, "max_difference": float(max_diff), "threshold": threshold}
                )

        attr_results["statistical_test"] = _chi2_test_if_valid(contingency)
        results["attribute_tests"][attr_name] = attr_results

    if not results["overall_parity"]:
        results["recommendations"].append(
            "Demographic parity violations detected. Review training data, thresholds, or fairness constraints."
        )

    return results


def equalized_odds_test(
    audit_df: pl.DataFrame,
    protected_attributes: Dict[str, np.ndarray],
    threshold: float = 0.1,
) -> Dict[str, Any]:
    """Equalized odds (TPR/FPR parity) via Polars-segregated confusion matrices."""
    logger.info("Performing equalized odds test (Polars)")

    results: Dict[str, Any] = {
        "overall_equality": True,
        "attribute_tests": {},
        "violations": [],
    }

    for attr_name in protected_attributes:
        grouped = _group_confusion_metrics(audit_df, attr_name)
        attr_results: Dict[str, Any] = {
            "attribute": attr_name,
            "groups": {},
            "equality_met": True,
            "tpr_difference": 0.0,
            "fpr_difference": 0.0,
        }
        tprs: List[float] = []
        fprs: List[float] = []

        for row in grouped.iter_rows(named=True):
            group_key = str(row[attr_name])
            tp, fp, tn, fn = int(row["tp"]), int(row["fp"]), int(row["tn"]), int(row["fn"])
            tpr = tp / (tp + fn) if (tp + fn) else 0.0
            fpr = fp / (fp + tn) if (fp + tn) else 0.0
            attr_results["groups"][group_key] = {
                "tpr": float(tpr),
                "fpr": float(fpr),
                "sample_size": int(row["n"]),
                "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
            }
            tprs.append(tpr)
            fprs.append(fpr)

        if len(tprs) > 1:
            tpr_diff = max(tprs) - min(tprs)
            fpr_diff = max(fprs) - min(fprs)
            attr_results["tpr_difference"] = float(tpr_diff)
            attr_results["fpr_difference"] = float(fpr_diff)
            if tpr_diff > threshold or fpr_diff > threshold:
                attr_results["equality_met"] = False
                results["overall_equality"] = False
                results["violations"].append(
                    {
                        "attribute": attr_name,
                        "tpr_difference": float(tpr_diff),
                        "fpr_difference": float(fpr_diff),
                    }
                )

        results["attribute_tests"][attr_name] = attr_results

    return results


def comprehensive_bias_audit(
    model: Any,
    X_test: Union[pl.DataFrame, np.ndarray],
    y_test: Union[pl.Series, np.ndarray],
    protected_attributes: Optional[Dict[str, np.ndarray]] = None,
    classification_threshold: float = 0.5,
) -> Dict[str, Any]:
    """Comprehensive bias audit with Polars-native segregation."""
    logger.info("Performing comprehensive bias audit")

    if protected_attributes is None:
        logger.warning("Protected attributes missing. Bias audit not evaluated.")
        return {
            "audit_date": datetime.now().isoformat(),
            "demographic_parity": {"status": "Not Evaluated"},
            "equalized_odds": {"status": "Not Evaluated"},
            "overall_compliance": False,
            "status": "Not Evaluated",
            "error": "Real protected attributes are required to run the bias audit.",
        }

    if isinstance(X_test, pl.DataFrame):
        y_pred_proba = predict_proba_ebm(model, X_test)
        y_series = (
            y_test
            if isinstance(y_test, pl.Series)
            else pl.Series("y_true", np.asarray(y_test).ravel())
        )
    else:
        import pandas as pd

        X_pd = pd.DataFrame(X_test)
        y_pred_proba = np.asarray(model.predict_proba(X_pd)[:, 1], dtype=np.float64)
        y_series = pl.Series("y_true", np.asarray(y_test).ravel())

    audit_df = _build_audit_frame(y_series, y_pred_proba, protected_attributes, classification_threshold)

    y_pred_bin = (y_pred_proba >= classification_threshold).astype(np.int8)
    n_positive_preds = int(y_pred_bin.sum())
    n_unique_scores = int(np.unique(np.round(y_pred_proba, 8)).size)
    audit_valid = n_positive_preds > 0 and n_unique_scores > 1

    demo = demographic_parity_test(audit_df, protected_attributes, threshold=0.1)
    eq = equalized_odds_test(audit_df, protected_attributes, threshold=0.1)

    result: Dict[str, Any] = {
        "audit_date": datetime.now().isoformat(),
        "demographic_parity": demo,
        "equalized_odds": eq,
        "overall_compliance": bool(
            audit_valid and demo["overall_parity"] and eq["overall_equality"]
        ),
        "classification_threshold": classification_threshold,
        "audit_valid": audit_valid,
        "prediction_summary": {
            "positive_prediction_rate": float(n_positive_preds / len(y_pred_bin)),
            "unique_score_count": n_unique_scores,
        },
    }
    if not audit_valid:
        result["status"] = "⚠️ Invalid audit"
        result["error"] = (
            "The model predicts the same probability for every row or no positives "
            "at the current threshold. This usually indicates misaligned artifacts (model vs "
            "feature engineer) or an incorrect threshold — do not interpret 0.000 as real fairness."
        )
    return result
