"""
Streamlit Model Card — Porto Seguro Insurance Claim Prediction (official entrypoint).
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from utils.data_loaders import (
    audit_results_mtime,
    load_compliance_status,
    load_model_info,
    load_performance_metrics,
    performance_metrics_mtime,
)

st.set_page_config(
    page_title="Porto Seguro — Model Card",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
    }
    .benchmark-box {
        background-color: #e8f4fc;
        padding: 1rem 1.25rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin: 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<h1 class="main-header">📊 Porto Seguro — Insurance Claim Prediction Model Card</h1>',
    unsafe_allow_html=True,
)
st.markdown("---")

model_info = load_model_info()
metrics = load_performance_metrics(performance_metrics_mtime())
compliance = load_compliance_status(audit_results_mtime())

unified_report: dict = {}
for report_path in (Path("docs/compliance_report.json"), Path("docs/model_card.json")):
    if report_path.exists():
        try:
            unified_report = json.loads(report_path.read_text(encoding="utf-8"))
            break
        except Exception:
            pass

roc_auc = metrics.get("roc_auc", 0.0)
test_f1 = metrics.get("f1_score", 0.0)
optimal_threshold = metrics.get("optimal_threshold", 0.5)

st.header("Executive Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("ROC-AUC (hold-out test)", f"{roc_auc:.3f}")
col2.metric("F1 (optimal threshold)", f"{test_f1:.3f}")
col3.metric("Optimal threshold", f"{optimal_threshold:.3f}")
col4.metric("Compliance", compliance.get("overall", "N/A"))

st.markdown(
    f"""
    <div class="benchmark-box">
    <strong>Market benchmark (Kaggle Porto Seguro):</strong> on this highly imbalanced dataset
    (~96.4% no claim / ~3.6% with claim), a ROC-AUC of <strong>0.63–0.64</strong> on hold-out test
    is the realistic competitive range. Much higher values often indicate leakage or overfitting;
    values near 0.50 are equivalent to random chance.<br><br>
    <strong>This model:</strong> ROC-AUC = <strong>{roc_auc:.4f}</strong> (hold-out test 20% only, never mixed 595k).
    The primary metric is hold-out ROC-AUC; do not use AUC on train+test (inflates to ~0.645). F1 depends on the threshold (~{optimal_threshold:.3f}).
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Model")
c1, c2 = st.columns(2)
with c1:
    st.write(f"**Type:** {model_info.get('model_type', 'EBM')}")
    st.write(f"**Framework:** {model_info.get('framework', 'InterpretML')}")
    st.write(f"**Architecture:** {model_info.get('architecture', 'Polars + EBM')}")
    st.write(f"**Training date:** {model_info.get('training_date', 'N/A')}")
with c2:
    st.write("**Intended use:** claim probability for underwriting and pricing")
    st.write("**Data:** Porto Seguro Safe Driver (595,212 records, 57 features)")
    st.write("**Explainability:** native EBM (global, local, interactions)")

if unified_report:
    with st.expander("Unified report (reporting_generator)", expanded=False):
        perf = unified_report.get("performance_metrics", {})
        st.json(
            {
                "roc_auc": perf.get("roc_auc", roc_auc),
                "f1_score": perf.get("f1_score", test_f1),
                "compliance_standards": unified_report.get("report_metadata", {}).get(
                    "compliance_standards", []
                ),
            }
        )

st.markdown("---")
st.subheader("Navigation")
st.info(
    "Explore the sections in the sidebar: **Overview**, **Performance**, "
    "**Explainability**, **Compliance** (EU AI Act / Solvency II), **Drift Monitoring**, "
    "and **DPIA GDPR** (EIPD art. 35 RGPD)."
)

if Path("training_results.json").exists():
    st.caption("Metrics loaded from `training_results.json` (full pipeline, no subsampling).")
else:
    st.warning("Run `python run_training_full.py` to generate production metrics.")
