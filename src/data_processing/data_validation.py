"""
Data Validation Module — Polars-native quality and bias signal detection.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import polars as pl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MISSINGNESS_ALERT_PCT = 50.0
HIGH_MISSING_PCT = 10.0
LOW_CLASS_PCT = 1.0


def validate_data_quality(df: pl.DataFrame, target_col: str = "target") -> Dict:
    """
    Comprehensive data quality validation using native Polars aggregations.
    """
    logger.info("Validating data quality (Polars-native)")

    n_rows = df.height
    validation_results: Dict = {
        "total_records": n_rows,
        "total_features": len(df.columns),
        "missing_values": {},
        "target_distribution": {},
        "data_types": {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)},
        "quality_score": 0.0,
        "warnings": [],
        "missingness_signals": [],
        "constant_features": [],
    }

    if n_rows == 0:
        validation_results["warnings"].append("Empty dataset")
        return validation_results

    null_profile = df.select(pl.all().null_count()).transpose(
        include_header=True, header_name="column", column_names=["null_count"]
    )
    for row in null_profile.iter_rows(named=True):
        col = row["column"]
        null_count = int(row["null_count"])
        if null_count == 0:
            continue
        null_pct = (null_count / n_rows) * 100.0
        validation_results["missing_values"][col] = {
            "count": null_count,
            "percentage": round(null_pct, 2),
        }
        if null_pct >= MISSINGNESS_ALERT_PCT:
            validation_results["missingness_signals"].append(col)
            validation_results["warnings"].append(
                f"Missingness signal in {col}: {null_pct:.1f}% null (>{MISSINGNESS_ALERT_PCT}%)"
            )
        elif null_pct > HIGH_MISSING_PCT:
            validation_results["warnings"].append(f"Elevated missing values in {col}: {null_pct:.1f}%")

    if target_col in df.columns:
        target_dist = (
            df.group_by(target_col)
            .agg(pl.len().alias("count"))
            .with_columns((pl.col("count") / n_rows * 100).round(2).alias("percentage"))
            .sort(target_col)
        )
        for row in target_dist.iter_rows(named=True):
            key = int(row[target_col])
            validation_results["target_distribution"][key] = {
                "count": int(row["count"]),
                "percentage": float(row["percentage"]),
            }

        if len(validation_results["target_distribution"]) == 2:
            pcts = [v["percentage"] for v in validation_results["target_distribution"].values()]
            imbalance_ratio = min(pcts) / max(pcts) if max(pcts) else 0.0
            if imbalance_ratio < 0.1:
                validation_results["warnings"].append(
                    f"Severe class imbalance detected: {imbalance_ratio:.2f} ratio"
                )

    feature_cols = [c for c in df.columns if c != target_col]
    n_unique_df = df.select(pl.col(c).n_unique().alias(c) for c in feature_cols)
    for col in feature_cols:
        n_unique = int(n_unique_df[col][0])
        if n_unique == 1:
            validation_results["constant_features"].append(col)

    passed_checks = 0
    high_missing = sum(
        1 for v in validation_results["missing_values"].values() if v["percentage"] > HIGH_MISSING_PCT
    )
    if high_missing == 0:
        passed_checks += 1
    if validation_results["target_distribution"]:
        passed_checks += 1
    if len(validation_results["warnings"]) < 3:
        passed_checks += 1

    validation_results["quality_score"] = round(passed_checks / 3, 2)
    logger.info("Data quality score: %s", validation_results["quality_score"])
    return validation_results


def detect_potential_bias(df: pl.DataFrame, feature_cols: List[str]) -> Dict:
    """Detect constant and low-variance features via `.n_unique()` and Polars aggregations."""
    logger.info("Detecting potential bias signals (Polars-native)")

    bias_results: Dict = {
        "high_variance_features": [],
        "constant_features": [],
        "low_variance_features": [],
    }

    existing = [c for c in feature_cols if c in df.columns]
    if not existing:
        return bias_results

    n_rows = df.height
    stats_df = df.select(
        pl.col(c).n_unique().alias(f"{c}__n_unique") for c in existing
    )

    for col in existing:
        n_unique = int(stats_df[f"{col}__n_unique"][0])
        if n_unique == 1:
            bias_results["constant_features"].append(col)
            continue
        if n_unique != 2:
            continue

        counts = df[col].value_counts().sort("count", descending=True)
        if counts.height < 2:
            continue
        min_count = int(counts["count"].min())
        min_pct = (min_count / n_rows) * 100.0 if n_rows else 0.0
        if min_pct < LOW_CLASS_PCT:
            bias_results["low_variance_features"].append(
                {"feature": col, "min_class_percentage": round(min_pct, 2)}
            )

    return bias_results
