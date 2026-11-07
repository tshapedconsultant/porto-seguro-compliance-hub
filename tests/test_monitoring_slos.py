"""Generation and validation of operational monitoring SLOs."""

from copy import deepcopy
from pathlib import Path

import pytest

import json

from src.monitoring.slo import (
    SLO_IDS,
    SloValidationError,
    artifact_hash_for,
    build_monitoring_slo_report,
    resolve_alert,
    validate_monitoring_slo_report,
)


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "docs" / "schemas"


def _by_id(report):
    return {item["slo_id"]: item for item in report["slos"]}


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_catalog_covers_required_signals():
    report = build_monitoring_slo_report()
    assert [item["slo_id"] for item in report["slos"]] == list(SLO_IDS)
    assert report["open_alert_count"] == 0
    assert report["business_decision"]["status"] == "not_taken"
    for item in report["slos"]:
        assert item["status"] == "not_evaluated"
        assert item["alert"] is None
        assert item["evidence"]["status"] == "missing"
        assert item["business_decision"] == "not_inferred"
        for key in (
            "condition",
            "severity",
            "owner",
            "required_action",
            "deadline",
            "evidence",
            "status",
        ):
            assert key in item


def test_generator_never_emits_resolved():
    report = build_monitoring_slo_report(
        data_drift={"drift_detected": True, "drift_score": 0.9, "feature_drifts": {}}
    )
    assert all(item.get("alert", {}).get("status") != "resolved" for item in report["slos"] if item["alert"])
    assert all(alert["status"] == "open" for alert in report["alerts"])


def test_ks_drift_opens_technical_alert():
    report = build_monitoring_slo_report(
        data_drift={
            "drift_detected": True,
            "drift_score": 0.934,
            "feature_drifts": {"ps_car_13": {"drift_detected": True, "ks_statistic": 0.934}},
        }
    )
    item = _by_id(report)["mon.ks_drift"]
    assert item["status"] == "breached"
    alert = item["alert"]
    assert alert["status"] == "open"
    assert alert["severity"] == "high"
    assert alert["owner"] == "unassigned"
    assert alert["deadline"] == "P2D"
    assert alert["deadline_at"]
    assert alert["evidence"]["status"] == "available"
    assert alert["business_decision"] == "not_taken"
    assert alert["not_a_legal_finding"] is True
    assert "retrain" in alert["required_action"].lower() or "investigate" in alert["required_action"].lower()
    assert "discriminat" not in alert["required_action"].lower()


def test_performance_degradation_is_not_conformity():
    report = build_monitoring_slo_report(
        model_drift={
            "drift_detected": True,
            "metric_changes": {
                "roc_auc": {
                    "reference": 0.64,
                    "current": 0.50,
                    "relative_change": -0.21875,
                    "drift_detected": True,
                }
            },
        }
    )
    alert = _by_id(report)["mon.performance_degradation"]["alert"]
    assert alert["status"] == "open"
    assert "non-conformity" in alert["required_action"].lower() or "not a regulatory" in alert["required_action"].lower()
    assert alert["not_a_legal_finding"] is True


def test_calibration_drift_uses_internal_threshold():
    within = build_monitoring_slo_report(calibration={"ece": 0.02})
    assert _by_id(within)["mon.calibration_drift"]["status"] == "within_slo"
    breached = build_monitoring_slo_report(calibration={"max_absolute_error": 0.08})
    assert _by_id(breached)["mon.calibration_drift"]["status"] == "breached"
    assert _by_id(breached)["mon.calibration_drift"]["alert"]["severity"] == "medium"


def test_fairness_alert_is_not_a_discrimination_finding():
    report = build_monitoring_slo_report(
        fairness={
            "overall_assessment": "review_required",
            "demographic_parity": {
                "attribute_tests": {
                    "region_proxy_ps_reg_03": {"parity_screening_result": "pass_with_review"}
                }
            },
        }
    )
    item = _by_id(report)["mon.fairness_screening"]
    assert item["status"] == "breached"
    alert = item["alert"]
    blob = f"{alert['condition']} {alert['required_action']}".lower()
    assert "discriminat" not in blob
    assert alert["not_a_discrimination_finding"] is True
    assert alert["business_decision"] == "not_taken"


def test_shadow_monitor_and_production_gate():
    report = build_monitoring_slo_report(
        shadow_monitor={"ran": True, "artifacts_present": False, "ks_alert": False},
        production_gate={
            "monitoring_passed": False,
            "overall_status": "drift_detected",
            "evidence_path": "docs/drift_monitoring_latest.json",
        },
    )
    assert _by_id(report)["mon.shadow_monitor"]["status"] == "breached"
    gate = _by_id(report)["mon.production_gate"]
    assert gate["status"] == "breached"
    assert gate["alert"]["severity"] == "critical"
    assert gate["alert"]["deadline"] == "P1D"
    healthy = build_monitoring_slo_report(
        shadow_monitor={"ran": True, "artifacts_present": True, "ks_alert": False},
        production_gate={"monitoring_passed": True, "overall_status": "healthy"},
    )
    assert _by_id(healthy)["mon.shadow_monitor"]["status"] == "within_slo"
    assert _by_id(healthy)["mon.production_gate"]["status"] == "within_slo"
    assert healthy["open_alert_count"] == 0


