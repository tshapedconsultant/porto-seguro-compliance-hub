CONTROL_PLANE_BANNER = (
    "Control plane scope: `execute_guarded` in **this process** only. "
    "`POST /predict` is wrapped by that adapter here. Stop, circuit breaker and "
    "approvals are **in-memory singletons** — they do not replicate across Streamlit "
    "or FastAPI workers. Role strings are not authentication. Residual scores in the "
    "static EIPD pack are **estimated pending verification**."
)
