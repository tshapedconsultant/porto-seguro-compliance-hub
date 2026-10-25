"""
Run EBM Training Pipeline on the full Porto Seguro dataset (~595k records).
"""

import json
from pathlib import Path

from src.models.ebm_train import train_ebm_pipeline

if __name__ == "__main__":
    print("=" * 60)
    print("FULL PIPELINE - entire dataset (sample_size=None)")
    print("=" * 60)
    print()

    results = train_ebm_pipeline(
        data_path=".",
        sample_size=None,
        random_seed=42,
    )

    results_file = Path("training_results.json")
    payload = {**results["metrics"]}
    if results.get("paths", {}).get("calibration_plot"):
        payload["calibration_plot"] = results["paths"]["calibration_plot"]
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    m = results["metrics"]
    print()
    print("=" * 60)
    print("[SUCCESS] TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Train ROC-AUC: {m['train_auc']:.4f}")
    print(f"  Test ROC-AUC:  {m['test_auc']:.4f}")
    print(f"  Test F1:       {m['test_f1']:.4f} (optimal threshold)")
    print(f"  Test F1 @0.5:  {m.get('test_f1_default', 0):.4f}")
    if m.get("brier_score") is not None:
        print(f"  Brier score:   {m['brier_score']:.4f}")
    print(f"  Test Precision:{m['test_precision']:.4f}")
    print(f"  Test Recall:   {m['test_recall']:.4f}")
    print(f"  Threshold:     {m['optimal_threshold']:.4f}")
    print(f"  Model:         {results['paths']['model']}")
    print(f"  Results:       {results_file}")
