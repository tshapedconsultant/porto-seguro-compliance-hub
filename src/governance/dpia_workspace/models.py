from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

LIFECYCLE_STATES = (
    "draft",
    "processing_description",
    "necessity_screening",
    "necessity_proportionality",
    "risk_assessment",
    "mitigation_planning",
    "residual_risk_review",
    "privacy_dpo_review",
    "decision",
    "periodic_reassessment",
)

DECISION_STATES = (
    "draft",
    "incomplete",
    "pending_review",
    "approved_internally",
    "rejected",
    "requires_additional_mitigation",
    "art36_consultation_flagged",
)

# Porto Seguro internal scale — NOT an official AEPD formula.
LIKELIHOOD_LABELS = {1: "rare", 2: "unlikely", 3: "possible", 4: "likely", 5: "almost_certain"}
SEVERITY_LABELS = {1: "negligible", 2: "limited", 3: "significant", 4: "high", 5: "very_high"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


@dataclass
class Assessment:
    assessment_id: str
    title: str
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    modified_at: str = field(default_factory=utc_now)
    owner: str = ""
    lifecycle_state: str = "draft"
    decision_state: str = "draft"
    processing: dict[str, Any] = field(default_factory=dict)
    screening: dict[str, Any] = field(default_factory=dict)
    proportionality: dict[str, Any] = field(default_factory=dict)
    risks: list[dict[str, Any]] = field(default_factory=list)
    controls: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    legal_uncertainty: list[str] = field(default_factory=list)
    generated_proposals_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Assessment":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def bump(self) -> None:
        self.modified_at = utc_now()
        self.version += 1


def empty_processing() -> dict[str, Any]:
    return {
        "activity_name": "",
        "controller": {"name": "", "contact": ""},
        "dpo_contact": "",
        "process_owner": "",
        "processors": [],
        "joint_controllers": [],
        "purposes": [],
        "legal_bases": [],
        "data_subjects": [],
        "personal_data_categories": [],
        "special_category_art9": False,
        "criminal_data_art10": False,
        "sources": [],
        "recipients": [],
        "international_transfers": [],
        "retention": "",
        "deletion_anonymisation": "",
        "systems": [],
        "data_flows": [],
        "approximate_individuals": None,
        "frequency": "",
        "toms": [],
        "uses_identifiable_personal_data": False,
        "data_status": "none_demo",
        "anonymisation_justification": "",
        "art9_condition": "",
        "automated_decisions_with_legal_effects": False,
        "vulnerable_individuals": False,
        "ai_system_id": "porto-seguro-ebm-v1",
    }


def validate_processing(processing: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    contradictions: list[str] = []
    if not processing.get("activity_name"):
        missing.append("processing.activity_name")
    if not processing.get("controller", {}).get("name"):
        missing.append("processing.controller.name")
    if not processing.get("purposes"):
        missing.append("processing.purposes")
    if processing.get("uses_identifiable_personal_data") and not processing.get("legal_bases"):
        missing.append("processing.legal_bases (required when identifiable personal data are processed)")
    if processing.get("special_category_art9") and not processing.get("uses_identifiable_personal_data"):
        contradictions.append("Art. 9 special-category flag is set but identifiable personal data is marked false.")
    if processing.get("international_transfers") and not processing.get("uses_identifiable_personal_data"):
        contradictions.append("International transfers listed while processing is described as non-personal / anonymised.")
    return missing, contradictions
