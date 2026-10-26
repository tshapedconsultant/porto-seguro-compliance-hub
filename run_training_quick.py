"""
Quick Training Script (Small Sample - For Testing Only)

WARNING:
  - Uses a small sample; metrics can be inflated.
  - Does NOT overwrite production artifacts under models/artifacts/.
  - Writes under models/artifacts/quick/ by default (or --output-dir).

Use run_training.py / run_training_full.py for production-ready evaluation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.models.ebm_train import train_ebm_pipeline

DEFAULT_QUICK_DIR = Path("models/artifacts/quick")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-train EBM on a small sample. Artifacts go to models/artifacts/quick/ "
            "by default so production models/artifacts/ is never overwritten."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_QUICK_DIR,
        help=f"Artifact directory (default: {DEFAULT_QUICK_DIR}). Required alternative to production path.",
    )
    parser.add_argument("--sample-size", type=int, default=10000)
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument("--data-path", type=str, default=".")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_dir = args.output_dir
    if output_dir.resolve() == Path("models/artifacts").resolve():
        raise SystemExit(
            "Refusing to write quick-run artifacts into models/artifacts/ "
            "(production path). Use the default models/artifacts/quick/ or another --output-dir."
        )

    print("=" * 60)
    print("QUICK TRAINING (Small Sample - Testing Only)")
    print("WARNING: Metrics will be inflated due to small test set")
    print(f"Artifacts will be written to: {output_dir}")
    print("Production models/artifacts/ will NOT be overwritten")
    print("Use run_training.py for realistic evaluation")
    print("=" * 60)
    print()

    try:
        results = train_ebm_pipeline(
            data_path=args.data_path,
            sample_size=args.sample_size,
            hyperparameters={"max_rounds": args.max_rounds},
            random_seed=args.seed,
            artifacts_dir=output_dir,
            write_legacy_copies=False,
        )

        print()
        print("=" * 60)
        print("[WARNING] These metrics are INFLATED due to small sample size")
        print("Run with sample_size=None for realistic metrics")
        print("=" * 60)
        print()
        print("Performance Metrics (Inflated):")
        print(f"   Train ROC-AUC: {results['metrics']['train_auc']:.4f}")
        print(f"   Test ROC-AUC:  {results['metrics']['test_auc']:.4f}")
        print(f"   Test F1-Score: {results['metrics']['test_f1']:.4f}")
        print(f"   Optimal Threshold: {results['metrics']['optimal_threshold']:.4f}")
        print()
        print("Artifacts Saved (quick sandbox only):")
        print(f"   Model: {results['paths']['model']}")
        print(f"   Feature Engineer: {results['paths']['feature_engineer']}")
        print(f"   Run manifest: {results['paths'].get('run_manifest')}")
        print(f"   Run id: {results.get('run_id')}")
        print(
            "   Note: run_manifest_latest.json is a non-authoritative pointer; "
            "authoritative file is run_manifest_<run_id>.json"
        )

    except ImportError as e:
        print(f"\n[ERROR] Missing dependency: {e}")
        print("\nTo install InterpretML, run:")
        print("  pip install interpret")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
