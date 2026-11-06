"""GDPR evidence block: validation, honesty constraints, pack compatibility."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.governance.gdpr_evidence import (
    COMPLIANCE_STATUS,
    EVALUATION_IDS,
    GDPR_BLOCK_SCHEMA_VERSION,
    attach_gdpr_block,
    build_gdpr_evidence_block,
    is_safe_repo_ref,
    merge_gdpr_into_pack,
    serialize_gdpr_block,
    upsert_top_level_json_key,
    validate_gdpr_block,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "schemas" / "gdpr_evidence.schema.json"


def test_build_serialise_and_unknown_fields_stay_null():
    block = build_gdpr_evidence_block(ROOT)
    dumped = serialize_gdpr_block(block, repo_root=ROOT)
    loaded = json.loads(dumped)

    assert loaded["schema_version"] == GDPR_BLOCK_SCHEMA_VERSION
    assert loaded["assurance_level"] == "evidence_only"
    assert loaded["compliance_status"] == COMPLIANCE_STATUS
    assert loaded["review_required"] is True
    assert loaded["open_gaps"]
    assert _has_timezone(loaded["generated_at"])

    roles = loaded["evaluations"]["roles_and_accountability"]
    assert roles["owner"] is None
    assert roles["reviewer"] is None
    assert roles["reviewed_at"] is None
    assert roles["findings"]["controller"] is None
    assert roles["findings"]["dpo_required"] == "unknown"

    basis = loaded["evaluations"]["purposes_and_lawful_basis"]
    assert basis["findings"]["art6_lawful_basis"] == "unknown"
    assert basis["findings"]["art6_justification"] is None
    assert basis["findings"]["consent_selected_by_default"] is False
    assert basis["findings"]["art9_condition"] is None

    adm = loaded["evaluations"]["automated_decision_making"]
    assert adm["findings"]["article_22_applicable"] == "unknown"
    assert adm["applicability"] != "not_applicable"


def test_missing_evidence_creates_gaps_and_review_required(tmp_path):
    block = build_gdpr_evidence_block(tmp_path)
    assert block["review_required"] is True
    assert block["open_gaps"]
    retention = block["evaluations"]["retention_and_deletion"]
    assert retention["evidence_status"] in {"missing", "partial"}
    assert retention["gaps"]
    assert retention["review_required"] is True
    assert retention["control_status"] == "not_tested"


def test_no_automatic_conformity_claims():
    block = build_gdpr_evidence_block(ROOT)
    blob = json.dumps(block)
    assert "gdpr_compliant" not in blob
    assert '"compliant": true' not in blob.lower()
    assert "Compliant" not in blob
    assert block["compliance_status"] == "not_a_legal_determination"
    for section in block["evaluations"].values():
        assert section["control_status"] != "passed"


def test_publisher_anonymisation_does_not_imply_non_applicability():
    block = build_gdpr_evidence_block(ROOT)
    anon = block["evaluations"]["applicability_and_anonymisation"]
    assert anon["applicability"] == "unknown"
    assert anon["findings"]["recital_26_legal_finding"] is False
    assert anon["findings"]["personal_data_in_demo"] == "unknown"

    mutated = copy.deepcopy(block)
    mutated["evaluations"]["applicability_and_anonymisation"]["applicability"] = "not_applicable"
    errors = validate_gdpr_block(mutated, repo_root=ROOT)
    assert any("not_applicable" in e for e in errors)


def test_not_applicable_without_justification_is_invalid():
    block = build_gdpr_evidence_block(ROOT)
    section = block["evaluations"]["processors_and_transfers"]
    section["applicability"] = "not_applicable"
    section["applicability_rationale"] = ""
    errors = validate_gdpr_block(block, repo_root=ROOT)
    assert any("justification" in e or "applicability_rationale" in e for e in errors)


def test_passed_without_test_evidence_is_invalid():
    block = build_gdpr_evidence_block(ROOT)
    section = block["evaluations"]["security_of_processing"]
    section["control_status"] = "passed"
    section["evidence_status"] = "available"
    section["evidence_refs"] = [{"path": "README.md", "kind": "document"}]
    errors = validate_gdpr_block(block, repo_root=ROOT)
    assert any("test evidence" in e or "passed requires" in e for e in errors)

    section["evidence_status"] = "partial"
    section["evidence_refs"] = [{"path": "tests/test_dpia_workspace.py", "kind": "test"}]
    errors = validate_gdpr_block(block, repo_root=ROOT)
    assert any("available" in e for e in errors)


def test_evidence_refs_must_stay_inside_repo():
    assert is_safe_repo_ref("gdpr_dpia_v1.json", ROOT) is True
    assert is_safe_repo_ref("../secrets.txt", ROOT) is False
    assert is_safe_repo_ref("..\\Windows\\system.ini", ROOT) is False
    assert is_safe_repo_ref("/etc/passwd", ROOT) is False
    assert is_safe_repo_ref(str(ROOT.parent / "outside.json"), ROOT) is False

    block = build_gdpr_evidence_block(ROOT)
    block["evaluations"]["transparency"]["evidence_refs"] = [
        {"path": "../outside.txt", "kind": "document"}
    ]
    errors = validate_gdpr_block(block, repo_root=ROOT)
    assert any("escapes" in e for e in errors)


def test_export_contains_no_personal_data_or_secrets():
    block = build_gdpr_evidence_block(ROOT)
    blob = json.dumps(block)
    assert "demo@localhost" not in blob
    assert "BEGIN PRIVATE KEY" not in blob
    assert "api_key" not in blob.lower()
    errors = validate_gdpr_block(block, repo_root=ROOT)
    assert errors == []


def test_fairness_metrics_are_not_used_as_gdpr_proof():
    block = build_gdpr_evidence_block(ROOT)
    blob = json.dumps(block)
    assert "max_difference" not in blob
    assert "parity_met" not in blob
    assert "chi2_statistic" not in blob
    inventory = block["evaluations"]["data_inventory_and_minimisation"]["findings"]
    assert inventory["fairness_audit_inputs"]["not_gdpr_fairness_evidence"] is True
    assert inventory["fairness_audit_inputs"]["collected_as_protected_attributes"] is False


def test_human_review_does_not_clear_article_22():
    block = build_gdpr_evidence_block(ROOT)
    adm = block["evaluations"]["automated_decision_making"]
    assert adm["findings"]["human_review_does_not_prove_art22_inapplicable"] is True
    mutated = copy.deepcopy(block)
    mutated["evaluations"]["automated_decision_making"]["applicability"] = "not_applicable"
    mutated["evaluations"]["automated_decision_making"]["applicability_rationale"] = (
        "A human reviewer exists in the Streamlit demo so Art. 22 does not apply."
    )
    errors = validate_gdpr_block(mutated, repo_root=ROOT)
    assert any("Art. 22" in e for e in errors)


def test_parent_report_compatibility():
    from src.governance.reporting_generator import generate_unified_ai_report

    report = generate_unified_ai_report(
        model_info={"name": "compat"},
        performance_metrics={"roc_auc": 0.6, "f1_score": 0.1},
        training_data_info={"total_records": 10, "total_features": 3},
        explainability_report={"compliance_notes": {"global": "stub"}},
    )
    for key in (
        "schema_version",
        "disclaimer",
        "assurance",
        "model_details",
        "intended_use",
        "eu_ai_act_compliance",
        "responsible_ai_compliance",
        "gdpr",
    ):
        assert key in report
    assert report["schema_version"] == "1.1.0"
    assert report["eu_ai_act_compliance"]["compliance_status"] == "not_a_conformity_decision"
    assert report["gdpr"]["compliance_status"] == COMPLIANCE_STATUS
    assert "Compliant" not in json.dumps(report)
    attached = attach_gdpr_block({"schema_version": "1.1.0"}, repo_root=ROOT)
    assert attached["schema_version"] == "1.1.0"
    assert attached["gdpr"]["schema_version"] == GDPR_BLOCK_SCHEMA_VERSION


def test_upsert_preserves_sibling_metrics(tmp_path):
    original = (
        '{\n'
        '  "schema_version": "1.1.0",\n'
        '  "fairness": {\n'
        '    "max_difference": 0.04185275007378039,\n'
        '    "parity_met": true\n'
        '  }\n'
        '}\n'
    )
    pack = tmp_path / "pack.json"
    pack.write_text(original, encoding="utf-8")
    # Copy required evidence so the builder can reference this temp root? Builder
    # uses repo files relative to tmp_path; that's fine (partial/missing).
    merge_gdpr_into_pack(pack, repo_root=ROOT)
    text = pack.read_text(encoding="utf-8")
    assert "0.04185275007378039" in text
    assert '"parity_met": true' in text
    parsed = json.loads(text)
    assert parsed["fairness"]["max_difference"] == 0.04185275007378039
    assert "gdpr" in parsed
    assert parsed["gdpr"]["review_required"] is True


def test_upsert_replaces_existing_gdpr_key():
    text = '{\n  "a": 1,\n  "gdpr": {"old": true}\n}\n'
    updated = upsert_top_level_json_key(text, "gdpr", {"schema_version": "1.0.0"})
    parsed = json.loads(updated)
    assert parsed["a"] == 1
    assert parsed["gdpr"] == {"schema_version": "1.0.0"}
    assert "old" not in parsed["gdpr"]


def test_all_evaluation_ids_present():
    block = build_gdpr_evidence_block(ROOT)
    assert tuple(block["evaluations"]) == EVALUATION_IDS or set(block["evaluations"]) == set(
        EVALUATION_IDS
    )
    for eid in EVALUATION_IDS:
        assert eid in block["evaluations"]


def test_published_packs_include_generated_gdpr_block():
    for name in ("eu_ai_act_conformity_v1.json", "gdpr_dpia_v1.json"):
        data = json.loads((ROOT / name).read_text(encoding="utf-8"))
        block = data["gdpr"]
        assert block["compliance_status"] == COMPLIANCE_STATUS
        assert block["assurance_level"] == "evidence_only"
        assert block["review_required"] is True
        assert "gdpr_compliant" not in data


@pytest.mark.skipif(not SCHEMA_PATH.is_file(), reason="JSON Schema not published")
def test_block_matches_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    block = build_gdpr_evidence_block(ROOT)
    jsonschema.validate(instance=block, schema=schema)


def _has_timezone(value: str) -> bool:
    return value.endswith("Z") or ("+" in value[-6:] or value[-6:].count("-") == 1)
