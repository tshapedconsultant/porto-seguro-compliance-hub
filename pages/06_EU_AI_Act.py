"""
EU AI Act mapping - Article-by-article compliance traceability.
Maps Porto Seguro pipeline to EU AI Act obligations for high-risk AI systems.
"""

from __future__ import annotations

import streamlit as st

from src.control_plane.regulatory_library import applicable_mappings, classify_system
from utils.control_plane_notice import CONTROL_PLANE_BANNER

st.title("⚖️ EU AI Act - Article-by-Article Mapping")
st.warning(CONTROL_PLANE_BANNER)
st.markdown(
    "This scoring demo **may** fall under high-risk duties **if** it is used for "
    "insurance risk assessment and pricing in life and health insurance within "
    "Annex III, **and** the operator's role (provider vs deployer) is established. "
    "Classification is **conditional** — not inferred from the EBM library or model name. "
    "Conformity assessment (Art. 43) is **not** automatically a third-party notified-body "
    "process for every Annex III system; it depends on the applicable path. "
    "Source of truth for dates and actors: `src/control_plane/regulatory_library.py`."
)
_cls = classify_system(
    {
        "role": "unknown",
        "intended_purpose": "claim probability decision support",
        "insurance_product": "motor",
        "annex_iii_point": "unknown",
        "decision_context": "advisory underwriting analogue on anonymised Kaggle rows",
    }
)
st.caption(
    f"Screening (not a legal classification): potential_high_risk={_cls['potential_high_risk']} "
    f"· is_legal_classification={_cls['is_legal_classification']} · role={_cls['role_declared']}"
)
with st.expander("Regulatory library (conditional applicability)", expanded=False):
    rows = [
        {
            "id": m["id"],
            "article": m["article"],
            "actor": m["actor"],
            "computed": m["computed_applicability"],
        }
        for m in applicable_mappings(_cls)
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)

st.markdown("---")

# --- Article mapping table ---
st.header("Compliance traceability")

mapping = [
    {
        "Article": "Art. 9 - Risk Management System",
        "Obligation": "Continuous identification, evaluation and mitigation of risks throughout the system lifecycle.",
        "Implementation": "KS-test drift monitoring on production traffic with PSI tiers (WARN 0.10-0.20, ALERT > 0.20). Shadow Monitor runs independently of the cloud provider.",
        "Evidence in repo": "`shadow_monitor.py`, `pages/07_Drift_Monitoring.py`.",
    },
    {
        "Article": "Art. 10 - Data and data governance",
        "Obligation": "Training, validation and testing datasets must be relevant, representative, free of errors and complete.",
        "Implementation": "Stratified split (3.6% positive class preserved). Polars-native data validation module with quality score, missingness detection, bias signals. Feature engineer fit only on train (no leakage).",
        "Evidence in repo": "`data_validation.py`, `feature_engineering.py::ResponsibleFeatureEngineer.fit()`",
    },
    {
        "Article": "Art. 13 - Transparency and information to users",
        "Obligation": "AI system designed to enable users to interpret and use the output appropriately.",
        "Implementation": "Glass-Box EBM with native `explain_global()` and `explain_local()` - no SHAP wrapper needed. Per-feature shape functions visible. Model card published.",
        "Evidence in repo": "`explainability.py`, `pages/03_Explainability.py`.",
    },
    {
        "Article": "Art. 14 - Human oversight",
        "Obligation": "AI system designed to be effectively overseen by natural persons during use.",
        "Implementation": "Threshold-based routing to manual underwriting review queue. Auto-decisions only at extreme score percentiles. Model output is advisory, not autonomous.",
        "Evidence in repo": "`find_optimal_threshold.py`, `pages/05_Business_Context.py`.",
    },
    {
        "Article": "Art. 15 - Accuracy, robustness and cybersecurity",
        "Obligation": "Appropriate level of accuracy, robustness and cybersecurity throughout lifecycle.",
        "Implementation": "Adversarial testing via feature perturbation (10% noise) and feature dropout. Cross-validation 5-fold stratified. Test hold-out never seen during training or threshold tuning. SHA-256 artifact integrity checks.",
        "Evidence in repo": "`evaluation.py::adversarial_testing()`, `ebm_train.py` (SHA-256 sidecar).",
    },
    {
        "Article": "Annex IV - Technical documentation",
        "Obligation": "Detailed description of system, purpose, training methodology and performance metrics.",
        "Implementation": "Model Card (JSON), Compliance Report (JSON), this Streamlit dashboard.",
        "Evidence in repo": "`docs/model_card.json`, `docs/compliance_report.json`.",
    },
]

for item in mapping:
    with st.expander(f"📋 {item['Article']}", expanded=False):
        st.markdown(f"**Obligation:** {item['Obligation']}")
        st.markdown(f"**Implementation:** {item['Implementation']}")
        st.markdown(f"**Evidence in repo:** {item['Evidence in repo']}")

# --- Conformity assessment section ---
st.header("Conformity assessment (Art. 43)")

st.warning(
    "This dashboard demonstrates **technical readiness** for EU AI Act conformity. "
    "A production high-risk classification, if confirmed, triggers the applicable "
    "conformity path under Article 43 — which is **not always** a third-party "
    "assessment by an accredited body. This dashboard shows technical evidence, "
    "not a completed conformity procedure."
)

# --- Solvency II crosswalk ---
st.header("Crosswalk: EU AI Act <> Solvency II")

st.markdown(
    "European insurers must comply with **both** EU AI Act (high-risk AI) and "
    "Solvency II (Article 41 - governance system, Article 44 - risk management). "
    "Overlapping requirements:"
)

crosswalk = [
    {
        "EU AI Act": "Art. 9 (Risk Management)",
        "Solvency II": "Art. 44 (Risk Management System)",
        "Joint implementation": "Drift monitoring + actuarial review cycle.",
    },
    {
        "EU AI Act": "Art. 13 (Transparency)",
        "Solvency II": "Art. 41 (Governance, key functions)",
        "Joint implementation": "Glass-Box explanations + actuarial sign-off.",
    },
    {
        "EU AI Act": "Art. 14 (Human Oversight)",
        "Solvency II": "Art. 41 (Fit and proper requirements)",
        "Joint implementation": "Threshold-based routing + qualified underwriter review.",
    },
]
st.table(crosswalk)

st.caption(
    "Mapping is illustrative. Production compliance requires legal review and "
    "Article 43 conformity assessment by accredited body."
)

st.header("Crosswalk: EU AI Act <> GDPR (EIPD)")
st.info(
    "High-risk AI duties sit next to GDPR Art. 35. Open **DPIA GDPR** in the sidebar "
    "for the Art. 35 pack (`gdpr_dpia_v1.json`). That document is a demonstration EIPD, "
    "not a notification to the AEPD."
)
st.page_link("pages/08_DPIA_GDPR.py", label="Open DPIA / EIPD (GDPR Art. 35)")
