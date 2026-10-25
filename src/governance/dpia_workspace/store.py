from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.governance.dpia_workspace.models import (
    Assessment,
    empty_processing,
    new_id,
    utc_now,
    validate_processing,
)
from src.governance.dpia_workspace.seed import demo_assessment


class AssessmentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or "docs/governance/assessments")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, assessment_id: str) -> Path:
        return self.root / f"{assessment_id}.json"

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

    def get(self, assessment_id: str) -> Assessment | None:
        path = self._path(assessment_id)
        if not path.exists():
            return None
        return Assessment.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, assessment: Assessment, *, bump_version: bool = True) -> Assessment:
        missing, contradictions = validate_processing(assessment.processing)
        assessment.missing_information = missing
        assessment.contradictions = contradictions
        if assessment.decision_state == "approved_internally" and (
            missing or contradictions or assessment.lifecycle_state not in {"decision", "periodic_reassessment"}
        ):
            assessment.decision_state = "incomplete"
            assessment.legal_uncertainty.append(
                "Approval was blocked because the assessment is incomplete or contradictory."
            )
        if bump_version:
            assessment.bump()
        else:
            assessment.modified_at = utc_now()
        self._path(assessment.assessment_id).write_text(
            json.dumps(assessment.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return assessment

    def create(self, title: str, owner: str = "") -> Assessment:
        item = Assessment(
            assessment_id=new_id("EIPD"),
            title=title,
            owner=owner,
            processing=empty_processing(),
            assumptions=[
                "This workspace supports assessment; regulatory duties remain with the controller/operators.",
                "No AEPD, GDPR, or EU AI Act certification is claimed.",
            ],
        )
        return self.save(item, bump_version=False)

    def ensure_demo(self) -> Assessment:
        existing = self.get("EIPD-porto-demo")
        if existing:
            return existing
        demo = demo_assessment()
        return self.save(demo, bump_version=False)

    def add_review(
        self,
        assessment: Assessment,
        *,
        role: str,
        actor: str,
        decision: str,
        rationale: str,
        comments: str = "",
    ) -> Assessment:
        if role == "dpo" and decision == "approved_internally":
            # DPO advises; controller decides (Art. 35(2) consult, Art. 24 accountability).
            decision = "privacy_review_recorded"
        assessment.reviews.append(
            {
                "role": role,
                "actor": actor,
                "decision": decision,
                "rationale": rationale,
                "comments": comments,
                "assessment_version": assessment.version,
                "timestamp": utc_now(),
            }
        )
        if role == "decision_maker":
            if decision == "approved_internally" and (
                assessment.missing_information or assessment.contradictions
            ):
                assessment.decision_state = "incomplete"
            else:
                assessment.decision_state = decision
                if decision in {"approved_internally", "rejected", "requires_additional_mitigation", "art36_consultation_flagged"}:
                    assessment.lifecycle_state = "decision"
        return self.save(assessment)

    def export_dict(self, assessment_id: str) -> dict[str, Any]:
        item = self.get(assessment_id)
        if not item:
            raise FileNotFoundError(assessment_id)
        return item.to_dict()
