"""
Scheduled production compliance monitor (EU AI Act Art. 9).

Run recurrently via cron / Task Scheduler / CI:
    python run_production_monitor.py

Optional demo drift on ps_car_13:
    python run_production_monitor.py --simulate-drift
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Production drift & performance compliance gate")
    parser.add_argument(
        "--production-data",
        default=None,
        help="Optional CSV path for production batch (defaults to train.csv slice)",
    )
    parser.add_argument("--sample-size", type=int, default=5000)
    parser.add_argument("--production-sample-size", type=int, default=1000)
    parser.add_argument(
        "--simulate-drift",
        action="store_true",
        help="Inject demo covariate shift on ps_car_13 (Shadow Monitor test)",
    )
    parser.add_argument(
        "--refresh-audit",
        action="store_true",
        help="Regenerate docs/audit_results.json after monitoring run",
    )
    args = parser.parse_args()

    from src.monitoring.production_compliance_gate import run_scheduled_production_monitor

    logger.info("Starting production compliance gate...")
    report = run_scheduled_production_monitor(
        production_data_path=args.production_data,
        sample_size=args.sample_size,
        production_sample_size=args.production_sample_size,
        simulate_drift=args.simulate_drift,
    )

    status = report.get("overall_status", "unknown")
    passed = report.get("monitoring_passed", False)
    logger.info("Monitoring status: %s (monitoring_passed=%s)", status, passed)
    logger.info("Evidence: %s", report.get("evidence_path"))

    if args.refresh_audit:
        from utils.compliance_audit import run_full_compliance_audit

        logger.info("Refreshing compliance audit for EU AI Act dashboard...")
        run_full_compliance_audit(sample_size=10000)

    summary_path = Path("monitoring/latest_run_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "overall_status": status,
                "monitoring_passed": passed,
                "alerts": report.get("alerts", []),
                "evidence_path": report.get("evidence_path"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
