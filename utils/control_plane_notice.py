CONTROL_PLANE_BANNER = (
    "Control plane scope: `execute_guarded` in **this process** only. "
    "`POST /predict` is wrapped by that adapter here. Stop, circuit breaker and "
    "approvals are **in-memory / per-process** — they do not replicate across "
    "Streamlit or FastAPI workers (use `uvicorn --workers 1`; optional `STOP_FILE` "
    "shares emergency stop via filesystem). In-memory rate limit is demo-only. "
    "Approval JSON is rewritable (not WORM); AuditLog appends are local append-only "
    "only. Role / reviewer strings are not SSO. Residual scores in the static EIPD "
    "pack are **estimated pending verification**."
)
