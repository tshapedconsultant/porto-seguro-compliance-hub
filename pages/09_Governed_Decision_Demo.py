"""
Governed Decision Demo — Streamlit control room (AEPD lab / recording).

Language: ``?lang=es`` (default) or ``?lang=en`` — UI + diagrams match voiceover.
Recording: ``record_demo.bat`` / ``docs/governance/auto_record_demo.py``.
Honest scope: in-process ReferenceRuntime + demo AuditLog. Not certification.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import streamlit as st

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.runtime import ReferenceRuntime, RuntimeBlocked

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "governance" / "demo_assets"
DEMO_AUDIT = ROOT / "docs" / "governance" / "_demo_streamlit_audit.jsonl"
DEMO_APPROVALS = ROOT / "docs" / "governance" / "_demo_streamlit_approvals.json"
TAMPER_AUDIT = ROOT / "docs" / "governance" / "_demo_streamlit_tamper.jsonl"
# Orchestrator writes step names here — no browser URL bar / Ctrl+L (breaks F11 takes)
STEP_FILE = ROOT / "docs" / "governance" / "_demo_record_tmp" / "current_step.txt"

UI = {
    "es": {
        "page_title": "Demo decisión gobernada",
        "steps": [
            ("0:00–0:20", "Arquitectura", "architecture"),
            ("0:20–0:45", "Decisión de política (DENY)", "policy"),
            ("0:45–1:15", "Ciclo de aprobación", "approval"),
            ("1:15–1:35", "Anti-replay", "antireplay"),
            ("1:35–1:55", "Salida + redacción", "redact"),
            ("1:55–2:15", "Pista de auditoría", "audit"),
            ("2:15–2:25", "Manipulación (detección local)", "tamper"),
            ("2:25–2:30", "Cierre + esquemas", "close"),
        ],
        "sidebar_title": "### Demo · guion 0:00–2:30",
        "sidebar_radio": "Paso (sincronizado con la narración)",
        "auto_ok": "AUTO DEMO · acciones sin clic",
        "sidebar_term": "Terminal de evidencia: `python docs/governance/demo_90s.py`",
        "sidebar_rec": "Grabación: `record_demo.bat` (Game Bar automático)",
        "reset_btn": "Reiniciar runtime de demo",
        "reset_ok": "Runtime reiniciado",
        "hero_h1": "Sala de control — decisión de IA gobernada",
        "hero_p": (
            "Streamlit opera el flujo · el terminal prueba que el control es real · "
            "evidencia técnica reproducible (no certificación AEPD / RGPD / AI Act)."
        ),
        "banner": (
            "Alcance del plano de control: `execute_guarded` solo en **este proceso**. "
            "`POST /predict` pasa por ese adaptador aquí. Parada, circuit breaker y "
            "aprobaciones son **en memoria / por proceso** — no se replican entre workers "
            "de Streamlit o FastAPI (`uvicorn --workers 1`; `STOP_FILE` opcional para "
            "parada de emergencia por fichero). El rate limit en memoria es solo demo. "
            "El JSON de aprobaciones es reescribible (no WORM); AuditLog es append-only "
            "local. Roles / revisores no son SSO. Residuos en el pack EIPD estático son "
            "**estimaciones pendientes de verificación**."
        ),
        "m_events": "Eventos de auditoría",
        "m_chain": "Cadena",
        "m_chain_ok": "OK",
        "m_chain_break": "ROTA",
        "m_verify": "verify_chain",
        "m_ticket": "Último ticket",
        "arch_h": "1 · Arquitectura (5 capas)",
        "arch_cap": "Interfaz → API → Plano de control → Modelo → Auditoría",
        "layer_html": (
            '<div class="layer-row">'
            '<div class="layer-card"><strong>Interfaz</strong><span>Operadores</span></div>'
            '<div class="layer-card"><strong>API</strong><span>FastAPI</span></div>'
            '<div class="layer-card hot"><strong>Plano de control</strong><span>Políticas</span></div>'
            '<div class="layer-card"><strong>Modelo</strong><span>Propuesta</span></div>'
            '<div class="layer-card"><strong>Auditoría</strong><span>Cadena hash</span></div>'
            "</div>"
        ),
        "arch_info": (
            "El modelo **no** decide solo. Toda acción gobernada atraviesa el plano de control "
            "antes de ejecutarse. La auditoría registra el camino de decisión."
        ),
        "pol_h": "2 · Decisión de política",
        "pol_cap": "Evaluar / ejecutar con guarda — DENY antes de que corra el modelo",
        "pol_ctx": "**Contexto de evaluación**",
        "pol_btn": "Evaluar / Ejecutar con guarda",
        "pol_invoked": "Función del modelo invocada: **{ran}** (debe ser False en DENY)",
        "appr_h": "3 · Ciclo de vida del ticket",
        "appr_cap": "pendiente → aprobado → consumido (uso único)",
        "appr_payload": "payload (JSON)",
        "appr_bad_json": "JSON inválido — usando payload por defecto",
        "appr_req": "1 · Solicitar ticket",
        "appr_ok": "2 · Aprobar",
        "appr_run": "3 · Ejecutar con ticket",
        "appr_no_ticket": "Sin ticket",
        "anti_h": "4 · Anti-replay",
        "anti_cap": "Un ticket consumido no puede reutilizarse para otra acción",
        "anti_need": "Crea y consume un ticket en el paso anterior primero.",
        "anti_cur": "Ticket actual: `{tid}` · estado=`{status}`",
        "anti_btn": "Reintentar execute_guarded con el mismo ticket",
        "anti_unexpected": "INESPERADO: se permitió el replay",
        "anti_ok": "El ticket consumido no puede reutilizarse.",
        "red_h": "5 · Salida del modelo + redacción",
        "red_cap": "Campos personales eliminados; fail closed si falla la redacción",
        "red_btn": "Ejecutar predict con redact_output=true",
        "red_last": "**Último resultado visible al operador**",
        "aud_h": "6 · Pista de auditoría (cadena hash)",
        "aud_cap": "política → aprobación → ejecución → redacción, hashes enlazados",
        "aud_empty": "Sin eventos aún — ejecuta DENY / aprobación / redacción en pasos anteriores.",
        "col_rule": "regla / acción",
        "col_dec": "decisión",
        "tam_h": "7 · Manipulación — detección local",
        "tam_cap": "Reescritura torpe del JSONL rompe verify_chain — no es WORM",
        "tam_before": "Antes",
        "tam_after": "Después",
        "tam_btn": "Simular reescritura torpe + verify_chain",
        "tam_note": (
            "Detección local de manipulación burda. Quien controle JSONL + checkpoint "
            "puede derrotar la comprobación. No es WORM ni certificación."
        ),
        "close_h": "8 · Cierre y esquemas",
        "close_line": "El modelo propone. Los controles deciden. La evidencia permanece observable.",
        "close_disc": "La evidencia técnica no es certificación AEPD, RGPD ni AI Act.",
        "schemas": "**Cuatro esquemas (laboratorio)**",
        "sch1_t": "Decisión gobernada",
        "sch1_p": (
            "Contexto → <code>evaluate_policies</code> → efecto "
            "(DENY / REQUIRE_HUMAN_APPROVAL / REDACT / …) → invoke opcional → auditoría."
        ),
        "sch2_t": "Ticket de aprobación",
        "sch2_p": (
            "pendiente → aprobado|rechazado|caducado → consumido. "
            "Vinculación de acción + un solo uso (anti-replay)."
        ),
        "sch3_t": "Evento de auditoría",
        "sch3_p": (
            "JSONL append-only local · <code>event_hash</code> + "
            "<code>previous_event_hash</code> · <code>verify_chain()</code>."
        ),
        "sch4_t": "Redacción",
        "sch4_p": (
            "Campos personales → <code>[REDACTED]</code>. "
            "Si falla la redacción exigida → fail closed (DENY)."
        ),
        "footer": (
            "Esta página usa su propio runtime → `docs/governance/_demo_streamlit_*.jsonl` "
            "(gitignored). Terminal: `_demo_90s_audit.jsonl`. Grabación: `record_demo.bat`."
        ),
        "chip_allow": "ALLOW / EJECUTADO",
        "chip_deny": "DENY",
        "chip_approved": "EJECUCIÓN APROBADA",
        "chip_blocked": "BLOQUEADO",
        "chip_antireplay": "ANTI-REPLAY",
        "chip_redact": "REDACT",
        "chip_fail": "FAIL CLOSED",
        "chip_chain_ok": "CADENA OK",
        "chip_chain_break": "CADENA ROTA",
        "chip_tamper": "MANIPULACIÓN DETECTADA",
        "chip_unexpected": "INESPERADO",
    },
    "en": {
        "page_title": "Governed Decision Demo",
        "steps": [
            ("0:00–0:20", "Architecture", "architecture"),
            ("0:20–0:45", "Policy decision (DENY)", "policy"),
            ("0:45–1:15", "Approval cycle", "approval"),
            ("1:15–1:35", "Anti-replay", "antireplay"),
            ("1:35–1:55", "Output + redaction", "redact"),
            ("1:55–2:15", "Audit trail", "audit"),
            ("2:15–2:25", "Tamper (local detection)", "tamper"),
            ("2:25–2:30", "Close + schemas", "close"),
        ],
        "sidebar_title": "### Demo · timeline 0:00–2:30",
        "sidebar_radio": "Step (synced to narration)",
        "auto_ok": "AUTO DEMO · clickless actions",
        "sidebar_term": "Evidence terminal: `python docs/governance/demo_90s.py`",
        "sidebar_rec": "Recording: `record_demo.bat` (auto Game Bar)",
        "reset_btn": "Reset demo runtime",
        "reset_ok": "Runtime reset",
        "hero_h1": "Control room — governed AI decision",
        "hero_p": (
            "Streamlit drives the flow · the terminal proves control is real · "
            "reproducible technical evidence (not AEPD / GDPR / AI Act certification)."
        ),
        "banner": (
            "Control plane scope: `execute_guarded` in **this process** only. "
            "`POST /predict` is wrapped by that adapter here. Stop, circuit breaker and "
            "approvals are **in-memory / per-process** — they do not replicate across "
            "Streamlit or FastAPI workers (use `uvicorn --workers 1`; optional `STOP_FILE` "
            "shares emergency stop via filesystem). In-memory rate limit is demo-only. "
            "Approval JSON is rewritable (not WORM); AuditLog appends are local append-only "
            "only. Role / reviewer strings are not SSO. Residual scores in the static EIPD "
            "pack are **estimated pending verification**."
        ),
        "m_events": "Audit events",
        "m_chain": "Chain",
        "m_chain_ok": "OK",
        "m_chain_break": "BROKEN",
        "m_verify": "verify_chain",
        "m_ticket": "Last ticket",
        "arch_h": "1 · Architecture (5 layers)",
        "arch_cap": "Interface → API → Control Plane → Model → Audit",
        "layer_html": (
            '<div class="layer-row">'
            '<div class="layer-card"><strong>Interface</strong><span>Operators</span></div>'
            '<div class="layer-card"><strong>API</strong><span>FastAPI</span></div>'
            '<div class="layer-card hot"><strong>Control Plane</strong><span>Policies</span></div>'
            '<div class="layer-card"><strong>Model</strong><span>Proposal</span></div>'
            '<div class="layer-card"><strong>Audit</strong><span>Hash chain</span></div>'
            "</div>"
        ),
        "arch_info": (
            "The model does **not** decide alone. Every governed action crosses the control "
            "plane before execution. Audit records the decision path."
        ),
        "pol_h": "2 · Policy decision",
        "pol_cap": "Evaluate / execute guarded — DENY before the model runs",
        "pol_ctx": "**Evaluation context**",
        "pol_btn": "Evaluate / Execute guarded",
        "pol_invoked": "Model function invoked: **{ran}** (must be False on DENY)",
        "appr_h": "3 · Ticket lifecycle",
        "appr_cap": "pending → approved → consumed (single-use binding)",
        "appr_payload": "payload (JSON)",
        "appr_bad_json": "Invalid JSON — using default payload",
        "appr_req": "1 · Request ticket",
        "appr_ok": "2 · Approve",
        "appr_run": "3 · Execute with ticket",
        "appr_no_ticket": "No ticket",
        "anti_h": "4 · Anti-replay",
        "anti_cap": "A consumed ticket cannot be reused for another action",
        "anti_need": "Create and consume a ticket in the previous step first.",
        "anti_cur": "Current ticket: `{tid}` · status=`{status}`",
        "anti_btn": "Retry execute_guarded with the same ticket",
        "anti_unexpected": "UNEXPECTED: replay allowed",
        "anti_ok": "The consumed ticket cannot be reused.",
        "red_h": "5 · Model output + redaction",
        "red_cap": "Personal fields removed; fail closed if redaction fails",
        "red_btn": "Run predict with redact_output=true",
        "red_last": "**Last result visible to the operator**",
        "aud_h": "6 · Audit trail (hash chain)",
        "aud_cap": "policy → approval → execution → redaction, linked hashes",
        "aud_empty": "No events yet — run DENY / approval / redact in earlier steps.",
        "col_rule": "rule / action",
        "col_dec": "decision",
        "tam_h": "7 · Tamper — local detection",
        "tam_cap": "Clumsy JSONL rewrite breaks verify_chain — not WORM",
        "tam_before": "Before",
        "tam_after": "After",
        "tam_btn": "Simulate clumsy rewrite + verify_chain",
        "tam_note": (
            "Local detection of crude tampering. Whoever controls JSONL + checkpoint "
            "can defeat the check. Not WORM and not certification."
        ),
        "close_h": "8 · Close and schemas",
        "close_line": "The model proposes. Controls decide. Evidence remains observable.",
        "close_disc": "Technical evidence is not AEPD, GDPR, or EU AI Act certification.",
        "schemas": "**Four schemas (lab)**",
        "sch1_t": "Governed decision",
        "sch1_p": (
            "Context → <code>evaluate_policies</code> → effect "
            "(DENY / REQUIRE_HUMAN_APPROVAL / REDACT / …) → optional invoke → audit."
        ),
        "sch2_t": "Approval ticket",
        "sch2_p": (
            "pending → approved|rejected|expired → consumed. "
            "Action binding + single use (anti-replay)."
        ),
        "sch3_t": "Audit event",
        "sch3_p": (
            "Local append-only JSONL · <code>event_hash</code> + "
            "<code>previous_event_hash</code> · <code>verify_chain()</code>."
        ),
        "sch4_t": "Redaction",
        "sch4_p": (
            "Personal fields → <code>[REDACTED]</code>. "
            "If required redaction fails → fail closed (DENY)."
        ),
        "footer": (
            "This page owns its runtime → `docs/governance/_demo_streamlit_*.jsonl` "
            "(gitignored). Terminal strip: `_demo_90s_audit.jsonl`. Recording: `record_demo.bat`."
        ),
        "chip_allow": "ALLOW / EXECUTED",
        "chip_deny": "DENY",
        "chip_approved": "APPROVED RUN",
        "chip_blocked": "BLOCKED",
        "chip_antireplay": "ANTI-REPLAY",
        "chip_redact": "REDACT",
        "chip_fail": "FAIL CLOSED",
        "chip_chain_ok": "CHAIN OK",
        "chip_chain_break": "CHAIN BREAK",
        "chip_tamper": "TAMPER DETECTED",
        "chip_unexpected": "UNEXPECTED",
    },
}

st.set_page_config(
    page_title="Governed Decision Demo",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --navy: #0B1F33;
      --slate: #1A3348;
      --amber: #D4A017;
      --deny: #C44536;
      --allow: #3D8B6E;
      --muted: #9BB0C3;
    }
    .demo-hero {
      background: linear-gradient(135deg, #0B1F33 0%, #16324A 55%, #1A3A4A 100%);
      border: 1px solid #2A4A63;
      border-radius: 10px;
      padding: 1.1rem 1.35rem;
      margin-bottom: 0.75rem;
    }
    .demo-hero h1 {
      color: #E8EEF4; margin: 0 0 0.35rem 0; font-size: 1.55rem;
    }
    .demo-hero p { color: #9BB0C3; margin: 0; font-size: 0.95rem; }
    .chip {
      display: inline-block; padding: 0.18rem 0.55rem; border-radius: 4px;
      font-weight: 700; font-size: 0.78rem; letter-spacing: 0.04em;
      margin-right: 0.35rem;
    }
    .chip-deny { background: #C44536; color: #fff; }
    .chip-allow { background: #3D8B6E; color: #fff; }
    .chip-amber { background: #D4A017; color: #0B1F33; }
    .chip-slate { background: #2A4A63; color: #E8EEF4; }
    .layer-row {
      display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.75rem 0 0.25rem 0;
    }
    .layer-card {
      flex: 1; min-width: 120px; background: #13293D; border: 1px solid #2A4A63;
      border-radius: 8px; padding: 0.7rem 0.6rem; text-align: center;
    }
    .layer-card strong { color: #E8EEF4; display: block; font-size: 0.92rem; }
    .layer-card span { color: #9BB0C3; font-size: 0.75rem; }
    .layer-card.hot { border-color: #D4A017; box-shadow: 0 0 0 1px #D4A01733; }
    .schema-card {
      background: #13293D; border-left: 4px solid #2A9D8F; border-radius: 6px;
      padding: 0.85rem 1rem; margin-bottom: 0.6rem; min-height: 7.5rem;
    }
    .schema-card h4 { color: #E8EEF4; margin: 0 0 0.35rem 0; font-size: 0.95rem; }
    .schema-card p { color: #9BB0C3; margin: 0; font-size: 0.82rem; }
    .final-line {
      background: #0F2740; border: 1px solid #D4A01766; border-radius: 8px;
      padding: 1rem 1.2rem; color: #E8EEF4; font-size: 1.05rem; text-align: center;
    }
    .final-line em { color: #D4A017; font-style: normal; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _chip(label: str, kind: str = "slate") -> str:
    return f'<span class="chip chip-{kind}">{label}</span>'


def _asset(stem: str, lang: str) -> Path:
    named = ASSETS / f"{stem}_{lang}.png"
    if named.exists():
        return named
    return ASSETS / f"{stem}.png"


def _reset_demo_files() -> None:
    for path in (
        DEMO_AUDIT,
        DEMO_AUDIT.with_suffix(DEMO_AUDIT.suffix + ".checkpoint.json"),
        DEMO_APPROVALS,
        TAMPER_AUDIT,
        TAMPER_AUDIT.with_suffix(TAMPER_AUDIT.suffix + ".checkpoint.json"),
    ):
        if path.exists():
            path.unlink()


@st.cache_resource
def _runtime_bundle() -> dict:
    DEMO_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(DEMO_AUDIT)
    store = ApprovalStore(path=DEMO_APPROVALS, audit=audit, backend="json")
    rt = ReferenceRuntime(approvals=store, audit=audit)
    return {"rt": rt, "audit": audit, "store": store}


def _get_rt() -> ReferenceRuntime:
    return _runtime_bundle()["rt"]


def _get_audit() -> AuditLog:
    return _runtime_bundle()["audit"]


_qp_lang = str(st.query_params.get("lang", "") or "").strip().lower()
lang = _qp_lang if _qp_lang in UI else "es"
t = UI[lang]
STEPS = t["steps"]

# --- sidebar ---
st.sidebar.markdown(t["sidebar_title"])
step_labels = [f"{tm} · {name}" for tm, name, _ in STEPS]
step_keys = [k for _, _, k in STEPS]
_qp_step = str(st.query_params.get("step", "") or "").strip().lower()
_auto = str(st.query_params.get("auto", "") or "").strip().lower() in ("1", "true", "yes")


def _read_step_file() -> str:
    if not STEP_FILE.exists():
        return ""
    try:
        return STEP_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""


_file_step = _read_step_file()
# auto: file wins, then ?step=, then first step — never stick on radio-only
if _auto:
    if _file_step in step_keys:
        step_key = _file_step
    elif _qp_step in step_keys:
        step_key = _qp_step
    else:
        step_key = step_keys[0]
    _default_idx = step_keys.index(step_key)
    st.sidebar.radio(t["sidebar_radio"], step_labels, index=_default_idx, disabled=True)
    st.sidebar.success(t["auto_ok"] + f" · `{step_key}`")

    @st.fragment(run_every=timedelta(seconds=0.6))
    def _poll_step_file() -> None:
        nxt = _read_step_file()
        if nxt in step_keys and nxt != st.session_state.get("_file_step_seen"):
            st.session_state["_file_step_seen"] = nxt
            st.rerun()

    # seed seen so first paint does not immediate-rerun loop
    if "_file_step_seen" not in st.session_state:
        st.session_state["_file_step_seen"] = step_key
    _poll_step_file()
else:
    _default_idx = step_keys.index(_qp_step) if _qp_step in step_keys else 0
    choice = st.sidebar.radio(t["sidebar_radio"], step_labels, index=_default_idx)
    step_key = STEPS[step_labels.index(choice)][2]

st.sidebar.markdown("---")
st.sidebar.caption(t["sidebar_term"])
st.sidebar.caption(t["sidebar_rec"])
if st.sidebar.button(t["reset_btn"], use_container_width=True):
    _runtime_bundle.clear()
    _reset_demo_files()
    st.sidebar.success(t["reset_ok"])
    st.rerun()

st.markdown(
    f"""
    <div class="demo-hero">
      <h1>{t["hero_h1"]}</h1>
      <p>{t["hero_p"]}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t["banner"])

