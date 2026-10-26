"""
FastAPI REST API Server for Insurance Claim Prediction
Part of Insurance Claim Prediction - Responsible AI Architecture

Deployment limits / not multi-worker safe (see README + LINE_REPORT):
- In-memory rate limiter is **demo-only** (per process). Use gateway limits
  (nginx/Cloudflare) for multi-replica. ``RATE_LIMIT_BACKEND=memory|disabled``.
- ``TRUST_PROXY`` honors X-Forwarded-For only when the TCP peer is in
  ``TRUSTED_PROXY_IPS`` / ``TRUSTED_PROXY_CIDRS`` (fail closed otherwise).
- Approvals use free-text reviewer/requester strings (not SSO). Set
  ``REQUIRE_AUTH=true`` + ``API_KEY`` for static key gate on predict/approvals.
- Control-plane stop/circuit/approvals are process-local; prefer
  ``uvicorn --workers 1``. Optional ``STOP_FILE`` shares emergency stop via FS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import joblib
import polars as pl
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.control_plane.approvals import AUTHN_NOTE, ApprovalError
from src.control_plane.binding import canonical_json
from src.control_plane.runtime import RuntimeBlocked, RuntimeStopped, get_runtime
from src.models.interpret_bridge import predict_proba_ebm
from utils.client_ip import parse_trusted_proxy_networks, resolve_client_ip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_BACKEND = (os.getenv("RATE_LIMIT_BACKEND", "memory") or "memory").strip().lower()
MAX_FEATURES_PER_REQUEST = int(os.getenv("MAX_FEATURES_PER_REQUEST", "200"))
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "logs/prediction_audit.jsonl"))
AUDIT_CHECKPOINT_PATH = Path(
    os.getenv("AUDIT_CHECKPOINT_PATH", str(AUDIT_LOG_PATH) + ".checkpoint.json")
)
_AUDIT_GENESIS = "0" * 64
UNCERTAINTY_MARGIN = float(os.getenv("UNCERTAINTY_MARGIN", "0.05"))
REQUIRE_ARTIFACT_HASH = os.getenv("REQUIRE_ARTIFACT_HASH", "false").lower() in ("1", "true", "yes")
MAX_BATCH_RECORDS = int(os.getenv("MAX_BATCH_RECORDS", "1000"))
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")
_TRUSTED_PROXY_NETWORKS = parse_trusted_proxy_networks(
    os.getenv("TRUSTED_PROXY_IPS", ""),
    os.getenv("TRUSTED_PROXY_CIDRS", ""),
)
CONTROL_PLANE_STRICT = os.getenv("CONTROL_PLANE_STRICT", "").lower() in ("1", "true", "yes")

app = FastAPI(
    title="Insurance Claim Prediction API",
    description="REST API for insurance claim prediction using EBM model",
    version="1.0.0",
)

cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:8501")
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Approval-Ticket"],
)

model = None
feature_engineer = None
optimal_threshold = 0.5
rate_limit_bucket: Dict[str, List[float]] = {}
_audit_lock = threading.Lock()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_hash_for_artifact(path: Path, env_var_name: str) -> Optional[str]:
    env_hash = os.getenv(env_var_name)
    if env_hash:
        return env_hash.strip().lower()
    sidecar = path.with_name(path.name + ".sha256")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    return None


def _verify_file_hash(path: Path, env_var_name: str) -> None:
    """
    Deterministic SHA-256 verification before joblib load (pickle exploit mitigation).
    Expected hash: env var MODEL_SHA256 / FEATURE_ENGINEER_SHA256 or sidecar `.pkl.sha256`.
    """
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")

    expected = _expected_hash_for_artifact(path, env_var_name)
    if not expected:
        if REQUIRE_ARTIFACT_HASH:
            raise RuntimeError(
                f"No SHA-256 configured for {path.name}. Set {env_var_name} or create {path.name}.sha256"
            )
        logger.warning(
            "No SHA-256 for %s — set %s or %s.sha256 (REQUIRE_ARTIFACT_HASH=true to enforce)",
            path.name,
            env_var_name,
            path.name,
        )
        return

    actual = _sha256_file(path)
    if actual.lower() != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {path.name}. Refusing to load artifact (possible tampering)."
        )
    logger.info("SHA-256 verified for %s", path.name)


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    return resolve_client_ip(
        peer,
        request.headers.get("X-Forwarded-For"),
        trust_proxy=TRUST_PROXY,
        trusted_networks=_TRUSTED_PROXY_NETWORKS,
    )


def _enforce_api_key(x_api_key: Optional[str]) -> None:
    """Static API key gate. REQUIRE_AUTH=true demands API_KEY be configured."""
    if REQUIRE_AUTH and not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Server misconfigured: REQUIRE_AUTH=true but API_KEY is not set.",
        )
    if not API_KEY:
        return
    provided = x_api_key or ""
    try:
        ok = secrets.compare_digest(provided, API_KEY)
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _enforce_rate_limit(request: Request) -> None:
    """
    In-memory per-process limiter (demo-only). Not effective across replicas/workers.
    Set RATE_LIMIT_BACKEND=disabled and enforce limits at the gateway in multi-replica.
    No Redis backend ships here (avoid heavy deps); use nginx/Cloudflare rate limits.
    """
    if RATE_LIMIT_BACKEND == "disabled":
        return
    if RATE_LIMIT_BACKEND not in ("memory", "disabled"):
        logger.warning(
            "Unknown RATE_LIMIT_BACKEND=%s — treating as memory (process-local).",
            RATE_LIMIT_BACKEND,
        )

    now = time.time()
    window_start = now - 60
    stale = [ip for ip, stamps in rate_limit_bucket.items() if not any(ts > window_start for ts in stamps)]
    for ip in stale[:500]:
        rate_limit_bucket.pop(ip, None)
    if len(rate_limit_bucket) > 10000:
        oldest = sorted(rate_limit_bucket, key=lambda k: min(rate_limit_bucket[k] or [now]))[:1000]
        for ip in oldest:
            rate_limit_bucket.pop(ip, None)

    client_ip = _client_ip(request)
    history = [ts for ts in rate_limit_bucket.get(client_ip, []) if ts > window_start]
    if len(history) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    history.append(now)
    rate_limit_bucket[client_ip] = history


def _enforce_security(request: Request, x_api_key: Optional[str]) -> None:
    _enforce_api_key(x_api_key)
    _enforce_rate_limit(request)


def _expected_features() -> List[str]:
    expected: List[str] = []
    if hasattr(feature_engineer, "num_features"):
        expected.extend(getattr(feature_engineer, "num_features", []))
    if hasattr(feature_engineer, "cat_features"):
        expected.extend(getattr(feature_engineer, "cat_features", []))
    return list(dict.fromkeys(expected))


def _normalize_features(raw_features: Dict[str, Any]) -> Dict[str, Optional[float]]:
    if not raw_features:
        raise HTTPException(status_code=422, detail="No features provided in request payload.")
    if len(raw_features) > MAX_FEATURES_PER_REQUEST:
        raise HTTPException(status_code=413, detail="Payload has too many features.")

    expected = _expected_features()
    if not expected:
        raise HTTPException(status_code=500, detail="Feature schema unavailable from feature engineer.")

    normalized: Dict[str, Optional[float]] = {}
    for key, value in raw_features.items():
        if key not in expected:
            raise HTTPException(status_code=422, detail=f"Unexpected feature: {key}")
        if value is None:
            normalized[key] = None
            continue
        try:
            val = float(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Feature '{key}' must be numeric.") from exc
        if not math.isfinite(val):
            raise HTTPException(status_code=422, detail=f"Feature '{key}' must be finite.")
        normalized[key] = val

    for feat in expected:
        normalized.setdefault(feat, None)
    return normalized


def _prediction_audit_tail_hash() -> str:
    if not AUDIT_LOG_PATH.exists():
        return _AUDIT_GENESIS
    last = _AUDIT_GENESIS
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            last = row.get("event_hash") or last
    return last


def _write_audit_log_sync(event: Dict[str, Any]) -> None:
    """
    Append-only JSONL with a lightweight hash chain + checkpoint sidecar.

    Not WORM: local files remain rewriteable. Prefer Object Lock / external store in production.
    """
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _audit_lock:
            previous = _prediction_audit_tail_hash()
            body = {
                k: v
                for k, v in event.items()
                if k not in {"event_hash", "previous_event_hash"}
            }
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
            digest = hashlib.sha256((canonical + previous).encode("utf-8")).hexdigest()
            record = {
                **body,
                "previous_event_hash": previous,
                "event_hash": digest,
            }
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            # Local integrity snapshot (detection aid only — worm_claimed is always false).
            event_count = sum(1 for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
            checkpoint = {
                "audit_path": str(AUDIT_LOG_PATH).replace("\\", "/"),
                "event_count": event_count,
                "tail_event_hash": digest,
                "content_sha256": hashlib.sha256(AUDIT_LOG_PATH.read_bytes()).hexdigest(),
                "signed_at": datetime.now().isoformat(),
                "worm_claimed": False,
                "integrity_note": (
                    "Local checkpoint only. True immutability needs an external append-only store."
                ),
            }
            AUDIT_CHECKPOINT_PATH.write_text(
                json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Could not write audit log: %s", exc)


def _schedule_audit(background_tasks: BackgroundTasks, event: Dict[str, Any]) -> None:
    background_tasks.add_task(_write_audit_log_sync, event)


def _require_api_key(x_api_key: Optional[str]) -> None:
    _enforce_security_key_only(x_api_key)


def _enforce_security_key_only(x_api_key: Optional[str]) -> None:
    _enforce_api_key(x_api_key)


def _features_binding(normalized: Dict[str, Any]) -> Dict[str, Any]:
    digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return {"normalized_features_sha256": digest, "feature_count": len(normalized)}


def _features_for_inference(df_transformed: pl.DataFrame) -> pl.DataFrame:
    drop = [c for c in ("target", "id") if c in df_transformed.columns]
    return df_transformed.drop(drop)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    request.state.client_request_id = request.headers.get("X-Request-ID")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if request.state.client_request_id:
        response.headers["X-Client-Request-ID"] = request.state.client_request_id
    return response


def _log_deployment_limits() -> None:
    """Honest startup warnings: process-local rate limit + control plane."""
    if RATE_LIMIT_BACKEND == "disabled":
        logger.info("RATE_LIMIT_BACKEND=disabled — rely on gateway rate limits.")
    else:
        logger.warning(
            "In-memory rate limiter is process-local (demo-only). "
            "Ineffective behind multiple replicas/workers; use nginx/Cloudflare "
            "or set RATE_LIMIT_BACKEND=disabled. No Redis backend in this build."
        )
    if TRUST_PROXY and not _TRUSTED_PROXY_NETWORKS:
        logger.warning(
            "TRUST_PROXY=true without TRUSTED_PROXY_IPS/CIDRS — X-Forwarded-For ignored."
        )
    if REQUIRE_AUTH and not API_KEY:
        logger.error("REQUIRE_AUTH=true but API_KEY unset — protected routes will return 503.")
    logger.warning(
        "control plane state is process-local; use uvicorn --workers 1 "
        "(STOP_FILE optional for shared emergency stop). CONTROL_PLANE_STRICT=%s",
        CONTROL_PLANE_STRICT,
    )


@app.on_event("startup")
def load_model() -> None:
    global model, feature_engineer, optimal_threshold

    _log_deployment_limits()
    # Touch get_runtime early so CONTROL_PLANE_STRICT / worker env is evaluated at boot.
    try:
        get_runtime()
    except RuntimeError as exc:
        logger.error("Control plane init refused: %s", exc)
        raise

    try:
        artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", "models/artifacts"))
        model_path = artifacts_dir / "ebm_model_v1.pkl"
        fe_path = artifacts_dir / "feature_engineer_v1.pkl"
        threshold_path = artifacts_dir / "optimal_threshold.txt"

        if not model_path.exists():
            model_path = Path("models/ebm_model.pkl")
        if not fe_path.exists():
            fe_path = Path("models/feature_engineer.pkl")
        if not threshold_path.exists():
            threshold_path = Path("models/optimal_threshold.txt")

        _verify_file_hash(model_path, "MODEL_SHA256")
        _verify_file_hash(fe_path, "FEATURE_ENGINEER_SHA256")

        logger.info("Loading model from: %s", model_path)
        model = joblib.load(model_path)

        logger.info("Loading feature engineer from: %s", fe_path)
        feature_engineer = joblib.load(fe_path)

        if threshold_path.exists():
            optimal_threshold = float(threshold_path.read_text(encoding="utf-8").strip())
            logger.info("Loaded optimal threshold: %s", optimal_threshold)

        logger.info("Model and feature engineer loaded successfully")
    except Exception as exc:
        logger.error("Error loading model: %s", exc)
        model = None
        feature_engineer = None


class PredictionRequest(BaseModel):
    features: Dict[str, Optional[float]]

    class Config:
        extra = "forbid"


class BatchPredictionRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ApprovalRequestBody(BaseModel):
    action: str = "predict_ebm"
    reason: str
    requester: str = "api-client"
    payload: Dict[str, Any] = Field(default_factory=dict)
    tool: str = "predict_ebm"
    ttl_seconds: int = 3600


class ApprovalDecisionBody(BaseModel):
    reviewer: str
    approve: bool
    rationale: str


class PredictionResponse(BaseModel):
    prediction: float
    risk_score: float
    claim_probability: float
    binary_prediction: int
    threshold_used: float
    review_required: bool
    uncertainty_flag: bool
    request_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    timestamp: str


@app.get("/", tags=["General"])
def root() -> Dict[str, Any]:
    return {
        "message": "Insurance Claim Prediction API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "predict": "/predict",
            "batch_predict": "/batch_predict",
            "compliance_monitor": "/compliance/monitor",
            "docs": "/docs",
        },
    }


@app.post("/approvals/request", tags=["Approvals"])
def request_approval(
    body: ApprovalRequestBody,
    http_request: Request,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _enforce_security(http_request, x_api_key)
    ticket = get_runtime().approvals.request(
        action=body.action,
        requester=body.requester,
        reason=body.reason,
        payload=body.payload,
        tool=body.tool,
        ttl_seconds=body.ttl_seconds,
        execution_id="",
    )
    ticket["authn_note"] = AUTHN_NOTE
    ticket["reviewer_auth_note"] = AUTHN_NOTE
    return ticket


@app.post("/approvals/{ticket_id}/decide", tags=["Approvals"])
def decide_approval(
    ticket_id: str,
    body: ApprovalDecisionBody,
    http_request: Request,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _enforce_security(http_request, x_api_key)
    try:
        ticket = get_runtime().approvals.decide(
            ticket_id,
            reviewer=body.reviewer,
            approve=body.approve,
            rationale=body.rationale,
        )
        ticket["authn_note"] = AUTHN_NOTE
        ticket["reviewer_auth_note"] = AUTHN_NOTE
        return ticket
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health", response_model=HealthResponse, tags=["General"])
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model_loaded": model is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/predict", response_model=PredictionResponse, tags=["Prediction"])
def predict(
    request: PredictionRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if model is None or feature_engineer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    request_id = getattr(http_request.state, "request_id", "unknown")
    try:
        _enforce_security(http_request, x_api_key)
        input_data = _normalize_features(request.features)
        legal_effect = bool(get_runtime().flow_legal_effect)

        def _infer(ctx: Dict[str, Any]) -> Dict[str, Any]:
            rows = ctx.get("records") or [input_data]
            df = pl.DataFrame(rows[:1])
            df_transformed = feature_engineer.transform(df)
            X_pl = _features_for_inference(df_transformed)
            prediction_proba = float(predict_proba_ebm(model, X_pl)[0])
            binary_pred = 1 if prediction_proba >= optimal_threshold else 0
            uncertainty_flag = abs(prediction_proba - optimal_threshold) <= UNCERTAINTY_MARGIN
            ts = datetime.utcnow().isoformat()
            return {
                "prediction": prediction_proba,
                "risk_score": prediction_proba,
                "claim_probability": prediction_proba * 100,
                "binary_prediction": int(binary_pred),
                "threshold_used": float(optimal_threshold),
                "review_required": bool(uncertainty_flag) or legal_effect,
                "uncertainty_flag": uncertainty_flag,
                "request_id": request_id,
                "timestamp": ts,
            }

        guarded = get_runtime().execute_guarded(
            "predict_ebm",
            _infer,
            {
                "tool": "predict_ebm",
                "action": "predict_ebm",
                "record_count": 1,
                "records": [input_data],
                "execution_id": "",
                "legal_effect_decision": legal_effect,
                "approval_ticket_id": http_request.headers.get("X-Approval-Ticket"),
                "approval_payload": _features_binding(input_data),
                "estimated_cost_eur": 0.0,
            },
        )
        result = guarded["result"]
        _schedule_audit(
            background_tasks,
            {
                "event_type": "single_prediction",
                "request_id": request_id,
                "timestamp": result["timestamp"],
                "threshold_used": float(optimal_threshold),
                "prediction": result["prediction"],
                "binary_prediction": result["binary_prediction"],
                "review_required": result["review_required"],
                "uncertainty_flag": result["uncertainty_flag"],
                "feature_count": len(request.features),
                "policy_id": guarded["decision"].get("policy_id"),
            },
        )
        return result
    except HTTPException:
        raise
    except RuntimeStopped:
        raise HTTPException(status_code=503, detail="Inference stopped by control plane.") from None
    except RuntimeBlocked:
        raise HTTPException(status_code=403, detail="Request blocked by control plane.") from None
    except Exception:
        logger.exception("Prediction error request_id=%s", request_id)
        raise HTTPException(status_code=500, detail="Prediction failed.") from None


@app.post("/batch_predict", tags=["Prediction"])
def batch_predict(
    request: BatchPredictionRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if model is None or feature_engineer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        _enforce_security(http_request, x_api_key)
        if not request.records:
            raise HTTPException(status_code=422, detail="Batch payload must include at least one record.")
        if len(request.records) > MAX_BATCH_RECORDS:
            raise HTTPException(
                status_code=413,
                detail=f"Batch exceeds hard limit of {MAX_BATCH_RECORDS} records.",
            )

        normalized_records = []
        for idx, record in enumerate(request.records):
            try:
                normalized_records.append(_normalize_features(record))
            except HTTPException as exc:
                raise HTTPException(status_code=422, detail=f"Record at index {idx}: {exc.detail}") from exc

        request_id = getattr(http_request.state, "request_id", "unknown")

        def _infer_batch(ctx: Dict[str, Any]) -> Dict[str, Any]:
            rows = ctx.get("records") or []
            df = pl.DataFrame(rows)
            df_transformed = feature_engineer.transform(df)
            X_pl = _features_for_inference(df_transformed)
            predictions_proba = predict_proba_ebm(model, X_pl)
            binary_predictions = (predictions_proba >= optimal_threshold).astype(int)
            results = []
            for i, (prob, binary) in enumerate(zip(predictions_proba, binary_predictions)):
                uncertainty_flag = abs(float(prob) - optimal_threshold) <= UNCERTAINTY_MARGIN
                results.append(
                    {
                        "record_id": i,
                        "prediction": float(prob),
                        "risk_score": float(prob),
                        "claim_probability": float(prob * 100),
                        "binary_prediction": int(binary),
                        "threshold_used": float(optimal_threshold),
                        "review_required": bool(uncertainty_flag),
                        "uncertainty_flag": bool(uncertainty_flag),
                    }
                )
            ts = datetime.utcnow().isoformat()
            return {
                "predictions": results,
                "count": len(results),
                "request_id": request_id,
                "timestamp": ts,
                "limit_applied": ctx.get("limit_applied"),
            }

        guarded = get_runtime().execute_guarded(
            "predict_ebm",
            _infer_batch,
            {
                "tool": "predict_ebm",
                "action": "predict_ebm",
                "record_count": len(normalized_records),
                "records": normalized_records,
                "execution_id": request_id,
                "legal_effect_decision": bool(get_runtime().flow_legal_effect),
                "approval_ticket_id": http_request.headers.get("X-Approval-Ticket"),
                "estimated_cost_eur": 0.0,
            },
        )
        payload = guarded["result"]
        _schedule_audit(
            background_tasks,
            {
                "event_type": "batch_prediction",
                "request_id": request_id,
                "timestamp": payload["timestamp"],
                "threshold_used": float(optimal_threshold),
                "record_count": payload["count"],
                "review_required_count": sum(1 for r in payload["predictions"] if r["review_required"]),
                "policy_id": guarded["decision"].get("policy_id"),
            },
        )
        return payload
    except HTTPException:
        raise
    except RuntimeStopped:
        raise HTTPException(status_code=503, detail="Inference stopped by control plane.") from None
    except RuntimeBlocked:
        raise HTTPException(status_code=403, detail="Request blocked by control plane.") from None
    except Exception:
        logger.exception("Batch prediction error")
        raise HTTPException(status_code=500, detail="Batch prediction failed.") from None


@app.get("/model_info", tags=["Model"])
def get_model_info() -> Dict[str, Any]:
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    try:
        return {
            "model_type": type(model).__name__,
            "framework": "Microsoft InterpretML (EBM)",
            "threshold": optimal_threshold,
            "features": len(feature_engineer.feature_names_)
            if hasattr(feature_engineer, "feature_names_")
            else "Unknown",
        }
    except Exception as exc:
        logger.error("Error getting model info: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/compliance/monitor", tags=["Compliance"])
def run_compliance_monitor(
    http_request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(default=None),
    simulate_drift: bool = False,
) -> Dict[str, Any]:
    """
    Run production compliance gate (data + model drift) and persist EU AI Act evidence.
    Invoke on a schedule or after batch inference windows.
    """
    _enforce_security(http_request, x_api_key)

    def _execute_monitor() -> None:
        try:
            from src.monitoring.production_compliance_gate import run_scheduled_production_monitor

            run_scheduled_production_monitor(simulate_drift=simulate_drift)
        except Exception as exc:
            logger.error("Compliance monitor failed: %s", exc)

    background_tasks.add_task(_execute_monitor)
    return {
        "status": "scheduled",
        "message": "Production compliance gate queued (drift + performance history).",
        "simulate_drift": simulate_drift,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/audit/summary", tags=["Audit"])
def get_audit_summary(
    x_api_key: Optional[str] = Header(default=None),
    last_n: int = 100,
) -> Dict[str, Any]:
    _require_api_key(x_api_key)
    if last_n <= 0 or last_n > 1000:
        raise HTTPException(status_code=422, detail="last_n must be between 1 and 1000.")

    if not AUDIT_LOG_PATH.exists():
        return {"log_path": str(AUDIT_LOG_PATH), "exists": False, "total_events": 0, "events": []}

    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        selected = lines[-last_n:]
        events = [json.loads(line) for line in selected if line.strip()]
        single_count = sum(1 for e in events if e.get("event_type") == "single_prediction")
        batch_count = sum(1 for e in events if e.get("event_type") == "batch_prediction")
        review_required_count = sum(
            int(e.get("review_required_count", 0)) if e.get("event_type") == "batch_prediction" else int(e.get("review_required", 0))
            for e in events
        )
        return {
            "log_path": str(AUDIT_LOG_PATH),
            "exists": True,
            "total_events": len(lines),
            "returned_events": len(events),
            "single_prediction_events": single_count,
            "batch_prediction_events": batch_count,
            "review_required_count": review_required_count,
            "events": events,
        }
    except Exception as exc:
        logger.error("Failed to read audit log summary: %s", exc)
        raise HTTPException(status_code=500, detail="Could not read audit summary.") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
