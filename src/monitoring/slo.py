"""
Operational monitoring SLOs.

Technical detection is not a business decision, a legal finding, or a
discrimination conclusion. An alert cannot be marked resolved without evidence.

Limitations (lab default, not production ops):
- owner stays unassigned until a named human is recorded; required before
  production — unassigned is not an on-call roster
- evidence_integrity is a local SHA-256 checksum, not a signature, WORM store,
  or external forensic evidence
- this module does not change process-local rate limits or the static API key
- no notification routing (email, pager, chat); JSON records conditions and
  deadlines only
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

SCHEMA_VERSION = "1.0.0"

SLO_IDS = (
    "mon.ks_drift",
    "mon.performance_degradation",
    "mon.calibration_drift",
    "mon.fairness_screening",
    "mon.shadow_monitor",
    "mon.production_gate",
)

SEVERITIES = ("critical", "high", "medium", "low")
SLO_STATUSES = ("not_evaluated", "within_slo", "breached")
ALERT_STATUSES = ("open", "acknowledged", "in_progress", "resolved")
EVIDENCE_STATUSES = ("missing", "available")

KS_THRESHOLD = 0.10
PERFORMANCE_RELATIVE_DROP = 0.05
CALIBRATION_ECE_THRESHOLD = 0.05

FORBIDDEN_CONCLUSION_TERMS = (
    "discriminat",
    "gdpr_compliant",
    "art. 43",
    "conformity decision",
    "illegal",
    "non-compliant",
    "certified",
)

_DURATION_TO_DELTA = {
    "P1D": timedelta(days=1),
    "P2D": timedelta(days=2),
    "P5D": timedelta(days=5),
}


class SloValidationError(ValueError):
    """Raised when an SLO report or alert resolution is invalid."""


# Internal screening catalog only. Thresholds are not legal limits.
# owner stays "unassigned" until a named person is written in — never invent a
# DPO or model owner. That is the correct lab default. Production requires a
# named human assignment before go-live; unassigned is not an operating model.
SLO_CATALOG: List[Dict[str, Any]] = [
    {
        "slo_id": "mon.ks_drift",
        "name": "KS data drift",
        "signal": "ks_drift",
        "condition": (
            f"Any numeric feature KS statistic > {KS_THRESHOLD} vs the reference "
            f"distribution, or mean KS > {KS_THRESHOLD}."
        ),
        "severity": "high",
        "owner": "unassigned",
        "owner_role": "monitoring-owner",
        "required_action": (
            "Investigate covariate shift against the reference slice. "
            "Do not retrain, promote, or change pricing from this alert alone."
        ),
        "deadline": "P2D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
    {
        "slo_id": "mon.performance_degradation",
        "name": "Performance degradation",
        "signal": "performance_degradation",
        "condition": (
            f"Hold-out ROC-AUC, F1, precision, or recall drops more than "
            f"{PERFORMANCE_RELATIVE_DROP:.0%} relative to the training baseline."
        ),
        "severity": "high",
        "owner": "unassigned",
        "owner_role": "model-owner",
        "required_action": (
            "Investigate the metric drop versus the hold-out baseline. "
            "Technical degradation is not a regulatory non-conformity."
        ),
        "deadline": "P2D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
    {
        "slo_id": "mon.calibration_drift",
        "name": "Calibration drift",
        "signal": "calibration_drift",
        "condition": (
            f"Expected calibration error or max |predicted-positive rate − observed rate| "
            f"> {CALIBRATION_ECE_THRESHOLD}."
        ),
        "severity": "medium",
        "owner": "unassigned",
        "owner_role": "model-owner",
        "required_action": (
            "Investigate score reliability (ECE / threshold calibration error). "
            "This is not a pricing, solvency, or legal conclusion."
        ),
        "deadline": "P5D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
    {
        "slo_id": "mon.fairness_screening",
        "name": "Fairness screening",
        "signal": "fairness_screening",
        "condition": (
            "overall_assessment is review_required, or any attribute screening is "
            "fail or pass_with_review."
        ),
        "severity": "high",
        "owner": "unassigned",
        "owner_role": "responsible-ai-owner",
        "required_action": (
            "Review screening labels (fail / pass_with_review) and the four fairness "
            "layers. This alert is technical screening only — not a protected-class "
            "legal finding and not a GDPR / AI Act decision."
        ),
        "deadline": "P2D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
    {
        "slo_id": "mon.shadow_monitor",
        "name": "Shadow monitor",
        "signal": "shadow_monitor",
        "condition": (
            "Shadow monitor did not complete with artifacts, or the injected-drift / "
            "KS health check fired."
        ),
        "severity": "medium",
        "owner": "unassigned",
        "owner_role": "monitoring-owner",
        "required_action": (
            "Confirm shadow-monitor artifacts and last-run evidence. "
            "Not a production go-live decision."
        ),
        "deadline": "P2D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
    {
        "slo_id": "mon.production_gate",
        "name": "Production compliance gate",
        "signal": "production_gate",
        "condition": "monitoring_passed is false or overall_status is not healthy.",
        "severity": "critical",
        "owner": "unassigned",
        "owner_role": "monitoring-owner",
        "required_action": (
            "Hold promotion until a named owner records a business decision with "
            "evidence. The gate is an internal screen — not an Art. 43 result."
        ),
        "deadline": "P1D",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
        "business_decision": "not_inferred",
    },
]


def _utc_now(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _deadline_at(duration: str, now: datetime) -> str:
    delta = _DURATION_TO_DELTA.get(duration)
    if delta is None:
        raise SloValidationError(f"Unsupported deadline duration: {duration}")
    return (now + delta).isoformat()


def _evidence(*, status: str, refs: Sequence[str], summary: str) -> Dict[str, Any]:
    if status not in EVIDENCE_STATUSES:
        raise SloValidationError(f"Invalid evidence status: {status}")
    clean_refs = [str(item) for item in refs if str(item).strip()]
    return {
        "status": status,
        "refs": clean_refs,
        "summary": summary,
        "sufficient_to_resolve": False,
    }


def _alert_from_catalog(
    spec: Mapping[str, Any],
    *,
    now: datetime,
    evidence: Dict[str, Any],
    observed: Optional[str] = None,
) -> Dict[str, Any]:
    condition = spec["condition"]
    if observed:
        condition = f"{condition} Observed: {observed}"
    return {
        "slo_id": spec["slo_id"],
        "condition": condition,
        "severity": spec["severity"],
        "owner": spec["owner"],
        "owner_role": spec["owner_role"],
        "required_action": spec["required_action"],
        "deadline": spec["deadline"],
        "deadline_at": _deadline_at(spec["deadline"], now),
        "evidence": evidence,
        "status": "open",
        "resolved_requires_evidence": True,
        "detection_layer": "technical",
        "business_decision": "not_taken",
        "not_a_legal_finding": True,
        "not_a_discrimination_finding": True,
    }


def _evaluate_ks_drift(data_drift: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data_drift, Mapping) or not data_drift:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    features = data_drift.get("feature_drifts") or {}
    flagged = [
        name
        for name, info in features.items()
        if isinstance(info, Mapping) and info.get("drift_detected")
    ]
    breached = bool(data_drift.get("drift_detected")) or bool(flagged)
    score = data_drift.get("drift_score")
    observed = None
    if score is not None:
        observed = f"mean KS={float(score):.3f}"
        if flagged:
            observed += f"; features={', '.join(flagged[:8])}"
    refs = ["data_drift"]
    if flagged:
        refs.extend(f"data_drift.feature_drifts.{name}" for name in flagged[:8])
    return {"evaluated": True, "breached": breached, "observed": observed, "refs": refs}


def _evaluate_performance(model_drift: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(model_drift, Mapping) or not model_drift:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    changes = model_drift.get("metric_changes") or {}
    flagged = [
        name
        for name, info in changes.items()
        if isinstance(info, Mapping) and info.get("drift_detected")
    ]
    breached = bool(model_drift.get("drift_detected")) or bool(flagged)
    bits = []
    for name in flagged:
        rel = (changes.get(name) or {}).get("relative_change")
        if rel is not None:
            bits.append(f"{name} {float(rel):+.1%}")
    observed = "; ".join(bits) if bits else None
    refs = ["model_drift"]
    refs.extend(f"model_drift.metric_changes.{name}" for name in flagged)
    return {"evaluated": True, "breached": breached, "observed": observed, "refs": refs}


def _calibration_value(calibration: Mapping[str, Any]) -> Optional[float]:
    for key in ("ece", "max_ece", "max_absolute_error", "expected_calibration_error"):
        value = calibration.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _evaluate_calibration(calibration: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(calibration, Mapping) or not calibration:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    value = _calibration_value(calibration)
    if value is None and calibration.get("status") in {None, "not_computed", "missing"}:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    if value is None:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    breached = value > CALIBRATION_ECE_THRESHOLD
    return {
        "evaluated": True,
        "breached": breached,
        "observed": f"calibration_error={value:.4f} (threshold={CALIBRATION_ECE_THRESHOLD})",
        "refs": ["calibration"],
    }


def _screening_labels(fairness: Mapping[str, Any]) -> List[str]:
    labels: List[str] = []
    for block in ("demographic_parity", "equalized_odds"):
        tests = ((fairness.get(block) or {}).get("attribute_tests") or {})
        for info in tests.values():
            if not isinstance(info, Mapping):
                continue
            for key in (
                "parity_screening_result",
                "odds_screening_result",
                "tpr_screening_result",
                "fpr_screening_result",
            ):
                value = info.get(key)
                if isinstance(value, str):
                    labels.append(value)
    return labels


def _evaluate_fairness(fairness: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(fairness, Mapping) or not fairness:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    labels = _screening_labels(fairness)
    assessment = fairness.get("overall_assessment")
    evaluated = assessment is not None or bool(labels)
    if not evaluated:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    breached = assessment == "review_required" or any(
        label in {"fail", "pass_with_review"} for label in labels
    )
    observed = f"overall_assessment={assessment}"
    if labels:
        observed += f"; labels={', '.join(sorted(set(labels)))}"
    return {
        "evaluated": True,
        "breached": breached,
        "observed": observed,
        "refs": ["fairness.overall_assessment"],
    }


def _evaluate_shadow(shadow: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(shadow, Mapping) or not shadow:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    ran = shadow.get("ran")
    artifacts = shadow.get("artifacts_present")
    if ran is None and artifacts is None and shadow.get("last_run_at") is None:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    ks_alert = bool(shadow.get("ks_alert") or shadow.get("simulate_drift_fired"))
    missing_artifacts = artifacts is False
    did_not_run = ran is False
    breached = bool(did_not_run or missing_artifacts or ks_alert)
    bits = [
        f"ran={ran}",
        f"artifacts_present={artifacts}",
        f"ks_alert={ks_alert}",
    ]
    refs = ["shadow_monitor"]
    if shadow.get("evidence_path"):
        refs.append(str(shadow["evidence_path"]))
    return {
        "evaluated": True,
        "breached": breached,
        "observed": "; ".join(bits),
        "refs": refs,
    }


def _evaluate_gate(gate: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(gate, Mapping) or not gate:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    passed = gate.get("monitoring_passed")
    status = gate.get("overall_status")
    if passed is None and status is None:
        return {"evaluated": False, "breached": False, "observed": None, "refs": []}
    breached = passed is False or (status not in {None, "healthy"} and passed is not True)
    observed = f"monitoring_passed={passed}; overall_status={status}"
    refs = ["production_gate"]
    if gate.get("evidence_path"):
        refs.append(str(gate["evidence_path"]))
    return {
        "evaluated": True,
        "breached": breached,
        "observed": observed,
        "refs": refs,
    }


_EVALUATORS = {
    "mon.ks_drift": ("ks_drift", _evaluate_ks_drift),
    "mon.performance_degradation": ("performance_degradation", _evaluate_performance),
    "mon.calibration_drift": ("calibration_drift", _evaluate_calibration),
    "mon.fairness_screening": ("fairness_screening", _evaluate_fairness),
    "mon.shadow_monitor": ("shadow_monitor", _evaluate_shadow),
    "mon.production_gate": ("production_gate", _evaluate_gate),
}


def _signals_for(
    slo_id: str,
    *,
    data_drift: Optional[Mapping[str, Any]],
    model_drift: Optional[Mapping[str, Any]],
    calibration: Optional[Mapping[str, Any]],
    fairness: Optional[Mapping[str, Any]],
    shadow_monitor: Optional[Mapping[str, Any]],
    production_gate: Optional[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    mapping = {
        "mon.ks_drift": data_drift,
        "mon.performance_degradation": model_drift,
        "mon.calibration_drift": calibration,
        "mon.fairness_screening": fairness,
        "mon.shadow_monitor": shadow_monitor,
        "mon.production_gate": production_gate,
    }
    return mapping[slo_id]


def build_monitoring_slo_report(
    *,
    data_drift: Optional[Mapping[str, Any]] = None,
    model_drift: Optional[Mapping[str, Any]] = None,
    calibration: Optional[Mapping[str, Any]] = None,
    fairness: Optional[Mapping[str, Any]] = None,
    shadow_monitor: Optional[Mapping[str, Any]] = None,
    production_gate: Optional[Mapping[str, Any]] = None,
    generated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build the six operational SLOs from technical signals.

    Missing signals → not_evaluated (not a silent pass).
    The generator never emits status=resolved.
    Does not send notifications (no email, pager, or chat).
    Does not assign owners, change rate limits, or issue API keys.
    """
    now = _utc_now(generated_at)
    slos: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []

    for spec in SLO_CATALOG:
        slo_id = spec["slo_id"]
        _name, evaluator = _EVALUATORS[slo_id]
        verdict = evaluator(
            _signals_for(
                slo_id,
                data_drift=data_drift,
                model_drift=model_drift,
                calibration=calibration,
                fairness=fairness,
                shadow_monitor=shadow_monitor,
                production_gate=production_gate,
            )
        )
        if not verdict["evaluated"]:
            status = "not_evaluated"
            evidence = _evidence(
                status="missing",
                refs=[],
                summary="No technical signal supplied. not_evaluated is not within_slo.",
            )
            alert = None
        elif verdict["breached"]:
            status = "breached"
            evidence = _evidence(
                status="available",
                refs=verdict["refs"],
                summary=verdict["observed"] or spec["condition"],
            )
            alert = _alert_from_catalog(
                spec, now=now, evidence=evidence, observed=verdict["observed"]
            )
            alerts.append(alert)
        else:
            status = "within_slo"
            evidence = _evidence(
                status="available",
                refs=verdict["refs"],
                summary=verdict["observed"] or "Condition not met on this run.",
            )
            alert = None

        slos.append(
            {
                "slo_id": spec["slo_id"],
                "name": spec["name"],
                "signal": spec["signal"],
                "condition": spec["condition"],
                "severity": spec["severity"],
                "owner": spec["owner"],
                "owner_role": spec["owner_role"],
                "required_action": spec["required_action"],
                "deadline": spec["deadline"],
                "evidence": evidence,
                "status": status,
                "alert": alert,
                "detection_layer": "technical",
                "business_decision": "not_inferred",
                "not_a_legal_finding": True,
                "not_a_discrimination_finding": True,
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "disclaimer": {
            "technical_detection_is_not_a_business_decision": True,
            "not_a_legal_or_discrimination_finding": True,
            "resolved_requires_evidence": True,
            "text": (
                "SLOs are operational screens. An open alert is technical detection. "
                "It is not a go-live decision, Art. 43 conformity result, or a finding "
                "of discrimination. Owner stays unassigned until a named human is "
                "recorded (required before production). evidence_integrity is a local "
                "checksum, not a signature, WORM store, or external forensic evidence. "
                "This module does not change process-local rate limits or the static "
                "API key, and does not send notifications."
            ),
        },
        "catalog_ref": "src/monitoring/slo.py",
        "slos": slos,
        "alerts": alerts,
        "open_alert_count": len(alerts),
        "business_decision": {
            "status": "not_taken",
            "note": "Detection does not promote, retrain, price, or close a legal issue.",
        },
    }
    report = _attach_evidence_integrity(report)
    gaps = validate_monitoring_slo_report(report)
    if gaps:
        raise SloValidationError("; ".join(gaps))
    return report


def attach_slos_to_gate_report(gate_report: Dict[str, Any]) -> Dict[str, Any]:
    """Attach monitoring_slos to a production-gate / drift report."""
    out = dict(gate_report)
    out["monitoring_slos"] = build_monitoring_slo_report(
        data_drift=out.get("data_drift"),
        model_drift=out.get("model_drift"),
        production_gate={
            "monitoring_passed": out.get("monitoring_passed"),
            "overall_status": out.get("overall_status"),
            "evidence_path": out.get("evidence_path"),
        },
    )
    return out


CANONICALIZATION = (
    "json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str) "
    "of the report without evidence_integrity"
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _hash_evidence_ref(ref: str) -> Dict[str, Any]:
    """Hash a ref. File bytes if the path exists; otherwise the ref string (never invent a file SHA)."""
    raw = str(ref).strip()
    path = Path(raw.split("#", 1)[0])
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "ref": raw,
            "hash": f"sha256:{digest}",
            "hash_scope": "file_bytes",
            "file_present": True,
        }
    digest = _sha256_hex(raw.encode("utf-8"))
    return {
        "ref": raw,
        "hash": f"sha256:{digest}",
        "hash_scope": "ref_string",
        "file_present": False,
        "note": "Pointer or missing file — hash is of the ref string, not file bytes.",
    }


def _collect_evidence_refs(report: Mapping[str, Any]) -> List[str]:
    refs: List[str] = []
    seen = set()
    for slo in report.get("slos") or []:
        if not isinstance(slo, dict):
            continue
        for ref in (slo.get("evidence") or {}).get("refs") or []:
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(str(ref))
        alert = slo.get("alert")
        if isinstance(alert, dict):
            for ref in (alert.get("evidence") or {}).get("refs") or []:
                if ref and ref not in seen:
                    seen.add(ref)
                    refs.append(str(ref))
            for ref in (alert.get("resolution_evidence") or {}).get("refs") or []:
                if ref and ref not in seen:
                    seen.add(ref)
                    refs.append(str(ref))
    return refs


def artifact_hash_for(report: Mapping[str, Any]) -> str:
    """SHA-256 of the report body. Excludes evidence_integrity to avoid a circular hash."""
    body = {key: value for key, value in report.items() if key != "evidence_integrity"}
    return f"sha256:{_sha256_hex(_canonical_bytes(body))}"


def _attach_evidence_integrity(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Checksum + per-ref hashes.

    Not a cryptographic signature, not WORM, and not external forensic evidence
    a third party can rely on.
    """
    out = dict(report)
    generated_at = str(out.get("generated_at") or _utc_now().isoformat())
    out.pop("evidence_integrity", None)
    hashed_refs = [_hash_evidence_ref(ref) for ref in _collect_evidence_refs(out)]
    integrity = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "artifact_hash": artifact_hash_for(out),
        "hash_alg": "sha256",
        "canonicalization": CANONICALIZATION,
        "evidence_refs": hashed_refs,
        "not_a_cryptographic_signature": True,
        "not_worm": True,
    }
    out["evidence_integrity"] = integrity
    return out


def _iter_alerts(report: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    for item in report.get("alerts") or []:
        if isinstance(item, dict):
            yield item
    for slo in report.get("slos") or []:
        alert = slo.get("alert") if isinstance(slo, dict) else None
        if isinstance(alert, dict):
            yield alert


def validate_monitoring_slo_report(report: Mapping[str, Any]) -> List[str]:
    """Return human-readable gaps. Empty list means structurally valid."""
    gaps: List[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        gaps.append("schema_version")
    integrity = report.get("evidence_integrity")
    if not isinstance(integrity, dict):
        gaps.append("evidence_integrity.missing")
    else:
        if integrity.get("schema_version") != SCHEMA_VERSION:
            gaps.append("evidence_integrity.schema_version")
        if not integrity.get("generated_at"):
            gaps.append("evidence_integrity.generated_at")
        elif integrity.get("generated_at") != report.get("generated_at"):
            gaps.append("evidence_integrity.generated_at_mismatch")
        if integrity.get("artifact_hash") != artifact_hash_for(report):
            gaps.append("evidence_integrity.artifact_hash")
        if integrity.get("not_a_cryptographic_signature") is not True:
            gaps.append("evidence_integrity.not_a_cryptographic_signature")
        refs = integrity.get("evidence_refs")
        if not isinstance(refs, list):
            gaps.append("evidence_integrity.evidence_refs")
        else:
            for item in refs:
                if not isinstance(item, dict) or not item.get("ref") or not item.get("hash"):
                    gaps.append("evidence_integrity.evidence_refs.entry")
                    break
                if not str(item.get("hash", "")).startswith("sha256:"):
                    gaps.append("evidence_integrity.evidence_refs.hash")
                    break
    slos = report.get("slos")
    if not isinstance(slos, list) or len(slos) != len(SLO_IDS):
        gaps.append("slos.must_include_six_catalog_entries")
        return gaps
    seen = [item.get("slo_id") for item in slos if isinstance(item, dict)]
    if seen != list(SLO_IDS):
        gaps.append("slos.ids_must_match_catalog_order")
    for item in slos:
        if not isinstance(item, dict):
            gaps.append("slo.not_object")
            continue
        if item.get("status") not in SLO_STATUSES:
            gaps.append(f"{item.get('slo_id')}.status")
        if item.get("severity") not in SEVERITIES:
            gaps.append(f"{item.get('slo_id')}.severity")
        if item.get("business_decision") != "not_inferred":
            gaps.append(f"{item.get('slo_id')}.business_decision")
        if item.get("not_a_legal_finding") is not True:
            gaps.append(f"{item.get('slo_id')}.not_a_legal_finding")
        if item.get("not_a_discrimination_finding") is not True:
            gaps.append(f"{item.get('slo_id')}.not_a_discrimination_finding")
        blob = " ".join(
            str(item.get(key) or "")
            for key in ("condition", "required_action", "name")
        ).lower()
        for term in FORBIDDEN_CONCLUSION_TERMS:
            if term in blob and term != "art. 43":
                gaps.append(f"{item.get('slo_id')}.forbidden_term:{term}")
        if item.get("status") == "breached" and not item.get("alert"):
            gaps.append(f"{item.get('slo_id')}.breached_without_alert")
        if item.get("status") != "breached" and item.get("alert"):
            gaps.append(f"{item.get('slo_id')}.alert_without_breach")
        if item.get("status") == "not_evaluated":
            evidence = item.get("evidence") or {}
            if evidence.get("status") != "missing":
                gaps.append(f"{item.get('slo_id')}.not_evaluated_must_have_missing_evidence")

    for alert in _iter_alerts(report):
        gaps.extend(_validate_alert(alert))
    expected_open = sum(
        1
        for item in slos
        if isinstance(item, dict) and item.get("status") == "breached"
    )
    if report.get("open_alert_count") != expected_open and not any(
        alert.get("status") == "resolved" for alert in _iter_alerts(report)
    ):
        if report.get("open_alert_count") != len(
            [
                a
                for a in _iter_alerts(report)
                if a.get("status") in {"open", "acknowledged", "in_progress"}
            ]
        ):
            gaps.append("open_alert_count")
    return gaps


def _validate_alert(alert: Mapping[str, Any]) -> List[str]:
    gaps: List[str] = []
    slo_id = alert.get("slo_id") or "alert"
    required = (
        "condition",
        "severity",
        "owner",
        "required_action",
        "deadline",
        "evidence",
        "status",
    )
    for key in required:
        if key not in alert:
            gaps.append(f"{slo_id}.alert.missing:{key}")
    if alert.get("status") not in ALERT_STATUSES:
        gaps.append(f"{slo_id}.alert.status")
    if alert.get("severity") not in SEVERITIES:
        gaps.append(f"{slo_id}.alert.severity")
    if alert.get("business_decision") != "not_taken":
        gaps.append(f"{slo_id}.alert.business_decision")
    if alert.get("not_a_legal_finding") is not True:
        gaps.append(f"{slo_id}.alert.not_a_legal_finding")
    if alert.get("not_a_discrimination_finding") is not True:
        gaps.append(f"{slo_id}.alert.not_a_discrimination_finding")
    evidence = alert.get("evidence") or {}
    if alert.get("status") == "resolved":
        resolution = alert.get("resolution_evidence") or {}
        refs = list(resolution.get("refs") or [])
        if not refs:
            gaps.append(f"{slo_id}.alert.resolved_without_evidence")
        if evidence.get("sufficient_to_resolve") is True and not refs:
            gaps.append(f"{slo_id}.alert.detection_evidence_is_not_resolution")
    blob = f"{alert.get('condition', '')} {alert.get('required_action', '')}".lower()
    if "discriminat" in blob:
        gaps.append(f"{slo_id}.alert.must_not_state_discrimination")
    return gaps


def resolve_alert(
    report: Mapping[str, Any],
    slo_id: str,
    *,
    evidence_refs: Sequence[str],
    note: str,
    resolved_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Close one alert only with non-empty evidence refs. business_decision stays not_taken."""
    refs = [str(item).strip() for item in evidence_refs if str(item).strip()]
    if not refs:
        raise SloValidationError("Cannot resolve an alert without evidence refs.")
    out = deepcopy(dict(report))
    found = False
    for slo in out.get("slos") or []:
        if slo.get("slo_id") != slo_id:
            continue
        alert = slo.get("alert")
        if not isinstance(alert, dict):
            raise SloValidationError(f"No open alert for {slo_id}")
        found = True
        stamp = _utc_now(resolved_at).isoformat()
        alert["status"] = "resolved"
        alert["resolution_evidence"] = {
            "refs": refs,
            "note": note,
            "resolved_at": stamp,
            "business_decision_still_not_taken": True,
        }
        alert["business_decision"] = "not_taken"
        slo["alert"] = alert
        break
    if not found:
        raise SloValidationError(f"Unknown slo_id: {slo_id}")
    out["alerts"] = [
        dict(slo["alert"])
        for slo in out.get("slos") or []
        if isinstance(slo.get("alert"), dict)
    ]
    out["open_alert_count"] = sum(
        1
        for alert in out["alerts"]
        if alert.get("status") in {"open", "acknowledged", "in_progress"}
    )
    out = _attach_evidence_integrity(out)
    gaps = validate_monitoring_slo_report(out)
    if gaps:
        raise SloValidationError("; ".join(gaps))
    return out
