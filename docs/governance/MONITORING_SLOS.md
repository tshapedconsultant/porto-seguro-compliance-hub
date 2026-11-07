# Monitoring SLOs

Operational screens for KS drift, performance degradation, calibration, fairness
screening, the shadow monitor, and the production gate.

**Detection is not a decision.** An open alert is a technical signal. It does not
retrain, promote, price, or close a legal issue. It is **not** a finding of
discrimination, an Art. 43 conformity result, or a GDPR determination.

Generator: `src/monitoring/slo.py`  
Schema: `docs/schemas/monitoring_slo.schema.json` (`schema_version` **1.0.0**)  
Alert sub-schema: `docs/schemas/monitoring_slo_alert.schema.json`

`evidence_integrity` is a checksum of the report body (`artifact_hash`) plus per-ref hashes. It is **not** a signature, WORM store, or legal seal. If a path exists, the hash is of file bytes; otherwise it is the SHA-256 of the ref string (no invented file SHA).

## Alert fields

| Field | Meaning |
|---|---|
| `condition` | What was measured and the internal threshold |
| `severity` | `critical` \| `high` \| `medium` \| `low` |
| `owner` | Named person, or `unassigned` — never invented |
| `required_action` | Technical next step; not a legal conclusion |
| `deadline` | ISO-8601 duration (`P1D` / `P2D` / `P5D`) from the moment the alert opens |
| `evidence` | Pointers to the detecting payload (`missing` if the signal was not supplied) |
| `status` | SLO: `not_evaluated` \| `within_slo` \| `breached`. Alert: `open` \| `acknowledged` \| `in_progress` \| `resolved` |

`not_evaluated` is **not** `within_slo`. A missing shadow run or missing ECE is a gap.

## Rules enforced in code

- The generator never emits `resolved`.
- `resolve_alert(...)` requires non-empty evidence refs; otherwise it raises.
- `business_decision` stays `not_taken` / `not_inferred` on generation and on resolve.
- Fairness alerts must not state discrimination.
- Detection evidence (`sufficient_to_resolve: false`) is not enough to close the ticket.

## Catalog (internal heuristics, not legal thresholds)

| SLO | Condition | Severity | Deadline |
|---|---|---|---|
| `mon.ks_drift` | Feature or mean KS > 0.10 vs reference | high | P2D |
| `mon.performance_degradation` | Relative drop > 5% vs hold-out baseline | high | P2D |
| `mon.calibration_drift` | ECE or max absolute calibration error > 0.05 | medium | P5D |
| `mon.fairness_screening` | `review_required` or fail / pass_with_review | high | P2D |
| `mon.shadow_monitor` | Did not run, missing artifacts, or KS health check fired | medium | P2D |
| `mon.production_gate` | `monitoring_passed` is false | critical | P1D |

The 0.10 KS gate and 5% drop are the same internal screens as
`src/monitoring/drift_monitoring.py`. They are not EDPB, AEPD, or Art. 9 legal limits.

## Commands

```bash
python -c "from src.monitoring.slo import build_monitoring_slo_report; print(build_monitoring_slo_report()['open_alert_count'])"
python -m pytest tests/test_monitoring_slos.py -q
```
