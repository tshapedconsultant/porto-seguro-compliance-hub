"""
Fairness subgroup tests on synthetic group attributes.

Technical detection only — not a legal fairness certification or GDPR claim.
"""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.governance.bias_audit import (
    GOVERNANCE_THRESHOLD,
    _build_audit_frame,
    annotate_fairness_payload,
    classify_screening_result,
    demographic_parity_test,
    derive_overall_assessment,
    equalized_odds_test,
)


def test_screening_layers_are_independent():
    assert classify_screening_result(0.0419, True) == "pass_with_review"
    assert classify_screening_result(0.0594, True) == "pass_with_review"
    assert classify_screening_result(0.094, False) == "pass_with_review"
    assert classify_screening_result(0.04, False) == "monitor"
    assert classify_screening_result(0.001, False) == "pass"
    assert classify_screening_result(0.12, False) == "fail"


def test_overall_assessment_never_silent_pass():
    assert derive_overall_assessment(["pass"], audit_valid=True, proxy_attributes=True) == "review_required"
    assert derive_overall_assessment(["pass"], audit_valid=True, proxy_attributes=False) == "conditional"
    assert (
        derive_overall_assessment(["pass_with_review"], audit_valid=True, proxy_attributes=False)
        == "review_required"
    )


def test_demographic_parity_detects_group_difference():
    """Biased positive rates across groups must fail the governance gate."""
    group = np.array([0] * 100 + [1] * 100)
    y_pred_proba = np.concatenate([np.full(100, 0.1), np.full(100, 0.9)])
    y_true = pl.Series("y_true", np.concatenate([np.zeros(100, dtype=int), np.ones(100, dtype=int)]))
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = demographic_parity_test(audit_df, protected, threshold=0.1)
    attr = result["attribute_tests"]["proxy_group"]
    assert result["overall_parity"] is False
    assert attr["max_difference"] > 0.5
    assert attr["parity_screening_result"] == "fail"
    assert "parity_met" not in attr
    assert attr["governance_threshold_met"] is False
    assert "observed_difference" in attr
    assert "statistically_significant" in attr
    assert len(result["violations"]) >= 1
    assert "impact" in attr


def test_demographic_parity_passes_when_rates_match():
    group = np.array([0] * 100 + [1] * 100)
    y_pred_proba = np.tile([0.2, 0.8], 100)
    y_true = pl.Series("y_true", np.tile([0, 1], 100))
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = demographic_parity_test(audit_df, protected, threshold=0.1)
    attr = result["attribute_tests"]["proxy_group"]
    assert result["overall_parity"] is True
    assert attr["max_difference"] < 0.1
    assert attr["parity_screening_result"] == "pass"
    assert attr["statistically_significant"] is False
    assert attr["governance_threshold_met"] is True


def test_equalized_odds_detects_tpr_fpr_gap():
    y_true = pl.Series(
        "y_true",
        np.array([0, 0, 0, 0, 1, 1, 1, 1] * 10, dtype=int),
    )
    group = np.array([0] * 40 + [1] * 40)
    scores_a = np.array([0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9] * 5)
    scores_b = np.array([0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1] * 5)
    y_pred_proba = np.concatenate([scores_a, scores_b])
    protected = {"proxy_group": group}
    audit_df = _build_audit_frame(y_true, y_pred_proba, protected, classification_threshold=0.5)

    result = equalized_odds_test(audit_df, protected, threshold=0.1)
    attr = result["attribute_tests"]["proxy_group"]
    assert result["overall_equality"] is False
    assert attr["tpr_difference"] > 0.5 or attr["fpr_difference"] > 0.5
    assert attr["odds_screening_result"] == "fail"
    assert "equality_met" not in attr
    assert len(result["violations"]) >= 1
    assert "calibration" in attr


def test_annotate_published_numbers_are_review_required():
    """Porto Seguro static pack: 4.19%/5.94% significant, EO ~9.3% near the gate."""
    payload = {
        "audit_valid": True,
        "proxy_attributes": True,
        "overall_compliance": True,
        "demographic_parity": {
            "overall_parity": True,
            "attribute_tests": {
                "region_proxy_ps_reg_03": {
                    "max_difference": 0.04185275007378039,
                    "parity_met": True,
                    "statistical_test": {"skipped": False, "p_value": 4e-15, "significant": True},
                    "groups": {
                        "high": {"positive_rate": 0.070456, "sample_size": 4627, "positive_count": 326},
                        "low": {"positive_rate": 0.028603, "sample_size": 2692, "positive_count": 77},
                    },
                },
                "vehicle_proxy_ps_car_13": {
                    "max_difference": 0.05940000000000001,
                    "parity_met": True,
                    "statistical_test": {"skipped": False, "p_value": 1e-40, "significant": True},
                    "groups": {
                        "above_median": {"positive_rate": 0.0816, "sample_size": 5000, "positive_count": 408},
                        "below_median": {"positive_rate": 0.0222, "sample_size": 5000, "positive_count": 111},
                    },
                },
            },
        },
        "equalized_odds": {
            "overall_equality": True,
            "attribute_tests": {
                "region_proxy_ps_reg_03": {
                    "tpr_difference": 0.09254864736592314,
                    "fpr_difference": 0.039972703452626976,
                    "equality_met": True,
                    "groups": {},
                },
                "vehicle_proxy_ps_car_13": {
                    "tpr_difference": 0.09416098602217171,
                    "fpr_difference": 0.05594017458366829,
                    "equality_met": True,
                    "groups": {},
                },
            },
        },
    }
    out = annotate_fairness_payload(payload)
    assert "overall_compliance" not in out
    assert out["overall_assessment"] == "review_required"
    region = out["demographic_parity"]["attribute_tests"]["region_proxy_ps_reg_03"]
    assert region["parity_screening_result"] == "pass_with_review"
    assert region["statistically_significant"] is True
    assert region["governance_threshold_met"] is True
    assert "parity_met" not in region
    vehicle_eo = out["equalized_odds"]["attribute_tests"]["vehicle_proxy_ps_car_13"]
    assert vehicle_eo["odds_screening_result"] == "pass_with_review"
    assert out["governance_threshold"]["value"] == GOVERNANCE_THRESHOLD
    assert out["business_decision"]["status"] == "not_taken"
    assert "observed_difference" in out["layers"]


def test_published_conformity_pack_uses_screening_not_binary_pass():
    path = Path(__file__).resolve().parents[1] / "eu_ai_act_conformity_v1.json"
    fairness = json.loads(path.read_text(encoding="utf-8"))["responsible_ai_compliance"]["fairness"]
    assert fairness["overall_assessment"] == "review_required"
    assert "overall_compliance" not in fairness
    region = fairness["demographic_parity"]["attribute_tests"]["region_proxy_ps_reg_03"]
    assert region["max_difference"] == 0.04185275007378039
    assert region["parity_screening_result"] == "pass_with_review"
    assert region["statistically_significant"] is True
    assert region["governance_threshold_met"] is True
    assert "parity_met" not in region