audit = _get_audit()
ok, msg = audit.verify_chain()
rows = audit.read_all()
c1, c2, c3, c4 = st.columns(4)
c1.metric(t["m_events"], len(rows))
c2.metric(t["m_chain"], t["m_chain_ok"] if ok else t["m_chain_break"])
c3.metric(t["m_verify"], msg)
tickets = list((_get_rt().approvals._tickets or {}).values())  # noqa: SLF001
last = tickets[-1]["status"] if tickets else "—"
c4.metric(t["m_ticket"], last)

if step_key == "architecture":
    st.subheader(t["arch_h"])
    st.caption(t["arch_cap"])
    img = _asset("architecture_layers", lang)
    if img.exists():
        st.image(str(img), use_container_width=True)
    else:
        st.markdown(t["layer_html"], unsafe_allow_html=True)
    st.info(t["arch_info"])

elif step_key == "policy":
    st.subheader(t["pol_h"])
    st.caption(t["pol_cap"])
    col_a, col_b = st.columns([1, 1])
    with col_a:
        art5 = st.toggle("art5_concern", value=True)
        pii = st.toggle("identifiable_personal_data", value=False)
        legal = st.toggle("legal_effect_decision", value=False)
        redact = st.toggle("redact_output", value=False)
        action = st.selectbox("action", ["predict_ebm", "score", "export_external"], index=0)
    with col_b:
        st.markdown(t["pol_ctx"])
        st.json(
            {
                "art5_concern": art5,
                "identifiable_personal_data": pii,
                "legal_effect_decision": legal,
                "redact_output": redact,
                "tool": "predict_ebm" if action != "export_external" else None,
            }
        )

    def _run_policy_eval() -> None:
        rt = _get_rt()
        invoked = {"ran": False}

        def _fn():
            invoked["ran"] = True
            return {"score": 0.42, "email": "claimant@example.com", "name": "Ada"}

        ctx = {
            "art5_concern": art5,
            "identifiable_personal_data": pii,
            "legal_effect_decision": legal,
            "redact_output": redact,
            "record_count": 1,
        }
        if action != "export_external":
            ctx["tool"] = "predict_ebm"
        elif pii:
            ctx["tool"] = "predict_ebm"

        try:
            out = rt.execute_guarded(action, _fn, ctx)
            st.markdown(
                _chip(t["chip_allow"], "allow") + f" effect=`{out['decision'].get('effect')}`",
                unsafe_allow_html=True,
            )
            st.json(out.get("result"))
            st.session_state["last_result"] = out.get("result")
        except RuntimeBlocked as exc:
            st.markdown(
                _chip(t["chip_deny"], "deny")
                + f" `{exc.decision.get('policy_id')}` · `{exc.decision.get('effect')}`",
                unsafe_allow_html=True,
            )
            st.write(exc.decision.get("explanation") or "")
            st.caption(t["pol_invoked"].format(ran=invoked["ran"]))

    if st.button(t["pol_btn"], type="primary", use_container_width=True):
        _run_policy_eval()
    elif _auto and not st.session_state.get("auto_done_policy"):
        st.session_state["auto_done_policy"] = True
        _run_policy_eval()

