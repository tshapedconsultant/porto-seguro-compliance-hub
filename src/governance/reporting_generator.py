"""
Unified Reporting Generator Module
Part of Insurance Claim Prediction - Responsible AI Architecture

Consolidates Model Card and Compliance Reporting into one cohesive
regulatory artifact for Responsible AI, EU AI Act, and Solvency II.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DRIFT_EVIDENCE_DEFAULT_PATH = Path("docs/drift_monitoring_latest.json")


def format_drift_monitoring_section(
    drift_monitoring_results: Optional[Dict] = None,
    evidence_path: Path = DRIFT_EVIDENCE_DEFAULT_PATH,
) -> Dict[str, Any]:
    """
    Build Art. 9 post-market monitoring block for conformity reports.

    Loads docs/drift_monitoring_latest.json when no live results are passed.
    """
    payload = drift_monitoring_results
    if not payload and evidence_path.exists():
        try:
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read drift evidence %s: %s", evidence_path, exc)

    if not payload:
        return {
            "status": "Not Evaluated",
            "overall_status": "not_evaluated",
            "monitoring_passed": None,
            "evidence_file": str(evidence_path),
            "monitoring_module": "src.monitoring.production_compliance_gate",
            "summary": (
                "Post-market monitoring not yet executed. "
                "Run: python run_production_monitor.py"
            ),
        }

    drift_report = payload.get("drift_report", payload)
    overall = drift_report.get("overall_status", "unknown")
    monitoring_passed = payload.get("monitoring_passed")
    if monitoring_passed is None:
        monitoring_passed = overall == "healthy"

    return {
        "status": "evidence_available" if monitoring_passed else "review_required",
        "overall_status": overall,
        "monitoring_passed": bool(monitoring_passed),
        "evidence_file": str(evidence_path),
        "monitoring_module": "src.monitoring.production_compliance_gate",
        "last_monitored_at": payload.get("saved_at") or drift_report.get("monitoring_date"),
        "data_drift_detected": drift_report.get("data_drift", {}).get("drift_detected"),
        "model_drift_detected": drift_report.get("model_drift", {}).get("drift_detected"),
        "alerts": drift_report.get("alerts", []),
        "summary": (
            "Evaluated continuously via production_compliance_gate. "
            f"See {evidence_path.name} for current status."
        ),
    }


def generate_unified_ai_report(
    model_info: Dict,
    performance_metrics: Dict,
    training_data_info: Dict,
    explainability_report: Optional[Dict] = None,
    data_quality_report: Optional[Dict] = None,
    bias_audit_results: Optional[Dict] = None,
    drift_monitoring_results: Optional[Dict] = None,
    validation_results: Optional[Dict] = None,
    output_path: Optional[str] = None,
) -> Dict:
    """
    Generate a unified AI report (Model Card + Compliance Report).

    Args:
        model_info: Model metadata and configuration
        performance_metrics: Model performance metrics
        training_data_info: Training dataset information
        explainability_report: Explainability outputs
        data_quality_report: Data quality validation results
        bias_audit_results: Bias and fairness audit results
        drift_monitoring_results: Drift monitoring outputs
        validation_results: Validation outputs
        output_path: Optional path to save report

    Returns:
        dict: Unified report
    """
    logger.info("Generating unified AI report")

    explainability_report = explainability_report or {}
    data_quality_report = data_quality_report or {}
    bias_audit_results = bias_audit_results or {}
    drift_monitoring_results = drift_monitoring_results or {}
    validation_results = validation_results or {}

    report = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "document_type": "Unified AI Report",
            "compliance_standards": [
                "Solvency II (EU Insurance Regulation)",
                "EU AI Act (High-Risk AI Systems)",
                "Responsible AI Framework",
            ],
        },
        "model_details": {
            "name": model_info.get("name", "Porto Seguro Insurance Claim Prediction - EBM"),
            "version": model_info.get("version", "1.0.0"),
            "date": model_info.get("training_date", datetime.now().isoformat()),
            "description": model_info.get(
                "description", "Explainable Boosting Machine for predicting insurance claims"
            ),
            "model_type": model_info.get("model_type", "ExplainableBoostingClassifier"),
            "framework": model_info.get("framework", "Microsoft InterpretML"),
            "architecture": model_info.get("architecture", "Polars (data processing) + EBM (modeling)"),
            "hyperparameters": model_info.get("hyperparameters", {}),
        },
        "intended_use": {
            "primary_use": "Predict probability of insurance claim for policyholders",
            "use_cases": [
                "Risk assessment for insurance underwriting",
                "Premium pricing optimization",
                "Claim prediction for portfolio management",
            ],
            "out_of_scope": [
                "Direct premium calculation (requires actuarial models)",
                "Fraud detection (requires specialized models)",
                "Legal or regulatory compliance decisions",
            ],
            "users": "Insurance underwriters, actuaries, risk managers",
        },
        "training_data": {
            "dataset": "Porto Seguro Safe Driver Prediction",
            "source": "Kaggle Competition",
            "source_file": training_data_info.get("source_file", "train.csv"),
            "records": training_data_info.get("total_records", 0),
            "features": training_data_info.get("total_features", 0),
            "target_distribution": training_data_info.get("target_distribution", {}),
            "positive_class_rate": training_data_info.get("positive_class_rate"),
            "train_test_split": training_data_info.get("train_test_split", "80/20 stratified (hold-out test)"),
            "data_quality_score": training_data_info.get(
                "quality_score", data_quality_report.get("quality_score", 0.0)
            ),
            "missing_value_columns": training_data_info.get("missing_value_columns", 0),
        },
        "performance_metrics": {
            "roc_auc": performance_metrics.get("roc_auc", 0.0),
            "f1_score": performance_metrics.get("f1_score", 0.0),
            "precision": performance_metrics.get("precision", 0.0),
            "recall": performance_metrics.get("recall", 0.0),
            "accuracy": performance_metrics.get("accuracy", 0.0),
            "evaluation_method": "Train-test split and/or cross-validation",
        },
        "explainability_compliance": {
            "global_explanations": "Available",
            "local_explanations": "Available",
            "feature_interactions": "Available",
            "explainability_method": "Native EBM glass-box explainability (InterpretML)",
            "evidence_status": "evidence_available" if explainability_report else "not_assessed",
            "summary": explainability_report.get("compliance_notes", {}),
        },
        "solvency_ii_compliance": {
            "risk_management": "Model explainability enables risk assessment",
            "governance": "Model documentation and monitoring in place",
            "validation": "Model performance validated on test set",
            "evidence_status": "review_required",
            "compliance_status": "not_a_conformity_decision",
        },
        "eu_ai_act_compliance": {
            "risk_category": "conditional — Annex III 5(c) is life/health, not all insurance",
            "transparency": "Native explainability provided",
            "human_oversight": "Model supports human-in-the-loop decisions",
            "accuracy_robustness": f"ROC-AUC: {performance_metrics.get('roc_auc', 0.0):.4f}",
            "evidence_status": "conditional",
            "compliance_status": "not_a_conformity_decision",
        },
        "responsible_ai_compliance": {
            "fairness": bias_audit_results or "Not Evaluated",
            "transparency": "Full explainability provided",
            "accountability": "Model decisions are traceable",
            "robustness": validation_results or "Not Evaluated",
            "privacy": "Demo Kaggle features are publisher-anonymised; not a Recital 26 legal finding",
            "drift_monitoring": format_drift_monitoring_section(drift_monitoring_results),
            "evidence_status": "review_required",
            "compliance_status": "not_a_conformity_decision",
        },
        "recommendations": [
            "Monitor model performance in production",
            "Regular retraining with updated data",
            "Maintain explainability reports for audits",
            "Document model decisions for regulatory compliance",
        ],
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Unified AI report saved to {output_path}")

    return report


def generate_compliance_report(
    model_info: Dict,
    performance_metrics: Dict,
    explainability_report: Dict,
    data_quality_report: Dict,
    bias_audit_results: Optional[Dict] = None,
    drift_monitoring_results: Optional[Dict] = None,
    validation_results: Optional[Dict] = None,
    training_data_info: Optional[Dict] = None,
    shap_lime_results: Optional[Dict] = None,
    output_path: Optional[str] = None,
) -> Dict:
    """
    Backward-compatible wrapper for compliance report generation.
    """
    merged_training = dict(training_data_info or {})
    if not merged_training.get("total_records") and data_quality_report.get("records"):
        merged_training.setdefault("total_records", data_quality_report["records"])

    return generate_unified_ai_report(
        model_info=model_info,
        performance_metrics=performance_metrics,
        training_data_info=merged_training,
        explainability_report=explainability_report,
        data_quality_report=data_quality_report,
        bias_audit_results=bias_audit_results,
        drift_monitoring_results=drift_monitoring_results,
        validation_results=validation_results,
        output_path=output_path,
    )


def generate_model_card(
    model_info: Dict,
    performance_metrics: Dict,
    training_data_info: Dict,
    output_path: Optional[str] = None,
) -> Dict:
    """
    Backward-compatible wrapper for model card generation.
    """
    return generate_unified_ai_report(
        model_info=model_info,
        performance_metrics=performance_metrics,
        training_data_info=training_data_info,
        output_path=output_path,
    )
