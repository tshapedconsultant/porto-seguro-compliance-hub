"""
GDPR Art. 35 necessity screening.

AEPD lists of treatments requiring an EIPD are informative, not exhaustive
(GDPR Art. 35(4)–(5); AEPD guidance). Outcomes are decision support, not a
determination of legal obligation.
"""

from __future__ import annotations

from typing import Any

from src.governance.dpia_workspace.models import utc_now

SCREENING_QUESTIONS = [
    {
        "id": "q_profiling",
        "text_es": "¿Hay evaluación o elaboración de perfiles sistemática y exhaustiva de personas?",
        "gdpr": "Art. 35(3)(a)",
        "weight": "indicator",
    },
    {
        "id": "q_automated_legal",
        "text_es": "¿Hay decisiones automatizadas con efectos jurídicos o igualmente significativos (p. ej. suscripción)?",
        "gdpr": "Art. 35(3)(a); Art. 22",
        "weight": "strong",
    },
    {
        "id": "q_monitoring",
        "text_es": "¿Hay observación sistemática de una zona de acceso público a gran escala?",
        "gdpr": "Art. 35(3)(c)",
        "weight": "strong",
    },
    {
        "id": "q_art9_scale",
        "text_es": "¿Hay tratamiento a gran escala de categorías especiales (art. 9) o datos de condenas (art. 10)?",
        "gdpr": "Art. 35(3)(b)",
        "weight": "strong",
    },
    {
        "id": "q_novel_tech",
        "text_es": "¿Se usan tecnologías nuevas o combinaciones nuevas (modelos, embeddings, agentes)?",
        "gdpr": "Art. 35(1); considering 91",
        "weight": "indicator",
    },
    {
        "id": "q_vulnerable",
        "text_es": "¿Se tratan datos de personas vulnerables?",
        "gdpr": "Art. 35(1); considering 75",
        "weight": "indicator",
    },
    {
        "id": "q_access_block",
        "text_es": "¿El tratamiento puede impedir ejercer un derecho o acceder a un servicio (seguro, crédito, empleo)?",
        "gdpr": "Art. 35(1); WP248",
        "weight": "strong",
    },
    {
        "id": "q_combine_datasets",
        "text_es": "¿Se combinan conjuntos recogidos con otras finalidades u otros responsables?",
        "gdpr": "Art. 35(1); considering 91",
        "weight": "indicator",
    },
    {
        "id": "q_ai_training_pd",
        "text_es": "¿Se usan datos personales identificables para entrenar, ajustar o evaluar el modelo?",
        "gdpr": "Art. 5(1)(b)–(c); Art. 35",
        "weight": "indicator",
    },
    {
        "id": "q_third_party_model",
        "text_es": "¿Hay proveedor de modelo / logs / embeddings de terceros?",
        "gdpr": "Art. 28; Art. 32; Art. 44",
        "weight": "indicator",
    },
]


def screen_necessity(
    answers: dict[str, bool | None],
    processing: dict[str, Any] | None = None,
    *,
    author: str = "",
) -> dict[str, Any]:
    processing = processing or {}
    indicators: list[str] = []
    strong: list[str] = []
    missing_evidence: list[str] = []
    uncertainty: list[str] = []

    invalid: list[str] = []
    for q in SCREENING_QUESTIONS:
        val = answers.get(q["id"])
        if val is None:
            missing_evidence.append(q["id"])
            uncertainty.append(f"Unanswered: {q['id']}")
            continue
        if val is not True and val is not False:
            invalid.append(q["id"])
            uncertainty.append(f"Invalid non-boolean answer for {q['id']}")
            continue
        if val is True:
            (strong if q["weight"] == "strong" else indicators).append(q["id"])

    if invalid:
        return {
            "outcome": "further_assessment_required",
            "reasoning": "Screening answers must be true, false, or omitted — not strings.",
            "strong_indicators": [],
            "other_indicators": [],
            "missing_evidence": missing_evidence,
            "uncertainty": uncertainty,
            "invalid_answers": invalid,
            "is_legal_determination": False,
            "voluntary_eipa_allowed": True,
            "author": author,
            "recorded_at": utc_now(),
            "answers": answers,
            "scope": "invalid_input",
        }

    data_status = processing.get("data_status") or (
        "identifiable" if processing.get("uses_identifiable_personal_data") else "none_demo"
    )
    if data_status in {"anonymised_claimed", "none_demo"}:
        uncertainty.append(
            "Controller asserts demo/anonymised data (Recital 26). If anonymisation is not irreversible, Art. 35 analysis still applies."
        )

    # No official numeric threshold. Strong Art. 35(3) matches drive "necessary".
    if strong:
        outcome = "full_eipa_appears_necessary"
        reasoning = (
            "One or more GDPR Art. 35(3) or equivalent high-risk indicators are present. "
            "AEPD lists are informative and not exhaustive; a full EIPD appears necessary."
        )
    elif missing_evidence:
        outcome = "further_assessment_required"
        reasoning = "Material screening questions are unanswered. A legal obligation cannot be ruled out."
    elif indicators:
        outcome = "further_assessment_required"
        reasoning = (
            "No automatic Art. 35(3) match, but residual high-risk indicators exist. "
            "A reasoned EIPD is recommended; the controller may conduct one voluntarily."
        )
    else:
        outcome = "full_eipa_may_not_be_necessary"
        reasoning = (
            "Available answers do not currently match typical Art. 35(3) triggers. "
            "This is not a finding that an EIPD is legally unnecessary."
        )

    scope = "gdpr_personal_data" if data_status == "identifiable" else "voluntary_design_assessment"
    if scope == "voluntary_design_assessment" and outcome == "full_eipa_appears_necessary":
        outcome = "voluntary_design_eipa_recommended"
        reasoning = (
            "High-risk indicators would support an Art. 35 EIPD IF identifiable personal data "
            "were processed. This record claims demo/anonymised data; this is not a finding "
            "that GDPR Art. 35 legally applies to that file."
        )

    refs = sorted({q["gdpr"] for q in SCREENING_QUESTIONS if answers.get(q["id"]) is True})
    return {
        "outcome": outcome,
        "scope": scope,
        "data_status": data_status,
        "reasoning": reasoning,
        "strong_indicators": strong,
        "other_indicators": indicators,
        "missing_evidence": missing_evidence,
        "uncertainty": uncertainty,
        "regulatory_references": refs or ["GDPR Art. 35", "AEPD EIPD guidance (informative lists)"],
        "recommended_next_steps": _next_steps(outcome),
        "voluntary_eipa_allowed": True,
        "author": author,
        "recorded_at": utc_now(),
        "answers": {k: answers.get(k) for k in [q["id"] for q in SCREENING_QUESTIONS]},
        "is_legal_determination": False,
        "methodology_note": "Porto Seguro screening is decision support. The controller decides whether Art. 35 applies.",
    }


def _next_steps(outcome: str) -> list[str]:
    if outcome == "full_eipa_appears_necessary":
        return [
            "Complete processing description and legal bases",
            "Necessity and proportionality (Art. 35(7)(b))",
            "Risk register on rights and freedoms",
            "Do not mark approved until DPO/privacy review and authorised decision",
        ]
    if outcome == "further_assessment_required":
        return ["Resolve unanswered screening items", "Document uncertainty", "Controller may still run a voluntary EIPD"]
    return [
        "Record the reasoned decision not to proceed, or run a voluntary EIPD",
        "Reassess if purpose, data, or automation changes",
    ]
