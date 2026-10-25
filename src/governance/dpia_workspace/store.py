from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
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

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$")


def _content_fingerprint(assessment: Assessment) -> str:
    body = assessment.to_dict()
    for skip in ("modified_at", "version", "reviews", "approved_content_hash", "approved_version"):
        body.pop(skip, None)
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def approval_eligible(assessment: Assessment) -> tuple[bool, list[str]]:
    """AEPD-style minimum: description, necessity/proportionality, risks, measures. Not a legal clearance."""
    gaps: list[str] = []
    missing, contradictions = validate_processing(assessment.processing)
    gaps.extend(missing)
    gaps.extend(contradictions)
    if not assessment.screening.get("outcome"):
        gaps.append("screening.outcome")
    if not assessment.proportionality:
        gaps.append("necessity_and_proportionality")
    if not assessment.risks:
        gaps.append("risk_register")
    proc = assessment.processing or {}
    if proc.get("data_status") == "identifiable" and not proc.get("legal_bases"):
        gaps.append("legal_bases_per_purpose")
    if proc.get("special_category_art9") and not proc.get("art9_condition"):
        gaps.append("art9_condition")
    if proc.get("data_status") == "anonymised_claimed" and not proc.get("anonymisation_justification"):
        gaps.append("anonymisation_justification")
    return (not gaps, gaps)


class AssessmentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or "docs/governance/assessments").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_id(self, assessment_id: str) -> str:
        if not SAFE_ID.match(assessment_id or ""):
            raise ValueError("invalid assessment_id")
        return assessment_id

    def _path(self, assessment_id: str) -> Path:
        aid = self._safe_id(assessment_id)
        path = (self.root / f"{aid}.json").resolve()
        if not str(path).startswith(str(self.root) + os.sep) and path.parent != self.root:
            raise ValueError("assessment path escapes store root")
        return path

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json") if SAFE_ID.match(p.stem))

    def get(self, assessment_id: str) -> Assessment | None:
        path = self._path(assessment_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Assessment.from_dict(data)

    def save(self, assessment: Assessment, *, bump_version: bool = True) -> Assessment:
        self._safe_id(assessment.assessment_id)
        missing, contradictions = validate_processing(assessment.processing)
        assessment.missing_information = missing
        assessment.contradictions = contradictions
        ok, gaps = approval_eligible(assessment)
        fingerprint = _content_fingerprint(assessment)
        if assessment.decision_state == "approved_internally":
            prior = assessment.to_dict().get("approved_content_hash")
            if not ok:
                assessment.decision_state = "incomplete"
                assessment.legal_uncertainty.append("Approval blocked: " + "; ".join(gaps))
            elif prior and prior != fingerprint:
                assessment.decision_state = "pending_review"
                assessment.legal_uncertainty.append(
                    "Material change invalidated prior internal approval; new review required."
                )
        if bump_version:
            assessment.bump()
        else:
            assessment.modified_at = utc_now()
        payload = assessment.to_dict()
        path = self._path(assessment.assessment_id)
        fd, tmp = tempfile.mkstemp(prefix=".eipa_", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
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
        try:
            existing = self.get("EIPD-porto-demo")
        except ValueError:
            existing = None
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
            decision = "privacy_review_recorded"
        if role == "decision_maker" and decision == "approved_internally":
            ok, gaps = approval_eligible(assessment)
            if not ok:
                decision = "incomplete"
                rationale = (rationale + " | gaps: " + "; ".join(gaps)).strip()
        assessment.reviews.append(
            {
                "role": role,
                "actor": actor,
                "decision": decision,
                "rationale": rationale,
                "comments": comments,
                "assessment_version": assessment.version,
                "content_hash": _content_fingerprint(assessment),
                "timestamp": utc_now(),
            }
        )
        if role == "decision_maker":
            assessment.decision_state = decision
            if decision == "approved_internally":
                assessment.lifecycle_state = "decision"
                data = assessment.to_dict()
                data["approved_content_hash"] = _content_fingerprint(assessment)
                data["approved_version"] = assessment.version
                assessment = Assessment.from_dict(data)
            elif decision in {"rejected", "requires_additional_mitigation", "art36_consultation_flagged", "incomplete"}:
                if decision != "incomplete":
                    assessment.lifecycle_state = "decision"
        return self.save(assessment)

    def export_dict(self, assessment_id: str) -> dict[str, Any]:
        item = self.get(assessment_id)
        if not item:
            raise FileNotFoundError(assessment_id)
        return item.to_dict()
