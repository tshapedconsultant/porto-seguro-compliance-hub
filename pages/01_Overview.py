from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.data_loaders import load_model_info

st.header("Model Overview")
model_info = load_model_info()

col1, col2 = st.columns(2)
with col1:
    st.subheader("Model Details")
    st.write("**Name:** Porto Seguro Insurance Claim Prediction")
    st.write(f"**Type:** {model_info.get('model_type', 'EBM')}")
    st.write(f"**Version:** {model_info.get('version', '1.0.0')}")
    st.write(f"**Framework:** {model_info.get('framework', 'Microsoft InterpretML')}")
    st.write(f"**Architecture:** {model_info.get('architecture', 'Polars + EBM')}")
    training_date = model_info.get("training_date", datetime.now().strftime("%Y-%m-%d"))
    st.write(f"**Training Date:** {training_date}")

with col2:
    st.subheader("Intended Use")
    st.write("**Primary use:** Predict claim probability for policyholders")
    st.write("- Risk assessment for underwriting")
    st.write("- Premium optimization")
    st.write("- Claim prediction for portfolio management")

st.markdown("---")
st.subheader("Training Data")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Dataset", "Porto Seguro")
col2.metric("Training Records", "595,212")
col3.metric("Features", "57")
col4.metric("Target", "Binary (0/1)")

st.markdown("---")
st.subheader("📊 About the Kaggle Competition")
with st.expander("View competition details", expanded=True):
    st.markdown(
        """
        **Porto Seguro's Safe Driver Prediction** is a Kaggle competition focused on claim prediction.
        - **Competition Type:** Binary Classification
        - **Evaluation Metric:** Normalized Gini Coefficient
        - **Dataset Size:** 595,212 samples and 57 features
        - **Challenge:** Class imbalance (~3.6% positive class)
        """
    )
