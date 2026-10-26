"""
Test Governance Modules
Part of Insurance Claim Prediction - Responsible AI Architecture
"""

import pytest
import json
import tempfile
import os
from src.governance.reporting_generator import generate_compliance_report
from src.governance.reporting_generator import generate_model_card
from src.monitoring.performance_tracking import PerformanceTracker


def test_generate_compliance_report():
    """Test compliance report generation."""
    model_info = {
        "model_type": "EBM",
        "training_date": "2024-01-01",
        "hyperparameters": {"max_rounds": 100}
    }
    
    performance_metrics = {
        "roc_auc": 0.65,
        "f1_score": 0.45,
        "precision": 0.50,
        "recall": 0.40,
        "accuracy": 0.85
    }
    
    explainability_report = {
        "global_explanation": {"feature_importance": {"feature_1": 0.5}},
        "compliance_notes": {"model_type": "EBM"}
    }
    
    data_quality_report = {
        "quality_score": 0.9,
        "missing_values": {},
        "target_distribution": {0: 0.9, 1: 0.1},
        "warnings": []
    }
    
    report = generate_compliance_report(
        model_info=model_info,
        performance_metrics=performance_metrics,
        explainability_report=explainability_report,
        data_quality_report=data_quality_report
    )
    
    assert "report_metadata" in report
    assert "model_details" in report
    assert "performance_metrics" in report
    assert "explainability_compliance" in report
    assert "training_data" in report
    assert "solvency_ii_compliance" in report
    assert "eu_ai_act_compliance" in report
    assert "responsible_ai_compliance" in report
    assert "recommendations" in report
    assert report["eu_ai_act_compliance"]["compliance_status"] == "not_a_conformity_decision"


def test_generate_compliance_report_with_file():
    """Test compliance report generation with file output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "compliance_report.json")
        
        model_info = {"model_type": "EBM"}
        performance_metrics = {"roc_auc": 0.65}
        explainability_report = {"global_explanation": {}}
        data_quality_report = {"quality_score": 0.9}
        
        report = generate_compliance_report(
            model_info=model_info,
            performance_metrics=performance_metrics,
            explainability_report=explainability_report,
            data_quality_report=data_quality_report,
            output_path=output_path
        )
        
        # Check file was created
        assert os.path.exists(output_path)
        
        # Check file content
        with open(output_path, 'r') as f:
            loaded_report = json.load(f)
        
        assert "report_metadata" in loaded_report


def test_generate_model_card():
    """Test model card generation."""
    model_info = {
        "model_type": "EBM",
        "hyperparameters": {"max_rounds": 100}
    }
    
    performance_metrics = {
        "roc_auc": 0.65,
        "f1_score": 0.45,
        "precision": 0.50,
        "recall": 0.40,
        "accuracy": 0.85
    }
    
    training_data_info = {
        "total_records": 100000,
        "total_features": 57,
        "target_distribution": {0: 0.9, 1: 0.1},
        "quality_score": 0.9
    }
    
    model_card = generate_model_card(
        model_info=model_info,
        performance_metrics=performance_metrics,
        training_data_info=training_data_info
    )
    
    assert "model_details" in model_card
    assert "intended_use" in model_card
    assert "training_data" in model_card
    assert "performance_metrics" in model_card
    assert "eu_ai_act_compliance" in model_card
    assert model_card["eu_ai_act_compliance"]["compliance_status"] == "not_a_conformity_decision"


def test_performance_tracker():
    """Test performance tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_file = os.path.join(tmpdir, "performance_tracking.json")
        
        tracker = PerformanceTracker(tracking_file=tracking_file)
        
        # Log performance
        metrics = {
            "roc_auc": 0.65,
            "f1_score": 0.45
        }
        
        tracker.log_performance(metrics, model_version="1.0.0")
        
        # Check that history was saved
        assert len(tracker.performance_history) == 1
        assert tracker.performance_history[0]["metrics"]["roc_auc"] == 0.65
        
        # Test drift detection
        current_metrics = {"roc_auc": 0.60, "f1_score": 0.40}
        drift_results = tracker.detect_drift(current_metrics, threshold=0.05)
        
        assert "drift_detected" in drift_results
        assert "metric_changes" in drift_results
        
        # Test summary
        summary = tracker.get_performance_summary()
        assert "total_logs" in summary
        assert "latest_metrics" in summary
        assert "metric_trends" in summary







