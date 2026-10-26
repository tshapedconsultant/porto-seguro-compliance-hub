"""
EBM Training Pipeline - Production Ready
Part of Insurance Claim Prediction - Responsible AI Architecture

This module orchestrates the training pipeline:
1. Loads data efficiently with Polars.
2. Performs Stratified Split (Critical for 3.6% target imbalance).
3. Executes Stateful Feature Engineering (No Data Leakage).
4. Trains Explainable Boosting Machine (EBM).
5. Saves both Model and Feature Engineer artifacts for inference.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import polars as pl

# Configuration (must be before logger usage)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# InterpretML (EBM)
try:
    from interpret.glassbox import ExplainableBoostingClassifier
    from sklearn.metrics import roc_auc_score, classification_report
    INTERPRET_AVAILABLE = True
except ImportError:
    INTERPRET_AVAILABLE = False
    logger.warning("InterpretML not available. Install with: pip install interpret")

# Internal Modules
from src.data_processing.load_data_polars import load_porto_seguro_data
from src.data_processing.feature_engineering import (
    ResponsibleFeatureEngineer, 
    get_stratified_split
)
from src.models.evaluation import compute_f1_optimal_threshold

DEFAULT_ARTIFACTS_DIR = Path("models/artifacts")
# Back-compat alias; prefer passing artifacts_dir= into train_ebm_pipeline.
ARTIFACTS_DIR = DEFAULT_ARTIFACTS_DIR


def _package_version(name: str) -> Optional[str]:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_hash(df: pl.DataFrame) -> str:
    """Canonical hash of column names + dtypes (integrity checksum, not a signature)."""
    schema_payload = [{"name": name, "dtype": str(dtype)} for name, dtype in df.schema.items()]
    canonical = json.dumps(schema_payload, sort_keys=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_dataset_provenance(
    data_path: str,
    sample_size: Optional[int],
    random_seed: int,
    df: Optional[pl.DataFrame] = None,
    dataset_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dataset integrity metadata for operational manifests.

    When train.csv is present: full SHA-256, size, row count, schema hash, URI/path.
    When absent: synthetic_or_missing marker (no invented file hash).
    This is NOT cryptographic provenance, WORM storage, or legal evidence.
    """
    root = Path(data_path)
    train_csv = root / "train.csv"
    base: Dict[str, Any] = {
        "sample_size": sample_size,
        "random_seed": random_seed,
        "dataset_uri": str(train_csv.resolve()) if train_csv.exists() else str(root.resolve()),
        "dataset_version": dataset_version,
        "integrity_note": (
            "Integrity checksums only — not a cryptographic signature, "
            "not WORM/legal provenance, not a conformity claim."
        ),
    }
    if not train_csv.exists():
        loaded = int(df.height) if df is not None else None
        base.update(
            {
                "status": "synthetic_or_missing",
                "dataset_sha256": None,
                "file_size_bytes": None,
                "row_count": loaded,
                "loaded_row_count": loaded,
                "schema_sha256": _schema_hash(df) if df is not None else None,
                "legacy_fingerprint": f"synthetic_or_missing:sample={sample_size}:seed={random_seed}",
            }
        )
        return base

    file_sha = _sha256_file(train_csv)
    # File row count (header excluded); loaded_row_count may be smaller when sampling.
    with train_csv.open("rb") as fh:
        file_row_count = max(sum(1 for _ in fh) - 1, 0)
    loaded = int(df.height) if df is not None else None
    schema = _schema_hash(df) if df is not None else None
    base.update(
        {
            "status": "file_present",
            "dataset_sha256": file_sha,
            "file_size_bytes": int(train_csv.stat().st_size),
            "row_count": file_row_count,
            "loaded_row_count": loaded,
            "schema_sha256": schema,
            # Back-compat string for older consumers (full hash, not truncated).
            "legacy_fingerprint": (
                f"train.csv:{file_sha}:sample={sample_size}:seed={random_seed}"
            ),
        }
    )
    return base


