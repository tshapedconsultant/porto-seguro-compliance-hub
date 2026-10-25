"""
Performance Tracking Module
Part of Insurance Claim Prediction - Responsible AI Architecture

Model monitoring for:
- Performance drift detection
- Data quality monitoring
- Explainability tracking
"""

import json
from typing import Dict, Optional, List
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Track model performance over time for monitoring and governance.
    """
    
    def __init__(self, tracking_file: Optional[str] = None):
        """
        Initialize performance tracker.
        
        Args:
            tracking_file: Optional path to JSON file for persistence
        """
        self.tracking_file = tracking_file
        self.performance_history: List[Dict] = []
        
        # Load existing history if file exists
        if tracking_file:
            try:
                with open(tracking_file, 'r') as f:
                    self.performance_history = json.load(f)
            except FileNotFoundError:
                logger.info(f"Creating new tracking file: {tracking_file}")
    
    def log_performance(
        self,
        metrics: Dict,
        model_version: str = "1.0.0",
        dataset_info: Optional[Dict] = None
    ):
        """
        Log model performance metrics.
        
        Args:
            metrics: Performance metrics dictionary
            model_version: Model version identifier
            dataset_info: Optional dataset information
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model_version": model_version,
            "metrics": metrics,
            "dataset_info": dataset_info or {}
        }
        
        self.performance_history.append(log_entry)
        
        # Save to file if tracking file specified
        if self.tracking_file:
            with open(self.tracking_file, 'w') as f:
                json.dump(self.performance_history, f, indent=2)
        
        logger.info(f"Logged performance metrics for version {model_version}")
    
    def detect_drift(
        self,
        current_metrics: Dict,
        baseline_metrics: Optional[Dict] = None,
        threshold: float = 0.05
    ) -> Dict:
        """
        Detect performance drift compared to baseline.
        
        Args:
            current_metrics: Current performance metrics
            baseline_metrics: Baseline metrics (or latest from history)
            threshold: Threshold for drift detection (relative change)
            
        Returns:
            dict: Drift detection results
        """
        if baseline_metrics is None and len(self.performance_history) > 0:
            baseline_metrics = self.performance_history[-1]["metrics"]
        elif baseline_metrics is None:
            return {
                "drift_detected": False,
                "message": "No baseline available for comparison"
            }
        
        drift_results = {
            "drift_detected": False,
            "metric_changes": {},
            "warnings": []
        }
        
        # Compare key metrics
        key_metrics = ["roc_auc", "f1_score", "precision", "recall"]
        
        for metric in key_metrics:
            if metric in current_metrics and metric in baseline_metrics:
                baseline_val = baseline_metrics[metric]
                current_val = current_metrics[metric]
                
                if baseline_val > 0:
                    relative_change = (current_val - baseline_val) / baseline_val
                    drift_results["metric_changes"][metric] = {
                        "baseline": baseline_val,
                        "current": current_val,
                        "relative_change": relative_change,
                        "absolute_change": current_val - baseline_val
                    }
                    
                    # Detect significant drift
                    if abs(relative_change) > threshold:
                        drift_results["drift_detected"] = True
                        drift_results["warnings"].append(
                            f"Significant drift in {metric}: {relative_change:.2%} change"
                        )
        
        return drift_results
    
    def get_performance_summary(self) -> Dict:
        """
        Get summary of performance history.
        
        Returns:
            dict: Performance summary
        """
        if not self.performance_history:
            return {"message": "No performance history available"}
        
        # Extract metrics over time
        summary = {
            "total_logs": len(self.performance_history),
            "latest_metrics": self.performance_history[-1]["metrics"],
            "metric_trends": {}
        }
        
        # Calculate trends for key metrics
        key_metrics = ["roc_auc", "f1_score", "precision", "recall"]
        
        for metric in key_metrics:
            values = [
                entry["metrics"].get(metric, 0) 
                for entry in self.performance_history 
                if metric in entry["metrics"]
            ]
            if values:
                summary["metric_trends"][metric] = {
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                    "latest": values[-1]
                }
        
        return summary

    def export_timeline(self) -> Dict:
        """Export ROC-AUC timeline for Streamlit drift dashboard charts."""
        timeline = []
        for entry in self.performance_history:
            metrics = entry.get("metrics", {})
            if "roc_auc" not in metrics:
                continue
            date_str = entry.get("timestamp", "")[:10] or "unknown"
            timeline.append(
                {
                    "Date": date_str,
                    "ROC-AUC": float(metrics["roc_auc"]),
                    "model_version": entry.get("model_version", "unknown"),
                }
            )
        return {"timeline": timeline}