elif step_key == "approval":
    st.subheader(t["appr_h"])
    st.caption(t["appr_cap"])
    img = _asset("ticket_lifecycle", lang)
    if img.exists():
        st.image(str(img), use_container_width=True)

    payload_raw = st.text_input(t["appr_payload"], value='{"case":"porto_lab_score"}')
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {"case": "porto_lab_score"}
        st.warning(t["appr_bad_json"])

    c1, c2, c3 = st.columns(3)
    rt = _get_rt()

    def _auto_approval_flow() -> None:
        ticket = rt.approvals.request(
            action="score",
            requester="demo-req",
            reason="legal_effect lab",
            payload=payload,
        )
        st.session_state["demo_ticket_id"] = ticket["ticket_id"]
        st.session_state["demo_payload"] = payload
        st.success(f"pending · {ticket['ticket_id']}")
        decided = rt.approvals.decide(
            ticket["ticket_id"], reviewer="demo-rev", approve=True, rationale="HITL ok"
        )
        st.success(f"{decided['status']} · {ticket['ticket_id']}")
        try:
            out = rt.execute_guarded(
                "score",
                lambda: {"score": 0.31, "email": "a@b.c", "name": "Ada"},
                {
                    "legal_effect_decision": True,
                    "approval_ticket_id": ticket["ticket_id"],
                    "approval_payload": payload,
                },
            )
            st.markdown(_chip(t["chip_approved"], "allow"), unsafe_allow_html=True)
            st.json(
                {
                    "status": out["status"],
                    "effect": out["decision"].get("effect"),
                    "result": out.get("result"),
                }
            )
            st.session_state["last_result"] = out.get("result")
            st.session_state["ticket_consumed"] = True
        except RuntimeBlocked as exc:
            st.markdown(_chip(t["chip_blocked"], "deny"), unsafe_allow_html=True)
            st.write(exc.decision)

    with c1:
        if st.button(t["appr_req"], use_container_width=True):
            ticket = rt.approvals.request(
                action="score",
                requester="demo-req",
                reason="legal_effect lab",
                payload=payload,
            )
            st.session_state["demo_ticket_id"] = ticket["ticket_id"]
            st.session_state["demo_payload"] = payload
            st.success(f"pending · {ticket['ticket_id']}")
    with c2:
        if st.button(t["appr_ok"], use_container_width=True):
            tid = st.session_state.get("demo_ticket_id")
            if not tid:
                st.error(t["appr_no_ticket"])
            else:
                decided = rt.approvals.decide(
                    tid, reviewer="demo-rev", approve=True, rationale="HITL ok"
                )
                st.success(f"{decided['status']} · {tid}")
    with c3:
        if st.button(t["appr_run"], use_container_width=True):
            tid = st.session_state.get("demo_ticket_id")
            pl = st.session_state.get("demo_payload") or payload
            if not tid:
                st.error(t["appr_no_ticket"])
            else:
                try:
                    out = rt.execute_guarded(
                        "score",
                        lambda: {"score": 0.31, "email": "a@b.c", "name": "Ada"},
                        {
                            "legal_effect_decision": True,
                            "approval_ticket_id": tid,
                            "approval_payload": pl,
                        },
                    )
                    st.markdown(_chip(t["chip_approved"], "allow"), unsafe_allow_html=True)
                    st.json(
                        {
                            "status": out["status"],
                            "effect": out["decision"].get("effect"),
                            "result": out.get("result"),
                        }
                    )
                    st.session_state["last_result"] = out.get("result")
                    st.session_state["ticket_consumed"] = True
                except RuntimeBlocked as exc:
                    st.markdown(_chip(t["chip_blocked"], "deny"), unsafe_allow_html=True)
                    st.write(exc.decision)

    if _auto and not st.session_state.get("auto_done_approval"):
        st.session_state["auto_done_approval"] = True
        _auto_approval_flow()

    tid = st.session_state.get("demo_ticket_id")
    if tid:
        ticket = rt.approvals.get(tid)
        st.markdown(
            _chip((ticket or {}).get("status", "?").upper(), "amber") + f" `{tid}`",
            unsafe_allow_html=True,
        )
        st.json(ticket)

