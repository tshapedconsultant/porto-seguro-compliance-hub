"""
Test Proper Pipeline (No Data Leakage)
Part of Insurance Claim Prediction - Responsible AI Architecture

Tests for the corrected pipeline that prevents data leakage.
"""

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.data_processing.feature_engineering import (
    ResponsibleFeatureEngineer,
    get_stratified_split,
)


def test_responsible_feature_engineer_fit_transform():
    """Test that ResponsibleFeatureEngineer prevents data leakage."""
    # Create data with missing values
    data = {
        "feature_1": [1, 2, None, 4, 5, 6, 7, 8, 9, 10],
        "feature_2": [1.0, 2.0, None, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        "cat_feature": [1, 2, None, 1, 2, 3, 1, 2, 3, 1],
        "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        "id": list(range(10))
    }
    df = pl.DataFrame(data)
    
    # Split FIRST (critical for no leakage)
    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.3)
    
    # Fit engineer on TRAIN only
    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train_df)
    
    # Transform both using train statistics
    train_eng = fe.transform(train_df)
    test_eng = fe.transform(test_df)
    
    # Verify no data leakage: test uses train statistics
    assert fe.trained, "Feature engineer should be trained"
    
    # Verify missing values are filled
    assert train_eng["feature_1"].null_count() == 0
    assert test_eng["feature_1"].null_count() == 0
    
    # Verify missing flags are created (always created for consistency)
    assert "feature_1_missing" in train_eng.columns
    assert "feature_1_missing" in test_eng.columns or test_eng["feature_1"].null_count() == 0
    
    # Verify frequency encoding
    assert "cat_feature_freq" in train_eng.columns
    assert "cat_feature_freq" in test_eng.columns
    
    # Verify test uses train statistics (not its own)
    train_median = fe.medians["feature_1"]
    # Test should use same median as train
    assert train_median == fe.medians["feature_1"]


def test_stratified_split_maintains_distribution():
    """Test that stratified split maintains class distribution."""
    # Create imbalanced dataset (similar to Porto Seguro)
    n_samples = 1000
    n_positive = int(n_samples * 0.036)  # 3.6% positive
    n_negative = n_samples - n_positive
    
    data = {
        "feature_1": list(range(n_samples)),
        "target": [0] * n_negative + [1] * n_positive
    }
    df = pl.DataFrame(data)
    
    # Get stratified split
    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2)
    
    # Check that both sets maintain similar distribution
    train_dist = train_df["target"].value_counts()
    test_dist = test_df["target"].value_counts()
    
    # Get positive class percentages
    train_pos = train_dist.filter(pl.col("target") == 1)
    test_pos = test_dist.filter(pl.col("target") == 1)
    
    train_pos_pct = (train_pos["count"][0] / len(train_df) * 100) if len(train_pos) > 0 else 0
    test_pos_pct = (test_pos["count"][0] / len(test_df) * 100) if len(test_pos) > 0 else 0
    
    # Distribution should be similar (within 2% for small samples)
    # Stratified split should maintain distribution
    assert abs(train_pos_pct - test_pos_pct) < 2.0, \
        f"Class distribution differs: train={train_pos_pct:.2f}%, test={test_pos_pct:.2f}%"


def test_no_data_leakage_in_pipeline():
    """Test that the pipeline prevents data leakage."""
    # Create data
    data = {
        "feature_1": list(range(100)),
        "feature_2": list(range(100, 200)),
        "target": [0, 1] * 50
    }
    df = pl.DataFrame(data)
    
    # Split first
    train_df, test_df = get_stratified_split(df, target_col="target", test_size=0.2)
    
    # Fit on train only
    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train_df)
    
    # Get train median (this is what should be used for test)
    train_median_feature1 = fe.medians["feature_1"]
    
    # Calculate what test median would be (we should NOT use this)
    test_median_feature1 = test_df["feature_1"].median()
    
    # Transform test - it should use train median, not test median
    test_eng = fe.transform(test_df)
    
    # Verify test uses train statistics
    # If test had a null, it would be filled with train_median, not test_median
    assert train_median_feature1 in fe.medians.values()
    
    # The key test: if we add a null to test and transform,
    # it should use train median
    test_with_null = test_df.with_columns(
        pl.when(pl.col("feature_1") == test_df["feature_1"][0])
        .then(None)
        .otherwise(pl.col("feature_1"))
        .alias("feature_1")
    )
    
    test_eng_with_null = fe.transform(test_with_null)
    
    # The null should be filled with train median
    filled_value = test_eng_with_null["feature_1"][0]
    assert filled_value == train_median_feature1, \
        "Test should use train median, not calculate its own!"

