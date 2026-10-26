"""
Model Evaluation Module
Part of Insurance Claim Prediction - Responsible AI Architecture

Evaluation metrics aligned with insurance industry standards:
- AUC-ROC (primary metric for imbalanced data)
- Precision-Recall
- F1-Score
- Confusion Matrix

Comprehensive Model Validation Module
Part of Insurance Claim Prediction - Responsible AI Architecture

Implements cross-validation, adversarial testing, and rigorous validation
practices seen in top Kaggle competitions.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_validate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _as_numpy_features(X) -> np.ndarray:
    if isinstance(X, pl.DataFrame):
        return X.to_numpy()
    if isinstance(X, pd.DataFrame):
        return X.to_numpy()
    if isinstance(X, np.ndarray):
        return X
    raise TypeError(f"Unsupported X type: {type(X)}")


def _as_pandas_features(X, model=None) -> pd.DataFrame:
    """Convert features to pandas with column names preserved for EBM inference."""
    if isinstance(X, pl.DataFrame):
        X_pd = X.to_pandas()
    elif isinstance(X, pd.DataFrame):
        X_pd = X.copy()
    else:
        X_pd = pd.DataFrame(_as_numpy_features(X))

    expected = getattr(model, "feature_names_in_", None)
    if expected is not None:
        for name in expected:
            if name not in X_pd.columns:
                X_pd[name] = 0.0
        X_pd = X_pd[list(expected)]
    return X_pd


def _as_numpy_target(y, target_col: str = "target") -> np.ndarray:
    if isinstance(y, pl.DataFrame):
        if target_col in y.columns:
            return y.select(target_col).to_numpy().ravel()
        return y.to_numpy().ravel()
    if isinstance(y, pl.Series):
        return y.to_numpy().ravel()
    if isinstance(y, pd.DataFrame):
        if target_col in y.columns:
            return y[target_col].to_numpy().ravel()
        return y.iloc[:, 0].to_numpy().ravel()
    if isinstance(y, pd.Series):
        return y.to_numpy().ravel()
    if isinstance(y, np.ndarray):
        return y.ravel()
    raise TypeError(f"Unsupported y type: {type(y)}")


def evaluate_model(
    model,
    X_test: pl.DataFrame,
    y_test: pl.DataFrame,
    target_col: str = "target",
    threshold: Optional[float] = None,
) -> Dict:
    """
    Comprehensive model evaluation for insurance claim prediction.

    Args:
        model: Trained EBM model
        X_test: Test features (Polars DataFrame)
        y_test: Test target (Polars DataFrame)
        target_col: Target column name
        threshold: Optional threshold for binary classification (default: 0.5)
                   For imbalanced data, use optimal threshold from find_optimal_threshold()

    Returns:
        dict: Evaluation metrics
    """
    logger.info("Evaluating model performance")

    X_test_np = _as_numpy_features(X_test)
    y_test_np = _as_numpy_target(y_test, target_col=target_col)

    from src.models.interpret_bridge import predict_proba_ebm

    if isinstance(X_test, pl.DataFrame):
        y_pred_proba = predict_proba_ebm(model, X_test, drop_cols=tuple(c for c in ("id", target_col) if c in X_test.columns))
    else:
        y_pred_proba = model.predict_proba(X_test_np)[:, 1]

    # Threshold / F1 alignment with ebm_train.py:
    # - ebm_train tunes optimal_threshold on TRAIN (precision_recall_curve on y_train),
    #   then applies it to TEST for test_f1 / test_precision / test_recall in training_results.json.
    # - This helper defaults to threshold=0.5 when threshold is None (test_f1_default semantics).
    # Pass optimal_threshold from training_results.json to match production F1 from the pipeline.
    if threshold is None:
        threshold = 0.5
        y_pred = (y_pred_proba >= threshold).astype(int) if hasattr(model, "predict_proba") else model.predict(X_test_np)
    else:
        y_pred = (y_pred_proba >= threshold).astype(int)
        logger.info(f"Using custom threshold: {threshold:.4f}")

    metrics = {
        "roc_auc": roc_auc_score(y_test_np, y_pred_proba),
        "accuracy": accuracy_score(y_test_np, y_pred),
        "precision": precision_score(y_test_np, y_pred, zero_division=0),
        "recall": recall_score(y_test_np, y_pred, zero_division=0),
        "f1_score": f1_score(y_test_np, y_pred, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test_np, y_pred).tolist(),
    }

    metrics["classification_report"] = classification_report(
        y_test_np, y_pred, output_dict=True, zero_division=0
    )

    fpr, tpr, thresholds_roc = roc_curve(y_test_np, y_pred_proba)
    metrics["roc_curve"] = {
        "fpr": fpr.tolist(),
        "tpr": tpr.tolist(),
        "thresholds": thresholds_roc.tolist(),
    }

    precision_curve, recall_curve, thresholds_pr = precision_recall_curve(y_test_np, y_pred_proba)
    metrics["pr_curve"] = {
        "precision": precision_curve.tolist(),
        "recall": recall_curve.tolist(),
        "thresholds": thresholds_pr.tolist(),
    }

    logger.info(f"ROC-AUC: {metrics['roc_auc']:.4f}")
    logger.info(f"F1-Score: {metrics['f1_score']:.4f}")
    logger.info(f"Precision: {metrics['precision']:.4f}")
    logger.info(f"Recall: {metrics['recall']:.4f}")

    return metrics


def calculate_business_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_pred_proba: np.ndarray,
    claim_cost: float = 10000.0,
    premium: float = 1000.0,
) -> Dict:
    """
    Illustrative cost model only — not an actuarial or pricing result.

    Args:
        y_true: True labels
        y_pred: Predicted labels
        y_pred_proba: Predicted probabilities
        claim_cost: Average cost of a claim
        premium: Average premium per policy

    Returns:
        dict: Business metrics
    """
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    total_cost = (fn * claim_cost) + (fp * premium * 0.1)
    total_revenue = (tp + tn) * premium
    net_profit = total_revenue - total_cost

    return {
        "illustrative_only": True,
        "true_positives": int(tp),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "total_cost": float(total_cost),
        "total_revenue": float(total_revenue),
        "net_profit": float(net_profit),
        "cost_per_prediction": float(total_cost / len(y_true)),
    }


def stratified_cross_validation(
    model,
    X,
    y,
    n_splits: int = 5,
    scoring: str = "roc_auc",
) -> Dict:
    """
    Perform stratified k-fold cross-validation.

    Stratified CV ensures each fold has similar class distribution,
    critical for imbalanced datasets like insurance claims.

    Args:
        model: Model to validate
        X: Features
        y: Target variable
        n_splits: Number of folds (default: 5)
        scoring: Scoring metric (default: 'roc_auc')

    Returns:
        dict: Cross-validation results
    """
    logger.info(f"Performing {n_splits}-fold stratified cross-validation")

    X_np = _as_numpy_features(X)
    y_np = _as_numpy_target(y)
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    scoring_metrics = {
        "roc_auc": "roc_auc",
        "f1": "f1",
        "precision": "precision",
        "recall": "recall",
    }

    cv_results = cross_validate(
        model,
        X_np,
        y_np,
        cv=cv,
        scoring=scoring_metrics,
        return_train_score=True,
        n_jobs=-1,
    )

    results = {"n_splits": n_splits, "metrics": {}, "fold_results": []}
    for metric_name in scoring_metrics.keys():
        test_scores = cv_results[f"test_{metric_name}"]
        train_scores = cv_results[f"train_{metric_name}"]
        results["metrics"][metric_name] = {
            "test_mean": float(np.mean(test_scores)),
            "test_std": float(np.std(test_scores)),
            "test_scores": test_scores.tolist(),
            "train_mean": float(np.mean(train_scores)),
            "train_std": float(np.std(train_scores)),
            "overfitting": float(np.mean(train_scores) - np.mean(test_scores)),
        }

    for fold_idx in range(n_splits):
        results["fold_results"].append(
            {
                "fold": fold_idx + 1,
                "test_roc_auc": float(cv_results["test_roc_auc"][fold_idx]),
                "test_f1": float(cv_results["test_f1"][fold_idx]),
                "train_roc_auc": float(cv_results["train_roc_auc"][fold_idx]),
            }
        )

    logger.info(
        "CV ROC-AUC: %.4f (+/- %.4f)",
        results["metrics"]["roc_auc"]["test_mean"],
        results["metrics"]["roc_auc"]["test_std"],
    )
    return results


def adversarial_testing(
    model,
    X_test,
    y_test,
    perturbation_ratio: float = 0.1,
) -> Dict:
    """
    Perform adversarial testing to assess model robustness.

    Tests model performance under small perturbations to input features,
    simulating data drift or adversarial attacks.

    Args:
        model: Trained model
        X_test: Test features
        y_test: Test labels
        perturbation_ratio: Ratio of feature values to perturb (default: 0.1 = 10%)

    Returns:
        dict: Adversarial testing results
    """
    logger.info("Performing adversarial testing")
    X_test_df = _as_pandas_features(X_test, model=model)
    y_test_np = _as_numpy_target(y_test)

    if hasattr(model, "predict_proba"):
        baseline_auc = roc_auc_score(y_test_np, model.predict_proba(X_test_df)[:, 1])
    else:
        baseline_auc = roc_auc_score(y_test_np, model.predict(X_test_df))

    results = {"baseline_auc": float(baseline_auc), "perturbation_ratio": perturbation_ratio, "tests": []}

    np.random.seed(42)
    X_perturbed = X_test_df.copy()
    for col in X_perturbed.columns:
        if X_perturbed[col].dtype in [np.float64, np.float32, np.int64, np.int32]:
            noise = np.random.normal(0, X_perturbed[col].std() * perturbation_ratio, len(X_perturbed))
            X_perturbed[col] = X_perturbed[col] + noise

    if hasattr(model, "predict_proba"):
        perturbed_auc = roc_auc_score(y_test_np, model.predict_proba(X_perturbed)[:, 1])
    else:
        perturbed_auc = roc_auc_score(y_test_np, model.predict(X_perturbed))
    results["tests"].append(
        {
            "test_name": "random_noise_perturbation",
            "auc": float(perturbed_auc),
            "degradation": float(baseline_auc - perturbed_auc),
            "robust": abs(baseline_auc - perturbed_auc) < 0.05,
        }
    )

    X_dropout = X_test_df.copy()
    n_features_to_drop = int(len(X_dropout.columns) * perturbation_ratio)
    features_to_drop = np.random.choice(X_dropout.columns, n_features_to_drop, replace=False)
    X_dropout[features_to_drop] = 0

    if hasattr(model, "predict_proba"):
        dropout_auc = roc_auc_score(y_test_np, model.predict_proba(X_dropout)[:, 1])
    else:
        dropout_auc = roc_auc_score(y_test_np, model.predict(X_dropout))
    results["tests"].append(
        {
            "test_name": "feature_dropout",
            "auc": float(dropout_auc),
            "degradation": float(baseline_auc - dropout_auc),
            "robust": abs(baseline_auc - dropout_auc) < 0.05,
        }
    )

    max_degradation = max(test["degradation"] for test in results["tests"])
    results["overall_robust"] = max_degradation < 0.05
    results["max_degradation"] = float(max_degradation)
    logger.info(f"Adversarial testing complete. Max degradation: {max_degradation:.4f}")
    return results


def _resolve_classification_threshold(threshold: Optional[float]) -> float:
    if threshold is not None:
        return float(threshold)
    threshold_path = Path("models/artifacts/optimal_threshold.txt")
    if threshold_path.exists():
        return float(threshold_path.read_text(encoding="utf-8").strip())
    return 0.5


def comprehensive_validation(
    model,
    X_train,
    y_train,
    X_test,
    y_test,
    perform_cv: bool = True,
    perform_adversarial: bool = True,
    classification_threshold: Optional[float] = None,
) -> Dict:
    """
    Perform comprehensive model validation including CV and adversarial testing.

    Args:
        model: Trained model
        X_train: Training features
        y_train: Training labels
        X_test: Test features
        y_test: Test labels
        perform_cv: Whether to perform cross-validation
        perform_adversarial: Whether to perform adversarial testing

    Returns:
        dict: Comprehensive validation results
    """
    logger.info("Performing comprehensive model validation")
    results = {
        "validation_date": pd.Timestamp.now().isoformat(),
        "cross_validation": {},
        "adversarial_testing": {},
        "test_set_performance": {},
    }

    if perform_cv:
        results["cross_validation"] = stratified_cross_validation(model, X_train, y_train, n_splits=5)
    if perform_adversarial:
        results["adversarial_testing"] = adversarial_testing(model, X_test, y_test)

    X_test_pd = _as_pandas_features(X_test, model=model)
    y_test_np = _as_numpy_target(y_test)
    threshold = _resolve_classification_threshold(classification_threshold)
    if hasattr(model, "predict_proba"):
        y_pred_proba = model.predict_proba(X_test_pd)[:, 1]
        y_pred = (y_pred_proba >= threshold).astype(int)
        roc_auc = roc_auc_score(y_test_np, y_pred_proba)
    else:
        y_pred = model.predict(X_test_pd)
        roc_auc = roc_auc_score(y_test_np, y_pred)

    results["test_set_performance"] = {
        "roc_auc": float(roc_auc),
        "f1_score": float(f1_score(y_test_np, y_pred, zero_division=0)),
        "precision": float(precision_score(y_test_np, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test_np, y_pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_test_np, y_pred)),
        "threshold_used": float(threshold),
    }
    return results
