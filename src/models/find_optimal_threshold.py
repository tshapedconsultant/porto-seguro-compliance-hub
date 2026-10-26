"""
Optimal Threshold Finder — anti-leakage evaluation on hold-out test ONLY.

NEVER report ROC-AUC on the full 595k (train+test): that mixes in-sample train
predictions and inflates AUC (~0.645 vs ~0.638 on true hold-out).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.append(os.getcwd())

from src.data_processing.feature_engineering import get_stratified_split
from src.data_processing.load_data_polars import load_porto_seguro_data
from src.models.evaluation import compute_f1_optimal_threshold
from src.models.interpret_bridge import predict_proba_ebm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "models/artifacts"))
MODEL_PATH = ARTIFACTS_DIR / "ebm_model_v1.pkl"
FE_PATH = ARTIFACTS_DIR / "feature_engineer_v1.pkl"
TARGET_COL = "target"
DROP_COLS = ("id", TARGET_COL)
SPLIT_SEED = 42
MAX_TRAIN_TEST_AUC_GAP = 0.05


def load_artifacts() -> Tuple[Any, Any]:
    logger.info("Loading artifacts from %s...", ARTIFACTS_DIR)
    model = joblib.load(MODEL_PATH)
    fe = joblib.load(FE_PATH)
    if not getattr(fe, "trained", False):
        raise RuntimeError("Feature engineer artifact is not in fitted state.")
    logger.info("Model and fitted Feature Engineer loaded (statistics frozen at training time).")
    return model, fe


def audit_feature_leakage(feature_cols: List[str]) -> List[str]:
    """Detect target/id or obvious leakage columns in the model input matrix."""
    issues: List[str] = []
    forbidden = {TARGET_COL, "id", "claim", "loss", "indemnity"}
    for col in feature_cols:
        low = col.lower()
        if col in forbidden or low == TARGET_COL:
            issues.append(f"Forbidden column in model inputs: {col}")
        if low.endswith("_target") or low.startswith("target_"):
            issues.append(f"Suspicious target-derived column: {col}")
    return issues


def _probabilities_and_labels(
    model: Any,
    feature_engineer: Any,
    df: pl.DataFrame,
) -> Tuple[np.ndarray, np.ndarray]:
    """Transform with saved FE only (no refit). Predict via interpret bridge."""
    df_eng = feature_engineer.transform(df)
    drop = tuple(c for c in DROP_COLS if c in df_eng.columns)
    feature_cols = [c for c in df_eng.columns if c not in drop]

    issues = audit_feature_leakage(feature_cols)
    if issues:
        raise ValueError("Data leakage audit failed:\n  - " + "\n  - ".join(issues))

    y = df_eng.select(TARGET_COL).to_numpy().ravel().astype(np.int8)
    y_prob = predict_proba_ebm(model, df_eng, drop_cols=drop)
    return y_prob, y


def find_optimal_threshold(
    model: Any = None,
    feature_engineer: Any = None,
    data_path: str = ".",
    sample_size: Optional[int] = None,
    use_test_set: bool = True,
    optimize_threshold: bool = True,
    report_train_auc_diagnostic: bool = True,
) -> Dict[str, Any]:
    """
    Evaluate / tune threshold with strict anti-leakage rules.

    Rules:
    - Split FIRST (same seed=42 as training pipeline).
    - Feature engineer is LOADED, never refit here.
    - Official ROC-AUC is computed ONLY on hold-out test (20%).
    - Full-dataset AUC is NOT computed (misleading / in-sample on train rows).
    """
    if model is None or feature_engineer is None:
        model, feature_engineer = load_artifacts()

    if not use_test_set:
        raise ValueError(
            "use_test_set=False is disabled: evaluating on train+test inflates metrics. "
            "Use use_test_set=True for unbiased ROC-AUC."
        )

    logger.info("Loading data (sample_size=%s)...", sample_size)
    df = load_porto_seguro_data(data_path, sample_size=sample_size, random_seed=SPLIT_SEED)
    n_total = df.height

    df_train, df_test = get_stratified_split(
        df, target_col=TARGET_COL, test_size=0.2, random_seed=SPLIT_SEED
    )
    logger.info(
        "Anti-leakage split: train=%s (in-sample diagnostic only), test=%s (official metrics)",
        df_train.height,
        df_test.height,
    )

    logger.info("Official ROC-AUC on HOLD-OUT TEST only...")
    y_prob_test, y_test = _probabilities_and_labels(model, feature_engineer, df_test)
    test_auc = float(roc_auc_score(y_test, y_prob_test))

    y_prob_train, y_train = _probabilities_and_labels(model, feature_engineer, df_train)
    train_auc = float(roc_auc_score(y_train, y_prob_train))
    auc_gap = train_auc - test_auc
    leakage_warnings: List[str] = []

    if auc_gap > MAX_TRAIN_TEST_AUC_GAP:
        leakage_warnings.append(
            f"Train-test AUC gap {auc_gap:.4f} > {MAX_TRAIN_TEST_AUC_GAP}: possible overfitting "
            "(not necessarily feature leakage)."
        )

    if optimize_threshold:
        # Match ebm_train.py: tune threshold on TRAIN only, evaluate F1 on test
        best_threshold = compute_f1_optimal_threshold(y_train, y_prob_train)
    else:
        path = ARTIFACTS_DIR / "optimal_threshold.txt"
        best_threshold = float(path.read_text(encoding="utf-8").strip()) if path.exists() else 0.5

    y_pred_default = (y_prob_test >= 0.5).astype(int)
    y_pred_optimal = (y_prob_test >= best_threshold).astype(int)

    default_f1 = float(f1_score(y_test, y_pred_default, zero_division=0))
    optimal_f1 = float(f1_score(y_test, y_pred_optimal, zero_division=0))
    optimal_precision = float(precision_score(y_test, y_pred_optimal, zero_division=0))
    optimal_recall = float(recall_score(y_test, y_pred_optimal, zero_division=0))

    if optimize_threshold:
        leakage_warnings.append(
            "Threshold tuned on train split (aligned with ebm_train.py); F1/precision/recall reported on test."
        )

    print("\n" + "=" * 60)
    print("THRESHOLD / AUC EVALUATION (ANTI-LEAKAGE)")
    print("=" * 60)
    print(f"\nRecords loaded: {n_total:,}")
    print(f"Official eval set (test only): {len(y_test):,}")
    print(f"\n*** ROC-AUC OFICIAL (hold-out test): {test_auc:.4f} ***")
    print("    Rango competitivo Porto Seguro: ~0.63-0.64")
    if report_train_auc_diagnostic:
        print(f"\n[Diagnostico] ROC-AUC train (in-sample, NO usar para reporting): {train_auc:.4f}")
        print(f"[Diagnostico] Gap train-test: {auc_gap:.4f}")
    print("\nNO se calcula AUC sobre 595k — incluiría filas de entrenamiento y subestima el riesgo.")

    if leakage_warnings:
        print("\n[WARN] Advertencias:")
        for w in leakage_warnings:
            print(f"   - {w}")

    print(f"\nUmbral óptimo (test): {best_threshold:.4f}")
    print(f"F1 @ umbral óptimo: {optimal_f1:.4f} | F1 @ 0.5: {default_f1:.4f}")
    print(f"Precision: {optimal_precision:.4f} | Recall: {optimal_recall:.4f}")
    print("-" * 60)

    cm = confusion_matrix(y_test, y_pred_optimal)
    print("\nConfusion Matrix (test, optimal threshold):")
    print(f"TN: {cm[0][0]:6d} | FP: {cm[0][1]:6d}")
    print(f"FN: {cm[1][0]:6d} | TP: {cm[1][1]:6d}")

    try:
        if optimize_threshold:
            from sklearn.metrics import precision_recall_curve

            precisions, recalls, thresholds = precision_recall_curve(y_train, y_prob_train)
            f1_scores_plot = 2 * (precisions[:-1] * recalls[:-1]) / (precisions[:-1] + recalls[:-1] + 1e-10)
            plt.figure(figsize=(12, 8))
            plt.subplot(2, 1, 1)
            plt.plot(thresholds, f1_scores_plot, label="F1 (train-tuned)", color="blue")
            plt.axvline(best_threshold, color="red", linestyle=":", label=f"Optimal {best_threshold:.3f}")
            plt.title("Threshold optimization (tuned on train split only)")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.subplot(2, 1, 2)
            prec_t, rec_t, _ = precision_recall_curve(y_test, y_prob_test)
            plt.plot(rec_t, prec_t, color="blue")
            plt.title("Precision-Recall (hold-out test)")
            plt.tight_layout()
            out = ARTIFACTS_DIR / "threshold_analysis.png"
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            plt.savefig(out, dpi=150, bbox_inches="tight")
            plt.close()
    except Exception as exc:
        logger.warning("Plot skipped: %s", exc)

    results: Dict[str, Any] = {
        "optimal_threshold": best_threshold,
        "n_records_loaded": n_total,
        "n_test_records": int(len(y_test)),
        "n_train_records": int(df_train.height),
        "metrics": {
            "test_auc": test_auc,
            "train_auc_diagnostic": train_auc,
            "train_test_auc_gap": auc_gap,
            "auc": test_auc,
            "optimal": {
                "f1": optimal_f1,
                "precision": optimal_precision,
                "recall": optimal_recall,
            },
            "default": {"f1": default_f1},
        },
        "leakage_warnings": leakage_warnings,
        "confusion_matrix": {"tn": int(cm[0][0]), "fp": int(cm[0][1]), "fn": int(cm[1][0]), "tp": int(cm[1][1])},
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "optimal_threshold.txt").write_text(f"{best_threshold}\n", encoding="utf-8")
    Path("threshold_optimization_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Threshold / AUC — Production 595k (hold-out test metrics only)")
    print("=" * 60)

    try:
        results = find_optimal_threshold(
            data_path=".",
            sample_size=None,
            use_test_set=True,
            optimize_threshold=True,
            report_train_auc_diagnostic=True,
        )
        print("\n[SUCCESS] Official test ROC-AUC:", f"{results['metrics']['test_auc']:.4f}")
    except Exception as exc:
        logger.error("Error: %s", exc, exc_info=True)
