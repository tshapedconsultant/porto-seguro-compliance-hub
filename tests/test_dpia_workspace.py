"""Edge cases for EIPD/DPIA workspace engines."""

from __future__ import annotations

import pytest

from src.governance.dpia_workspace.models import Assessment, empty_processing
from src.governance.dpia_workspace.proportionality import assess_proportionality
from src.governance.dpia_workspace.reports import assessment_pdf_bytes, build_eipa_report
from src.governance.dpia_workspace.risk_engine import art36_needed, reassess_residual, score_risk
from src.governance.dpia_workspace.screening import SCREENING_QUESTIONS, screen_necessity
from src.governance.dpia_workspace.store import AssessmentStore


def test_create_save_load(tmp_path):
    store = AssessmentStore(tmp_path)
    created = store.create("Lab EIPD", owner="andre")
    loaded = store.get(created.assessment_id)
    assert loaded is not None
    assert loaded.title == "Lab EIPD"
    assert loaded.decision_state != "approved_internally"


def test_screening_all_unanswered():
    result = screen_necessity({})
    assert result["outcome"] == "further_assessment_required"
    assert result["is_legal_determination"] is False
    assert len(result["missing_evidence"]) == len(SCREENING_QUESTIONS)


def test_screening_strong_indicator():
    answers = {q["id"]: False for q in SCREENING_QUESTIONS}
    answers["q_automated_legal"] = True
    result = screen_necessity(answers)
    assert result["outcome"] == "full_eipa_appears_necessary"
    assert "q_automated_legal" in result["strong_indicators"]


def test_screening_all_false_not_a_legal_greenlight():
    answers = {q["id"]: False for q in SCREENING_QUESTIONS}
    result = screen_necessity(answers)
    assert result["outcome"] == "full_eipa_may_not_be_necessary"
    assert result["is_legal_determination"] is False
    assert result["voluntary_eipa_allowed"] is True


def test_processing_contradiction_art9_without_personal_data(tmp_path):
    store = AssessmentStore(tmp_path)
    item = store.create("bad")
    item.processing = empty_processing()
    item.processing["activity_name"] = "x"
    item.processing["controller"] = {"name": "c"}
    item.processing["purposes"] = ["p"]
    item.processing["special_category_art9"] = True
    item.processing["uses_identifiable_personal_data"] = False
    saved = store.save(item)
    assert saved.contradictions
    assert saved.decision_state != "approved_internally"


def test_save_strips_premature_approval(tmp_path):
    store = AssessmentStore(tmp_path)
    item = store.create("incomplete")
    item.decision_state = "approved_internally"
    item.lifecycle_state = "draft"
    saved = store.save(item)
    assert saved.decision_state == "incomplete"


def test_dpo_cannot_be_controller_approval(tmp_path):
    store = AssessmentStore(tmp_path)
    item = store.create("dpo")
    item.processing["activity_name"] = "act"
    item.processing["controller"] = {"name": "ctrl"}
    item.processing["purposes"] = ["p"]
    item.lifecycle_state = "decision"
    store.add_review(
        item,
        role="dpo",
        actor="dpo@lab",
        decision="approved_internally",
        rationale="advice only",
    )
    loaded = store.get(item.assessment_id)
    assert loaded.reviews[-1]["decision"] == "privacy_review_recorded"
    assert loaded.decision_state != "approved_internally"


def test_residual_unchanged_for_proposed_controls():
    risk = score_risk(likelihood=4, severity=4, threat="t", harm="h")
    inherent = risk["inherent_score"]
    controls = [
        {
            "addresses_risks": [risk["risk_id"]],
            "status": "proposed",
            "verification_state": "unverified",
        }
    ]
    out = reassess_residual(risk, controls)
    assert out["residual_score"] == inherent


def test_residual_changes_only_with_verified_linked_control():
    risk = score_risk(likelihood=4, severity=4, threat="t", harm="h")
    inherent = risk["inherent_score"]
    controls = [
        {
            "addresses_risks": [risk["risk_id"]],
            "status": "verified_in_target",
            "verification_state": "verified",
        }
    ]
    out = reassess_residual(risk, controls)
    assert out["residual_score"] < inherent


def test_unlinked_verified_control_does_not_help():
    risk = score_risk(likelihood=5, severity=5, threat="t", harm="h")
    controls = [{"addresses_risks": ["RSK-other"], "status": "verified_in_target", "verification_state": "verified"}]
    out = reassess_residual(risk, controls)
    assert out["residual_score"] == 25


def test_report_does_not_mutate_decision():
    item = Assessment(assessment_id="x", title="t", decision_state="pending_review")
    before = item.decision_state
    build_eipa_report(item)
    assert item.decision_state == before


def test_pdf_magic():
    item = Assessment(assessment_id="x", title="t")
    pdf = assessment_pdf_bytes(item)
    assert pdf.startswith(b"%PDF")


def test_art36_flag_not_auto_submit():
    risk = score_risk(likelihood=5, severity=5, threat="t", harm="h", family="rights_and_freedoms")
    reassess_residual(risk, [])
    flag = art36_needed([risk])
    assert flag["may_require_prior_consultation"] is True
    assert flag["auto_submit"] is False


def test_unknown_risk_family():
    with pytest.raises(ValueError):
        score_risk(likelihood=1, severity=1, family="not_a_family", threat="t", harm="h")


def test_score_clamped():
    risk = score_risk(likelihood=99, severity=0, threat="t", harm="h")
    assert risk["likelihood"] == 5
    assert risk["severity"] == 1
    assert risk["inherent_score"] == 5


def test_proportionality_blocks_personal_data_without_basis():
    processing = empty_processing()
    processing["uses_identifiable_personal_data"] = True
    processing["purposes"] = ["underwriting"]
    result = assess_proportionality(processing)
    assert result["blocking_lawfulness_or_necessity"] is True
