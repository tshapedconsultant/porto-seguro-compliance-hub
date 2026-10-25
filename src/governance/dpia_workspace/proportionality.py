"""GDPR Art. 35(7)(b) necessity and proportionality — flags, not a legal clearance."""

from __future__ import annotations

from typing import Any

from src.governance.dpia_workspace.models import utc_now


def assess_proportionality(processing: dict[str, Any], answers: dict[str, Any] | None = None) -> dict[str, Any]:
    answers = answers or {}
    concerns: list[str] = []
    findings: dict[str, str] = {}

    purposes = processing.get("purposes") or []
    findings["purpose_specification"] = "specified" if purposes else "missing"
    if not purposes:
        concerns.append("Purpose is not specified.")

    if processing.get("uses_identifiable_personal_data") and not processing.get("legal_bases"):
        findings["lawfulness"] = "unresolved"
        concerns.append("Identifiable personal data without a documented Art. 6 (and Art. 9 if applicable) basis.")
    elif not processing.get("uses_identifiable_personal_data"):
        findings["lawfulness"] = "recital_26_anonymisation_asserted"
    else:
        findings["lawfulness"] = "basis_documented_pending_legal_review"

    if answers.get("less_intrusive_alternative_exists") is True and answers.get("alternative_rejected_reason") in (None, ""):
        concerns.append("A less intrusive alternative was acknowledged without a recorded reason to reject it.")

    if answers.get("personal_data_necessary_for_ai") is False and processing.get("uses_identifiable_personal_data"):
        concerns.append("Personal data are marked unnecessary for the AI function but processing still uses them.")

    if processing.get("automated_decisions_with_legal_effects") and not answers.get("art22_safeguards"):
        concerns.append("Automated decisions with legal/similar effects lack documented Art. 22(3) safeguards.")

    blocking = any("without a documented" in c or "still uses them" in c for c in concerns)
    return {
        "article": "GDPR Art. 35(7)(b)",
        "findings": findings,
        "concerns": concerns,
        "blocking_lawfulness_or_necessity": blocking,
        "note": "Technical safeguards cannot compensate for processing that fails essential lawfulness, necessity, or proportionality.",
        "assessed_at": utc_now(),
        "answers": answers,
    }
