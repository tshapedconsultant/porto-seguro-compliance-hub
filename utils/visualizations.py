"""
Plotly visualization utilities for Streamlit pages.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def create_feature_importance_chart(feature_importance_data: dict | None):
    if not feature_importance_data:
        feature_importance_data = {
            "ps_ind_03": 0.045,
            "ps_ind_15": 0.038,
            "ps_reg_03": 0.032,
            "ps_car_13": 0.028,
            "ps_ind_05_cat": 0.025,
            "ps_calc_01": 0.022,
            "ps_ind_17_bin": 0.020,
            "ps_car_07_cat": 0.018,
            "ps_calc_14": 0.015,
            "ps_car_01_cat": 0.012,
        }

    df = pd.DataFrame(
        {"Feature": list(feature_importance_data.keys()), "Importance": list(feature_importance_data.values())}
    ).sort_values("Importance", ascending=True)

    fig = px.bar(
        df,
        x="Importance",
        y="Feature",
        orientation="h",
        title="Top 10 Feature Importance (Global Explanation)",
        labels={"Importance": "Feature Importance Score", "Feature": "Feature Name"},
        color="Importance",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=500, showlegend=False, xaxis_title="Importance Score", yaxis_title="")
    return fig


def create_performance_metrics_chart(metrics: dict):
    candidates = [
        ("ROC-AUC", metrics.get("roc_auc")),
        ("F1-Score", metrics.get("f1_score")),
        ("Precision", metrics.get("precision")),
        ("Recall", metrics.get("recall")),
        ("Accuracy", metrics.get("accuracy")),
    ]
    metric_names = []
    metric_values = []
    for name, value in candidates:
        if value is None:
            continue
        metric_names.append(name)
        metric_values.append(float(value))

    if not metric_values:
        metric_names = ["ROC-AUC", "F1-Score", "Precision", "Recall"]
        metric_values = [0.0, 0.0, 0.0, 0.0]

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=metric_names,
            y=metric_values,
            marker_color=colors[: len(metric_values)],
            text=[f"{value:.3f}" for value in metric_values],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Model Performance Metrics",
        xaxis_title="Metric",
        yaxis_title="Score",
        yaxis_range=[0, 1],
        height=400,
        showlegend=False,
    )
    return fig


def create_confusion_matrix_heatmap(cm=None):
    """
    Build a 2×2 heatmap from threshold_optimization_results.json format or a nested list.

    Expected dict keys: tn, fp, fn, tp (sklearn layout: [[tn, fp], [fn, tp]]).
    """
    if cm is None:
        return None

    if isinstance(cm, dict):
        tn = int(cm.get("tn", 0))
        fp = int(cm.get("fp", 0))
        fn = int(cm.get("fn", 0))
        tp = int(cm.get("tp", 0))
        cm_array = np.array([[tn, fp], [fn, tp]])
        text = [[f"TN<br>{tn:,}", f"FP<br>{fp:,}"], [f"FN<br>{fn:,}", f"TP<br>{tp:,}"]]
    else:
        cm_array = np.array(cm)
        text = [[f"{int(v):,}" for v in row] for row in cm_array]

    fig = go.Figure(
        data=go.Heatmap(
            z=cm_array,
            x=["Predicted: No Claim (0)", "Predicted: Claim (1)"],
            y=["Actual: No Claim (0)", "Actual: Claim (1)"],
            text=text,
            texttemplate="%{text}",
            hovertemplate="Count: %{z:,}<extra></extra>",
            colorscale="Blues",
            showscale=True,
        )
    )
    fig.update_layout(
        title="Confusion Matrix (hold-out test, optimal threshold)",
        height=420,
        yaxis=dict(autorange="reversed"),
    )
    return fig


def plot_executive_drift(
    reference_auc: float,
    current_auc: float,
    threshold: float = 0.05,
):
    """
    Executive bar chart: training baseline vs production ROC-AUC.
    Highlights alert when relative drop exceeds the degradation threshold.
    """
    degradation = reference_auc - current_auc
    relative_drop = (degradation / reference_auc) if reference_auc > 0 else 0.0
    is_alert = relative_drop > threshold and current_auc < reference_auc
    current_color = "#d13438" if is_alert else "#0078d4"

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=["Baseline (Training)"],
            y=[reference_auc],
            name="Reference",
            marker_color="#a6a6a6",
            text=[f"{reference_auc:.4f}"],
            textposition="auto",
        )
    )
    fig.add_trace(
        go.Bar(
            x=["Current (Production)"],
            y=[current_auc],
            name="Production",
            marker_color=current_color,
            text=[f"{current_auc:.4f}"],
            textposition="auto",
        )
    )

    safety_limit = reference_auc * (1 - threshold)
    fig.add_hline(
        y=safety_limit,
        line_dash="dot",
        line_color="#d13438",
        annotation_text=f"Alert limit (-{threshold * 100:.0f}%)",
        annotation_position="bottom right",
    )

    y_min = min(0.5, current_auc - 0.1, safety_limit - 0.02)
    y_max = max(reference_auc, current_auc) + 0.05
    fig.update_layout(
        title="Model Drift (Degradation Monitoring)",
        yaxis_title="ROC-AUC Score",
        yaxis_range=[y_min, y_max],
        template="plotly_white",
        showlegend=False,
        height=400,
        bargap=0.35,
    )
    return fig
