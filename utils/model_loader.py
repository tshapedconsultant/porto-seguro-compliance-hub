"""
Cached model/pipeline helpers for Streamlit pages.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from utils.data_loaders import resolve_shadow_monitor_paths


@st.cache_resource(show_spinner=False)
def get_cached_ebm_pipeline():
    """Single source of truth for loading and caching the EBM pipeline."""
    try:
        from src.models.ebm_train import load_ebm_pipeline

        paths = resolve_shadow_monitor_paths()
        if paths["model_path"].exists() and paths["feature_engineer_path"].exists():
            model, feature_engineer = load_ebm_pipeline(
                model_path=str(paths["model_path"]),
                feature_engineer_path=str(paths["feature_engineer_path"]),
            )
            return model, feature_engineer, True
        return None, None, False
    except Exception as exc:
        st.error(f"Error loading model: {exc}")
        return None, None, False


@st.cache_data
def compute_cached_cv_metrics(
    model_mtime: float,
    feature_engineer_mtime: float,
    train_mtime: float,
    sample_size: int = 10000,
    n_splits: int = 3,
):
    """Compute CV metrics and invalidate cache when artifacts change."""
    _ = (model_mtime, feature_engineer_mtime, train_mtime)

    from src.data_processing.load_data_polars import load_porto_seguro_data
    from src.models.evaluation import stratified_cross_validation

    model, feature_engineer, is_loaded = get_cached_ebm_pipeline()
    if not is_loaded:
        raise RuntimeError("Model pipeline could not be loaded for CV.")

    df = load_porto_seguro_data(".", sample_size=sample_size)
    df_engineered = feature_engineer.transform(df)
    feature_cols = [col for col in df_engineered.columns if col not in ["id", "target"]]
    X_pl = df_engineered.select(feature_cols)
    y = df_engineered.select(["target"]).to_series()
    # CV still needs numpy matrix for sklearn; build via short-lived bridge per fold internally
    X_np = X_pl.to_numpy()
    y_np = y.to_numpy()
    return stratified_cross_validation(model, X_np, y_np, n_splits=n_splits)


def get_artifact_mtimes():
    """Get artifact mtimes to control cache invalidation."""
    paths = resolve_shadow_monitor_paths()
    if not (
        paths["model_path"].exists()
        and paths["feature_engineer_path"].exists()
        and paths["train_csv"].exists()
    ):
        return None
    return {
        "model_mtime": paths["model_path"].stat().st_mtime,
        "feature_engineer_mtime": paths["feature_engineer_path"].stat().st_mtime,
        "train_mtime": paths["train_csv"].stat().st_mtime,
    }


@st.cache_data(show_spinner=False)
def get_cached_predictions(sample_size: int = 1000):
    """Generate cached transformed samples for explainability."""
    try:
        from src.data_processing.load_data_polars import load_porto_seguro_data

        model, feature_engineer, is_loaded = get_cached_ebm_pipeline()
        if is_loaded and Path("train.csv").exists():
            df = load_porto_seguro_data(".", sample_size=sample_size)
            df_engineered = feature_engineer.transform(df)
            feature_cols = [col for col in df_engineered.columns if col not in ["id", "target"]]
            X = df_engineered.select(feature_cols)
            y = df_engineered.select("target").to_series() if "target" in df_engineered.columns else None
            return X, y, True
        return None, None, False
    except Exception:
        return None, None, False
