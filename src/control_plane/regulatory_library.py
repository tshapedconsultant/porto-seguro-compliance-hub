"""
Versioned EU AI Act / GDPR applicability rules.

Dates follow Regulation (EU) 2024/1689 as commonly applied:
- Entry into force: 1 Aug 2024 (Art. 113)
- Art. 5 prohibitions (selected) and AI literacy: 2 Feb 2025
- GPAI: 2 Aug 2025
- Most high-risk Annex III obligations: 2 Aug 2026
Re-verify against the current EUR-Lex consolidated text before relying on a date.
"""

from __future__ import annotations

from datetime import date
from typing import Any

SOURCE_VERIFIED_AT = "2026-10-25"
AI_ACT_CELEX = "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"

APPLICATION_CALENDAR = {
    "version": "2024/1689-calendar-v1",
    "source": AI_ACT_CELEX,
    "verified_at": SOURCE_VERIFIED_AT,
    "milestones": [
        {"id": "entry_into_force", "date": "2024-08-01", "refs": ["Art. 113"]},
        {"id": "prohibitions_and_literacy", "date": "2025-02-02", "refs": ["Art. 5", "Art. 4", "Art. 113"]},
        {"id": "gpai", "date": "2025-08-02", "refs": ["GPAI chapter", "Art. 113"]},
        {"id": "high_risk_annex_iii", "date": "2026-08-02", "refs": ["Annex III", "Arts 9-15", "Art. 26", "Art. 113"]},
        {"id": "embedded_high_risk_extension", "date": "2027-08-02", "refs": ["Art. 113 transitional"]},
    ],
}

MAPPINGS = [
    {
        "id": "AIA-5",
        "instrument": "EU AI Act",
        "article": "5",
        "summary": "Prohibited AI practices (conditions and exceptions in the legal text).",
        "actor": "any operator placing/using a prohibited practice",
        "conditions": "Use matches an Art. 5 prohibition after applying definitions and exceptions.",
        "applicability_status": "conditional",
        "application_milestone": "prohibitions_and_literacy",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "screening flag + DENY pending legal review",
        "human_review": True,
    },
    {
        "id": "AIA-9",
        "instrument": "EU AI Act",
        "article": "9",
        "summary": "Risk-management system for high-risk AI systems.",
        "actor": "provider of a high-risk AI system (deployer duties differ — Art. 26)",
        "conditions": "System is high-risk under Art. 6 / Annex I or III and no exemption applies.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "link EIPD risks + drift monitor evidence",
        "human_review": True,
    },
    {
        "id": "AIA-10",
        "instrument": "EU AI Act",
        "article": "10",
        "summary": "Data and data governance for high-risk systems.",
        "actor": "provider (high-risk)",
        "conditions": "High-risk classification confirmed.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "dataset validation evidence",
        "human_review": True,
    },
    {
        "id": "AIA-12",
        "instrument": "EU AI Act",
        "article": "12",
        "summary": "Record-keeping / logging capabilities for high-risk systems.",
        "actor": "provider (high-risk)",
        "conditions": "High-risk classification confirmed.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "JSONL audit events",
        "human_review": True,
    },
    {
        "id": "AIA-13",
        "instrument": "EU AI Act",
        "article": "13",
        "summary": "Transparency and information to deployers.",
        "actor": "provider (high-risk)",
        "conditions": "High-risk classification confirmed.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "model card + local explanations",
        "human_review": True,
    },
    {
        "id": "AIA-14",
        "instrument": "EU AI Act",
        "article": "14",
        "summary": "Human oversight for high-risk systems.",
        "actor": "provider design + deployer operationalisation",
        "conditions": "High-risk classification confirmed.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "approval tickets; advisory scores",
        "human_review": True,
    },
    {
        "id": "AIA-15",
        "instrument": "EU AI Act",
        "article": "15",
        "summary": "Accuracy, robustness, cybersecurity.",
        "actor": "provider (high-risk)",
        "conditions": "High-risk classification confirmed.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "hold-out metrics + SHA-256 + adversarial tests",
        "human_review": True,
    },
    {
        "id": "AIA-26",
        "instrument": "EU AI Act",
        "article": "26",
        "summary": "Obligations of deployers of high-risk AI systems.",
        "actor": "deployer",
        "conditions": "User is a deployer of a high-risk system.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "role must be declared; not inferred from model name",
        "human_review": True,
    },
    {
        "id": "AIA-27",
        "instrument": "EU AI Act",
        "article": "27",
        "summary": "Fundamental rights impact assessment for certain deployers of high-risk systems.",
        "actor": "specified deployers (public bodies and selected private deployers in the article)",
        "conditions": "Art. 27 personal scope — not all deployers.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "flag for legal review only",
        "human_review": True,
    },
    {
        "id": "AIA-50",
        "instrument": "EU AI Act",
        "article": "50",
        "summary": "Specified transparency obligations for certain AI systems.",
        "actor": "depends on system type (e.g. chatbot, deepfake — see article)",
        "conditions": "System falls within Art. 50 categories.",
        "applicability_status": "conditional",
        "application_milestone": "see Art. 113 / Art. 50",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "not assumed for tabular EBM scoring",
        "human_review": True,
    },
    {
        "id": "AIA-72",
        "instrument": "EU AI Act",
        "article": "72",
        "summary": "Post-market monitoring by providers of high-risk AI systems.",
        "actor": "provider (high-risk)",
        "conditions": "High-risk provider role.",
        "applicability_status": "conditional",
        "application_milestone": "high_risk_annex_iii",
        "source": AI_ACT_CELEX,
        "verified_at": SOURCE_VERIFIED_AT,
        "automation": "drift / production compliance gate",
        "human_review": True,
    },
]


def classify_system(answers: dict[str, Any]) -> dict[str, Any]:
    """Structured assessment — not a final legal classification."""
    role = answers.get("role", "unknown")  # provider | deployer | other | unknown
    annex_iii_insurance = bool(answers.get("annex_iii_insurance_scoring"))
    prohibited_flag = bool(answers.get("art5_concern"))
    missing = [k for k in ("role", "intended_purpose", "annex_iii_insurance_scoring") if answers.get(k) in (None, "", "unknown")]
    potential_high_risk = annex_iii_insurance
    return {
        "is_legal_classification": False,
        "role_declared": role,
        "potential_high_risk": potential_high_risk,
        "potential_art5_issue": prohibited_flag,
        "potential_art50": bool(answers.get("chatbot_or_synthetic_content")),
        "outstanding_legal_questions": missing,
        "note": "Classification is not inferred from model vendor or the mere presence of an AI component.",
        "calendar": APPLICATION_CALENDAR,
        "as_of": date.today().isoformat(),
    }


def applicable_mappings(classification: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in MAPPINGS:
        applicable = "uncertain"
        if item["article"] == "5":
            applicable = "review_required" if classification.get("potential_art5_issue") else "not_indicated"
        elif item["article"] == "50":
            applicable = "review_required" if classification.get("potential_art50") else "not_indicated"
        elif item["article"] == "27":
            applicable = "uncertain"
        elif classification.get("potential_high_risk"):
            if item["actor"].startswith("provider") and classification.get("role_declared") == "deployer":
                applicable = "possibly_not_this_actor"
            elif item["actor"].startswith("deployer") and classification.get("role_declared") == "provider":
                applicable = "possibly_not_this_actor"
            else:
                applicable = "potentially_applicable"
        else:
            applicable = "not_indicated_as_high_risk"
        out.append({**item, "computed_applicability": applicable})
    return out
