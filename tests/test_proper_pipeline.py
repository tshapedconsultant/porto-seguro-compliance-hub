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
    # Deterministic case: train median != test median so leakage would fail.
    train_df = pl.DataFrame(
        {
            "feature_1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "feature_2": [1.0, 2.0, None, 4.0, 5.0, 6.0],
            "cat_feature": [1, 2, None, 1, 2, 3],
            "target": [0, 1, 0, 1, 0, 1],
            "id": list(range(6)),
        }
    )
    test_df = pl.DataFrame(
        {
            "feature_1": [100.0, 200.0, 300.0],
            "feature_2": [10.0, 20.0, 30.0],
            "cat_feature": [1, 2, 1],
            "target": [0, 1, 0],
            "id": [6, 7, 8],
        }
    )

    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train_df)

    train_eng = fe.transform(train_df)
    test_eng = fe.transform(test_df)

    assert fe.trained, "Feature engineer should be trained"
    assert train_eng["feature_1"].null_count() == 0
    assert test_eng["feature_1"].null_count() == 0
    assert "feature_1_missing" in train_eng.columns
    assert "feature_1_missing" in test_eng.columns
    assert "cat_feature_freq" in train_eng.columns
    assert "cat_feature_freq" in test_eng.columns

    expected_train_median = train_df["feature_1"].median()
    assert fe.medians["feature_1"] == expected_train_median
    assert expected_train_median != test_df["feature_1"].median()

    # Always force nulls in test so transform imputation is exercised
    test_with_null = test_df.with_columns(pl.lit(None).alias("feature_1"))
    transformed = fe.transform(test_with_null)
    assert transformed["feature_1"][0] == expected_train_median
    assert transformed["feature_1"][0] != test_df["feature_1"].median()


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
    """Test that the pipeline prevents data leakage with forced train/test median gap."""
    train_df = pl.DataFrame(
        {
            "feature_1": list(range(80)),
            "feature_2": list(range(80, 160)),
            "target": [0, 1] * 40,
        }
    )
    test_df = pl.DataFrame(
        {
            "feature_1": list(range(1000, 1020)),
            "feature_2": list(range(2000, 2020)),
            "target": [0, 1] * 10,
        }
    )

    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train_df)

    expected_train_median = train_df["feature_1"].median()
    assert fe.medians["feature_1"] == expected_train_median
    assert expected_train_median != test_df["feature_1"].median()

    test_with_null = test_df.with_columns(pl.lit(None).alias("feature_1"))
    transformed = fe.transform(test_with_null)
    assert transformed["feature_1"][0] == expected_train_median
    assert transformed["feature_1"][0] != test_df["feature_1"].median()

