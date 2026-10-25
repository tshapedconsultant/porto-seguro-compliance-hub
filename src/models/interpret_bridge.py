"""
Last-millisecond bridge: Polars feature matrices -> InterpretML (pandas/numpy only at predict/fit).
"""

from __future__ import annotations

import gc
from typing import Any, Sequence, Tuple

import numpy as np
import polars as pl

DEFAULT_DROP_COLS: Tuple[str, ...] = ("target", "id")


def feature_matrix_for_ebm(
    df_pl: pl.DataFrame,
    drop_cols: Sequence[str] = DEFAULT_DROP_COLS,
) -> np.ndarray:
    """Convert Polars features to numpy for EBM; caller must not retain pandas intermediates."""
    cols = [c for c in df_pl.columns if c not in drop_cols]
    return df_pl.select(cols).to_numpy()


def predict_proba_ebm(
    model: Any,
    df_pl: pl.DataFrame,
    drop_cols: Sequence[str] = DEFAULT_DROP_COLS,
) -> np.ndarray:
    """Run predict_proba with a single short-lived pandas bridge, then free RAM."""
    import pandas as pd

    cols = [c for c in df_pl.columns if c not in drop_cols]
    X_pd = df_pl.select(cols).to_pandas()
    expected = getattr(model, "feature_names_in_", None)
    if expected is not None:
        for name in expected:
            if name not in X_pd.columns:
                X_pd[name] = 0.0
        X_pd = X_pd[list(expected)]
    try:
        return np.asarray(model.predict_proba(X_pd)[:, 1], dtype=np.float64)
    finally:
        del X_pd
        gc.collect()


def fit_ebm(
    model: Any,
    X_pl: pl.DataFrame,
    y: np.ndarray | pl.Series,
    drop_cols: Sequence[str] = DEFAULT_DROP_COLS,
) -> Any:
    """Fit EBM with pandas bridge only at fit time."""
    import pandas as pd

    cols = [c for c in X_pl.columns if c not in drop_cols]
    X_pd = X_pl.select(cols).to_pandas()
    y_arr = y.to_numpy() if isinstance(y, pl.Series) else np.asarray(y).ravel()
    try:
        model.fit(X_pd, y_arr)
        return model
    finally:
        del X_pd
        gc.collect()