def test_resolve_without_evidence_is_rejected():
    report = build_monitoring_slo_report(
        data_drift={"drift_detected": True, "drift_score": 0.4, "feature_drifts": {}}
    )
    with pytest.raises(SloValidationError, match="evidence"):
        resolve_alert(report, "mon.ks_drift", evidence_refs=[], note="looks fine")
    with pytest.raises(SloValidationError, match="evidence"):
        resolve_alert(report, "mon.ks_drift", evidence_refs=["  "], note="looks fine")


def test_resolve_with_evidence_keeps_business_decision_untaken():
    report = build_monitoring_slo_report(
        data_drift={"drift_detected": True, "drift_score": 0.4, "feature_drifts": {}}
    )
    resolved = resolve_alert(
        report,
        "mon.ks_drift",
        evidence_refs=["docs/drift_monitoring_latest.json#ps_car_13"],
        note="Shift was a demo inject on ps_car_13; no promotion.",
    )
    alert = _by_id(resolved)["mon.ks_drift"]["alert"]
    assert alert["status"] == "resolved"
    assert alert["resolution_evidence"]["refs"]
    assert alert["business_decision"] == "not_taken"
    assert resolved["open_alert_count"] == 0
    assert validate_monitoring_slo_report(resolved) == []


def test_validate_rejects_resolved_alert_without_evidence():
    report = build_monitoring_slo_report(
        data_drift={"drift_detected": True, "drift_score": 0.4, "feature_drifts": {}}
    )
    tampered = deepcopy(report)
    tampered["slos"][0]["alert"]["status"] = "resolved"
    tampered["alerts"][0]["status"] = "resolved"
    gaps = validate_monitoring_slo_report(tampered)
    assert any("resolved_without_evidence" in gap for gap in gaps)


def test_evidence_integrity_has_hash_version_and_refs():
    report = build_monitoring_slo_report(
        data_drift={
            "drift_detected": True,
            "drift_score": 0.4,
            "feature_drifts": {"ps_car_13": {"drift_detected": True}},
        }
    )
    integrity = report["evidence_integrity"]
    assert integrity["schema_version"] == report["schema_version"]
    assert integrity["generated_at"] == report["generated_at"]
    assert integrity["artifact_hash"].startswith("sha256:")
    assert integrity["artifact_hash"] == artifact_hash_for(report)
    assert integrity["not_a_cryptographic_signature"] is True
    assert integrity["not_worm"] is True
    assert integrity["evidence_refs"]
    assert all(item["hash"].startswith("sha256:") for item in integrity["evidence_refs"])
    assert all("ref" in item for item in integrity["evidence_refs"])
    tampered = deepcopy(report)
    tampered["open_alert_count"] = 99
    assert artifact_hash_for(tampered) != integrity["artifact_hash"]


def test_generated_report_matches_slo_and_alert_schemas():
    """Integration: a live generator payload validates against both schemas."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load_schema("monitoring_slo.schema.json")
    alert_schema = _load_schema("monitoring_slo_alert.schema.json")
    report = build_monitoring_slo_report(
        production_gate={"monitoring_passed": False, "overall_status": "drift_detected"}
    )
    jsonschema.validate(instance=report, schema=schema)
    assert report["alerts"]
    jsonschema.validate(instance=report["alerts"][0], schema=alert_schema)
    nested = report["slos"][5]["alert"]
    jsonschema.validate(instance=nested, schema=alert_schema)


def test_schema_rejects_extra_slo_fields():
    """Unit: SLO items set additionalProperties false."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load_schema("monitoring_slo.schema.json")
    extra = deepcopy(build_monitoring_slo_report())
    extra["slos"][0]["unexpected_field"] = "should_fail"
    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(instance=extra, schema=schema)
    assert exc.value.validator == "additionalProperties"


def test_schema_rejects_incomplete_alert():
    """Unit: alert schema requires deadline_at and evidence."""
    jsonschema = pytest.importorskip("jsonschema")
    alert_schema = _load_schema("monitoring_slo_alert.schema.json")
    report = build_monitoring_slo_report(
        production_gate={"monitoring_passed": False, "overall_status": "drift_detected"}
    )
    incomplete = deepcopy(report["alerts"][0])
    incomplete.pop("deadline_at")
    incomplete.pop("evidence")
    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(instance=incomplete, schema=alert_schema)
    assert exc.value.validator == "required"
    assert "deadline_at" in exc.value.message or "evidence" in exc.value.message


def test_evidence_integrity_always_present():
    report = build_monitoring_slo_report()
    assert "evidence_integrity" in report
    integrity = report["evidence_integrity"]
    for key in ("artifact_hash", "schema_version", "generated_at", "evidence_refs"):
        assert key in integrity
    assert isinstance(integrity["evidence_refs"], list)
    for item in integrity["evidence_refs"]:
        assert "ref" in item
        assert "hash" in item
        assert str(item["hash"]).startswith("sha256:")
    assert integrity["not_a_cryptographic_signature"] is True
    assert integrity["not_worm"] is True
    blob = json.dumps(integrity).lower()
    assert "forensic" not in blob
    assert "cryptographic_signature" not in blob.replace("not_a_cryptographic_signature", "")


def test_healthy_ks_is_within_slo_not_a_pass_stamp():
    report = build_monitoring_slo_report(
        data_drift={
            "drift_detected": False,
            "drift_score": 0.02,
            "feature_drifts": {"ps_calc_02": {"drift_detected": False, "ks_statistic": 0.02}},
        }
    )
    item = _by_id(report)["mon.ks_drift"]
    assert item["status"] == "within_slo"
    assert item["alert"] is None
    assert item["not_a_legal_finding"] is True
