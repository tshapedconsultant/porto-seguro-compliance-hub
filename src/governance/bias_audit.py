"""
Bias Audit Module — Polars-segregated confusion matrices; chi-square only when valid.

Screening language is technical, not a fairness certification or GDPR finding.
Observed difference, statistical significance, the 10% governance gate, and any
business decision are recorded as separate layers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import polars as pl
from scipy import stats

from src.models.interpret_bridge import predict_proba_ebm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_CHI2_CELL_COUNT = 5
MIN_INTERSECTION_N = 30
SIGNIFICANCE_ALPHA = 0.05
# Absolute rate-difference screen. Not a legal or AEPD threshold.
GOVERNANCE_THRESHOLD = 0.10
# 80% of the gate (8pp): close enough that a binary "pass" is not defensible.
NEAR_THRESHOLD_RATIO = 0.80
# Watch-band: material enough to report even if not significant and not near the gate.
MONITOR_BAND = 0.03

SCREENING_RESULTS = ("pass", "pass_with_review", "monitor", "fail")

GOVERNANCE_THRESHOLD_POLICY: Dict[str, Any] = {
    "value": GOVERNANCE_THRESHOLD,
    "unit": "absolute_difference_in_group_rates",
    "metrics": [
        "demographic_parity_positive_rate",
        "equalized_odds_tpr",
        "equalized_odds_fpr",
    ],
    "origin": "internal_screening_heuristic",
    "source": (
        "Common configurable 10 percentage-point absolute-difference screen in ML "
        "fairness toolkits (e.g. Fairlearn/Aequitas-style dashboards). It is not the "
        "US EEOC four-fifths *ratio* rule, not an EDPB/AEPD metric, and not a GDPR "
        "Art. 5(1)(a) test."
    ),
    "justification": (
        "A 0.10 absolute gap is used only as a governance *gate* so large disparities "
        "are never silent. Gaps below 0.10 can still be statistically significant or "
        "operationally material; those cases are pass_with_review or monitor, not pass. "
        "Crossing 0.10 is fail for this screen only — not a legal finding of discrimination."
    ),
    "not_a_legal_threshold": True,
    "pass_does_not_mean_no_disparity": True,
    "significance_alpha": SIGNIFICANCE_ALPHA,
    "near_threshold": round(GOVERNANCE_THRESHOLD * NEAR_THRESHOLD_RATIO, 4),
    "monitor_band": MONITOR_BAND,
}

LAYER_DEFINITIONS: Dict[str, str] = {
    "observed_difference": "Always reported (max group rate − min group rate).",
    "statistical_significance": (
        f"Chi-square on the relevant 2×K table when cell counts allow; "
        f"p < {SIGNIFICANCE_ALPHA} ⇒ statistically_significant=true. Independent of the 10% gate."
    ),
    "governance_threshold": (
        "Internal 10pp absolute screen (see governance_threshold policy). "
        "threshold_met is not a fairness certificate."
    ),
    "business_decision": (
        "Not inferred by this module. overall_assessment is screening only; "
        "deployment, pricing, or threshold changes require a named owner."
    ),
}


def classify_screening_result(
    observed_difference: float,
    statistically_significant: bool,
    threshold: float = GOVERNANCE_THRESHOLD,
) -> str:
    """
    Map numbers to a screening label. Does not take a business decision.

    fail              → observed gap exceeds the governance gate
    pass_with_review  → gate met, but significant or within 20% of the gate
    monitor           → smaller material gap, not significant
    pass              → below the watch-band and not significant
    """
    observed = abs(float(observed_difference))
    if observed > threshold:
        return "fail"
    near = threshold * NEAR_THRESHOLD_RATIO
    if statistically_significant or observed >= near:
        return "pass_with_review"
    if observed >= MONITOR_BAND:
        return "monitor"
    return "pass"


def _worse_screening(*statuses: str) -> str:
    rank = {"pass": 0, "monitor": 1, "pass_with_review": 2, "fail": 3}
    return max(statuses, key=lambda s: rank.get(s, 0))


def derive_overall_assessment(
    screening_results: Sequence[str],
    *,
    audit_valid: bool,
    proxy_attributes: bool,
) -> str:
    """
    overall_assessment is never a silent pass.

    review_required — fail, pass_with_review, invalid audit, or proxy-only screen
    conditional     — governance gate held, only pass/monitor remain
    """
    if not audit_valid:
        return "review_required"
    worst = _worse_screening(*(screening_results or ("pass_with_review",)))
    if worst in {"fail", "pass_with_review"} or proxy_attributes:
        return "review_required"
    return "conditional"


def _chi2_test_if_valid(contingency_rows: List[List[int]]) -> Dict[str, Any]:
    """Run chi-square only when all marginal cell counts are statistically adequate."""
    if len(contingency_rows) < 2:
        return {"skipped": True, "reason": "fewer than two groups", "significant": False}

    for row in contingency_rows:
        if sum(row) < MIN_CHI2_CELL_COUNT:
            return {"skipped": True, "reason": "insufficient group sample size", "significant": False}

    try:
        chi2, p_value, _dof, expected = stats.chi2_contingency(contingency_rows)
        if np.any(expected < MIN_CHI2_CELL_COUNT):
            return {"skipped": True, "reason": "expected cell frequencies below minimum", "significant": False}
        return {
            "skipped": False,
            "chi2_statistic": float(chi2),
            "p_value": float(p_value),
            "significant": bool(p_value < SIGNIFICANCE_ALPHA),
        }
    except Exception as exc:
        logger.warning("Chi-square test failed: %s", exc)
        return {"skipped": True, "reason": str(exc), "significant": False}


def _ece_numpy(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> Optional[float]:
    """Bin-wise |confidence − accuracy|. Technical metric only."""
    y_true = np.asarray(y_true).ravel().astype(float)
    y_score = np.asarray(y_score).ravel().astype(float)
    n = len(y_true)
    if n < n_bins:
        return None
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (y_score >= lo) & (y_score <= hi if i == n_bins - 1 else y_score < hi)
        if not np.any(mask):
            continue
        ece += (np.sum(mask) / n) * abs(float(np.mean(y_true[mask])) - float(np.mean(y_score[mask])))
    return float(ece)


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
        pl.col("y_true").mean().alias("observed_rate"),
        pl.col("y_score").mean().alias("mean_score"),
    )


def _impact_from_groups(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Potential harm analogue: extra flags vs the lowest predicted-positive group."""
    if not groups:
        return {"status": "not_computed"}
    rates: Dict[str, float] = {}
    for name, info in groups.items():
        n = int(info.get("sample_size") or info.get("n") or 0)
        if n <= 0:
            continue
        if "positive_rate" in info:
            rates[name] = float(info["positive_rate"])
        else:
            cm = info.get("confusion_matrix") or {}
            rates[name] = (int(cm.get("tp", 0)) + int(cm.get("fp", 0))) / n
    if len(rates) < 2:
        return {"status": "not_computed", "reason": "fewer than two groups"}
    high = max(rates, key=rates.get)
    low = min(rates, key=rates.get)
    n_high = int(groups[high].get("sample_size") or groups[high].get("n") or 0)
    extra_flags = (rates[high] - rates[low]) * n_high
    ratio = (rates[high] / rates[low]) if rates[low] > 0 else None
    per_group = {
        name: {
            "positive_prediction_rate": float(rate),
            "approval_rate_analogue": float(1.0 - rate),
            "sample_size": int(groups[name].get("sample_size") or groups[name].get("n") or 0),
        }
        for name, rate in rates.items()
    }
    return {
        "status": "computed",
        "highest_positive_rate_group": high,
        "lowest_positive_rate_group": low,
        "positive_rate_ratio": None if ratio is None else float(ratio),
        "extra_flags_vs_lowest_group": float(extra_flags),
        "groups": per_group,
        "potential_harm": (
            f"Group '{high}' is flagged positive {rates[high] - rates[low]:.2%} more often "
            f"than '{low}' (~{extra_flags:.0f} extra flags on n={n_high}). In an underwriting "
            "analogue this can mean tighter terms; this is not a legal harm assessment."
        ),
        "not_a_legal_harm_assessment": True,
    }


