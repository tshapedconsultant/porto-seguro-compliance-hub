"""
AEPD 90s walkthrough — EIPD is the narrative, runtime controls are evidence.

Identify processing → risk to rights → control → inspect evidence → residual risk.
Not a formal EIPD filing or Art. 36 prior consultation.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.runtime import ReferenceRuntime, RuntimeBlocked

ROOT = Path(__file__).resolve().parents[1]
DPIA_PATH = ROOT / "gdpr_dpia_v1.json"
STEP_FILE = ROOT / "docs" / "governance" / "_demo_record_tmp" / "current_step.txt"
DEMO_AUDIT = ROOT / "docs" / "governance" / "_demo_aepd_audit.jsonl"
DEMO_APPROVALS = ROOT / "docs" / "governance" / "_demo_aepd_approvals.json"
TAMPER_AUDIT = ROOT / "docs" / "governance" / "_demo_aepd_tamper.jsonl"
REPO_URL = "https://github.com/tshapedconsultant/porto-seguro-compliance-hub"

STEPS = [
    ("0:00", "Alcance", "scope"),
    ("0:10", "EIPD", "eipd"),
    ("0:25", "Controles", "controls"),
    ("0:45", "Evidencia", "evidence"),
    ("1:00", "Registro", "register"),
    ("1:15", "Límites", "close"),
]

RISK_ES = {
    "R1": "Puntuación injusta por proxies geográficos o de conducta (sin atributos del art. 9).",
    "R2": "La deriva de datos degrada un subgrupo y cambia las puntuaciones.",
    "R3": "Reidentificación residual si un extracto de producción se cruza con ficheros externos.",
    "R4": "Sesgo de automatización: sobreconfianza en la puntuación sin impugnación.",
    "R5": "Fallo de integridad: artefacto de modelo erróneo o manipulado.",
}

st.set_page_config(
    page_title="EIPD · laboratorio AEPD",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu, footer, header {visibility: hidden; height: 0;}
    .stApp { background: #F4F6F8; }
    .block-container { padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1180px; }
    .saas-top {
      display: flex; justify-content: space-between; align-items: center;
      background: #fff; border: 1px solid #E2E8F0; border-radius: 12px;
      padding: 0.85rem 1.15rem; margin-bottom: 0.7rem;
    }
    .saas-brand { font-size: 1.05rem; font-weight: 700; color: #0F172A; }
    .saas-brand span { color: #0F766E; font-weight: 600; }
    .pill {
      display: inline-block; font-size: 0.72rem; font-weight: 700; letter-spacing: .04em;
      padding: 0.22rem 0.55rem; border-radius: 999px; margin-left: 0.35rem;
    }
    .pill-lab { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
    .pill-warn { background: #FFF7ED; color: #C2410C; border: 1px solid #FED7AA; }
    .scope-strip {
      background: #0F172A; color: #E2E8F0; border-radius: 10px;
      padding: 0.7rem 1rem; font-size: 0.88rem; margin-bottom: 0.85rem;
    }
    .scope-strip strong { color: #5EEAD4; }
    .progress {
      display: flex; gap: 0.35rem; margin: 0 0 1rem 0;
    }
    .progress div {
      flex: 1; height: 6px; border-radius: 99px; background: #E2E8F0;
    }
    .progress div.on { background: #0F766E; }
    .card {
      background: #fff; border: 1px solid #E2E8F0; border-radius: 12px;
      padding: 1rem 1.1rem; height: 100%;
    }
    .card h3 { margin: 0 0 0.4rem 0; font-size: 0.92rem; color: #64748B; font-weight: 600; }
    .card p, .card li { color: #0F172A; font-size: 0.95rem; }
    .kpi {
      background: #fff; border: 1px solid #E2E8F0; border-radius: 12px;
      padding: 0.85rem 1rem;
    }
    .kpi .n { font-size: 1.35rem; font-weight: 700; color: #0F172A; }
    .kpi .l { font-size: 0.75rem; color: #64748B; text-transform: uppercase; letter-spacing: .04em; }
    .chip {
      display: inline-block; padding: 0.16rem 0.5rem; border-radius: 6px;
      font-weight: 700; font-size: 0.75rem; margin-right: 0.3rem;
    }
    .chip-deny { background: #FEE2E2; color: #B91C1C; }
    .chip-ok { background: #D1FAE5; color: #047857; }
    .chip-amber { background: #FEF3C7; color: #92400E; }
    .close-box {
      background: #0F172A; color: #F8FAFC; border-radius: 12px;
      padding: 1.2rem 1.3rem;
    }
    .close-box a { color: #5EEAD4; }
    .close-box .muted { color: #94A3B8; font-size: 0.9rem; margin-top: 0.55rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _chip(label: str, kind: str) -> str:
    return f'<span class="chip chip-{kind}">{label}</span>'


def _load_dpia() -> dict:
    if not DPIA_PATH.exists():
        return {}
    return json.loads(DPIA_PATH.read_text(encoding="utf-8"))


@st.cache_resource
def _runtime_bundle() -> dict:
    DEMO_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(DEMO_AUDIT)
    store = ApprovalStore(path=DEMO_APPROVALS, audit=audit, backend="json")
    return {"rt": ReferenceRuntime(approvals=store, audit=audit), "audit": audit}


def _rt() -> ReferenceRuntime:
    return _runtime_bundle()["rt"]


def _audit() -> AuditLog:
    return _runtime_bundle()["audit"]


def _read_step_file() -> str:
    if not STEP_FILE.exists():
        return ""
    try:
        return STEP_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""


dpia = _load_dpia()
proc = dpia.get("processing_description", {})
cats = proc.get("data_categories", {})
residual = dpia.get("residual_risk_summary", {})
disclaimer = dpia.get("disclaimer", {})
roles = dpia.get("roles", {})

step_keys = [k for _, _, k in STEPS]
_qp_step = str(st.query_params.get("step", "") or "").strip().lower()
_auto = str(st.query_params.get("auto", "") or "").strip().lower() in ("1", "true", "yes")
_file_step = _read_step_file()

if _auto:
    if _file_step in step_keys:
        step_key = _file_step
    elif _qp_step in step_keys:
        step_key = _qp_step
    else:
        step_key = "scope"
    if "_file_step_seen" not in st.session_state:
        st.session_state["_file_step_seen"] = step_key

    @st.fragment(run_every=timedelta(seconds=0.6))
    def _poll() -> None:
        nxt = _read_step_file()
        if nxt in step_keys and nxt != st.session_state.get("_file_step_seen"):
            st.session_state["_file_step_seen"] = nxt
            st.rerun()

    _poll()
else:
    labels = [f"{t}  {n}" for t, n, _ in STEPS]
    idx = step_keys.index(_qp_step) if _qp_step in step_keys else 0
    choice = st.sidebar.radio("Paso", labels, index=idx)
    step_key = STEPS[labels.index(choice)][2]

# --- chrome ---
st.markdown(
    """
    <div class="saas-top">
      <div class="saas-brand">Porto Seguro <span>Hub de cumplimiento</span></div>
      <div>
        <span class="pill pill-lab">LABORATORIO · NO PRODUCCIÓN</span>
        <span class="pill pill-warn">SIN CERTIFICACIÓN AEPD</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    f"""
    <div class="scope-strip">
      Dataset de referencia: <strong>{cats.get("demo_dataset", "Kaggle Porto Seguro")}</strong>
      · {int(cats.get("records", 595212)):,} registros anonimizados
      · sin cartera real de seguros
      · responsable y DPO: <strong>pendiente / hipotético</strong>
      · no es presentación formal de EIPD ni consulta previa art. 36
    </div>
    """,
    unsafe_allow_html=True,
)

