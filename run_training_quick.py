"""
Quick Training Script (Small Sample - For Testing Only)
WARNING: This uses a small sample and will give inflated metrics.
Use run_training.py for production-ready evaluation.
"""

from src.models.ebm_train import train_ebm_pipeline

if __name__ == "__main__":
    print("=" * 60)
    print("QUICK TRAINING (Small Sample - Testing Only)")
    print("WARNING: Metrics will be inflated due to small test set")
    print("Use run_training.py for realistic evaluation")
    print("=" * 60)
    print()
    
    try:
        # Quick test with small sample
        results = train_ebm_pipeline(
            data_path=".",
            sample_size=10000,  # Small sample for quick testing
            hyperparameters={"max_rounds": 100},  # Reduced for speed
            random_seed=42
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
        print("Artifacts Saved:")
        print(f"   Model: {results['paths']['model']}")
        print(f"   Feature Engineer: {results['paths']['feature_engineer']}")
        
    except ImportError as e:
        print(f"\n[ERROR] Missing dependency: {e}")
        print("\nTo install InterpretML, run:")
        print("  pip install interpret")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()







