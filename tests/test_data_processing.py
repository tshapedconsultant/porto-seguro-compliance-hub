"""
Test Data Processing Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import os
import tempfile

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.data_processing.load_data_polars import load_porto_seguro_data, validate_data_quality


def test_load_porto_seguro_data_with_sample():
    """Test loading data with sampling."""
    # Create a temporary CSV file for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create synthetic data
        n_samples = 1000
        n_features = 10
        data = {}
        for i in range(n_features):
            data[f"feature_{i}"] = np.random.randn(n_samples)
        data["target"] = np.random.randint(0, 2, n_samples)
        data["id"] = range(n_samples)
        
        df = pl.DataFrame(data)
        csv_path = os.path.join(tmpdir, "train.csv")
        df.write_csv(csv_path)
        
        # Test loading with sample
        loaded_df = load_porto_seguro_data(tmpdir, sample_size=100, random_seed=42)
        
        assert len(loaded_df) == 100
        assert "target" in loaded_df.columns
        assert len(loaded_df.columns) == n_features + 2  # features + target + id


@pytest.mark.skipif(not os.path.exists("train.csv"), reason="train.csv not found")
def test_load_porto_seguro_data_real():
    """Test loading real data if available."""
    if os.path.exists("train.csv"):
        df = load_porto_seguro_data(".", sample_size=100)
        assert len(df) > 0
        assert "target" in df.columns


def test_validate_data_quality():
    """Test data quality validation."""
    # Create test data with some missing values
    data = {
        "feature_1": [1, 2, None, 4, 5],
        "feature_2": [1.0, 2.0, 3.0, None, 5.0],
        "target": [0, 1, 0, 1, 0]
    }
    df = pl.DataFrame(data)
    
    quality_report = validate_data_quality(df, target_col="target")
    
    assert quality_report["total_records"] == 5
    assert "feature_1" in quality_report["missing_values"]
    assert "feature_2" in quality_report["missing_values"]
    assert "target" in quality_report["target_distribution"]
    assert "data_types" in quality_report


def test_validate_data_quality_target_distribution():
    """Test target distribution in quality validation."""
    data = {
        "feature_1": [1, 2, 3, 4, 5],
        "target": [0, 0, 0, 1, 1]
    }
    df = pl.DataFrame(data)
    
    quality_report = validate_data_quality(df, target_col="target")
    
    assert len(quality_report["target_distribution"]) > 0