active_i = step_keys.index(step_key) if step_key in step_keys else 0
bars = "".join(
    f'<div class="{"on" if i <= active_i else ""}"></div>' for i in range(len(STEPS))
)
st.markdown(f'<div class="progress">{bars}</div>', unsafe_allow_html=True)
st.caption(f"**{STEPS[active_i][1]}** · {STEPS[active_i][0]}")

# =====================================================================
if step_key == "scope":
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(
        '<div class="kpi"><div class="l">Arquitectura</div>'
        '<div class="n">Referencia</div></div>',
        unsafe_allow_html=True,
    )
    k2.markdown(
        '<div class="kpi"><div class="l">Registros demo</div>'
        f'<div class="n">{int(cats.get("records", 595212)):,}</div></div>'.replace(",", "."),
        unsafe_allow_html=True,
    )
    k3.markdown(
        '<div class="kpi"><div class="l">Identificadores</div>'
        '<div class="n">Ninguno</div></div>',
        unsafe_allow_html=True,
    )
    k4.markdown(
        '<div class="kpi"><div class="l">Aseguramiento</div>'
        '<div class="n">Solo evidencia</div></div>',
        unsafe_allow_html=True,
    )
    a, b = st.columns(2)
    with a:
        st.markdown(
            """
            <div class="card">
              <h3>Qué es</h3>
              <p>Arquitectura de referencia para evaluación técnica (laboratorio de innovación).
              El modelo propone; el plano de control decide; la evidencia queda observable.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(
            """
            <div class="card">
              <h3>Qué no es</h3>
              <p>No es un sistema aprobado por la AEPD, ni un despliegue sobre la cartera
              de un asegurador, ni una EIPD firmada, ni una consulta previa del artículo 36 RGPD.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

elif step_key == "eipd":
    a, b, c = st.columns(3)
    with a:
        st.markdown(
            """
            <div class="card">
              <h3>Tratamiento</h3>
              <p>Apoyo a la suscripción: estimar P(siniestro) sobre un registro.
              Fuera de alcance: prima automática, rechazo autónomo del contrato, art. 9.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(
            """
            <div class="card">
              <h3>Necesidad y proporcionalidad</h3>
              <p>Finalidad única (art. 5.1.b). Minimización: columnas <code>ps_*</code>
              ya anonimizadas; sin nombre, DNI ni contacto. Exactitud: ROC-AUC ~0,639
              (no se usa el 87&nbsp;% de acierto como éxito).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c:
        st.markdown(
            """
            <div class="card">
              <h3>Por qué hay EIPD</h3>
              <p>Art. 35.3.a: evaluación sistemática a gran escala con efectos análogos
              a una decisión de seguro. El fichero demo no identifica personas;
              el pack es el control de diseño que un responsable real firmaría.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.info(
        "Riesgos principales para los derechos: equidad (proxies) · exactitud (deriva) · "
        "art. 22 (automatización) · integridad del artefacto. Siguiente: un control vivo."
    )

elif step_key == "controls":
    st.markdown("**Riesgo → control.** La puntuación no se ejecuta si hay un riesgo para derechos.")
    c1, c2, c3 = st.columns(3)

    def _deny() -> None:
        invoked = {"ran": False}

        def _fn():
            invoked["ran"] = True
            return {"score": 0.42}

        try:
            _rt().execute_guarded(
                "predict_ebm",
                _fn,
                {"art5_concern": True, "tool": "predict_ebm", "record_count": 1},
            )
            c1.error("INESPERADO: ALLOW")
        except RuntimeBlocked as exc:
            c1.markdown(
                _chip("DENY", "deny")
                + " antes de ejecutar el modelo",
                unsafe_allow_html=True,
            )
            c1.write(exc.decision.get("explanation") or exc.decision.get("effect"))
            c1.caption(f"Función del modelo invocada: **{invoked['ran']}** (debe ser False)")

    def _approve() -> None:
        payload = {"case": "porto_lab_score"}
        t = _rt().approvals.request(
            action="score", requester="lab", reason="efecto jurídico", payload=payload
        )
        _rt().approvals.decide(t["ticket_id"], reviewer="revisor", approve=True, rationale="HITL")
        try:
            out = _rt().execute_guarded(
                "score",
                lambda: {"score": 0.31, "email": "a@b.c"},
                {
                    "legal_effect_decision": True,
                    "approval_ticket_id": t["ticket_id"],
                    "approval_payload": payload,
                },
            )
            c2.markdown(_chip("APROBADO", "ok") + " ticket de un solo uso", unsafe_allow_html=True)
            c2.caption(f"estado={out['status']} · {t['ticket_id'][:12]}…")
            st.session_state["aepd_tid"] = t["ticket_id"]
            st.session_state["aepd_payload"] = payload
        except RuntimeBlocked as exc:
            c2.markdown(_chip("BLOQUEADO", "deny"), unsafe_allow_html=True)
            c2.write(exc.decision.get("effect"))

    def _redact() -> None:
        try:
            red = _rt().execute_guarded(
                "predict_ebm",
                lambda: {"email": "a@b.c", "name": "Ada", "score": 0.31},
                {"tool": "predict_ebm", "record_count": 1, "redact_output": True},
            )
            c3.markdown(_chip("REDACT", "amber") + " fail closed si falla", unsafe_allow_html=True)
            c3.json(
                {
                    "result": red.get("result"),
                    "redacted_fields": red.get("context", {}).get("redacted_fields"),
                }
            )
        except RuntimeBlocked as exc:
            c3.markdown(_chip("FAIL CLOSED", "deny"), unsafe_allow_html=True)
            c3.write(exc.decision.get("effect"))

    if _auto and not st.session_state.get("aepd_controls_done"):
        st.session_state["aepd_controls_done"] = True
        _deny()
        _approve()
        _redact()
    else:
        if c1.button("Denegar (art. 5)", use_container_width=True):
            _deny()
        if c2.button("Aprobar HITL", use_container_width=True):
            _approve()
        if c3.button("Redactar salida", use_container_width=True):
            _redact()

elif step_key == "evidence":
    e1, e2 = st.columns([1.2, 1])
    with e1:
        ok, msg = _audit().verify_chain()
        rows = _audit().read_all()
        st.markdown(
            (_chip("CADENA OK", "ok") if ok else _chip("CADENA ROTA", "deny"))
            + f" `{msg}` · {len(rows)} eventos",
            unsafe_allow_html=True,
        )
        if rows:
            st.dataframe(
                [
                    {
                        "evento": r.get("rule_triggered") or r.get("action_taken"),
                        "decisión": r.get("decision"),
                        "hash": (r.get("event_hash") or "")[:14],
                    }
                    for r in rows[-8:]
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Sin eventos aún — el paso de controles los genera.")
    with e2:

        def _tamper() -> None:
            for p in (
                TAMPER_AUDIT,
                TAMPER_AUDIT.with_suffix(TAMPER_AUDIT.suffix + ".checkpoint.json"),
            ):
                if p.exists():
                    p.unlink()
            log = AuditLog(TAMPER_AUDIT)
            log.append({"rule_triggered": "demo_a", "decision": "ALLOW"})
            log.append({"rule_triggered": "demo_b", "decision": "ALLOW"})
            ok1, m1 = log.verify_chain()
            lines = TAMPER_AUDIT.read_text(encoding="utf-8").splitlines()
            lines[0] = lines[0].replace('"demo_a"', '"demo_TAMPERED"')
            TAMPER_AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")
            ok2, m2 = log.verify_chain()
            a, b = st.columns(2)
            a.metric("Antes", f"{ok1}")
            b.metric("Después", f"{ok2}")
            st.markdown(_chip("MANIPULACIÓN DETECTADA", "deny"), unsafe_allow_html=True)
            st.caption(
                "Detección local. Quien controle JSONL + checkpoint puede derrotar la "
                "comprobación. No es WORM ni auditoría externa inmutable."
            )
            st.caption(f"{m1} → {m2}")

        if _auto and not st.session_state.get("aepd_tamper_done"):
            st.session_state["aepd_tamper_done"] = True
            _tamper()
        elif st.button("Simular reescritura torpe"):
            _tamper()

elif step_key == "register":
    st.markdown("**Registro de riesgos (pack `gdpr_dpia_v1.json`).** Residual = estimación pendiente de verificación.")
    rows = []
    for risk in dpia.get("risk_register", []):
        rid = risk.get("id")
        rows.append(
            {
                "ID": rid,
                "Riesgo para derechos": RISK_ES.get(rid, risk.get("risk")),
                "Inherente": risk.get("inherent_score"),
                "Residual": risk.get("residual_score"),
                "Estado residual": risk.get("residual_status"),
                "Mitigación": "; ".join(risk.get("mitigations", [])[:2]),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Riesgo residual (pack)", str(residual.get("overall", "medio")).upper())
    m2.metric("Intervención humana", residual.get("human_intervention", "required"))
    m3.metric("Firma DPO", roles.get("sign_off", {}).get("dpo", "pendiente"))
    st.caption(residual.get("scale_note", ""))

else:
    st.markdown(
        f"""
        <div class="close-box">
          <p style="font-size:1.15rem;font-weight:600;margin:0 0 .6rem 0">
            Arquitectura de referencia para evaluación, no una EIPD formal ni una consulta previa del artículo 36.
          </p>
          <p style="margin:0 0 .4rem 0">
            Lo que queda sin verificar es parte del método: puntuaciones residuales estimadas,
            revisión humana obligatoria, cadena hash local ≠ almacenamiento inmutable externo.
          </p>
          <p style="margin:0"><a href="{REPO_URL}">{REPO_URL}</a></p>
          <p class="muted">{disclaimer.get("text_es", "")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    n1, n2, n3 = st.columns(3)
    n1.markdown(
        '<div class="card"><h3>Siguiente (producción)</h3>'
        "<p>EIPD firmada por el responsable real · DPO · base jurídica · canal de oposición.</p></div>",
        unsafe_allow_html=True,
    )
    n2.markdown(
        '<div class="card"><h3>Siguiente (evidencia)</h3>'
        "<p>Residuos con <code>verification_state</code> tested|verified. WORM o apéndice externo.</p></div>",
        unsafe_allow_html=True,
    )
    n3.markdown(
        '<div class="card"><h3>Siguiente (personas)</h3>'
        "<p>Aviso de privacidad, art. 15.1.h operativo, impugnación art. 22.3 en el proceso.</p></div>",
        unsafe_allow_html=True,
    )
