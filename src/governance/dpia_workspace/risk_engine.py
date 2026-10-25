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

EFFECTIVE_STATES = {"tested", "verified_in_target", "partially_effective"}


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
    verified = [
        c
        for c in linked
        if c.get("status") in EFFECTIVE_STATES and c.get("verification_state") in {"tested", "verified"}
    ]
    if not verified:
        risk["residual_likelihood"] = risk["likelihood"]
        risk["residual_severity"] = risk["severity"]
        risk["residual_score"] = risk["inherent_score"]
        risk["residual_note"] = "No verified control evidence; residual equals inherent."
        risk["art36_flag"] = risk["residual_score"] >= 16 and risk.get("family") == "rights_and_freedoms"
        risk["updated_at"] = utc_now()
        return risk

    reduction = 0
    if any(c.get("status") == "verified_in_target" for c in verified):
        reduction = 2
    elif any(c.get("status") == "tested" for c in verified):
        reduction = 1
    elif any(c.get("status") == "partially_effective" for c in verified):
        reduction = 1

    rl = clamp_scale(risk["likelihood"] - min(reduction, 1))
    rs = clamp_scale(risk["severity"] - (1 if reduction >= 2 else 0))
    risk["residual_likelihood"] = rl
    risk["residual_severity"] = rs
    risk["residual_score"] = rl * rs
    risk["residual_note"] = f"Reassessed from {len(verified)} verified control(s); reduction_level={reduction}."
    risk["art36_flag"] = risk["residual_score"] >= 16 and risk.get("family") == "rights_and_freedoms"
    risk["updated_at"] = utc_now()
    return risk


def art36_needed(risks: list[dict[str, Any]]) -> dict[str, Any]:
    flagged = [r for r in risks if r.get("art36_flag")]
    return {
        "may_require_prior_consultation": bool(flagged),
        "article": "GDPR Art. 36",
        "auto_submit": False,
        "note": "A high residual score is a prompt for human legal review, not a consultation filing.",
        "flagged_risk_ids": [r["risk_id"] for r in flagged],
    }
