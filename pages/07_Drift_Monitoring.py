"""
Drift monitoring page (Shadow Monitor demo).

Reference batch = training sample. Current batch = subsample with an intentional
change on `ps_car_13` to verify the KS monitor fires an alert.
"""

from __future__ import annotations

import json
from pathlib import Path

import plotly.express as px
import polars as pl
import streamlit as st

from src.monitoring.drift_monitoring import detect_data_drift, detect_model_drift
from utils.data_loaders import (
    load_performance_metrics,
    performance_metrics_mtime,
    resolve_shadow_monitor_paths,
)
from utils.visualizations import plot_executive_drift

DRIFT_DEMO_FEATURE = "ps_car_13"
DRIFT_DEMO_SCALE = 1.5
DRIFT_DEMO_SHIFT = 0.5
KS_ALERT_THRESHOLD = 0.1
MODEL_DRIFT_THRESHOLD = 0.05

REFERENCE_SAMPLE_SIZE = 5000
CURRENT_SAMPLE_SIZE = 1000
CURRENT_SAMPLE_SEED = 123

DRIFT_EVIDENCE_PATH = Path("docs/drift_monitoring_latest.json")


def _inject_ps_car_13_covariate_shift(df: pl.DataFrame) -> pl.DataFrame:
    """Apply x' = scale * x + shift on ps_car_13 — demo-only, to trigger KS alert."""
    if DRIFT_DEMO_FEATURE not in df.columns:
        return df
    return df.with_columns(
        (pl.col(DRIFT_DEMO_FEATURE) * DRIFT_DEMO_SCALE + DRIFT_DEMO_SHIFT).alias(DRIFT_DEMO_FEATURE)
    )


def _load_production_auc_pair(default_ref: float) -> tuple[float, float]:
    """Reference vs production ROC-AUC from persisted compliance gate evidence."""
    ref_auc = default_ref
    curr_auc = default_ref
    if DRIFT_EVIDENCE_PATH.exists():
        try:
            payload = json.loads(DRIFT_EVIDENCE_PATH.read_text(encoding="utf-8"))
            ref_auc = float(payload.get("reference_metrics", {}).get("roc_auc", ref_auc))
            curr_auc = float(payload.get("current_metrics", {}).get("roc_auc", curr_auc))
        except Exception:
            pass
    return ref_auc, curr_auc


st.header("Drift Monitoring (Shadow Monitor)")
st.info(
    "Comparison of **reference (training)** vs **simulated production** using Polars "
    "+ Kolmogorov–Smirnov test (`scipy`). **Model** drift alerts only on metric "
    "**degradation**, not improvements."
)

paths = resolve_shadow_monitor_paths()
metrics = load_performance_metrics(performance_metrics_mtime())

with st.spinner("Computing drift with Polars-native engine..."):
    try:
        from src.data_processing.load_data_polars import load_porto_seguro_data

        if not paths["train_csv"].exists():
            st.warning("`train.csv` not found.")
            st.stop()

        df_ref = load_porto_seguro_data(".", sample_size=REFERENCE_SAMPLE_SIZE)
        df_curr = df_ref.sample(n=CURRENT_SAMPLE_SIZE, seed=CURRENT_SAMPLE_SEED).clone()
        df_curr = _inject_ps_car_13_covariate_shift(df_curr)
    except Exception as exc:
        st.error(f"Error initializing drift: {exc}")
        st.stop()

drift_report = detect_data_drift(df_ref, df_curr, threshold=KS_ALERT_THRESHOLD)
feature_drifts = drift_report.get("feature_drifts", {})

if not feature_drifts:
    st.error("No numeric features found to compute drift.")
    st.stop()

rows = [
    {
        "Feature": name,
        "Drift_Score": info["drift_score"],
        "P_Value": info["p_value"],
        "Status": "Alert" if info["drift_detected"] else "Healthy",
    }
    for name, info in sorted(feature_drifts.items(), key=lambda x: x[1]["drift_score"], reverse=True)
][:10]

drift_df = pl.DataFrame(rows).to_pandas()
n_alerts = len([r for r in rows if r["Status"] == "Alert"])

col1, col2, col3 = st.columns(3)
col1.metric("Data Drift Status", "🔴 Critical" if n_alerts > 0 else "🟢 Healthy")
col2.metric("Global KS score (mean)", f"{drift_report.get('drift_score', 0):.3f}")
col3.metric("Reference / Current", f"n={df_ref.height} / n={df_curr.height}")

fig_drift = px.bar(
    drift_df,
    x="Drift_Score",
    y="Feature",
    orientation="h",
    color="Status",
    color_discrete_map={"Healthy": "#28a745", "Alert": "#dc3545"},
    title="Drift by feature (Kolmogorov–Smirnov)",
    text="Drift_Score",
)
fig_drift.add_vline(
    x=KS_ALERT_THRESHOLD,
    line_dash="dash",
    line_color="red",
    annotation_text=f"Threshold ({KS_ALERT_THRESHOLD})",
)
fig_drift.update_traces(texttemplate="%{text:.3f}", textposition="outside")
st.plotly_chart(fig_drift, use_container_width=True)

ps_car_drift = feature_drifts.get(DRIFT_DEMO_FEATURE)
if ps_car_drift and ps_car_drift.get("drift_detected"):
    st.info(
        f"**`{DRIFT_DEMO_FEATURE}` is red on purpose.** Only this variable was modified "
        f"in the simulated production batch (`× {DRIFT_DEMO_SCALE} + {DRIFT_DEMO_SHIFT}`) "
        f"to verify the monitor detects drift when something changes. "
        f"Other features are untouched — that is why they appear green. "
        f"This does not indicate a real model problem."
    )

st.markdown("---")
st.subheader("Model drift (degradation only)")

ref_perf = {
    "roc_auc": metrics.get("roc_auc", 0.638),
    "f1_score": metrics.get("f1_score", 0.118),
    "precision": metrics.get("precision", 0.082),
    "recall": metrics.get("recall", 0.212),
}

ref_auc, curr_auc = _load_production_auc_pair(ref_perf["roc_auc"])
model_live = detect_model_drift(
    {"roc_auc": ref_auc},
    {"roc_auc": curr_auc},
    threshold=MODEL_DRIFT_THRESHOLD,
)

curr_improved = {k: v * 1.02 for k, v in ref_perf.items()}
model_improved = detect_model_drift(ref_perf, curr_improved, threshold=MODEL_DRIFT_THRESHOLD)

curr_degraded = {k: v * 0.92 for k, v in ref_perf.items()}
model_degraded = detect_model_drift(ref_perf, curr_degraded, threshold=MODEL_DRIFT_THRESHOLD)

m1, m2, m3 = st.columns(3)
m1.metric(
    "Production monitor",
    "🔴 Alert" if model_live["drift_detected"] else "🟢 Healthy",
)
m2.metric("Scenario +2% improvement", "No alert" if not model_improved["drift_detected"] else "Alert")
m3.metric("Scenario −8% drop", "Alert" if model_degraded["drift_detected"] else "No alert")

st.plotly_chart(
    plot_executive_drift(ref_auc, curr_auc, threshold=MODEL_DRIFT_THRESHOLD),
    use_container_width=True,
)

if DRIFT_EVIDENCE_PATH.exists():
    st.caption(
        f"ROC-AUC pair loaded from `{DRIFT_EVIDENCE_PATH}` "
        f"(run `python run_production_monitor.py` to refresh)."
    )
else:
    st.caption(
        "No production drift evidence yet — showing hold-out baseline for both bars. "
        "Run `python run_production_monitor.py` to populate production metrics."
    )
