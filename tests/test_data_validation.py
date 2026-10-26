"""
Test Data Validation Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.data_processing.data_validation import detect_potential_bias, validate_data_quality


def test_validate_data_quality_comprehensive():
    """Test comprehensive data quality validation."""
    data = {
        "feature_1": [1, 2, None, 4, 5, 6, 7, 8, 9, 10],
        "feature_2": [1.0] * 10,  # Constant feature
        "feature_3": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "target": [0] * 9 + [1]  # Imbalanced
    }
    df = pl.DataFrame(data)
    
    quality_report = validate_data_quality(df, target_col="target")
    
    assert "total_records" in quality_report
    assert "total_features" in quality_report
    assert "missing_values" in quality_report
    assert "target_distribution" in quality_report
    assert "quality_score" in quality_report
    assert "warnings" in quality_report
    
    assert quality_report["total_records"] == 10
    assert quality_report["total_features"] == 4


def test_validate_data_quality_class_imbalance():
    """Test detection of class imbalance."""
    data = {
        "feature_1": list(range(100)),
        "target": [0] * 95 + [1] * 5  # Severe imbalance
    }
    df = pl.DataFrame(data)
    
    quality_report = validate_data_quality(df, target_col="target")
    
    # Should detect severe imbalance
    assert len(quality_report["warnings"]) > 0
    assert any("imbalance" in warning.lower() for warning in quality_report["warnings"])


def test_detect_potential_bias_constant_features():
    """Test detection of constant features."""
    data = {
        "constant_feature": [1] * 100,
        "varying_feature": list(range(100)),
        "binary_feature": [0] * 99 + [1]
    }
    df = pl.DataFrame(data)
    
    bias_report = detect_potential_bias(df, ["constant_feature", "varying_feature", "binary_feature"])
    
    assert "constant_features" in bias_report
    assert "constant_feature" in bias_report["constant_features"]


def test_detect_potential_bias_low_variance():
    """Test detection of low variance features."""
    # Create data with extreme imbalance (0.5% in one class, which is < 1% threshold)
    data = {
        "extreme_imbalance": [0] * 199 + [1],  # 0.5% in one class (200 total)
        "normal": [0, 1] * 100  # 50/50 split (200 total to match length)
    }
    df = pl.DataFrame(data)
    
    bias_report = detect_potential_bias(df, ["extreme_imbalance", "normal"])
    
    assert "low_variance_features" in bias_report
    # Should detect extreme imbalance feature (0.5% < 1% threshold)
    assert len(bias_report["low_variance_features"]) > 0

