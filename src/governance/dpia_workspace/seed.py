from __future__ import annotations

from src.governance.dpia_workspace.models import Assessment, empty_processing, utc_now
from src.governance.dpia_workspace.risk_engine import score_risk
from src.governance.dpia_workspace.screening import screen_necessity


def demo_assessment() -> Assessment:
    processing = empty_processing()
    processing.update(
        {
            "activity_name": "Puntuación de probabilidad de siniestro (apoyo a suscripción) — demo Kaggle",
            "controller": {
                "name": "Porto Seguro Compliance Hub (controlador hipotético de laboratorio)",
                "contact": "demo@localhost",
            },
            "dpo_contact": "pendiente — demostración",
            "process_owner": "laboratorio de innovación",
            "purposes": [
                "Estimar P(siniestro) como apoyo a un revisor humano",
                "Generar explicaciones glass-box y evidencia de auditoría",
            ],
            "legal_bases": [
                "Demo: Recital 26 (datos de competición anonimizados; no se afirma base del art. 6 de un asegurador real)"
            ],
            "data_subjects": ["Ninguna persona identificable en el fichero demo"],
            "personal_data_categories": ["Variables anonimizadas ps_ind/ps_reg/ps_car/ps_calc"],
            "special_category_art9": False,
            "criminal_data_art10": False,
            "sources": ["Kaggle Porto Seguro Safe Driver Prediction (train.csv)"],
            "recipients": ["Operador local Streamlit/API"],
            "international_transfers": [],
            "retention": "Artefactos de reproducibilidad del demo; en producción definir plazo art. 5(1)(e)",
            "deletion_anonymisation": "Sin índice de identidad en el demo",
            "systems": ["Polars + EBM", "Streamlit Model Card", "FastAPI /predict"],
            "data_flows": ["CSV → FE (train-only fit) → EBM → explicación local → JSON de evidencia"],
            "approximate_individuals": 595212,
            "frequency": "batch de entrenamiento + inferencia bajo demanda",
            "toms": [
                "Sin atributos del art. 9",
                "SHA-256 de artefactos",
                "Montaje Docker de modelo en solo lectura",
                "Auditoría de sesgo por proxies",
            ],
            "uses_identifiable_personal_data": False,
            "automated_decisions_with_legal_effects": True,
            "vulnerable_individuals": False,
            "ai_system_id": "porto-seguro-ebm-v1",
        }
    )
    answers = {
        "q_profiling": True,
        "q_automated_legal": True,
        "q_monitoring": False,
        "q_art9_scale": False,
        "q_novel_tech": True,
        "q_vulnerable": False,
        "q_access_block": True,
        "q_combine_datasets": False,
        "q_ai_training_pd": False,
        "q_third_party_model": False,
    }
    screening = screen_necessity(answers, processing, author="seed")
    risk = score_risk(
        likelihood=4,
        severity=4,
        threat="Over-reliance on an advisory claim score without contestability (Art. 22 analogue)",
        harm="Applicant cannot obtain meaningful information or human intervention",
        existing_safeguards=["EBM local explanations", "threshold routing"],
        processing_id="EIPD-porto-demo",
    )
    return Assessment(
        assessment_id="EIPD-porto-demo",
        title="EIPD demo — Porto Seguro claim scoring",
        owner="laboratorio",
        lifecycle_state="residual_risk_review",
        decision_state="pending_review",
        processing=processing,
        screening=screening,
        risks=[risk],
        evidence=[
            {
                "evidence_id": "EVD-static-dpia",
                "type": "published_pack",
                "description": "Static Art. 35 pack gdpr_dpia_v1.json",
                "source": "gdpr_dpia_v1.json",
                "related": "EIPD-porto-demo",
                "owner": "governance",
                "collection_date": utc_now(),
                "verification_date": None,
                "verification_state": "declared",
            }
        ],
        assumptions=[
            "Demo architecture; not a supervisory notification or Art. 36 filing.",
            "Kaggle ps_* features are treated as anonymised competition data unless shown otherwise.",
        ],
        legal_uncertainty=[
            "Whether Recital 26 anonymisation holds is a facts-and-law question for the controller, not this software.",
        ],
        generated_proposals_only=True,
    )
