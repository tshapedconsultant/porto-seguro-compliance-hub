"""
Business Context - How model metrics translate to underwriting decisions.
Explains Precision, Recall, ROC-AUC, and threshold in operational terms.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from utils.data_loaders import (
    load_performance_metrics,
    performance_metrics_mtime,
)

metrics = load_performance_metrics(performance_metrics_mtime())
roc_auc = metrics.get("roc_auc", 0.5)
precision = metrics.get("precision", 0.0)
recall = metrics.get("recall", 0.0)
f1 = metrics.get("f1_score", 0.0)
threshold = metrics.get("optimal_threshold", 0.5)

_predictions_path = Path("docs/test_predictions.json")
base_rate_real = 0.036
if _predictions_path.exists():
    try:
        with open(_predictions_path, "r", encoding="utf-8") as f:
            base_rate_real = float(json.load(f)["base_rate"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass

st.title("💼 Business Context - Insurance Underwriting")
st.markdown(
    f"How do ROC-AUC **{roc_auc:.3f}**, Precision **{precision:.1%}** and Recall "
    f"**{recall:.1%}** translate to real underwriting decisions? "
    "This page answers without jargon."
)
st.markdown("---")

# --- Section 1: The base rate problem ---
st.header("1. The base rate problem")
st.markdown(
    f"""
    Porto Seguro's claim rate is **{base_rate_real:.1%}** of policies in the hold-out
    test set. That means a "model" that predicts NO CLAIM for every policy is
    **{(1 - base_rate_real):.1%} accurate** but useless.

    Our model's job is not to be accurate in absolute terms. It is to
    **concentrate human review** where claims are most likely.
    """
)

col1, col2, col3 = st.columns(3)
col1.metric(
    "Portfolio base rate",
    f"{base_rate_real:.2%}",
    help="Claims per 100 policies in the test set",
)
col2.metric("Model precision", f"{precision:.1%}", help="Claims per 100 model alerts")
col3.metric(
    "Concentration factor",
    f"{precision / base_rate_real:.1f}×" if precision > 0 and base_rate_real > 0 else "N/A",
    help="How much denser our alert list is vs random sampling",
)

st.info(
    f"**Interpretation:** A randomly sampled list of 100 policies contains "
    f"~{base_rate_real * 100:.1f} claims. Our model's top-scored 100 policies "
    f"contain ~{precision * 100:.0f} claims. That is "
    f"**{precision / base_rate_real:.1f} times denser** — the operational value."
)

f1_default = metrics.get("f1_score_default_threshold")
if f1_default is not None:
    f1_col1, f1_col2 = st.columns(2)
    f1_col1.metric(
        "F1 @ threshold 0.5 (default)",
        f"{f1_default:.3f}",
        help="Hold-out test with sklearn default threshold — same basis as CV / old carousel metrics.",
    )
    f1_col2.metric(
        "F1 @ optimal threshold",
        f"{f1:.3f}",
        help=f"Hold-out test with train-tuned threshold {threshold:.3f} (`test_f1` in training_results.json).",
    )
    st.caption(
        f"The metrics carousel once showed **F1 ≈ 0** because it used threshold **0.5** on "
        f"**{base_rate_real:.1%}** positives. The exact hold-out value is **F1 = {f1_default:.3f}** "
        f"(`test_f1_default`). "
        f"ROC-AUC **{roc_auc:.3f}** still shows ranking skill; at threshold **{threshold:.3f}**, "
        f"operational F1 is **{f1:.3f}**. Use Section 5 to explore other thresholds."
    )

# --- Section 2: Operational decisions ---
st.header("2. Operational decisions per threshold")

st.markdown(
    f"""
    The optimal F1 threshold ({threshold:.3f}) maximizes balance between
    catching claims and minimizing false alerts. But the right threshold
    depends on the business decision being made.
    """
)

decisions = [
    {
        "Decision": "Pricing (premium calculation)",
        "Recommended": "Calibrated probabilities (Platt or isotonic)",
        "Why": "Binary thresholds lose information; pricing needs continuous risk score.",
    },
    {
        "Decision": "Underwriting review queue",
        "Recommended": f"Threshold {threshold:.3f} (F1-optimal)",
        "Why": "Balances claim capture rate vs false review cost.",
    },
    {
        "Decision": "Auto-approval (low-risk fast lane)",
        "Recommended": "Threshold 0.02 (very low)",
        "Why": "Only auto-approve policies where claim probability is near base rate.",
    },
    {
        "Decision": "Auto-decline (high-risk gate)",
        "Recommended": "Threshold 0.20+ (high)",
        "Why": "Auto-decline only on strong signals; require human review for borderline.",
    },
]
st.table(decisions)

# --- Section 3: Cost-benefit framing ---
st.header("3. Cost-benefit framing")

with st.expander("How to set the operational threshold in a real insurer", expanded=False):
    st.markdown(
        """
        In production, the threshold is not chosen by F1-optimal. It is chosen
        by minimizing **expected loss**:

```
        Expected Loss(t) = FP(t) × cost_of_review + FN(t) × cost_of_missed_claim
```

        Where:
        - `cost_of_review`: ~€30-50 per policy for manual underwriting review.
        - `cost_of_missed_claim`: average claim payout (€2,000-€10,000 in motor).

        With these numbers, the operational threshold tends to be **higher than
        F1-optimal**, trading recall for fewer false alerts. The exact value
        depends on the insurer's portfolio composition and risk appetite.

        This case study reports F1-optimal because we lack real cost data, but
        the framework scales to whatever cost matrix the deployment requires.
        """
    )

# --- Section 4: What this is NOT ---
st.header("4. What this model is NOT")
st.warning(
    "This is a **risk ranking model**, not a claim certainty predictor. "
    "It identifies relative likelihood within the portfolio, not absolute "
    "probability of claim. For pricing, calibrate before use."
)

st.markdown(
    f"""
    **Risks if misused:**
    - ❌ Using raw probabilities as discount factors in premium pricing.
    - ❌ Auto-declining policies on raw score without human review.
    - ❌ Treating Recall {recall:.1%} as "captures {recall:.1%} of all claims" - it captures
      that fraction *within the model's alert volume*, not in the full portfolio.
    """
)

st.caption(
    f"Metrics loaded from `training_results.json` · "
    f"ROC-AUC test hold-out: {roc_auc:.3f} · F1: {f1:.3f} · threshold: {threshold:.3f}"
)

# --- Section 5: Interactive threshold exploration ---
st.markdown("---")
st.header("5. Threshold optimization · Underwriting impact")

st.markdown(
    "Move the slider to explore how the decision threshold affects model "
    "behavior and operational volume. The F1-optimal threshold "
    f"({threshold:.3f}) is marked in red."
)

predictions_path = _predictions_path

if not predictions_path.exists():
    st.warning(
        "Predictions file not found. Run `python analyze_results.py` "
        "to generate `docs/test_predictions.json`."
    )
else:
    import numpy as np
    import plotly.graph_objects as go
    from sklearn.metrics import f1_score, precision_score, recall_score

    @st.cache_data
    def _load_predictions(path_str: str, mtime: float):
        """Load precomputed test predictions. Cache invalidates by mtime."""
        with open(path_str, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            np.array(data["y_true"], dtype=np.int8),
            np.array(data["y_prob"], dtype=np.float32),
            data["n_test"],
            data["base_rate"],
        )

    mtime = predictions_path.stat().st_mtime
    y_true, y_prob, n_test, base_rate = _load_predictions(
        str(predictions_path), mtime
    )

    selected_threshold = st.slider(
        "Decision threshold",
        min_value=0.01,
        max_value=0.50,
        value=float(threshold),
        step=0.005,
        format="%.3f",
        help="Move to see how the threshold affects metrics and policy volume.",
    )

    y_pred = (y_prob >= selected_threshold).astype(int)
    cur_f1 = f1_score(y_true, y_pred, zero_division=0)
    cur_precision = precision_score(y_true, y_pred, zero_division=0)
    cur_recall = recall_score(y_true, y_pred, zero_division=0)
    n_alerts = int(y_pred.sum())
    n_true_positives = int(((y_pred == 1) & (y_true == 1)).sum())
    n_false_positives = int(((y_pred == 1) & (y_true == 0)).sum())
    n_missed_claims = int(((y_pred == 0) & (y_true == 1)).sum())

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("F1 @ threshold", f"{cur_f1:.3f}")
    mcol2.metric("Precision @ threshold", f"{cur_precision:.3f}")
    mcol3.metric("Recall @ threshold", f"{cur_recall:.3f}")
    mcol4.metric("Policies flagged", f"{n_alerts:,}")

    ocol1, ocol2, ocol3 = st.columns(3)
    ocol1.metric(
        "True alerts (real claims caught)",
        f"{n_true_positives:,}",
        help=f"Of {int(y_true.sum())} total claims in test set",
    )
    ocol2.metric(
        "False alerts (manual review cost)",
        f"{n_false_positives:,}",
        help="Policies flagged but not actually claims",
    )
    ocol3.metric(
        "Missed claims",
        f"{n_missed_claims:,}",
        help="Real claims the model did not flag",
    )

    st.markdown("### Curves over threshold range")

    thresholds_grid = np.linspace(0.01, 0.5, 60)
    f1_curve = []
    prec_curve = []
    rec_curve = []
    n_flagged_curve = []
    for t in thresholds_grid:
        yp = (y_prob >= t).astype(int)
        f1_curve.append(f1_score(y_true, yp, zero_division=0))
        prec_curve.append(precision_score(y_true, yp, zero_division=0))
        rec_curve.append(recall_score(y_true, yp, zero_division=0))
        n_flagged_curve.append(int(yp.sum()))

    fig_f1 = go.Figure()
    fig_f1.add_trace(
        go.Scatter(
            x=thresholds_grid,
            y=f1_curve,
            mode="lines",
            name="F1 score",
            line=dict(color="#1f77b4", width=3),
        )
    )
    fig_f1.add_vline(
        x=threshold,
        line=dict(color="red", width=2, dash="dash"),
        annotation_text=f"F1-optimal ({threshold:.3f})",
        annotation_position="top right",
    )
    fig_f1.add_vline(
        x=selected_threshold,
        line=dict(color="green", width=2, dash="dot"),
        annotation_text=f"Current ({selected_threshold:.3f})",
        annotation_position="top left",
    )
    fig_f1.update_layout(
        title="F1 score across decision thresholds",
        xaxis_title="Threshold",
        yaxis_title="F1 score",
        height=350,
        showlegend=False,
    )
    st.plotly_chart(fig_f1, use_container_width=True)

    fig_pr = go.Figure()
    fig_pr.add_trace(
        go.Scatter(
            x=thresholds_grid,
            y=prec_curve,
            mode="lines",
            name="Precision",
            line=dict(color="#2ca02c", width=2),
        )
    )
    fig_pr.add_trace(
        go.Scatter(
            x=thresholds_grid,
            y=rec_curve,
            mode="lines",
            name="Recall",
            line=dict(color="#ff7f0e", width=2),
        )
    )
    fig_pr.add_vline(
        x=selected_threshold,
        line=dict(color="green", width=2, dash="dot"),
    )
    fig_pr.update_layout(
        title="Precision vs Recall trade-off",
        xaxis_title="Threshold",
        yaxis_title="Score",
        height=350,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    st.plotly_chart(fig_pr, use_container_width=True)

    fig_vol = go.Figure()
    fig_vol.add_trace(
        go.Scatter(
            x=thresholds_grid,
            y=n_flagged_curve,
            mode="lines",
            name="Policies flagged for review",
            line=dict(color="#9467bd", width=3),
            fill="tozeroy",
        )
    )
    fig_vol.add_vline(
        x=selected_threshold,
        line=dict(color="green", width=2, dash="dot"),
        annotation_text=f"{n_alerts:,} policies @ current threshold",
        annotation_position="top right",
    )
    fig_vol.update_layout(
        title=f"Underwriting volume impact (test set, n={n_test:,})",
        xaxis_title="Threshold",
        yaxis_title="Number of policies flagged",
        height=350,
        showlegend=False,
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    flagged_pct = (n_alerts / n_test) * 100
    if selected_threshold < 0.02:
        narrative_msg = (
            f"At very low thresholds, the model flags {flagged_pct:.1f}% of all "
            f"policies. Operationally unmanageable: review queue would overflow."
        )
        narrative_type = "warning"
    elif selected_threshold > 0.20:
        narrative_msg = (
            f"At high thresholds, the model flags only {flagged_pct:.1f}% of policies, "
            f"but misses {n_missed_claims:,} real claims. Recall drops sharply."
        )
        narrative_type = "warning"
    else:
        narrative_msg = (
            f"At threshold {selected_threshold:.3f}, the model flags {flagged_pct:.1f}% "
            f"of policies for manual review. Of those, {n_true_positives:,} are real "
            f"claims and {n_false_positives:,} are false alerts. Operationally balanced "
            f"for an underwriting team."
        )
        narrative_type = "info"

    if narrative_type == "warning":
        st.warning(narrative_msg)
    else:
        st.info(narrative_msg)

    st.caption(
        f"Test set: {n_test:,} policies · Base rate: {base_rate:.3%} · "
        f"Predictions loaded from `docs/test_predictions.json`. "
        f"Regenerate with `python analyze_results.py`."
    )