def _canonical_manifest_body(manifest: Dict[str, Any]) -> str:
    """Deterministic JSON for integrity checksum (excludes manifest_sha256)."""
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def write_run_manifest(
    artifacts_dir: Path,
    *,
    run_id: str,
    dataset: Dict[str, Any],
    config: Dict[str, Any],
    metrics: Dict[str, Any],
    artifact_paths: Dict[str, Any],
) -> Path:
    """
    Emit per-run manifest (never overwrite a shared run_manifest.json).

    Writes:
      - artifacts_dir / run_id / run_manifest.json
      - artifacts_dir / run_manifest_<run_id>.json
      - artifacts_dir / run_manifest_latest.json  (non-authoritative pointer only)

    manifest_sha256 is an integrity checksum of the canonical JSON body
    (excluding that field). It is NOT a cryptographic signature.
    """
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        # Convenience alias used by older docs/tests.
        "dataset_hash": dataset.get("legacy_fingerprint") or dataset.get("dataset_sha256"),
        "config": config,
        "lib_versions": {
            "polars": _package_version("polars"),
            "interpret": _package_version("interpret"),
            "numpy": _package_version("numpy"),
            "scikit-learn": _package_version("scikit-learn"),
            "scipy": _package_version("scipy"),
            "joblib": _package_version("joblib"),
        },
        "metrics": metrics,
        "artifact_paths": artifact_paths,
        "note": (
            "Operational run record only — not cryptographic provenance, "
            "not a signature, not WORM/legal evidence, not regulatory certification."
        ),
        "integrity_note": (
            "manifest_sha256 is an integrity checksum of the canonical JSON body "
            "(sort_keys, excluding manifest_sha256). NOT a cryptographic signature "
            "and NOT legal provenance unless an external signing key path is added."
        ),
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        _canonical_manifest_body(manifest).encode("utf-8")
    ).hexdigest()

    payload = json.dumps(manifest, indent=2, default=str)
    path_nested = run_dir / "run_manifest.json"
    path_flat = artifacts_dir / f"run_manifest_{run_id}.json"
    path_nested.write_text(payload, encoding="utf-8")
    path_flat.write_text(payload, encoding="utf-8")

    pointer = {
        "run_id": run_id,
        "manifest_path": str(path_flat),
        "manifest_nested_path": str(path_nested),
        "created_at": manifest["created_at"],
        "note": (
            "Non-authoritative pointer to the latest run manifest for convenience "
            "(e.g. API discovery). Authoritative record is run_manifest_<run_id>.json "
            "or artifacts_dir/<run_id>/run_manifest.json."
        ),
    }
    (artifacts_dir / "run_manifest_latest.json").write_text(
        json.dumps(pointer, indent=2), encoding="utf-8"
    )
    logger.info("   ✅ Saved run manifest: %s (and %s)", path_flat, path_nested)
    return path_flat


