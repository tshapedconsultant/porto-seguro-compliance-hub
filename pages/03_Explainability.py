from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.optional_imports import OPTIONAL_MODULES
from utils.model_loader import get_cached_ebm_pipeline, get_cached_predictions
from utils.visualizations import create_feature_importance_chart

st.header("Model Explainability")
st.info("Native EBM explainability is primary; SHAP/LIME are optional when available.")

model_loaded = False
data_loaded = False
model = None
X_sample = None

try:
    model, _feature_engineer, model_loaded = get_cached_ebm_pipeline()
    X_all, y_all, data_ok = get_cached_predictions(sample_size=1000)
    if model_loaded and data_ok and X_all is not None:
        X_sample = X_all.head(10)
        data_loaded = True
except Exception as exc:
    st.warning(f"Model loading unavailable: {exc}")

st.subheader("Global Feature Importance")
if model_loaded and data_loaded:
    try:
        from src.models.explainability import explain_ebm_global

        global_exp = explain_ebm_global(model)
        fig = create_feature_importance_chart(global_exp.get("feature_importance", {}))
        st.success("✅ Using REAL feature importance from the loaded model.")
    except Exception as exc:
        st.warning(f"Using fallback importance: {exc}")
        fig = create_feature_importance_chart(None)
else:
    fig = create_feature_importance_chart(None)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Local Explanation")
sample_explanation = None

if model_loaded and data_loaded and X_sample is not None:
    try:
        from src.models.explainability import explain_ebm_local

        # Compatibility bridge: force Pandas before InterpretML inference
        X_local = X_sample.head(1)
        if hasattr(X_local, "to_pandas"):
            X_local = X_local.to_pandas()

        local_exp = explain_ebm_local(model, X_local)
        top_features = []

        # Scenario A: native InterpretML Explanation object (direct or wrapped)
        native_exp = local_exp
        if isinstance(local_exp, dict):
            native_exp = local_exp.get("explanation_object") or local_exp

        if hasattr(native_exp, "data"):
            data = native_exp.data(0)
            features_scores = list(zip(data["names"], data["scores"]))
            top_features = sorted(features_scores, key=lambda x: abs(x[1]), reverse=True)[:5]

        elif isinstance(local_exp, dict):
            explanations_list = (
                local_exp.get("local_explanations") or local_exp.get("explanations") or []
            )
            if isinstance(explanations_list, list) and explanations_list:
                first_exp = explanations_list[0] if isinstance(explanations_list[0], dict) else {}
                local_items = [(k, v) for k, v in first_exp.items() if isinstance(v, (int, float))]
                top_features = sorted(local_items, key=lambda x: abs(x[1]), reverse=True)[:5]
            else:
                st.error(
                    f"Returned dict missing expected keys. Available keys: {list(local_exp.keys())}"
                )
        else:
            st.error(f"Unrecognized explanation format. Type received: {type(local_exp)}")

        if top_features:
            sample_explanation = pd.DataFrame(
                {"Feature": [f[0] for f in top_features], "Contribution": [f[1] for f in top_features]}
            )
            st.success("✅ Using REAL local explanations from the loaded model.")
        elif sample_explanation is None:
            st.warning("No numeric feature contributions found for this record.")

    except Exception as exc:
        st.error(f"Could not generate real local explanation: {exc}")
else:
    st.warning("No model/data available for real local explanations.")

if sample_explanation is not None and not sample_explanation.empty:
    fig_local = px.bar(
        sample_explanation,
        x="Contribution",
        y="Feature",
        orientation="h",
        color="Contribution",
        color_continuous_scale="RdBu",
        title="Feature Contributions for Sample Prediction",
    )
    fig_local.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_local, use_container_width=True)

if model_loaded and data_loaded:
    feature_names = list(X_sample.columns) if X_sample is not None else None
    results = OPTIONAL_MODULES.comprehensive_explainability(model, X_sample.head(3), feature_names)
    methods = []
    if isinstance(results, dict):
        if results.get("shap", {}).get("available"):
            methods.append("SHAP")
        if results.get("lime", {}).get("available"):
            methods.append("LIME")
    if methods:
        st.info(f"Optional methods active: {', '.join(methods)}")
    else:
        st.info("SHAP/LIME inactive; native EBM explainability is active.")
