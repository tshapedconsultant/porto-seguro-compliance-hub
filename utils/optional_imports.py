"""
Centralized optional imports and availability flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


def _fallback_explainability(*args, **kwargs):
    return {"available": False, "error": "SHAP/LIME modules not available"}


@dataclass
class OptionalModules:
    bias_audit_available: bool
    validation_available: bool
    shap_available: bool
    drift_available: bool
    comprehensive_explainability: Callable[..., Any]
    shap_explanation: Callable[..., Any]
    lime_explanation: Callable[..., Any]


def load_optional_modules() -> OptionalModules:
    bias_audit_available = False
    validation_available = False
    shap_available = False
    drift_available = False

    comprehensive_explainability = _fallback_explainability
    shap_explanation = _fallback_explainability
    lime_explanation = _fallback_explainability

    try:
        from src.governance.bias_audit import comprehensive_bias_audit, demographic_parity_test  # noqa: F401

        bias_audit_available = True
    except Exception:
        pass

    try:
        from src.models.evaluation import (  # noqa: F401
            adversarial_testing,
            comprehensive_validation,
            stratified_cross_validation,
        )

        validation_available = True
    except Exception:
        pass

    try:
        from src.models import explainability

        comprehensive_explainability = explainability.comprehensive_explainability
        shap_explanation = explainability.shap_explanation
        lime_explanation = explainability.lime_explanation
        shap_available = explainability.SHAP_AVAILABLE
    except Exception:
        pass

    try:
        from src.monitoring.drift_monitoring import (  # noqa: F401
            continuous_drift_monitoring,
            detect_data_drift,
            detect_model_drift,
        )

        drift_available = True
    except Exception:
        pass

    return OptionalModules(
        bias_audit_available=bias_audit_available,
        validation_available=validation_available,
        shap_available=shap_available,
        drift_available=drift_available,
        comprehensive_explainability=comprehensive_explainability,
        shap_explanation=shap_explanation,
        lime_explanation=lime_explanation,
    )


OPTIONAL_MODULES = load_optional_modules()
