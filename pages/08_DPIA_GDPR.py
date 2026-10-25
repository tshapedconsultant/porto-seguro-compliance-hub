"""
DPIA / EIPD (GDPR Art. 35) — evidencia para laboratorio de innovación AEPD.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.control_plane_notice import CONTROL_PLANE_BANNER

DPIA_PATHS = (Path("gdpr_dpia_v1.json"), Path("docs/dpia_gdpr_v1.json"))


def _load_dpia() -> tuple[dict, Path]:
    for path in DPIA_PATHS:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
    return {}, Path("gdpr_dpia_v1.json")


dpia, dpia_path = _load_dpia()

st.title("EIPD / DPIA — RGPD art. 35")
st.caption("Evaluación de impacto relativa a la protección de datos · laboratorio de innovación AEPD")
st.warning(CONTROL_PLANE_BANNER)

st.warning(
    dpia.get("disclaimer", {}).get(
        "text_es",
        "Arquitectura de referencia. No es una notificación a la autoridad de control.",
    )
)

if not dpia:
    st.error("No se encontró `gdpr_dpia_v1.json`.")
    st.stop()

residual = dpia.get("residual_risk_summary", {})
why = dpia.get("why_dpia_is_required", {})
art22 = dpia.get("data_subject_rights", {}).get("automated_decisions_art_22", {})

c1, c2, c3, c4 = st.columns(4)
c1.metric("Disparador art. 35", "Sí (análogo)")
c2.metric("Riesgo residual", residual.get("overall", "N/A"))
st.caption(residual.get("residual_status", "estimated_pending_verification"))
c3.metric("Art. 22 intervención humana", residual.get("human_intervention", "required"))
c4.metric("Notificación AEPD", "No (demo)")

st.markdown("---")
st.header("Para un walkthrough de 3 minutos")
st.markdown(
    """
1. **Qué se trata:** puntuación de probabilidad de siniestro como apoyo a suscripción (no prima automática).
2. **Por qué hay EIPD:** art. 35.3.a RGPD — evaluación sistemática a gran escala con efectos análogos a una decisión de seguro.
3. **Matiz del demo:** el fichero Kaggle está anonimizado (`ps_*`). Si fuera irreversible (considerando 26), el RGPD no se aplica a esos registros; el pack existe como **control de diseño** para un responsable real.
4. **Art. 22:** el modelo es **asesor**; hay explicación nativa EBM (log-odds) y enrutado a revisión humana.
5. **Descargar** el JSON: es el sistema de registro, igual que la declaración de conformidad del Reglamento de IA.
"""
)

st.header("Descripción del tratamiento")
proc = dpia.get("processing_description", {})
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Finalidad")
    for item in proc.get("purposes", []):
        st.write(f"- {item}")
    st.subheader("Fuera de alcance")
    for item in proc.get("out_of_scope", []):
        st.write(f"- {item}")
with col_b:
    cats = proc.get("data_categories", {})
    st.subheader("Datos (demo)")
    st.write(f"**Fuente:** {cats.get('demo_dataset', 'N/A')}")
    st.write(f"**Registros:** {cats.get('records', 'N/A')}")
    st.write(f"**Identificadores directos:** {cats.get('direct_identifiers', 'N/A')}")
    st.write(f"**Art. 9 (categorías especiales):** {cats.get('special_categories_art_9', 'N/A')}")
    st.write(f"**Transferencias internacionales:** {proc.get('international_transfers', 'N/A')}")

with st.expander("Base jurídica (demo vs producción)", expanded=False):
    basis = proc.get("legal_basis", {})
    st.markdown(f"**Demo:** {basis.get('demo', {}).get('position', '')}")
    st.markdown("**Análogo de producción (no se afirma aquí):**")
    for item in basis.get("production_analogue", {}).get("candidate_bases", []):
        st.write(f"- {item}")

st.header("Por qué el art. 35")
st.write(why.get("article_35_3_a", ""))
st.info(why.get("demo_nuance", ""))
st.caption(why.get("aepd_list", ""))

st.header("Principios (art. 5)")
principles = dpia.get("necessity_and_proportionality", {})
principle_labels = {
    "purpose_limitation_art_5_1_b": "Limitación de la finalidad",
    "data_minimisation_art_5_1_c": "Minimización",
    "accuracy_art_5_1_d": "Exactitud",
    "storage_limitation_art_5_1_e": "Limitación del plazo",
    "integrity_confidentiality_art_5_1_f": "Integridad y confidencialidad",
    "accountability_art_5_2": "Responsabilidad proactiva",
}
for key, label in principle_labels.items():
    if key in principles:
        st.markdown(f"**{label}.** {principles[key]}")

st.header("Derechos (arts. 12–22)")
rights = dpia.get("data_subject_rights", {})
st.markdown(f"**Información (13–14).** {rights.get('information_art_13_14', '')}")
st.markdown(f"**Acceso (15).** {rights.get('access_art_15', '')}")
st.markdown(f"**Decisiones automatizadas (22).** {art22.get('position', '')}")
st.markdown("**Salvaguardas en este repositorio:**")
for item in art22.get("implementation_in_this_repo", []):
    st.write(f"- {item}")

st.header("Registro de riesgos")
st.caption("Puntuación = probabilidad × gravedad (1–5). Residual tras controles del código.")
rows = []
for risk in dpia.get("risk_register", []):
    rows.append(
        {
            "ID": risk.get("id"),
            "Riesgo": risk.get("risk"),
            "Inherente": risk.get("inherent_score"),
            "Residual": risk.get("residual_score"),
            "Estado": risk.get("status"),
        }
    )
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

with st.expander("Detalle de riesgos y mitigaciones", expanded=False):
    for risk in dpia.get("risk_register", []):
        st.markdown(f"**{risk.get('id')} — residual {risk.get('residual_score')}**")
        st.write(risk.get("risk"))
        for m in risk.get("mitigations", []):
            st.write(f"- {m}")

st.header("Medidas que ya están en el código")
for item in dpia.get("mitigations_in_code", []):
    st.markdown(f"- **{item.get('control')}** — `{item.get('evidence')}`")

st.header("Cruce RGPD × Reglamento de IA")
st.caption("Dos regímenes, un rastro de evidencia. El lab puede saltar a la página EU AI Act.")
cross = dpia.get("gdpr_eu_ai_act_crosswalk", [])
if cross:
    st.table(pd.DataFrame(cross))

st.page_link("pages/06_EU_AI_Act.py", label="Abrir mapeo artículo a artículo del Reglamento de IA")
st.page_link("pages/03_Explainability.py", label="Abrir explicabilidad nativa (art. 22 / art. 13 IA)")

st.markdown("---")
st.subheader("Pack de evidencia")
payload = json.dumps(dpia, indent=2, ensure_ascii=False)
st.download_button(
    label="Descargar EIPD (JSON)",
    data=payload,
    file_name="gdpr_dpia_v1.json",
    mime="application/json",
)
st.caption(f"Sistema de registro en disco: `{dpia_path}` · firma DPO pendiente (demo).")
st.caption(residual.get("article_36", ""))