elif step_key == "antireplay":
    st.subheader(t["anti_h"])
    st.caption(t["anti_cap"])
    rt = _get_rt()
    tid = st.session_state.get("demo_ticket_id")
    pl = st.session_state.get("demo_payload") or {"case": "porto_lab_score"}
    if not tid:
        st.warning(t["anti_need"])
    else:
        ticket = rt.approvals.get(tid)
        st.write(
            t["anti_cur"].format(tid=tid, status=(ticket or {}).get("status"))
        )

        def _run_antireplay() -> None:
            try:
                rt.execute_guarded(
                    "score",
                    lambda: {"score": 0.99},
                    {
                        "legal_effect_decision": True,
                        "approval_ticket_id": tid,
                        "approval_payload": pl,
                    },
                )
                st.error(t["anti_unexpected"])
            except RuntimeBlocked as exc:
                st.markdown(_chip(t["chip_antireplay"], "deny"), unsafe_allow_html=True)
                st.write(
                    exc.decision.get("effect"),
                    "—",
                    exc.decision.get("explanation") or "ticket not approved/consumed",
                )
                st.caption(t["anti_ok"])

        if st.button(t["anti_btn"], type="primary"):
            _run_antireplay()
        elif _auto and not st.session_state.get("auto_done_antireplay"):
            st.session_state["auto_done_antireplay"] = True
            _run_antireplay()

