"""Explainable risk scoring. Internal Porto Seguro methodology — not an AEPD official scale."""

from __future__ import annotations

from typing import Any

from src.governance.dpia_workspace.models import (
    LIKELIHOOD_LABELS,
    SEVERITY_LABELS,
    new_id,
    utc_now,
)

RISK_FAMILIES = (
    "rights_and_freedoms",
    "information_security",
    "regulatory_exposure",
    "business_operational",
)

CONTROL_STATES = (
    "proposed",
    "configured",
    "implemented_unverified",
    "tested",
    "verified_in_target",
    "partially_effective",
    "ineffective",
    "disabled_or_superseded",
    "not_applicable",
)

def clamp_scale(value: int) -> int:
    return max(1, min(5, int(value)))


def score_risk(
    *,
    likelihood: int,
    severity: int,
    family: str = "rights_and_freedoms",
    threat: str,
    harm: str,
    existing_safeguards: list[str] | None = None,
    processing_id: str = "",
) -> dict[str, Any]:
    if family not in RISK_FAMILIES:
        raise ValueError(f"Unknown risk family: {family}")
    lhd = clamp_scale(likelihood)
    sev = clamp_scale(severity)
    inherent = lhd * sev
    return {
        "risk_id": new_id("RSK"),
        "processing_id": processing_id,
        "family": family,
        "family_note": "Families are not interchangeable. Residual scoring below uses rights_and_freedoms unless specified.",
        "threat_scenario": threat,
        "potential_harm": harm,
        "existing_safeguards": existing_safeguards or [],
        "likelihood": lhd,
        "likelihood_label": LIKELIHOOD_LABELS[lhd],
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "inherent_score": inherent,
        "mitigations": [],
        "owner": "",
        "target_date": "",
        "evidence_requirements": [],
        "implementation_state": "proposed",
        "residual_likelihood": lhd,
        "residual_severity": sev,
        "residual_score": inherent,
        "acceptance_decision": "open",
        "decision_maker": "",
        "review_date": "",
        "scoring_methodology": "porto_seguro_lxd_1to5",
        "not_official_aepd_scale": True,
        "uncertainty": False,
        "updated_at": utc_now(),
    }


def reassess_residual(risk: dict[str, Any], controls: list[dict[str, Any]]) -> dict[str, Any]:
    """Residual risk changes only when linked controls have verification evidence — not by declaration."""
    linked = [c for c in controls if risk.get("risk_id") in c.get("addresses_risks", [])]
    operational = [
        c
        for c in linked
        if c.get("status") == "verified_in_target"
        and c.get("verification_state") == "verified"
        and c.get("reduction_justification")
        and c.get("affects_dimension") in {"likelihood", "severity", "both"}
    ]
    if not operational:
        risk["residual_likelihood"] = risk["likelihood"]
        risk["residual_severity"] = risk["severity"]
        risk["residual_score"] = risk["inherent_score"]
        risk["residual_note"] = (
            "No operational verification in the target environment with a documented "
            "reduction justification; residual equals inherent. 'tested' is not enough."
        )
        risk["art36_flag"] = False
        risk["legal_review_prompt"] = risk["inherent_score"] >= 16 and risk.get("family") == "rights_and_freedoms"
        risk["updated_at"] = utc_now()
        return risk

    max_l, max_s = 0, 0
    for control in operational:
        dim = control["affects_dimension"]
        mag = max(0, min(2, int(control.get("reduction_magnitude") or 1)))
        if dim in {"likelihood", "both"}:
            max_l = max(max_l, mag)
        if dim in {"severity", "both"}:
            max_s = max(max_s, mag)
    rl = clamp_scale(risk["likelihood"] - max_l)
    rs = clamp_scale(risk["severity"] - max_s)
    risk["residual_likelihood"] = rl
    risk["residual_severity"] = rs
    risk["residual_score"] = rl * rs
    risk["residual_note"] = (
        f"Non-stacking residual: max verified reduction per dimension "
        f"(n={len(operational)} controls; overlapping controls do not accumulate)."
    )
    risk["art36_flag"] = False
    risk["legal_review_prompt"] = risk["residual_score"] >= 16 and risk.get("family") == "rights_and_freedoms"
    risk["updated_at"] = utc_now()
    return risk


def art36_needed(risks: list[dict[str, Any]]) -> dict[str, Any]:
    review = []
    for risk in risks:
        score = int(risk.get("residual_score") or risk.get("inherent_score") or 0)
        if risk.get("family") == "rights_and_freedoms" and score >= 16:
            review.append(risk)
        if risk.get("unevaluated"):
            review.append(risk)
    if not risks:
        consultation_status = "not_assessed"
    elif review:
        consultation_status = "legal_review_required"
    else:
        consultation_status = "not_assessed"
    return {
        "consultation_status": consultation_status,
        "may_require_prior_consultation": None,
        "legal_review_required": bool(review),
        "article": "GDPR Art. 36",
        "auto_submit": False,
        "note": (
            "A numeric score never files an Art. 36 consultation. "
            "consultation_status is not_assessed | legal_review_required | documented_decision."
        ),
        "flagged_risk_ids": [r["risk_id"] for r in review],
    }
