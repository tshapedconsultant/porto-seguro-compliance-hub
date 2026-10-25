"""
Run EBM Training Pipeline
Quick script to execute the training pipeline
"""

from src.models.ebm_train import train_ebm_pipeline
from pathlib import Path

if __name__ == "__main__":
    print("=" * 60)
    print("Insurance Claim Prediction - EBM Training Pipeline")
    print("=" * 60)
    print()
    
    try:
        # Run pipeline with balanced sample for fast development
        # NOTE: sample_size=50000 is good balance between speed and metric reliability
        # For production, use sample_size=None for full dataset (595k records)
        results = train_ebm_pipeline(
            data_path=".",
            sample_size=50000,  # Balanced sample for fast development iteration
            hyperparameters={
                "max_rounds": 1000,       # Reduced rounds for faster iteration
                "early_stopping_rounds": 30,
                "outer_bags": 4,          # Reduced from 8 to 4 for speed
                "interactions": 5         # Only strongest interactions
            },
            random_seed=42
        )
        
        # Save results for analysis
        import json
        results_file = Path("training_results.json")
        with open(results_file, 'w') as f:
            json.dump(results['metrics'], f, indent=2)
        
        print()
        print("=" * 60)
        print("[SUCCESS] TRAINING COMPLETE!")
        print("=" * 60)
        print()
        print("Performance Metrics:")
        print(f"   Train ROC-AUC: {results['metrics']['train_auc']:.4f}")
        print(f"   Test ROC-AUC:  {results['metrics']['test_auc']:.4f}")
        print(f"   Test F1-Score: {results['metrics']['test_f1']:.4f}")
        print(f"   Test Precision: {results['metrics']['test_precision']:.4f}")
        print(f"   Test Recall:    {results['metrics']['test_recall']:.4f}")
        print(f"   Optimal Threshold: {results['metrics']['optimal_threshold']:.4f}")
        print()
        print("Metric Validation:")
        test_auc = results['metrics']['test_auc']
        print(f"   [INFO] Using sample_size=50000 (development mode)")
        print(f"   [INFO] For production, use sample_size=None for full dataset")
        if 0.62 <= test_auc <= 0.66:
            print(f"   [PASS] ROC-AUC {test_auc:.4f} is in realistic range")
        elif test_auc > 0.66:
            print(f"   [NOTE] ROC-AUC {test_auc:.4f} may be slightly inflated with sample")
            print(f"          Full dataset typically gives 0.63-0.64")
        else:
            print(f"   [INFO] ROC-AUC {test_auc:.4f} - may need tuning")
        print()
        print("Artifacts Saved:")
        print(f"   Model: {results['paths']['model']}")
        print(f"   Feature Engineer: {results['paths']['feature_engineer']}")
        print(f"   Results: training_results.json")
        print()
        print("[SUCCESS] Pipeline executed successfully!")
        print()
        print("Next step: Run 'python analyze_results.py' for detailed analysis")
        
    except ImportError as e:
        print(f"\n[ERROR] Missing dependency: {e}")
        print("\nTo install InterpretML, run:")
        print("  pip install interpret")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

