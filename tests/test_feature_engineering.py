"""
Test Feature Engineering Module
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.data_processing.feature_engineering import ResponsibleFeatureEngineer, get_stratified_split


def test_engineer_features_basic():
    """Test basic feature engineering using ResponsibleFeatureEngineer."""
    data = {
        "feature_1": [1, 2, None, 4, 5],
        "feature_2": [1.0, 2.0, None, 4.0, 5.0],
        "cat_feature": [1, 2, None, 1, 2],
        "target": [0, 1, 0, 1, 0],
        "id": [1, 2, 3, 4, 5]
    }
    df = pl.DataFrame(data)
    
    # Use proper fit/transform pattern
    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(df)  # Fit on same data for this test
    df_engineered = fe.transform(df)
    
    # Check that missing values are filled in numerical features
    assert df_engineered["feature_1"].null_count() == 0
    assert df_engineered["feature_2"].null_count() == 0
    
    # Check that missing flags are created
    assert "feature_1_missing" in df_engineered.columns
    assert "feature_2_missing" in df_engineered.columns
    
    # Check that target is preserved
    assert "target" in df_engineered.columns
    
    # Check that frequency encoding was applied to categorical
    assert "cat_feature_freq" in df_engineered.columns

def test_get_stratified_split():
    """Test stratified train-test split preparation."""
    data = {
        "feature_1": list(range(100)),
        "feature_2": list(range(100, 200)),
        "target": [0, 1] * 50,
        "id": list(range(100))
    }
    df = pl.DataFrame(data)
    
    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2, random_seed=42)
    
    # Check shapes
    assert len(train_df) + len(test_df) == 100
    assert "target" in train_df.columns
    assert "target" in test_df.columns
    assert "id" in train_df.columns
    assert "id" in test_df.columns


def test_get_stratified_split_proportions():
    """Test stratified train-test split proportions."""
    data = {
        "feature_1": list(range(1000)),
        "target": [0, 1] * 500
    }
    df = pl.DataFrame(data)
    
    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2, random_seed=42)
    
    # Check approximate proportions (allow small variance)
    assert abs(len(test_df) / 1000 - 0.2) < 0.05
    assert abs(len(train_df) / 1000 - 0.8) < 0.05

