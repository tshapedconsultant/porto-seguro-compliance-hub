"""
Pytest configuration and fixtures
Part of Insurance Claim Prediction - Responsible AI Architecture

Keep top-level imports free of Polars/interpret so governance CI
(`tests/test_dpia_workspace.py`, `test_control_plane.py`, `test_import_surface.py`)
collects cleanly without ML deps.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_dataframe():
    """Create a sample Polars DataFrame for testing."""
    pl = pytest.importorskip("polars")
    np = pytest.importorskip("numpy")

    n_samples = 100
    data = {
        "feature_1": np.random.randn(n_samples),
        "feature_2": np.random.randn(n_samples),
        "feature_3": np.random.randn(n_samples),
        "target": np.random.randint(0, 2, n_samples),
        "id": range(n_samples),
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_dataframe_with_missing():
    """Create a sample DataFrame with missing values."""
    pl = pytest.importorskip("polars")

    data = {
        "feature_1": [1, 2, None, 4, 5],
        "feature_2": [1.0, None, 3.0, 4.0, 5.0],
        "target": [0, 1, 0, 1, 0],
    }
    return pl.DataFrame(data)
