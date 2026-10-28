"""Validate published synthetic evidence packs against JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "schemas"
EVIDENCE_DIR = ROOT / "examples" / "evidence"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _packs_on_disk() -> bool:
    return SCHEMA_DIR.is_dir() and EVIDENCE_DIR.is_dir()


@pytest.mark.skipif(not _packs_on_disk(), reason="docs/schemas and examples/evidence are not in the published tree")
def test_synthetic_eu_ai_act_pack_matches_schema():
    schema = _load(SCHEMA_DIR / "eu_ai_act_conformity.schema.json")
    instance = _load(EVIDENCE_DIR / "eu_ai_act_conformity_synthetic.json")
    jsonschema.validate(instance=instance, schema=schema)
    assert instance["disclaimer"]["not_a_conformity_decision"] is True
    assert instance["assurance"]["dashboard_tiles_are_not_conformity"] is True
    assert instance["eu_ai_act_compliance"]["compliance_status"] == "not_a_conformity_decision"
    assert "Compliant" not in json.dumps(instance)


@pytest.mark.skipif(not _packs_on_disk(), reason="docs/schemas and examples/evidence are not in the published tree")
def test_synthetic_gdpr_dpia_pack_matches_schema():
    schema = _load(SCHEMA_DIR / "gdpr_dpia.schema.json")
    instance = _load(EVIDENCE_DIR / "gdpr_dpia_synthetic.json")
    jsonschema.validate(instance=instance, schema=schema)
    assert instance["disclaimer"]["not_a_supervisory_notification"] is True
    assert instance["assurance"]["overall_assurance_level"] in {
        "none",
        "evidence_only",
        "tested",
        "independently_reviewed",
    }


def test_reporting_generator_emits_assurance_fields():
    from src.governance.reporting_generator import generate_unified_ai_report

    report = generate_unified_ai_report(
        model_info={"name": "synth"},
        performance_metrics={"roc_auc": 0.6},
        training_data_info={"total_records": 10, "total_features": 3},
        explainability_report={"compliance_notes": {"global": "stub"}},
    )
    assert report["schema_version"] == "1.1.0"
    assert report["disclaimer"]["not_a_conformity_decision"] is True
    assert report["assurance"]["dashboard_tiles_are_not_conformity"] is True
    assert report["eu_ai_act_compliance"]["compliance_status"] == "not_a_conformity_decision"
    assert "control_tested" in report["eu_ai_act_compliance"]
    assert "assurance_level" in report["explainability_compliance"]
    assert report["explainability_compliance"]["evidence_available"] is True
