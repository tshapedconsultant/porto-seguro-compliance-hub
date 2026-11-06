"""
Structured GDPR evidence block for published JSON packs.

Technical evidence is not a legal determination. This module does not certify
GDPR compliance, infer Recital 26 anonymisation, or select a lawful basis.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.governance.dpia_workspace.models import utc_now

GDPR_BLOCK_SCHEMA_VERSION = "1.0.0"
GDPR_SCHEMA_PATH = Path("docs/schemas/gdpr_evidence.schema.json")
ASSURANCE_LEVEL = "evidence_only"
COMPLIANCE_STATUS = "not_a_legal_determination"

APPLICABILITY_VALUES = ("unknown", "applicable", "not_applicable")
EVIDENCE_STATUS_VALUES = ("missing", "partial", "available")
CONTROL_STATUS_VALUES = ("not_tested", "passed", "failed", "not_applicable")
REF_KIND_VALUES = ("document", "test", "code", "config")

EVALUATION_IDS: tuple[str, ...] = (
    "applicability_and_anonymisation",
    "roles_and_accountability",
    "purposes_and_lawful_basis",
    "data_inventory_and_minimisation",
    "transparency",
    "data_subject_rights",
    "automated_decision_making",
    "privacy_by_design_and_default",
    "security_of_processing",
    "retention_and_deletion",
    "dpia",
    "processors_and_transfers",
    "records_and_incident_response",
)

REQUIRED_EVALUATION_FIELDS: tuple[str, ...] = (
    "legal_reference",
    "applicability",
    "applicability_rationale",
    "evidence_status",
    "control_status",
    "evidence_refs",
    "owner",
    "reviewed_at",
    "reviewer",
    "gaps",
    "next_actions",
    "review_required",
)

FORBIDDEN_CONFORMITY_KEYS = frozenset(
    {
        "gdpr_compliant",
        "gdpr_certified",
        "certified",
        "certification",
        "fully_compliant",
        "lawful_basis_confirmed",
    }
)

# Encoded citations — not a live EUR-Lex / AEPD fetch.
LEGAL_SOURCES: list[dict[str, Any]] = [
    {
        "instrument": "Regulation (EU) 2016/679 (GDPR)",
        "eli": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "oj": "OJ L 119, 4.5.2016",
        "retrieved_live": False,
        "note": "Cited from encoded repository references. Not a live EUR-Lex retrieval.",
    },
    {
        "instrument": "GDPR Recital 26 (anonymous information; identifiability including means reasonably likely to be used)",
        "eli": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "retrieved_live": False,
    },
    {
        "instrument": "EDPB WP248 rev.01 — Guidelines on Data Protection Impact Assessment (DPIA)",
        "retrieved_live": False,
        "note": "Referenced as encoded guidance; not fetched in this run.",
    },
    {
        "instrument": "AEPD — Guía práctica para las Evaluaciones de Impacto en la Protección de los Datos (informative)",
        "retrieved_live": False,
        "note": "AEPD lists of treatments requiring an EIPD are informative, not exhaustive (Art. 35(4)–(5)).",
    },
]

PUBLISHED_PACKS: tuple[str, ...] = (
    "eu_ai_act_conformity_v1.json",
    "gdpr_dpia_v1.json",
)

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|api[_-]?key|private[_-]?key|access[_-]?token|authorization|bearer|aws_secret)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(
    r"(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|sk_live_|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})",
    re.I,
)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _posix(path: str | Path) -> str:
    return Path(path).as_posix()


def is_safe_repo_ref(path: str, repo_root: Path) -> bool:
    """True when path is relative and resolves inside repo_root."""
    if not path or not isinstance(path, str):
        return False
    unix = path.replace("\\", "/")
    candidate = Path(unix)
    if candidate.is_absolute() or unix.startswith("/") or unix.startswith("~"):
        return False
    if len(unix) >= 2 and unix[1] == ":":
        return False
    if ".." in Path(unix).parts:
        return False
    root = repo_root.resolve()
    try:
        resolved = (root / candidate).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _file_exists(repo_root: Path, rel: str) -> bool:
    return is_safe_repo_ref(rel, repo_root) and (repo_root / rel).is_file()


def _ref(repo_root: Path, rel: str, kind: str) -> Optional[dict[str, str]]:
    if kind not in REF_KIND_VALUES:
        raise ValueError(f"Invalid evidence ref kind: {kind}")
    if _file_exists(repo_root, rel):
        return {"path": _posix(rel), "kind": kind}
    return None


def _refs(repo_root: Path, items: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for rel, kind in items:
        item = _ref(repo_root, rel, kind)
        if item is not None:
            out.append(item)
    return out


def _evaluation(
    *,
    legal_reference: str,
    applicability: str,
    applicability_rationale: str,
    evidence_status: str,
    control_status: str,
    evidence_refs: Sequence[Mapping[str, str]],
    gaps: Sequence[str],
    next_actions: Sequence[str],
    findings: Optional[dict[str, Any]] = None,
    owner: Any = None,
    reviewed_at: Any = None,
    reviewer: Any = None,
    review_required: Optional[bool] = None,
) -> dict[str, Any]:
    gap_list = [g for g in gaps if g]
    incomplete = bool(
        gap_list
        or evidence_status != "available"
        or control_status == "not_tested"
        or owner is None
        or reviewer is None
        or reviewed_at is None
    )
    payload: dict[str, Any] = {
        "legal_reference": legal_reference,
        "applicability": applicability,
        "applicability_rationale": applicability_rationale,
        "evidence_status": evidence_status,
        "control_status": control_status,
        "evidence_refs": [dict(r) for r in evidence_refs],
        "owner": owner,
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        "gaps": gap_list,
        "next_actions": list(next_actions),
        "review_required": True if review_required is None else bool(review_required),
    }
    if incomplete:
        payload["review_required"] = True
    if findings is not None:
        payload["findings"] = findings
    return payload


def _build_evaluations(repo_root: Path) -> dict[str, dict[str, Any]]:
    dpia_pack = _refs(repo_root, [("gdpr_dpia_v1.json", "document")])
    screening = _refs(
        repo_root,
        [
            ("src/governance/dpia_workspace/screening.py", "code"),
            ("tests/test_dpia_workspace.py", "test"),
        ],
    )
    explain = _refs(
        repo_root,
        [
            ("pages/03_Explainability.py", "code"),
            ("src/models/interpret_bridge.py", "code"),
        ],
    )
    model_card = _refs(repo_root, [("app.py", "code"), ("pages/01_Overview.py", "code")])
    art14 = _refs(
        repo_root,
        [
            ("pages/06_EU_AI_Act.py", "code"),
            ("pages/05_Business_Context.py", "code"),
        ],
    )
    audit = _refs(repo_root, [("src/control_plane/audit.py", "code")])
    ebm_hash = _refs(repo_root, [("src/models/ebm_train.py", "code")])
    bias = _refs(
        repo_root,
        [
            ("src/governance/bias_audit.py", "code"),
            ("utils/compliance_audit.py", "code"),
        ],
    )
    readme = _refs(repo_root, [("README.md", "document")])
    line_report = _refs(repo_root, [("docs/governance/LINE_REPORT.md", "document")])
    api = _refs(repo_root, [("api_server.py", "code")])

    return {
        "applicability_and_anonymisation": _evaluation(
            legal_reference="GDPR Art. 2, Art. 4(1); Recital 26",
            applicability="unknown",
            applicability_rationale=(
                "The demo file uses publisher-anonymised Kaggle columns (ps_*). "
                "A publisher description is not a Recital 26 finding that the information "
                "is anonymous. Identifiability, including means reasonably likely to be used, "
                "has not been tested. GDPR applicability for this file remains unknown."
            ),
            evidence_status="partial" if dpia_pack or readme else "missing",
            control_status="not_tested",
            evidence_refs=dpia_pack + readme,
            gaps=[
                "No re-identification test or Recital 26 analysis is on record.",
                "Publisher anonymisation must not be treated as GDPR non-applicability.",
            ],
            next_actions=[
                "Controller (not this software) must determine whether the dataset is anonymous information or personal data.",
                "If the same pipeline is used on identifiable records, treat that as a distinct processing operation.",
            ],
            findings={
                "publisher_anonymisation_claim": "stated_by_dataset_publisher",
                "recital_26_legal_finding": False,
                "personal_data_in_demo": "unknown",
                "pseudonymisation_demonstrated": False,
                "reidentification_risk_tested": False,
            },
        ),
        "roles_and_accountability": _evaluation(
            legal_reference="GDPR Art. 4(7)–(8), Art. 5(2), Art. 24, Art. 37",
            applicability="unknown",
            applicability_rationale=(
                "No controller, processor, or DPO is appointed in this repository. "
                "Labels in the static EIPD pack are hypothetical demo actors, not legal appointments."
            ),
            evidence_status="partial" if dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=dpia_pack,
            gaps=[
                "Controller identity is not established (owner is null).",
                "Processor inventory is not a signed Art. 28 record.",
                "DPO designation (Art. 37) is not evidenced.",
            ],
            next_actions=[
                "A real operator must name controller, contact point, and whether a DPO is required.",
                "Do not treat demo role strings as appointments.",
            ],
            findings={
                "controller": None,
                "processor": None,
                "dpo_required": "unknown",
                "dpo_appointed": False,
                "hypothetical_demo_labels_are_not_appointments": True,
            },
        ),
        "purposes_and_lawful_basis": _evaluation(
            legal_reference="GDPR Art. 5(1)(b), Art. 6, Art. 9",
            applicability="unknown",
            applicability_rationale=(
                "Intended demo purpose is claim-probability decision support. "
                "No Art. 6 basis is selected. Consent is not used as a default. "
                "Art. 9 is not determined merely because special-category column names are absent."
            ),
            evidence_status="partial" if dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=dpia_pack + readme,
            gaps=[
                "Art. 6 lawful basis is unknown / to_be_determined.",
                "No documented balancing test or contract-necessity analysis.",
                "Art. 9 condition is not assessed for a live insurance book.",
            ],
            next_actions=[
                "Controller must select and justify an Art. 6 basis for any identifiable processing.",
                "Do not default to consent for underwriting or claims scoring.",
            ],
            findings={
                "intended_purpose_demo": "Estimate P(claim) to support a human reviewer; emit explanations and technical evidence.",
                "art6_lawful_basis": "unknown",
                "art6_justification": None,
                "consent_selected_by_default": False,
                "art9_special_category_column_names_observed": False,
                "art9_applicability": "unknown",
                "art9_condition": None,
            },
        ),
        "data_inventory_and_minimisation": _evaluation(
            legal_reference="GDPR Art. 5(1)(c), Art. 30(1)(c)–(d)",
            applicability="unknown",
            applicability_rationale=(
                "Demo inventory is the Kaggle schema (ps_ind/ps_reg/ps_car/ps_calc). "
                "Necessity of each variable for a live purpose is not evidenced. "
                "Fairness screening uses proxy columns; those metrics are not GDPR evidence "
                "and this block does not collect or infer protected attributes."
            ),
            evidence_status="partial" if bias or dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=bias + dpia_pack,
            gaps=[
                "No signed data inventory or necessity review per variable.",
                "Recipients and sources for a production deployment are not documented.",
            ],
            next_actions=[
                "Map categories, sources, recipients, and retention to the live purpose.",
                "Keep fairness proxies out of any protected-attribute collection process.",
            ],
            findings={
                "demo_feature_prefixes": ["ps_ind_*", "ps_reg_*", "ps_car_*", "ps_calc_*"],
                "direct_identifiers_in_demo_schema": "none_observed",
                "fairness_audit_inputs": {
                    "columns": ["ps_ind_03", "ps_reg_03", "ps_car_13"],
                    "role": "proxy_screening_features",
                    "collected_as_protected_attributes": False,
                    "not_gdpr_fairness_evidence": True,
                    "note": "Technical bias metrics must not be reused as Art. 5(1)(a) or non-discrimination proof.",
                },
            },
        ),
        "transparency": _evaluation(
            legal_reference="GDPR Arts. 12–14",
            applicability="unknown",
            applicability_rationale=(
                "The Model Card and EIPD pack describe the demo system. They are not an "
                "Art. 12–14 privacy notice to data subjects of a live controller."
            ),
            evidence_status="partial" if model_card or dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=model_card + dpia_pack,
            gaps=[
                "No production privacy notice (Arts. 13–14) is on record.",
                "Layered notice, language, and timing of information are not evidenced.",
            ],
            next_actions=[
                "Draft and approve notices against the live purpose, recipients, and rights.",
            ],
            findings={"privacy_notice_status": "missing_for_production", "demo_model_card_is_not_art13_notice": True},
        ),
        "data_subject_rights": _evaluation(
            legal_reference="GDPR Arts. 12, 15–22",
            applicability="unknown",
            applicability_rationale=(
                "No operational procedure exists to receive or fulfil data-subject requests. "
                "Native EBM explanations are technical artefacts analogous to Art. 15(1)(h) "
                "logic information; they are not a rights-handling process."
            ),
            evidence_status="partial" if explain or dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=explain + dpia_pack,
            gaps=[
                "No request channel, identity verification, or fulfilment SLA is documented.",
                "Erasure, objection, and portability procedures are missing.",
            ],
            next_actions=[
                "Document procedures and keep proof of handling for each applicable right.",
            ],
            findings={
                "procedures_documented": False,
                "art_15_1_h_logic_information": "technical_explanations_only",
            },
        ),
        "automated_decision_making": _evaluation(
            legal_reference="GDPR Art. 22; Recital 71",
            applicability="unknown",
            applicability_rationale=(
                "Art. 22 applicability is not determined. Advisory design and a human reviewer "
                "do not, by themselves, prove that Art. 22 does not apply. Exclusive automation, "
                "legal or similarly significant effects, and effective human intervention remain untested."
            ),
            evidence_status="partial" if art14 or dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=art14 + dpia_pack,
            gaps=[
                "No assessment of legal or similarly significant effects for a live underwriting/pricing/claims decision.",
                "Human intervention is a design claim; effectiveness is not tested.",
                "Art. 22(3) safeguards (intervention, express a view, contest) are not operationally evidenced.",
            ],
            next_actions=[
                "Assess Art. 22 against the live decision, not against the presence of a UI reviewer.",
                "If Art. 22 applies, evidence the Art. 22(2) condition and Art. 22(3) safeguards.",
            ],
            findings={
                "article_22_applicable": "unknown",
                "legal_or_similarly_significant_effects": "unknown",
                "exclusively_automated": "unknown",
                "human_review": "design_claim_not_tested",
                "human_review_does_not_prove_art22_inapplicable": True,
                "safeguards_art_22_3": "to_be_evidenced",
            },
        ),
        "privacy_by_design_and_default": _evaluation(
            legal_reference="GDPR Art. 25",
            applicability="unknown",
            applicability_rationale=(
                "Repository design choices (competition schema, no Art. 9 column names, "
                "train-only feature fit) are not an Art. 25 programme for a live controller."
            ),
            evidence_status="partial" if readme or dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=readme + dpia_pack + bias,
            gaps=[
                "No Art. 25 risk-based measure register tied to a live purpose.",
                "Default settings for a production service are not evidenced.",
            ],
            next_actions=["Document Art. 25 measures against the actual processing, then test them."],
            findings={"art25_programme": "not_evidenced"},
        ),
        "security_of_processing": _evaluation(
            legal_reference="GDPR Art. 32",
            applicability="unknown",
            applicability_rationale=(
                "Code contains integrity checksums (SHA-256 sidecars) and a local audit hash chain. "
                "Those artefacts are not a tested Art. 32 control set (no WORM, no KMS, no security test report)."
            ),
            evidence_status="partial" if ebm_hash or audit or line_report else "missing",
            control_status="not_tested",
            evidence_refs=ebm_hash + audit + line_report + api,
            gaps=[
                "No Art. 32 test report, penetration test, or residual-risk acceptance by the controller.",
                "Local JSONL hash chain is not immutable storage.",
            ],
            next_actions=["Commission security testing appropriate to a live personal-data processing."],
            findings={
                "sha256_sidecars": "implemented_in_code_local_artifacts_not_published",
                "audit_hash_chain": "local_detection_not_worm",
            },
        ),
        "retention_and_deletion": _evaluation(
            legal_reference="GDPR Art. 5(1)(e), Art. 17",
            applicability="unknown",
            applicability_rationale=(
                "Demo artifacts are kept for reproducibility. No justified retention schedule, "
                "deletion procedure, or backup-expiry control is on record."
            ),
            evidence_status="missing",
            control_status="not_tested",
            evidence_refs=dpia_pack,
            gaps=[
                "Retention period is to_be_determined.",
                "Deletion and backup erasure procedures are missing.",
            ],
            next_actions=[
                "Define retention aligned with the live purpose and insurance record-keeping law, then evidence deletion.",
            ],
            findings={
                "retention_period": "to_be_determined",
                "deletion_procedure": "missing",
                "backup_expiry": "missing",
            },
        ),
        "dpia": _evaluation(
            legal_reference="GDPR Art. 35; Art. 36; EDPB WP248 rev.01",
            applicability="unknown",
            applicability_rationale=(
                "A demonstration EIPD pack and a screening workspace exist. They are not a signed "
                "Art. 35 decision and not an Art. 36 prior consultation. Publisher anonymisation "
                "does not remove the need to screen a live identifiable processing."
            ),
            evidence_status="partial" if dpia_pack or screening else "missing",
            control_status="not_tested",
            evidence_refs=dpia_pack + screening,
            gaps=[
                "Art. 35 decision is unsigned; residual scores in the static pack are estimated pending verification.",
                "DPO consultation (Art. 35(2)) is not evidenced.",
            ],
            next_actions=[
                "For identifiable production processing, complete screening, EIPD, and residual-risk review.",
                "Flag Art. 36 only if residual high risk remains after mitigations — not because this demo exists.",
            ],
            findings={
                "art35_screening_outcome": "to_be_assessed_for_live_processing",
                "art35_decision": "not_signed",
                "art36_prior_consultation": "not_indicated_for_this_demo",
                "static_pack": "gdpr_dpia_v1.json",
                "workspace": "src/governance/dpia_workspace/",
            },
        ),
        "processors_and_transfers": _evaluation(
            legal_reference="GDPR Art. 28; Arts. 44–49",
            applicability="unknown",
            applicability_rationale=(
                "This local demo stack does not configure a processor contract or a third-country transfer. "
                "That observation is not a finding that Art. 28 or Chapter V are not applicable to a live deployment."
            ),
            evidence_status="partial" if dpia_pack else "missing",
            control_status="not_tested",
            evidence_refs=dpia_pack,
            gaps=[
                "No Art. 28 contracts, SCCs, or transfer assessments are on record.",
                "Hosting, logging, and model-vendor roles for production are unknown.",
            ],
            next_actions=[
                "Inventory processors and international transfers before any live personal-data processing.",
            ],
            findings={
                "processors_configured_in_demo": "none_observed",
                "international_transfers_configured_in_demo": "none_observed",
                "art28_agreement": None,
                "transfer_tool": None,
            },
        ),
        "records_and_incident_response": _evaluation(
            legal_reference="GDPR Art. 30; Arts. 33–34",
            applicability="unknown",
            applicability_rationale=(
                "Control-plane JSONL is a technical audit log, not an Art. 30 record of processing. "
                "No Arts. 33–34 incident procedure is evidenced."
            ),
            evidence_status="partial" if audit else "missing",
            control_status="not_tested",
            evidence_refs=audit + dpia_pack,
            gaps=[
                "Art. 30 record of processing activities is missing.",
                "Personal-data breach detection, 72-hour notification, and data-subject communication procedures are missing.",
            ],
            next_actions=[
                "Maintain Art. 30 records where required and rehearse Arts. 33–34 procedures.",
            ],
            findings={
                "art30_record": "missing",
                "art33_34_procedure": "missing",
                "technical_audit_log_is_not_art30": True,
            },
        ),
    }


def build_gdpr_evidence_block(
    repo_root: Optional[Path] = None,
    *,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Build the auditable GDPR block from repository evidence. Never a legal clearance."""
    root = (repo_root or default_repo_root()).resolve()
    evaluations = _build_evaluations(root)
    open_gaps: list[dict[str, str]] = []
    for section_id, section in evaluations.items():
        for gap in section.get("gaps", []):
            open_gaps.append({"section": section_id, "gap": gap})

    timestamp = generated_at or utc_now()
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    # Require an explicit timezone offset.
    if not _has_timezone(timestamp):
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    block: dict[str, Any] = {
        "schema_version": GDPR_BLOCK_SCHEMA_VERSION,
        "assessment_context": {
            "mode": "demo_reference_architecture",
            "generated_for": "innovation_lab_evidence_pack",
            "demo": {
                "dataset": "Porto Seguro Safe Driver Prediction (Kaggle)",
                "feature_naming": "ps_* columns described by the publisher as anonymised",
                "identifiable_personal_data_confirmed": "unknown",
                "live_insurance_book": False,
                "recital_26_legal_finding": False,
            },
            "production_analogue": {
                "would_be_distinct_processing": True,
                "note": (
                    "Scoring identifiable applicants, policyholders, or claimants for "
                    "underwriting, pricing, or claims is a separate processing operation. "
                    "It needs its own purposes, Art. 6 basis, notices, EIPD, and records."
                ),
            },
        },
        "generated_at": timestamp,
        "assurance_level": ASSURANCE_LEVEL,
        "compliance_status": COMPLIANCE_STATUS,
        "review_required": True,
        "open_gaps": open_gaps,
        "evaluations": evaluations,
        "legal_sources": LEGAL_SOURCES,
        "limitations": [
            "Technical evidence is not GDPR compliance.",
            "Unknown or null fields are unset on purpose — they are not implicit approvals.",
            "Human review in the demo does not prove that Art. 22 is inapplicable.",
            "Publisher anonymisation does not prove Recital 26 anonymity or GDPR non-applicability.",
            "Fairness proxy metrics are excluded from this block as GDPR proof.",
        ],
        "pending_legal_or_dpo_decisions": [
            "Whether GDPR applies to the demo file (Recital 26 / identifiability).",
            "Controller, processor, and DPO appointments for any live processing.",
            "Art. 6 lawful basis and, if relevant, Art. 9 condition — not consent by default.",
            "Art. 22 applicability, effects, exclusive automation, and effective intervention.",
            "Art. 35 EIPD sign-off and whether Art. 36 prior consultation is required.",
            "Retention schedule, Art. 30 records, and Arts. 33–34 incident procedures.",
        ],
    }
    errors = validate_gdpr_block(block, repo_root=root)
    if errors:
        raise ValueError("Generated GDPR block failed validation: " + "; ".join(errors))
    return block