elif step_key == "redact":
    st.subheader(t["red_h"])
    st.caption(t["red_cap"])
    rt = _get_rt()

    def _run_redact() -> None:
        try:
            red = rt.execute_guarded(
                "predict_ebm",
                lambda: {"email": "a@b.c", "name": "Ada", "score": 0.31},
                {"tool": "predict_ebm", "record_count": 1, "redact_output": True},
            )
            st.markdown(_chip(t["chip_redact"], "amber"), unsafe_allow_html=True)
            st.json(
                {
                    "result": red["result"],
                    "redacted_fields": red["context"].get("redacted_fields"),
                    "effect": red["decision"].get("effect"),
                }
            )
            st.session_state["last_result"] = red.get("result")
        except RuntimeBlocked as exc:
            st.markdown(_chip(t["chip_fail"], "deny"), unsafe_allow_html=True)
            st.write(exc.decision)

    if st.button(t["red_btn"], type="primary"):
        _run_redact()
    elif _auto and not st.session_state.get("auto_done_redact"):
        st.session_state["auto_done_redact"] = True
        _run_redact()

    if "last_result" in st.session_state:
        st.markdown(t["red_last"])
        st.json(st.session_state["last_result"])

elif step_key == "audit":
    st.subheader(t["aud_h"])
    st.caption(t["aud_cap"])
    img = _asset("hash_chain", lang)
    if img.exists():
        st.image(str(img), use_container_width=True)

    audit = _get_audit()
    ok, msg = audit.verify_chain()
    rows = audit.read_all()
    st.markdown(
        (_chip(t["chip_chain_ok"], "allow") if ok else _chip(t["chip_chain_break"], "deny"))
        + f" `{msg}` · events={len(rows)}",
        unsafe_allow_html=True,
    )
    if rows:
        display = [
            {
                t["col_rule"]: r.get("rule_triggered") or r.get("action_taken"),
                t["col_dec"]: r.get("decision"),
                "event_hash": (r.get("event_hash") or "")[:16],
                "previous_event_hash": (r.get("previous_event_hash") or "")[:16],
            }
            for r in rows[-12:]
        ]
        st.dataframe(display, hide_index=True, use_container_width=True)
    else:
        st.info(t["aud_empty"])