def _calibration_from_confusion(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Threshold-level calibration from a confusion matrix (no scores required)."""
    rows: Dict[str, Any] = {}
    errors: List[float] = []
    for name, info in groups.items():
        cm = info.get("confusion_matrix")
        n = int(info.get("sample_size") or 0)
        if not cm or n <= 0:
            continue
        tp, fp, tn, fn = (int(cm[k]) for k in ("tp", "fp", "tn", "fn"))
        observed = (tp + fn) / n
        predicted = (tp + fp) / n
        err = abs(predicted - observed)
        errors.append(err)
        rows[name] = {
            "observed_claim_rate": float(observed),
            "positive_prediction_rate": float(predicted),
            "absolute_calibration_error": float(err),
            "method": "threshold_confusion_matrix",
        }
    if not rows:
        return {"status": "not_computed", "reason": "no confusion matrices"}
    return {
        "status": "computed",
        "method": "threshold_confusion_matrix",
        "max_absolute_error": float(max(errors)),
        "groups": rows,
        "note": "Compares predicted-positive rate to observed claim rate at the decision threshold. Not score-level ECE.",
    }


def _score_calibration(audit_df: pl.DataFrame, attr_name: str) -> Dict[str, Any]:
    groups: Dict[str, Any] = {}
    eces: List[float] = []
    for row in (
        audit_df.group_by(attr_name)
        .agg(
            pl.len().alias("n"),
            pl.col("y_true").mean().alias("observed_rate"),
            pl.col("y_score").mean().alias("mean_score"),
        )
        .iter_rows(named=True)
    ):
        key = str(row[attr_name])
        n = int(row["n"])
        observed = float(row["observed_rate"] or 0.0)
        mean_score = float(row["mean_score"] or 0.0)
        sub = audit_df.filter(pl.col(attr_name) == row[attr_name])
        ece = _ece_numpy(sub["y_true"].to_numpy(), sub["y_score"].to_numpy())
        if ece is not None:
            eces.append(ece)
        groups[key] = {
            "sample_size": n,
            "observed_claim_rate": observed,
            "mean_predicted_score": mean_score,
            "absolute_calibration_error": abs(mean_score - observed),
            "ece": ece,
        }
    return {
        "status": "computed",
        "method": "mean_score_vs_observed_rate_plus_ece",
        "max_absolute_error": float(max((g["absolute_calibration_error"] for g in groups.values()), default=0.0)),
        "max_ece": float(max(eces)) if eces else None,
        "groups": groups,
    }


def _apply_parity_screening(attr_results: Dict[str, Any], threshold: float) -> None:
    """Attach the four layers to a demographic-parity attribute payload."""
    observed = float(attr_results.get("max_difference") or 0.0)
    test = attr_results.get("statistical_test") or {}
    significant = bool(test.get("significant")) and not test.get("skipped", False)
    screening = classify_screening_result(observed, significant, threshold)
    attr_results["observed_difference"] = observed
    attr_results["statistically_significant"] = significant
    attr_results["governance_threshold"] = threshold
    attr_results["governance_threshold_met"] = observed <= threshold
    attr_results["parity_screening_result"] = screening
    attr_results["business_decision"] = "not_taken"
    attr_results.pop("parity_met", None)
    attr_results["impact"] = _impact_from_groups(attr_results.get("groups") or {})
    alerts: List[str] = []
    if significant and screening != "fail":
        alerts.append(
            "Chi-square is statistically significant while the 10% governance gate is still met. "
            "This is not a silent pass."
        )
    if screening == "pass_with_review" and observed >= threshold * NEAR_THRESHOLD_RATIO:
        alerts.append("Observed gap is within 20% of the governance threshold.")
    attr_results["alerts"] = alerts


def _apply_odds_screening(attr_results: Dict[str, Any], threshold: float) -> None:
    tpr_diff = float(attr_results.get("tpr_difference") or 0.0)
    fpr_diff = float(attr_results.get("fpr_difference") or 0.0)
    observed = max(tpr_diff, fpr_diff)
    tests = attr_results.get("statistical_tests") or {}
    significant = any(
        bool((tests.get(name) or {}).get("significant"))
        and not (tests.get(name) or {}).get("skipped", False)
        for name in ("tpr", "fpr")
    )
    screening = classify_screening_result(observed, significant, threshold)
    attr_results["observed_difference"] = observed
    attr_results["statistically_significant"] = significant
    attr_results["governance_threshold"] = threshold
    attr_results["governance_threshold_met"] = observed <= threshold
    attr_results["odds_screening_result"] = screening
    attr_results["business_decision"] = "not_taken"
    attr_results.pop("equality_met", None)
    attr_results["impact"] = _impact_from_groups(attr_results.get("groups") or {})
    attr_results["calibration"] = _calibration_from_confusion(attr_results.get("groups") or {})
    alerts: List[str] = []
    if significant and screening != "fail":
        alerts.append("TPR/FPR chi-square is significant below the 10% gate — not a silent pass.")
    if observed >= threshold * NEAR_THRESHOLD_RATIO and observed <= threshold:
        alerts.append(
            f"Equalized-odds gap {observed:.2%} is close to the {threshold:.0%} governance threshold."
        )
    attr_results["alerts"] = alerts


def demographic_parity_test(
    audit_df: pl.DataFrame,
    protected_attributes: Dict[str, np.ndarray],
    threshold: float = GOVERNANCE_THRESHOLD,
) -> Dict[str, Any]:
    """Demographic parity using Polars group aggregations."""
    logger.info("Performing demographic parity test (Polars)")

    results: Dict[str, Any] = {
        "overall_parity": True,  # True iff every attribute meets the 10% *gate*
        "attribute_tests": {},
        "violations": [],
        "alerts": [],
        "recommendations": [],
    }

    for attr_name in protected_attributes:
        grouped = _group_confusion_metrics(audit_df, attr_name)
        attr_results: Dict[str, Any] = {
            "attribute": attr_name,
            "groups": {},
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
                "observed_claim_rate": float(row["observed_rate"] or 0.0),
                "mean_score": float(row["mean_score"] or 0.0),
                "approval_rate_analogue": float(1.0 - positive_rate),
            }
            rates.append(positive_rate)
            contingency.append([pred_pos, n - pred_pos])

        if len(rates) > 1:
            attr_results["max_difference"] = float(max(rates) - min(rates))

        attr_results["statistical_test"] = _chi2_test_if_valid(contingency)
        _apply_parity_screening(attr_results, threshold)
        attr_results["calibration"] = _score_calibration(audit_df, attr_name)

        if not attr_results["governance_threshold_met"]:
            results["overall_parity"] = False
            results["violations"].append(
                {
                    "attribute": attr_name,
                    "observed_difference": attr_results["observed_difference"],
                    "threshold": threshold,
                    "parity_screening_result": attr_results["parity_screening_result"],
                }
            )

        results["alerts"].extend(attr_results.get("alerts") or [])
        results["attribute_tests"][attr_name] = attr_results

    if results["violations"]:
        results["recommendations"].append(
            "Demographic parity governance-gate fail. Review training data, thresholds, or constraints."
        )
    elif any(
        t.get("statistically_significant") for t in results["attribute_tests"].values()
    ):
        results["recommendations"].append(
            "Statistically significant proxy gaps exist below the 10% gate. Treat as review, not pass."
        )

    return results


def equalized_odds_test(
    audit_df: pl.DataFrame,
    protected_attributes: Dict[str, np.ndarray],
    threshold: float = GOVERNANCE_THRESHOLD,
) -> Dict[str, Any]:
    """Equalized odds (TPR/FPR parity) via Polars-segregated confusion matrices."""
    logger.info("Performing equalized odds test (Polars)")

    results: Dict[str, Any] = {
        "overall_equality": True,
        "attribute_tests": {},
        "violations": [],
        "alerts": [],
    }

    for attr_name in protected_attributes:
        grouped = _group_confusion_metrics(audit_df, attr_name)
        attr_results: Dict[str, Any] = {
            "attribute": attr_name,
            "groups": {},
            "tpr_difference": 0.0,
            "fpr_difference": 0.0,
        }
        tprs: List[float] = []
        fprs: List[float] = []
        tpr_table: List[List[int]] = []
        fpr_table: List[List[int]] = []

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
            tpr_table.append([tp, fn])
            fpr_table.append([fp, tn])

        if len(tprs) > 1:
            attr_results["tpr_difference"] = float(max(tprs) - min(tprs))
            attr_results["fpr_difference"] = float(max(fprs) - min(fprs))

        attr_results["statistical_tests"] = {
            "tpr": _chi2_test_if_valid(tpr_table),
            "fpr": _chi2_test_if_valid(fpr_table),
        }
        _apply_odds_screening(attr_results, threshold)

        if not attr_results["governance_threshold_met"]:
            results["overall_equality"] = False
            results["violations"].append(
                {
                    "attribute": attr_name,
                    "tpr_difference": attr_results["tpr_difference"],
                    "fpr_difference": attr_results["fpr_difference"],
                    "odds_screening_result": attr_results["odds_screening_result"],
                }
            )

        results["alerts"].extend(attr_results.get("alerts") or [])
        results["attribute_tests"][attr_name] = attr_results

    return results


def intersectional_parity_test(
    audit_df: pl.DataFrame,
    protected_attributes: Dict[str, np.ndarray],
    threshold: float = GOVERNANCE_THRESHOLD,
) -> Dict[str, Any]:
    """Pairwise proxy combinations. Skipped when a cell has fewer than MIN_INTERSECTION_N rows."""
    names = [n for n in protected_attributes if n in audit_df.columns]
    if len(names) < 2:
        return {"status": "not_applicable", "reason": "fewer than two grouping attributes"}

    pair_results: Dict[str, Any] = {}
    for left, right in combinations(names, 2):
        col = f"{left}×{right}"
        tmp = audit_df.with_columns(
            (pl.col(left).cast(pl.Utf8) + pl.lit("×") + pl.col(right).cast(pl.Utf8)).alias(col)
        )
        counts = tmp.group_by(col).agg(pl.len().alias("n"))
        min_n = int(counts["n"].min()) if counts.height else 0
        if min_n < MIN_INTERSECTION_N:
            pair_results[col] = {
                "status": "insufficient_sample",
                "min_cell_n": min_n,
                "min_required": MIN_INTERSECTION_N,
            }
            continue
        dummy = {col: tmp[col].to_numpy()}
        sub = demographic_parity_test(tmp, dummy, threshold=threshold)
        pair_results[col] = sub["attribute_tests"][col]
        pair_results[col]["status"] = "computed"

    return {
        "status": "computed",
        "min_cell_n": MIN_INTERSECTION_N,
        "pairs": pair_results,
        "note": "Intersectional screening of proxy combinations, not a legal protected-class analysis.",
    }


def _collect_screening_labels(demo: Dict[str, Any], eq: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for info in (demo.get("attribute_tests") or {}).values():
        if isinstance(info, dict) and info.get("parity_screening_result"):
            labels.append(info["parity_screening_result"])
    for info in (eq.get("attribute_tests") or {}).values():
        if isinstance(info, dict) and info.get("odds_screening_result"):
            labels.append(info["odds_screening_result"])
    return labels


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
            "overall_assessment": "review_required",
            "status": "Not Evaluated",
            "error": "Real protected attributes are required to run the bias audit.",
            "layers": LAYER_DEFINITIONS,
            "governance_threshold": GOVERNANCE_THRESHOLD_POLICY,
            "business_decision": {
                "status": "not_taken",
                "note": "No screening numbers without grouping attributes.",
            },
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
    proxy_attributes = any("proxy" in str(name).lower() for name in protected_attributes)

    demo = demographic_parity_test(audit_df, protected_attributes, threshold=GOVERNANCE_THRESHOLD)
    eq = equalized_odds_test(audit_df, protected_attributes, threshold=GOVERNANCE_THRESHOLD)
    intersectionality = intersectional_parity_test(
        audit_df, protected_attributes, threshold=GOVERNANCE_THRESHOLD
    )

    screening_labels = _collect_screening_labels(demo, eq)
    for pair in (intersectionality.get("pairs") or {}).values():
        if isinstance(pair, dict) and pair.get("parity_screening_result"):
            screening_labels.append(pair["parity_screening_result"])

    assessment = derive_overall_assessment(
        screening_labels, audit_valid=audit_valid, proxy_attributes=proxy_attributes
    )

    result: Dict[str, Any] = {
        "audit_date": datetime.now().isoformat(),
        "demographic_parity": demo,
        "equalized_odds": eq,
        "intersectionality": intersectionality,
        "overall_assessment": assessment,
        "classification_threshold": classification_threshold,
        "audit_valid": audit_valid,
        "proxy_attributes": proxy_attributes,
        "prediction_summary": {
            "positive_prediction_rate": float(n_positive_preds / len(y_pred_bin)),
            "unique_score_count": n_unique_scores,
        },
        "layers": LAYER_DEFINITIONS,
        "governance_threshold": GOVERNANCE_THRESHOLD_POLICY,
        "business_decision": {
            "status": "not_taken",
            "overall_assessment_is_not_a_go_live_decision": True,
            "note": (
                "conditional / review_required are screening outcomes. They do not approve "
                "deployment, premium setting, or claim handling."
            ),
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


def annotate_fairness_payload(fairness: Dict[str, Any]) -> Dict[str, Any]:
    """
    Re-interpret an existing audit dict (published JSON) without retraining.

    Numeric rates, chi-square statistics and confusion matrices are left unchanged.
    """
    out = dict(fairness)
    demo = dict(out.get("demographic_parity") or {})
    tests = dict(demo.get("attribute_tests") or {})
    demo_alerts: List[str] = []
    for name, info in list(tests.items()):
        if not isinstance(info, dict):
            continue
        item = dict(info)
        _apply_parity_screening(item, GOVERNANCE_THRESHOLD)
        tests[name] = item
        demo_alerts.extend(item.get("alerts") or [])
    demo["attribute_tests"] = tests
    demo["alerts"] = demo_alerts
    if tests:
        demo["overall_parity"] = all(
            bool(v.get("governance_threshold_met", True)) for v in tests.values() if isinstance(v, dict)
        )
    out["demographic_parity"] = demo

    eq = dict(out.get("equalized_odds") or {})
    eq_tests = dict(eq.get("attribute_tests") or {})
    eq_alerts: List[str] = []
    for name, info in list(eq_tests.items()):
        if not isinstance(info, dict):
            continue
        item = dict(info)
        _apply_odds_screening(item, GOVERNANCE_THRESHOLD)
        eq_tests[name] = item
        eq_alerts.extend(item.get("alerts") or [])
    eq["attribute_tests"] = eq_tests
    eq["alerts"] = eq_alerts
    if eq_tests:
        eq["overall_equality"] = all(
            bool(v.get("governance_threshold_met", True)) for v in eq_tests.values() if isinstance(v, dict)
        )
    out["equalized_odds"] = eq

    labels = _collect_screening_labels(demo, eq)
    proxy = bool(out.get("proxy_attributes", True))
    audit_valid = bool(out.get("audit_valid", True))
    out["overall_assessment"] = derive_overall_assessment(
        labels, audit_valid=audit_valid, proxy_attributes=proxy
    )
    out.pop("overall_compliance", None)
    out["layers"] = LAYER_DEFINITIONS
    out["governance_threshold"] = GOVERNANCE_THRESHOLD_POLICY
    out.setdefault(
        "intersectionality",
        {
            "status": "not_computed_in_static_pack",
            "reason": "Pairwise cells need row-level labels; re-run comprehensive_bias_audit.",
        },
    )
    out["business_decision"] = {
        "status": "not_taken",
        "overall_assessment_is_not_a_go_live_decision": True,
        "note": (
            "conditional / review_required are screening outcomes. They do not approve "
            "deployment, premium setting, or claim handling."
        ),
    }
    if proxy:
        out["note"] = (
            "Audit uses proxies derived from anonymized features (Porto Seguro does not include "
            "real age/gender). Replace with real protected attributes in production. "
            "overall_assessment is not a fairness certificate."
        )
    return out


def _replace_first_object_key(text: str, key: str, value: Any) -> str:
    """Replace the first `"key": { ... }` object without dumping the rest of the file."""
    token = f'"{key}":'
    start = text.find(token)
    if start < 0:
        raise ValueError(f"Key {key!r} not found")
    colon = text.find(":", start)
    i = colon + 1
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    if i >= len(text) or text[i] != "{":
        raise ValueError(f"Key {key!r} is not a JSON object")
    depth = 0
    j = i
    in_str = False
    escape = False
    while j < len(text):
        ch = text[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
        j += 1
    indent = 4
    payload = json.dumps(value, indent=2, ensure_ascii=False)
    lines = payload.splitlines()
    pad = " " * indent
    rest = "\n".join(pad + line if line else line for line in lines[1:])
    rendered = lines[0] + (("\n" + rest) if rest else "")
    return text[:colon + 1] + " " + rendered + text[j:]


def annotate_fairness_in_conformity_pack(path: Path) -> Dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    parsed = json.loads(original)
    fairness = parsed.get("responsible_ai_compliance", {}).get("fairness")
    if not isinstance(fairness, dict):
        raise ValueError(f"No responsible_ai_compliance.fairness in {path}")
    annotated = annotate_fairness_payload(fairness)
    updated = _replace_first_object_key(original, "fairness", annotated)
    json.loads(updated)  # sanity
    path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")
    return annotated


if __name__ == "__main__":
    pack = Path("eu_ai_act_conformity_v1.json")
    if pack.is_file():
        result = annotate_fairness_in_conformity_pack(pack)
        print("overall_assessment=", result.get("overall_assessment"))