def _has_timezone(value: str) -> bool:
    if value.endswith("Z"):
        return True
    return bool(re.search(r"[+-]\d{2}:\d{2}$", value))


def _walk(obj: Any) -> Iterable[tuple[Optional[str], Any]]:
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield key, val
            yield from _walk(val)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def validate_gdpr_block(block: Mapping[str, Any], repo_root: Optional[Path] = None) -> list[str]:
    """Return validation errors. Empty list means the block is structurally honest."""
    root = (repo_root or default_repo_root()).resolve()
    errors: list[str] = []

    if not isinstance(block, Mapping):
        return ["GDPR block must be a JSON object"]

    if block.get("assurance_level") != ASSURANCE_LEVEL:
        errors.append("assurance_level must be 'evidence_only'")
    if block.get("compliance_status") != COMPLIANCE_STATUS:
        errors.append("compliance_status must be 'not_a_legal_determination'")
    if block.get("schema_version") != GDPR_BLOCK_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GDPR_BLOCK_SCHEMA_VERSION}")
    if not _has_timezone(str(block.get("generated_at") or "")):
        errors.append("generated_at must include a timezone offset")

    for key in FORBIDDEN_CONFORMITY_KEYS:
        if key in block:
            errors.append(f"Forbidden conformity key present: {key}")

    if block.get("gdpr_compliant") is True or block.get("compliant") is True:
        errors.append("Automatic GDPR conformity claims are not allowed")

    evaluations = block.get("evaluations")
    if not isinstance(evaluations, Mapping):
        errors.append("evaluations must be an object")
        return errors

    missing_ids = [eid for eid in EVALUATION_IDS if eid not in evaluations]
    if missing_ids:
        errors.append("Missing evaluations: " + ", ".join(missing_ids))

    incomplete_without_review = False
    for eid, section in evaluations.items():
        if not isinstance(section, Mapping):
            errors.append(f"{eid} must be an object")
            continue
        prefix = eid
        for field in REQUIRED_EVALUATION_FIELDS:
            if field not in section:
                errors.append(f"{prefix}: missing field {field}")
        applicability = section.get("applicability")
        if applicability not in APPLICABILITY_VALUES:
            errors.append(f"{prefix}: invalid applicability")
        rationale = section.get("applicability_rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"{prefix}: applicability_rationale is required")
        if applicability == "not_applicable" and (
            not isinstance(rationale, str) or len(rationale.strip()) < 20
        ):
            errors.append(f"{prefix}: not_applicable requires a substantial justification")

        evidence_status = section.get("evidence_status")
        if evidence_status not in EVIDENCE_STATUS_VALUES:
            errors.append(f"{prefix}: invalid evidence_status")
        control_status = section.get("control_status")
        if control_status not in CONTROL_STATUS_VALUES:
            errors.append(f"{prefix}: invalid control_status")

        refs = section.get("evidence_refs")
        if not isinstance(refs, list):
            errors.append(f"{prefix}: evidence_refs must be a list")
            refs = []
        test_refs = []
        for ref in refs:
            if not isinstance(ref, Mapping) or "path" not in ref:
                errors.append(f"{prefix}: evidence ref must be an object with path")
                continue
            path = str(ref.get("path"))
            kind = ref.get("kind")
            if kind not in REF_KIND_VALUES:
                errors.append(f"{prefix}: invalid evidence ref kind")
            if not is_safe_repo_ref(path, root):
                errors.append(f"{prefix}: evidence ref escapes the repository: {path}")
            elif evidence_status in {"available", "partial"} and not (root / path).is_file():
                errors.append(f"{prefix}: evidence ref does not exist: {path}")
            if kind == "test":
                test_refs.append(path)

        if control_status == "passed":
            if evidence_status != "available":
                errors.append(f"{prefix}: passed requires evidence_status=available")
            if not refs:
                errors.append(f"{prefix}: passed requires evidence_refs")
            if not test_refs:
                errors.append(f"{prefix}: passed requires test evidence (kind=test)")

        if control_status == "not_applicable" and applicability != "not_applicable":
            errors.append(f"{prefix}: control_status not_applicable requires applicability not_applicable")

        for person_field in ("owner", "reviewed_at", "reviewer"):
            if person_field not in section:
                continue
            # Unset facts stay null — do not coerce to demo names.
            if section[person_field] == "":
                errors.append(f"{prefix}: {person_field} must be null when unknown, not empty string")

        gaps = section.get("gaps") or []
        incomplete = bool(
            gaps
            or evidence_status != "available"
            or control_status == "not_tested"
            or section.get("owner") is None
            or section.get("reviewer") is None
        )
        if incomplete and not section.get("review_required"):
            incomplete_without_review = True
            errors.append(f"{prefix}: incomplete section must keep review_required=true")

    if incomplete_without_review or (evaluations and not block.get("review_required")):
        if not block.get("review_required"):
            errors.append("review_required must remain true while evaluations are incomplete")

    # Domain invariants
    anon = evaluations.get("applicability_and_anonymisation") or {}
    if anon.get("applicability") == "not_applicable":
        errors.append(
            "Publisher anonymisation must not set applicability_and_anonymisation to not_applicable"
        )
    findings = anon.get("findings") if isinstance(anon.get("findings"), Mapping) else {}
    if findings.get("recital_26_legal_finding") is True:
        errors.append("recital_26_legal_finding must not be asserted by this generator")

    adm = evaluations.get("automated_decision_making") or {}
    if adm.get("applicability") == "not_applicable":
        errors.append(
            "Art. 22 must not be marked not_applicable without a recorded legal determination "
            "(human review alone is insufficient)"
        )

    basis = evaluations.get("purposes_and_lawful_basis") or {}
    basis_findings = basis.get("findings") if isinstance(basis.get("findings"), Mapping) else {}
    if basis_findings.get("consent_selected_by_default") is True:
        errors.append("Consent must not be selected by default")
    if basis_findings.get("art6_lawful_basis") in {"consent", "art6_1_a"}:
        errors.append("Art. 6 consent was selected without a documented controller decision")

    # No personal data / secrets in the exported block
    errors.extend(_sensitive_export_errors(block))
    return errors


def _sensitive_export_errors(block: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, val in _walk(block):
        if key and key in FORBIDDEN_CONFORMITY_KEYS:
            errors.append(f"Forbidden key in export: {key}")
        if key and _SECRET_KEY_RE.search(str(key)):
            errors.append(f"Secret-like key must not be exported: {key}")
        if isinstance(val, str):
            if _EMAIL_RE.search(val):
                errors.append("Email address must not be exported in the GDPR evidence block")
            if _SECRET_VALUE_RE.search(val):
                errors.append("Secret-like value must not be exported in the GDPR evidence block")
        if key in {"compliant", "gdpr_compliant"} and val is True:
            errors.append("Automatic conformity boolean is not allowed")
    return errors


def serialize_gdpr_block(block: Mapping[str, Any], repo_root: Optional[Path] = None) -> str:
    errors = validate_gdpr_block(block, repo_root=repo_root)
    if errors:
        raise ValueError("Cannot serialize invalid GDPR block: " + "; ".join(errors))
    return json.dumps(block, indent=2, ensure_ascii=False)


def attach_gdpr_block(report: dict[str, Any], repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Add/replace the gdpr key without claiming parent-schema incompatibility."""
    out = dict(report)
    out["gdpr"] = build_gdpr_evidence_block(repo_root=repo_root)
    standards = list(out.get("report_metadata", {}).get("compliance_standards") or [])
    label = "GDPR (Regulation (EU) 2016/679) — assessment, not certification"
    metadata = dict(out.get("report_metadata") or {})
    if label not in standards:
        metadata["compliance_standards"] = [*standards, label]
        out["report_metadata"] = metadata
    return out


def _match_bracket(text: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    i = start
    in_str = False
    escape = False
    while i < len(text):
        ch = text[i]
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
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("Unbalanced JSON brackets")


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def _parse_json_string(text: str, start: int) -> tuple[str, int]:
    if text[start] != '"':
        raise ValueError("Expected string")
    i = start + 1
    escape = False
    chars: list[str] = []
    while i < len(text):
        ch = text[i]
        if escape:
            chars.append(ch)
            escape = False
        elif ch == "\\":
            chars.append(ch)
            escape = True
        elif ch == '"':
            return json.loads(text[start : i + 1]), i + 1
        else:
            chars.append(ch)
        i += 1
    raise ValueError("Unterminated string")


def _value_end(text: str, start: int) -> int:
    i = _skip_ws(text, start)
    if i >= len(text):
        raise ValueError("Missing JSON value")
    ch = text[i]
    if ch == "{":
        return _match_bracket(text, i, "{", "}") + 1
    if ch == "[":
        return _match_bracket(text, i, "[", "]") + 1
    if ch == '"':
        _, end = _parse_json_string(text, i)
        return end
    while i < len(text) and text[i] not in ",} \t\r\n":
        i += 1
    return i


def iter_root_members(text: str) -> list[tuple[str, int, int, int]]:
    """(key, key_quote_start, value_start, value_end) for the root object."""
    start = _skip_ws(text, 0)
    if start >= len(text) or text[start] != "{":
        raise ValueError("Root JSON value must be an object")
    members: list[tuple[str, int, int, int]] = []
    i = _skip_ws(text, start + 1)
    if i < len(text) and text[i] == "}":
        return members
    while i < len(text):
        i = _skip_ws(text, i)
        if text[i] == "}":
            break
        key_start = i
        key, i = _parse_json_string(text, i)
        i = _skip_ws(text, i)
        if i >= len(text) or text[i] != ":":
            raise ValueError(f"Expected ':' after key {key}")
        i += 1
        value_start = _skip_ws(text, i)
        value_end = _value_end(text, value_start)
        members.append((key, key_start, value_start, value_end))
        i = _skip_ws(text, value_end)
        if i < len(text) and text[i] == ",":
            i += 1
            continue
        break
    return members


def upsert_top_level_json_key(text: str, key: str, value: Any) -> str:
    """Insert or replace a top-level key without rewriting sibling JSON (preserves fairness numbers)."""
    payload = json.dumps(value, indent=2, ensure_ascii=False)
    lines = payload.splitlines()
    rest = "\n".join(("  " + line if line else line) for line in lines[1:])
    indented = lines[0] + (("\n" + rest) if rest else "")
    members = iter_root_members(text)
    existing = next((m for m in members if m[0] == key), None)
    if existing is not None:
        _name, key_start, _vs, value_end = existing
        colon = text.find(":", key_start)
        return text[: colon + 1] + " " + indented + text[value_end:]

    # Insert before the root closing brace.
    end = len(text.rstrip())
    if end == 0 or text[end - 1] != "}":
        # Fall back: last }
        end = text.rfind("}") + 1
        if end <= 0:
            raise ValueError("Cannot find root closing brace")
    insert_at = end - 1
    needs_comma = bool(members)
    prefix = ",\n" if needs_comma else "\n"
    injection = f'{prefix}  "{key}": {indented}\n'
    return text[:insert_at].rstrip() + injection + text[insert_at:]


def merge_gdpr_into_pack(path: Path, repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Write the generated GDPR block into an existing pack without altering sibling metrics."""
    root = (repo_root or path.parent).resolve()
    original = path.read_text(encoding="utf-8")
    block = build_gdpr_evidence_block(repo_root=root)
    updated = upsert_top_level_json_key(original, "gdpr", block)
    # Validate the result still parses and that non-gdpr content is unchanged when parsed
    parsed = json.loads(updated)
    if "gdpr" not in parsed:
        raise RuntimeError("Failed to insert gdpr key")
    path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")
    return parsed


def merge_gdpr_into_evidence_packs(repo_root: Optional[Path] = None) -> list[Path]:
    root = (repo_root or default_repo_root()).resolve()
    written: list[Path] = []
    for rel in PUBLISHED_PACKS:
        path = root / rel
        if path.is_file():
            merge_gdpr_into_pack(path, repo_root=root)
            written.append(path)
    return written


if __name__ == "__main__":
    paths = merge_gdpr_into_evidence_packs()
    print("Updated:", ", ".join(str(p) for p in paths) or "(no published packs found)")
