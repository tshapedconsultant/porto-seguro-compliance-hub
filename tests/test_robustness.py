"""
Robustness tests for feature engineering and inference edge cases.
Synthetic data only — no private train.csv required.
"""

from pathlib import Path
import tempfile

import numpy as np
import pytest

pytest.importorskip("polars")
import polars as pl

from src.data_processing.feature_engineering import ResponsibleFeatureEngineer

try:
    from src.models.ebm_train import train_ebm_pipeline, predict_with_pipeline

    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False


def _fit_simple_fe():
    train = pl.DataFrame(
        {
            "feature_1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "feature_2": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "cat_feature": [1, 1, 2, 2, 3, 3],
            "target": [0, 1, 0, 1, 0, 1],
            "id": list(range(6)),
        }
    )
    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train)
    return fe, train


def test_massive_missingness_imputed_with_train_stats():
    fe, train = _fit_simple_fe()
    messy = pl.DataFrame(
        {
            "feature_1": [None, None, None, None],
            "feature_2": [None, None, None, None],
            "cat_feature": [1, None, 99, 2],
            "target": [0, 1, 0, 1],
            "id": [10, 11, 12, 13],
        }
    )
    out = fe.transform(messy)
    assert out["feature_1"].null_count() == 0
    assert out["feature_2"].null_count() == 0
    assert (out["feature_1"] == fe.medians["feature_1"]).all()
    assert "feature_1_missing" in out.columns
    assert out["feature_1_missing"].sum() == 4


def test_outliers_do_not_break_transform():
    fe, _ = _fit_simple_fe()
    extreme = pl.DataFrame(
        {
            "feature_1": [1e9, -1e9, 0.0],
            "feature_2": [1e8, -1e8, 0.0],
            "cat_feature": [1, 2, 3],
            "target": [0, 1, 0],
            "id": [20, 21, 22],
        }
    )
    out = fe.transform(extreme)
    assert out.height == 3
    assert out["feature_1"].null_count() == 0


def test_oor_and_extra_columns_ignored_safely():
    fe, _ = _fit_simple_fe()
    with_extra = pl.DataFrame(
        {
            "feature_1": [1.0, 2.0],
            "feature_2": [3.0, 4.0],
            "cat_feature": [1, 2],
            "unknown_col": [99.0, 100.0],
            "target": [0, 1],
            "id": [30, 31],
        }
    )
    out = fe.transform(with_extra)
    assert "unknown_col" in out.columns
    assert out["feature_1"].null_count() == 0


def test_duplicate_ids_allowed_through_transform():
    fe, _ = _fit_simple_fe()
    dup = pl.DataFrame(
        {
            "feature_1": [1.0, 2.0, 3.0],
            "feature_2": [1.0, 2.0, 3.0],
            "cat_feature": [1, 1, 2],
            "target": [0, 1, 0],
            "id": [1, 1, 1],
        }
    )
    out = fe.transform(dup)
    assert out.height == 3
    assert out["id"].n_unique() == 1


def test_dtype_cast_friendly_numeric_strings_not_required():
    """Numeric columns stay numeric after fit; float inputs accepted."""
    fe, _ = _fit_simple_fe()
    as_float = pl.DataFrame(
        {
            "feature_1": pl.Series([1, 2], dtype=pl.Float32),
            "feature_2": pl.Series([3, 4], dtype=pl.Int64),
            "cat_feature": [1, 2],
            "target": [0, 1],
            "id": [40, 41],
        }
    )
    out = fe.transform(as_float)
    assert out["feature_1"].null_count() == 0


@pytest.mark.skipif(not INTERPRET_AVAILABLE, reason="interpret package not installed")
def test_prediction_with_shuffled_column_order():
    rng = np.random.default_rng(3)
    n = 400
    data = {f"feature_{i}": rng.normal(0, 1, n) for i in range(4)}
    data["target"] = (data["feature_0"] + rng.normal(0, 0.4, n) > 0).astype(int)
    data["id"] = np.arange(n)
    df = pl.DataFrame(data)

    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as art_dir:
        df.write_csv(Path(tmpdir) / "train.csv")
        results = train_ebm_pipeline(
            data_path=tmpdir,
            target_col="target",
            test_size=0.25,
            random_seed=3,
            hyperparameters={"max_rounds": 40, "interactions": 1, "outer_bags": 2},
            artifacts_dir=art_dir,
            write_legacy_copies=False,
            perform_cv=False,
            perform_adversarial=False,
        )

        new_data = pl.DataFrame(
            {
                "feature_3": rng.normal(0, 1, 8),
                "id": np.arange(8),
                "feature_0": rng.normal(0, 1, 8),
                "feature_2": rng.normal(0, 1, 8),
                "feature_1": rng.normal(0, 1, 8),
            }
        )
        ordered = new_data.select(["id", "feature_0", "feature_1", "feature_2", "feature_3"])
        shuffled = new_data.select(["feature_3", "id", "feature_0", "feature_2", "feature_1"])

        pred_a = predict_with_pipeline(results["model"], results["feature_engineer"], ordered)
        pred_b = predict_with_pipeline(results["model"], results["feature_engineer"], shuffled)
        np.testing.assert_allclose(pred_a["probabilities"], pred_b["probabilities"], rtol=1e-6, atol=1e-6)