def train_ebm_pipeline(
    data_path: str,
    target_col: str = "target",
    test_size: float = 0.2,
    random_seed: int = 42,
    sample_size: Optional[int] = None,
    hyperparameters: Optional[Dict] = None,
    artifacts_dir: Optional[str | Path] = None,
    write_legacy_copies: Optional[bool] = None,
    perform_cv: bool = True,
    perform_adversarial: bool = True,
) -> Dict[str, Any]:
    """
    Executes the full training pipeline with strict separation of concerns.
    
    Flow:
    1. Load Data
    2. Split (Stratified) -> Train / Test
    3. Fit Feature Engineer on TRAIN ONLY
    4. Transform Train and Test
    5. Train EBM Model
    6. Evaluate
    7. Save Artifacts (Model + FE)
    
    Args:
        data_path: Path to data directory
        target_col: Target column name
        test_size: Proportion for test set
        random_seed: Random seed for reproducibility
        sample_size: Optional sample size for faster testing
        hyperparameters: Optional EBM hyperparameters
        artifacts_dir: Where to write model/FE/threshold/manifest
            (default: models/artifacts). Use models/artifacts/quick/ for smoke runs.
        write_legacy_copies: Also write models/ebm_model.pkl etc. Defaults to True
            only when artifacts_dir is the production default.
        perform_cv / perform_adversarial: Toggle robustness block (tests may disable).
        
    Returns:
        dict: Dictionary containing model, feature_engineer, and metrics
    """
    
    if not INTERPRET_AVAILABLE:
        raise ImportError("InterpretML not available. Install with: pip install interpret")

    out_dir = Path(artifacts_dir) if artifacts_dir is not None else DEFAULT_ARTIFACTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if write_legacy_copies is None:
        write_legacy_copies = out_dir.resolve() == DEFAULT_ARTIFACTS_DIR.resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

    # --- 1. Data Loading (Polars) ---
    logger.info("🚀 Starting Pipeline...")
    logger.info("   Artifacts dir: %s", out_dir)
    df = load_porto_seguro_data(data_path, sample_size=sample_size, random_seed=random_seed)
    logger.info(f"📊 Loaded {len(df)} records with {len(df.columns)} features")
    dataset_provenance = build_dataset_provenance(
        data_path, sample_size, random_seed, df=df
    )
    
    # --- 2. Stratified Split (Crucial for Imbalanced Data) ---
    logger.info("✂️  Splitting data (Stratified for imbalanced dataset)...")
    # We use our custom wrapper that ensures class balance is preserved
    df_train, df_test = get_stratified_split(
        df, 
        target_col=target_col, 
        test_size=test_size, 
        random_seed=random_seed
    )
    
    logger.info(f"   Train: {len(df_train)} records")
    logger.info(f"   Test: {len(df_test)} records")
    
    # --- 3. Feature Engineering (Stateful - NO LEAKAGE) ---
    logger.info("🛠️  Fitting Feature Engineer (on Train only - prevents data leakage)...")
    
    # Initialize the engineer
    fe = ResponsibleFeatureEngineer(target_col=target_col)
    
    # FIT only on training data (CRITICAL: no test data seen here)
    fe.fit(df_train)
    
    # TRANSFORM both sets independently using train statistics
    logger.info("🔄 Transforming Train and Test sets...")
    df_train_eng = fe.transform(df_train)
    df_test_eng = fe.transform(df_test)
    
    logger.info(f"   Engineered features: {len(df_train_eng.columns)} total columns")
    
    # --- 4. Last-millisecond bridge to InterpretML (pandas only at fit) ---
    from src.models.interpret_bridge import fit_ebm, predict_proba_ebm

    y_train = df_train_eng[target_col]
    y_test = df_test_eng[target_col]
    logger.info(f"   Training on {df_train_eng.height} samples with engineered features")
    
    # --- 5. Model Training (EBM) ---
    logger.info("🧠 Training EBM Model (this may take a while)...")
    
    # EBM Configuration for production
    default_hyperparams = {
        "max_bins": 256,
        "max_interaction_bins": 32,
        "interactions": 10,         # Auto-detect top 10 interactions
        "outer_bags": 8,            # Ensemble size (higher = more stable)
        "inner_bags": 0,
        "learning_rate": 0.01,      # Low LR for better generalization
        "validation_size": 0.15,    # Internal validation for early stopping
        "early_stopping_rounds": 50,
        "n_jobs": -1,               # Use all CPUs
        "random_state": random_seed,
        "max_rounds": 5000
    }
    
    # Merge with user-provided hyperparameters
    if hyperparameters:
        default_hyperparams.update(hyperparameters)
    
    ebm = ExplainableBoostingClassifier(**default_hyperparams)
    fit_ebm(ebm, df_train_eng, y_train, drop_cols=("id", target_col))
    
    # --- 6. Evaluation ---
    logger.info("📉 Evaluating Model...")
    
    drop_cols = ("id", target_col)
    y_prob_train = predict_proba_ebm(ebm, df_train_eng, drop_cols=drop_cols)
    y_prob_test = predict_proba_ebm(ebm, df_test_eng, drop_cols=drop_cols)
    y_train = y_train.to_numpy().ravel()
    y_test = y_test.to_numpy().ravel()
    
    # Metrics
    train_auc = roc_auc_score(y_train, y_prob_train)
    test_auc = roc_auc_score(y_test, y_prob_test)
    
    logger.info(f"🏆 Results:")
    logger.info(f"   Train ROC-AUC: {train_auc:.4f}")
    logger.info(f"   Test ROC-AUC:  {test_auc:.4f} (Key Metric)")
    
    # Additional metrics with optimal threshold (for imbalanced data)
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_score,
        recall_score,
    )

    # Find optimal threshold on TRAIN only (never tune threshold on hold-out test)
    optimal_threshold = compute_f1_optimal_threshold(y_train, y_prob_train)

    # Apply train-tuned threshold to test for unbiased F1/precision/recall reporting
    y_pred_optimal = (y_prob_test >= optimal_threshold).astype(int)
    test_f1 = f1_score(y_test, y_pred_optimal, zero_division=0)
    test_precision = precision_score(y_test, y_pred_optimal, zero_division=0)
    test_recall = recall_score(y_test, y_pred_optimal, zero_division=0)
    test_accuracy = accuracy_score(y_test, y_pred_optimal)

    # Also calculate with default threshold for comparison
    y_pred_default = (y_prob_test >= 0.5).astype(int)
    default_f1 = f1_score(y_test, y_pred_default, zero_division=0)
    
    logger.info(f"   Optimal Threshold: {optimal_threshold:.4f} (tuned on train, applied to test)")
    logger.info(f"   Test F1-Score: {test_f1:.4f} (with optimal threshold)")
    logger.info(f"   Test F1-Score: {default_f1:.4f} (with default 0.5 threshold)")
    logger.info(f"   Test Precision: {test_precision:.4f}")
    logger.info(f"   Test Recall: {test_recall:.4f}")

    # Reliability diagram (calibration curve) on hold-out test — technical metric only
    calibration_plot_path = out_dir / "calibration_curve.png"
    brier_score = None
    try:
        from sklearn.calibration import calibration_curve
        from sklearn.metrics import brier_score_loss
        import matplotlib.pyplot as plt

        prob_true, prob_pred = calibration_curve(y_test, y_prob_test, n_bins=10, strategy="quantile")
        brier_score = float(brier_score_loss(y_test, y_prob_test))
        plt.figure(figsize=(6, 6))
        plt.plot([0, 1], [0, 1], "k--", linewidth=1, label="Perfect calibration")
        plt.plot(prob_pred, prob_true, "s-", linewidth=2, label="EBM (hold-out test)")
        plt.xlabel("Mean predicted probability")
        plt.ylabel("Fraction of positives")
        plt.title(f"Calibration curve (Brier={brier_score:.4f})")
        plt.legend(loc="lower right")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(calibration_plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info("   ✅ Saved calibration curve: %s", calibration_plot_path)
    except Exception as exc:
        logger.warning("   Calibration curve skipped: %s", exc)
        calibration_plot_path = None

    # --- 6b. Robustness & Red Teaming (adversarial + CV) ---
    from src.models.evaluation import comprehensive_validation

    drop_cols_set = {"id", target_col}
    feature_cols = [
        c
        for c in df_train_eng.columns
        if c not in drop_cols_set and c in df_test_eng.columns
    ]
    X_train_val = df_train_eng.select(feature_cols)
    X_test_val = df_test_eng.select(feature_cols)
    y_train_val = df_train_eng.select(target_col)
    y_test_val = df_test_eng.select(target_col)

    robustness_results: Dict[str, Any] = {}
    adversarial: Dict[str, Any] = {}
    overall_robust = False
    if perform_cv or perform_adversarial:
        logger.info("🛡️ Running robustness validation (CV + adversarial red teaming)...")
        robustness_results = comprehensive_validation(
            model=ebm,
            X_train=X_train_val,
            y_train=y_train_val,
            X_test=X_test_val,
            y_test=y_test_val,
            perform_cv=perform_cv,
            perform_adversarial=perform_adversarial,
            classification_threshold=optimal_threshold,
        )
        adversarial = robustness_results.get("adversarial_testing", {})
        overall_robust = bool(adversarial.get("overall_robust", False))
        logger.info(
            "   Robustness result: overall_robust=%s, max_degradation=%.4f",
            overall_robust,
            float(adversarial.get("max_degradation", 0.0)),
        )

    robustness_path = out_dir / "robustness_results.json"
    with open(robustness_path, "w", encoding="utf-8") as f:
        json.dump(robustness_results, f, indent=2, default=str)
    logger.info("   ✅ Saved robustness results: %s", robustness_path)

    # Keep a copy under docs/ only for production artifact runs
    if write_legacy_copies:
        docs_robustness = Path("docs/robustness_results.json")
        docs_robustness.parent.mkdir(parents=True, exist_ok=True)
        docs_robustness.write_text(robustness_path.read_text(encoding="utf-8"), encoding="utf-8")

    # --- 7. Save Artifacts ---
    logger.info("📦 Saving artifacts to %s ...", out_dir)

    model_path = out_dir / "ebm_model_v1.pkl"
    joblib.dump(ebm, model_path)

    # CRITICAL: Save the Feature Engineer object too!
    fe_path = out_dir / "feature_engineer_v1.pkl"
    joblib.dump(fe, fe_path)

    logger.info(f"   ✅ Saved Model: {model_path}")
    logger.info(f"   ✅ Saved Feature Engineer: {fe_path}")

    threshold_path = out_dir / "optimal_threshold.txt"
    threshold_path.write_text(str(optimal_threshold), encoding="utf-8")
    logger.info(f"   ✅ Saved Optimal Threshold: {threshold_path} ({optimal_threshold:.4f})")

    if write_legacy_copies:
        legacy_model_path = Path("models/ebm_model.pkl")
        legacy_model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(ebm, legacy_model_path)
        joblib.dump(fe, Path("models/feature_engineer.pkl"))

    for artifact in (model_path, fe_path):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        artifact.with_name(artifact.name + ".sha256").write_text(f"{digest}\n", encoding="utf-8")
        logger.info("   ✅ SHA-256 sidecar: %s.sha256", artifact.name)

    metrics = {
        "train_auc": train_auc,
        "test_auc": test_auc,
        "test_f1": test_f1,
        "test_f1_default": float(default_f1),
        "test_precision": test_precision,
        "test_recall": test_recall,
        "test_accuracy": float(test_accuracy),
        "optimal_threshold": float(optimal_threshold),
        "brier_score": brier_score,
        "robustness_passed": overall_robust,
        "robustness_max_degradation": float(adversarial.get("max_degradation", 0.0)),
    }
    paths = {
        "model": str(model_path),
        "feature_engineer": str(fe_path),
        "threshold": str(threshold_path),
        "calibration_plot": str(calibration_plot_path) if calibration_plot_path else None,
        "robustness_results": str(robustness_path),
        "artifacts_dir": str(out_dir),
    }
    manifest_path = write_run_manifest(
        out_dir,
        run_id=run_id,
        dataset=dataset_provenance,
        config={
            "data_path": str(data_path),
            "target_col": target_col,
            "test_size": test_size,
            "random_seed": random_seed,
            "sample_size": sample_size,
            "hyperparameters": hyperparameters or {},
            "artifacts_dir": str(out_dir),
        },
        metrics=metrics,
        artifact_paths=paths,
    )
    paths["run_manifest"] = str(manifest_path)
    paths["run_manifest_nested"] = str(out_dir / run_id / "run_manifest.json")
    paths["run_manifest_latest"] = str(out_dir / "run_manifest_latest.json")

    logger.info("✅ Pipeline completed successfully!")

    return {
        "model": ebm,
        "feature_engineer": fe,
        "metrics": metrics,
        "robustness_results": robustness_results,
        "run_id": run_id,
        "paths": paths,
    }


def load_ebm_pipeline(
    model_path: Optional[str] = None,
    feature_engineer_path: Optional[str] = None
) -> Tuple[Any, Any]:
    """
    Load trained model and feature engineer for inference.
    
    Args:
        model_path: Path to saved model (default: models/artifacts/ebm_model_v1.pkl)
        feature_engineer_path: Path to saved feature engineer (default: models/artifacts/feature_engineer_v1.pkl)
        
    Returns:
        tuple: (model, feature_engineer)
    """
    # Default paths
    if model_path is None:
        model_path = DEFAULT_ARTIFACTS_DIR / "ebm_model_v1.pkl"
        if not Path(model_path).exists():
            model_path = Path("models/ebm_model.pkl")
    
    if feature_engineer_path is None:
        feature_engineer_path = DEFAULT_ARTIFACTS_DIR / "feature_engineer_v1.pkl"
        if not Path(feature_engineer_path).exists():
            feature_engineer_path = Path("models/feature_engineer.pkl")
    
    logger.info(f"Loading model from: {model_path}")
    model = joblib.load(model_path)
    
    logger.info(f"Loading feature engineer from: {feature_engineer_path}")
    feature_engineer = joblib.load(feature_engineer_path)
    
    return model, feature_engineer


def predict_with_pipeline(
    model: Any,
    feature_engineer: Any,
    new_data: pl.DataFrame,
    target_col: str = "target"
) -> Dict[str, Any]:
    """
    Make predictions on new data using the trained pipeline.
    
    Args:
        model: Trained EBM model
        feature_engineer: Trained feature engineer
        new_data: New data as Polars DataFrame
        target_col: Target column name (optional, for validation)
        
    Returns:
        dict: Predictions and probabilities
    """
    logger.info(f"Processing {len(new_data)} new records...")
    
    # Transform using learned statistics
    new_data_eng = feature_engineer.transform(new_data)
    
    from src.models.interpret_bridge import predict_proba_ebm

    drop_cols = tuple(c for c in ("id", target_col) if c in new_data_eng.columns)
    probabilities = predict_proba_ebm(model, new_data_eng, drop_cols=drop_cols)
    threshold = float(getattr(model, "optimal_threshold_", 0.5))
    predictions = (probabilities >= threshold).astype(int)
    
    logger.info(f"Generated predictions for {len(predictions)} records")
    
    return {
        "predictions": predictions,
        "probabilities": probabilities,
        "data": new_data_eng
    }


if __name__ == "__main__":
    # Example usage
    # Ensure you have the data downloaded in the current directory or update path
    try:
        results = train_ebm_pipeline(
            data_path=".",
            sample_size=50000,  # Use sample for faster testing
            hyperparameters={"max_rounds": 500}  # Reduced for testing
        )
        print(f"\n✅ Training complete!")
        print(f"Test ROC-AUC: {results['metrics']['test_auc']:.4f}")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