elif step_key == "tamper":
    st.subheader(t["tam_h"])
    st.caption(t["tam_cap"])

    def _run_tamper() -> None:
        for p in (
            TAMPER_AUDIT,
            TAMPER_AUDIT.with_suffix(TAMPER_AUDIT.suffix + ".checkpoint.json"),
        ):
            if p.exists():
                p.unlink()
        tamper_log = AuditLog(TAMPER_AUDIT)
        tamper_log.append({"rule_triggered": "demo_a", "decision": "ALLOW"})
        tamper_log.append({"rule_triggered": "demo_b", "decision": "ALLOW"})
        ok1, msg1 = tamper_log.verify_chain()
        lines = TAMPER_AUDIT.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace('"demo_a"', '"demo_TAMPERED"')
        TAMPER_AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok2, msg2 = tamper_log.verify_chain()
        ca, cb = st.columns(2)
        ca.metric(t["tam_before"], f"{ok1} · {msg1}")
        cb.metric(t["tam_after"], f"{ok2} · {msg2}")
        st.markdown(
            _chip(t["chip_tamper"], "deny")
            if (ok1 and not ok2)
            else _chip(t["chip_unexpected"], "amber"),
            unsafe_allow_html=True,
        )
        st.caption(t["tam_note"])

    if st.button(t["tam_btn"], type="primary"):
        _run_tamper()
    elif _auto and not st.session_state.get("auto_done_tamper"):
        st.session_state["auto_done_tamper"] = True
        _run_tamper()

else:
    st.subheader(t["close_h"])
    st.markdown(
        f"""
        <div class="final-line">
          <em>{t["close_line"]}</em><br/>
          <span style="color:#9BB0C3;font-size:0.9rem">{t["close_disc"]}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.markdown(t["schemas"])
    s1, s2 = st.columns(2)
    with s1:
        st.markdown(
            f"""
            <div class="schema-card">
              <h4>{t["sch1_t"]}</h4>
              <p>{t["sch1_p"]}</p>
            </div>
            <div class="schema-card">
              <h4>{t["sch2_t"]}</h4>
              <p>{t["sch2_p"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            f"""
            <div class="schema-card">
              <h4>{t["sch3_t"]}</h4>
              <p>{t["sch3_p"]}</p>
            </div>
            <div class="schema-card">
              <h4>{t["sch4_t"]}</h4>
              <p>{t["sch4_p"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("---")
st.caption(t["footer"])
