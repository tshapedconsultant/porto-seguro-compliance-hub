# Porto Seguro — Responsible AI Compliance Hub

> **Production-oriented Responsible AI vendor-agnostic reference architecture** for highly regulated industries. Designed to support technical due diligence and AI governance assessments under the **EU AI Act** and **Solvency II** frameworks.
>
> **Dataset:** anonymized Kaggle Porto Seguro Safe Driver Prediction (`ps_*`, 595,212 rows) — **not** a live insurance book or identifiable policyholders.
>
> **Not** an AEPD filing, a signed EIPD, GDPR certification, an EU AI Act conformity decision, or an Art. 36 prior consultation. Hold-out metrics and demo packs are technical evidence; they do not prove regulatory compliance.

**Repo:** [tshapedconsultant/porto-seguro-compliance-hub](https://github.com/tshapedconsultant/porto-seguro-compliance-hub) · **site:** [tshapedconsultant.com](https://tshapedconsultant.com/#projects) · [ES](https://tshapedconsultant.com/es/#projects)

## Executive Architecture

Single-stack view for C-suite, compliance, and risk committees — five layers, one audit trail (demo evidence packs + in-process control plane).

```mermaid
flowchart TB
    subgraph DATA["① DATA LAYER"]
        direction LR
        D1["Kaggle Porto Seguro · 595K anonymized rows"]
        D2["Polars ingestion & validation"]
        D3["Art. 10 — dataset traceability"]
    end

    subgraph MODEL["② MODEL LAYER"]
        direction LR
        M1["EBM glass-box classifier"]
        M2["Native explainability"]
        M3["Optimal threshold · hold-out test"]
    end

    subgraph GOV["③ GOVERNANCE LAYER"]
        direction LR
        G1["Bias audit · proxy fairness"]
        G2["Adversarial robustness · Art. 15"]
        G3["Human oversight routing · Art. 14"]
    end

    subgraph MON["④ MONITORING LAYER"]
        direction LR
        N1["KS drift · asymmetric alerts"]
        N2["Shadow Monitor · off hot path"]
        N3["Production compliance gate · Art. 9"]
    end

    subgraph EVD["⑤ EVIDENCE LAYER"]
        direction LR
        E1["JSON audit packs"]
        E2["Streamlit Model Card"]
        E3["CI/CD deploy gate"]
    end

    DATA ==> MODEL ==> GOV ==> MON ==> EVD

    style DATA fill:#e8f4fc,stroke:#1a73e8
    style MODEL fill:#e6f4ea,stroke:#34a853
    style GOV fill:#fef7e0,stroke:#f9ab00
    style MON fill:#fce8e6,stroke:#ea4335
    style EVD fill:#f3e8fd,stroke:#9334e6
```

| Layer | Business question | Regulatory anchor |
|-------|-------------------|-------------------|
| **Data** | Is the training data complete, representative, and leakage-free? | EU AI Act **Art. 10** |
| **Model** | Can we explain every prediction to an underwriter or auditor? | EU AI Act **Art. 13** |
| **Governance** | Is the model fair, robust, and subject to human review? | **Art. 14** · **Art. 15** |
| **Monitoring** | Do we detect drift before it harms the portfolio? | EU AI Act **Art. 9** |
| **Evidence** | Can we show technical evidence to reviewers and Solvency II stakeholders? | **Annex IV** · Solvency II (evidence ≠ certification) |

### What runs locally vs what is demo-only

| Surface | Command / path | Demo vs readiness |
|---------|----------------|-------------------|
| **Streamlit Model Card** | `streamlit run app.py` → `:8501` | Starts on a clean clone **without** `train.csv` / `.pkl` |
| **DPIA / EIPD page** | Sidebar **DPIA GDPR** | Static pack `gdpr_dpia_v1.json` + optional workspace under `src/governance/dpia_workspace/` (assessments **not** published) |
| **Governed Decision Demo** | Sidebar **Governed Decision Demo** (`pages/09_…`) | Control-room walkthrough: DENY / HITL ticket / redact / local hash chain. `?lang=en\|es` |
| **AEPD EIPD Demo (~90s)** | Sidebar **AEPD EIPD Demo** (`pages/10_…`) | EIPD narrative: processing → rights risk → control → evidence → residual. Dataset is **anonymized Kaggle** (595,212 rows), not a live insurance book |
| **Recorded walkthroughs** | `record_demo.bat` · `record_demo.bat --es` · `record_demo.bat --aepd` | ffmpeg desktop + muxed VO (Edge fullscreen, Cursor minimized). **Not** Xbox Game Bar. Outputs under `%USERPROFILE%\Videos\Captures\` |
| **Inference API** | `python api_server.py` → `:8000` | `/predict` & `/batch_predict` wrapped by `execute_guarded` **in-process**; needs local artifacts for healthy inference |
| **ML pipeline** | `run_training.py` / `run_training_full.py` | Polars → feature engineering → EBM → explainability → monitoring; needs Kaggle `train.csv` locally |
| **CI governance job** | `.github/workflows/ci.yml` | Job `tests` (mandatory on every push/PR): control-plane + API security. Job `ml-synthetic` only on ML path changes, weekly cron, or `workflow_dispatch` — **no** `continue-on-error`; if that job runs and fails, the workflow fails |

### Walkthroughs (two cuts)

Technical evidence for lab / stakeholder review. **Not** a signed EIPD and **not** an Art. 36 filing.

| Cut | Page | How to record | What it shows | Published |
|-----|------|---------------|---------------|-----------|
| **AEPD EIPD (~90 s, Castilian)** | `pages/10_AEPD_EIPD_Demo.py` → `/AEPD_EIPD_Demo` | `record_demo.bat --aepd` | EIPD as the story: identify the processing (Kaggle, anonymized) → necessity and risks to rights → a live control (DENY before the model, single-use HITL ticket, fail-closed redact) → inspect the local hash chain → residual scores *estimated pending verification* → limits | [Spanish site · 05](https://tshapedconsultant.com/es/#projects) (`porto-seguro-aepd-es.mp4`) |
| **Control room (~2:20)** | `pages/09_Governed_Decision_Demo.py` → `/Governed_Decision_Demo` | `record_demo.bat` (EN) · `record_demo.bat --es` | Runtime evidence: policy DENY (model never invoked) → bound single-use approval → anti-replay → redact → `verify_chain()` → clumsy JSONL rewrite detected. Local hash chain ≠ WORM | [English site · 05](https://tshapedconsultant.com/#projects) (`porto-seguro-governed-en.mp4`); ES control-room cut on the Spanish card |

Capture is `docs/governance/auto_record_demo.py`: Edge fullscreen, Cursor minimized, ffmpeg `gdigrab`, continuous ElevenLabs VO muxed into the MP4. Xbox Game Bar is **not** used (it captured the IDE and dropped audio).

Playbooks: [`DEMO_PLAYBOOK.md`](docs/governance/DEMO_PLAYBOOK.md) (ES, AEPD-facing) · [`DEMO_PLAYBOOK_EN.md`](docs/governance/DEMO_PLAYBOOK_EN.md).

### Control plane limits (honest scope)

- **Single-process** singleton (`src/control_plane/`) — stop / approvals / circuit breaker do **not** replicate across workers.
- Audit JSONL is append-only + hash-chained + local checkpoint sidecar (+ optional `AUDIT_HMAC_KEY`) — **not WORM / not KMS** (dual-rewrite of JSONL + checkpoint defeats local check).
- Reviewer / requester strings are **not SSO** / authentication (no OIDC/JWT).
- Unclassified actions → **default-deny**; nested REDACT failures → fail-closed.
- Application calendar (Art. 113 after **2026/1744**): general application **2026-08-02**; Annex III high-risk duties **2027-12-02** — see `src/control_plane/regulatory_library.py` (encoded dates, not a live EUR-Lex fetch).
- **No GDPR / EU AI Act certification** — evidence packs and UI are lab artefacts, not AEPD / notified-body conformity.
- **Demo data ≠ live book** — Kaggle Porto Seguro Safe Driver Prediction (`ps_*`, 595,212 anonymized rows). Controller / DPO sign-off in the EIPD pack are **hypothetical / pending**.
- **Residual scores** in `gdpr_dpia_v1.json` are **estimated pending verification**. Human review remains required. A local hash chain is **not** immutable external audit storage.
- **Not an Art. 36 filing** — the EIPD pack and AEPD demo are a technical reference for evaluation, not a supervisory notification or prior consultation.

### What this still is not

Honest gaps (demo / lab). Pragmatic mitigations raise the bar; they do **not** close production threat models.

1. **Audit integrity ≠ WORM / KMS** — Checkpoint + JSONL (and optional HMAC) are filesystem-rewritable. They detect clumsy tamper, not an attacker with FS access who rewrites both files (and forges HMAC if they know `AUDIT_HMAC_KEY`). Production needs an external append-only / Object Lock store + KMS sign + independent verify. `AUDIT_HMAC_KEY` is a **shared secret**, not KMS.
2. **`approvals.json` is authoritative and mutable** — Audit trail visibility ≠ prevent ticket edit. `ApprovalStore.verify_against_audit()` (+ optional `APPROVAL_AUDIT_STRICT`) detects obvious JSON↔audit desync; it does not make tickets immutable. Production needs Postgres/Redis transactions + append-only audit. `APPROVAL_BACKEND=memory|json` only (`redis`/`postgres` are interface stubs — not implemented).
3. **`STOP_FILE` is an emergency brake, not transactional** — In-flight work may finish after the file appears. Predict: pre-check + post-check; if the file appears mid-flight, result still returns with `interrupted_by_stop=True` and audit `stop_during_execution`. Export-like (external-effect) actions use pre-check only. API `/predict` also pre-checks at the edge.
4. **Worker / replica detection is best-effort** — `WEB_CONCURRENCY` / `UVICORN_WORKERS` / `WORKERS` miss horizontal replicas (1 worker × N containers). Optional `INSTANCE_ID` + `CONTROL_PLANE_LEASE_DIR` FS heartbeats (TTL ~60s); with `CONTROL_PLANE_STRICT` and >1 recent distinct instance IDs → refuse start. Cheap filesystem lease — **not Redis**.
5. **Rate limit is local** — `RATE_LIMIT_BACKEND=memory|disabled`. No shared backend. Prefer disabled + gateway (nginx / Cloudflare / API Gateway / APIM).
6. **API key is static** — No identity, expiry, revocation, or scopes. Optional `APPROVAL_API_KEY` for `/approvals/decide` and `APPROVAL_SEPARATE_ACTORS=true` (reject reviewer==requester) are SoD demos — **still not OIDC**.

### Deployment limits / not multi-worker safe

See **What this still is not** above. Additional IP trust note:

- **TRUST_PROXY / client IP** — `X-Forwarded-For` is spoofable unless the immediate TCP peer is allowlisted via `TRUSTED_PROXY_IPS` / `TRUSTED_PROXY_CIDRS`. If `TRUST_PROXY=true` with an empty allowlist, XFF is **ignored** (fail closed). When the peer is trusted, the **leftmost** XFF hop is used (single reverse-proxy pattern).

### Governance & assurance docs

- [`docs/governance/LINE_REPORT.md`](docs/governance/LINE_REPORT.md) — Bottom-up operator facts, test coverage, and assurance boundaries
- [`docs/ROADMAP_V2.md`](docs/ROADMAP_V2.md) — Plan to make this a deployable service (phases 0–8). **Not implemented.** Does not claim conformity
- [`docs/governance/DEMO_PLAYBOOK.md`](docs/governance/DEMO_PLAYBOOK.md) — ES (AEPD-facing): EIPD 90‑s cut + control-room sequence + ticket lifecycle (technical evidence; not certification)
- [`docs/governance/DEMO_PLAYBOOK_EN.md`](docs/governance/DEMO_PLAYBOOK_EN.md) — English mirror of the demo playbook
- Conformity packs (demo artefacts): [`eu_ai_act_conformity_v1.json`](eu_ai_act_conformity_v1.json) · [`gdpr_dpia_v1.json`](gdpr_dpia_v1.json)

### Threat & Governance Scope

**Threats addressed**

- Data drift
- Model degradation
- Fairness regressions
- Documentation gaps
- Auditability failures
- Human oversight failures

**Out of scope**

- Adversarial prompt injection
- Agentic AI runtime controls
- LLM security threats
- Supply-chain security
- Formal EIPD submission / AEPD Art. 36 prior consultation
- Processing a live insurance book or identifiable policyholders
- WORM / Object Lock / KMS-signed audit (local JSONL + checkpoint only)

### Roadmap to production (P0 — not implemented here)

Short list. Full service roadmap (identity, shared state, durable evidence, ops, pilot): [`docs/ROADMAP_V2.md`](docs/ROADMAP_V2.md). Shipping that document does **not** close the gaps.

| Gap | Honest status | Next concrete step |
|-----|---------------|--------------------|
| Shared stop / approvals / circuit breaker | In-process; `STOP_FILE` + optional FS lease | Redis (or equivalent) shared state + sticky docs |
| API auth | Static `API_KEY` / optional `APPROVAL_API_KEY` | OIDC/JWT with IdP; drop UI role spoofing |
| Immutable audit | JSONL + checkpoint + optional HMAC (not KMS) | S3 Object Lock / WORM + KMS + independent verify |
| Approval authority | Mutable JSON + audit desync check | Postgres/Redis transactions + append-only audit |
| Multi-replica rate limit | In-memory demo limiter | Gateway rate limit; no Redis backend here |
| Evidence vs effectiveness | Assurance fields on JSON packs | Operational owners + scheduled control tests |
| Live book + signed EIPD | Kaggle `ps_*`; DPO sign-off hypothetical | Separate processing; unsigned workspace must not enable live `/predict` |
| Artifact pin | SHA-256 sidecars; `REQUIRE_ARTIFACT_HASH` off by default | Default **on** in a production profile |

---

![Model Overview and Metadata Card](porto9.png)

---

## Endpoints

| Service | Command | URL |
|---------|---------|-----|
| **Model Card Dashboard** | `streamlit run app.py` | `http://localhost:8501` |
| **DPIA / EIPD (GDPR Art. 35)** | sidebar **DPIA GDPR** | `http://localhost:8501` |
| **Governed Decision Demo** | sidebar page 09 · `record_demo.bat` | `http://localhost:8501/Governed_Decision_Demo` |
| **AEPD EIPD 90s Demo** | sidebar page 10 · `record_demo.bat --aepd` | `http://localhost:8501/AEPD_EIPD_Demo` |
| **Inference API Gateway** | `python api_server.py` | `http://localhost:8000` |
| **Compliance Monitor** | `POST /compliance/monitor` | `http://localhost:8000/compliance/monitor` |

---

## Reference Metrics (Hold-Out Test)

![Model Performance Executive Panel](porto8.png)

| Metric | Value | Note |
|--------|-------|------|
| **ROC-AUC** | 0.639 | Realistic Kaggle benchmark for highly imbalanced fraud/claim data. |
| **F1 @ Optimal Threshold** | **0.117** | Optimized at `0.059` vs. `0.003` at default threshold `0.5`. |
| **Precision** | 0.078 | Expected profile for imbalanced classes — ROC-AUC remains primary metric. |
| **Recall** | 0.228 | Tuned specifically for claim detection at a low-risk threshold. |
| **Accuracy** | ~87% | **Misleading** on imbalanced data — see the Business Context tab. |

These metrics are **technical performance evidence**. They are not a GDPR, AEPD, or AI Act conformity finding.

### Baseline Comparison Context

![ROC-AUC vs Competitive Baselines](porto7.png)

| Model | ROC-AUC |
|-------|---------|
| Random baseline | 0.50 |
| Naive (always no claim) | 0.50 |
| **Our EBM model** | **0.64** |
| Top Kaggle models | ~0.65 |

> ⚠️ **Production Safeguard:** Do not use `sample_size=10000` for production metrics validation. See detailed protocols in `docs/METRIC_VALIDATION.md` when present locally.

---

## JSON Evidence for Auditors

The architecture materializes audit logs into evidence packs for the dashboard. Status fields use **technical evidence** language (`not_a_conformity_decision` / evidence present) — not a legal “Compliant” stamp.

![EU AI Act Compliance Mapping - Articles 9, 10, 13](porto3.png)
![EU AI Act Compliance Mapping - Articles 14, 15, Annex IV](porto2.png)

| File | Content |
|------|---------|
| `docs/compliance_report.json` | Unified EU AI Act + Solvency II report (local / generated) |
| `docs/audit_results.json` | Per-pillar technical evidence status (local / generated) |
| `docs/drift_monitoring_latest.json` | Latest data drift gate check (Art. 9) |
| `docs/robustness_results.json` | Adversarial red teaming and noise tests (Art. 15) |
| `eu_ai_act_conformity_v1.json` | Exportable evidence pack (demo; **not** a completed Art. 43 procedure); `schema_version` + assurance fields |
| `gdpr_dpia_v1.json` | GDPR Art. 35 DPIA / EIPD pack (AEPD innovation-lab walkthrough; not a supervisory filing) |
| `training_results.json` | Hold-out metrics + optimal threshold parameters (local) |
| `monitoring/performance_history.json` | Production ROC-AUC historical logs (local) |

**EIPD static pack vs workspace:** `gdpr_dpia_v1.json` is the published demo pack. Editable assessments live under `src/governance/dpia_workspace/` with files in `docs/governance/assessments/` (gitignored). Residual scores in the static pack are **estimated pending verification**.

---

## Why This Stack for Insurance & Life Sciences

### 1. Explainable Boosting Machines (EBM)

Native glass-box explainability via Microsoft InterpretML — no production dependency on unstable SHAP/LIME wrappers.

* **Global Interpretability:** Feature importance across the population.

  ![Global Feature Importance Analysis](porto6.png)

* **Local Interpretability:** Per-prediction feature contributions for case review.

  ![Local Feature Contributions Profile](porto5.png)

### 2. High-Performance Data Processing (Polars)

Processes the 595K-row training set with headroom for larger production volumes without rewriting the pipeline shape.

### 3. Asymmetric Drift Guardrails

Kolmogorov–Smirnov gates isolate structural shifts from harmless variance.

![Data Drift Statistical Monitor Plot](porto1.png)

| Feature | Drift score | Status |
|---------|-------------|--------|
| `ps_car_12` … `ps_calc_02` | 0.025 – 0.042 | Healthy |
| **`ps_car_13`** (simulated shift) | **0.934** | **Alert** |

### 4. Privacy-by-Design Fairness Optimization

Proxy-based bias audits when sensitive demographics cannot be collected under privacy rules. Demo dataset ≠ Recital 26 determination.

![Demographic Parity and Equalized Odds Verification Table](porto4.png)

| Protected attribute (proxy) | Demographic parity disparity | Equal opportunity | Status |
|-----------------------------|------------------------------|-------------------|--------|
| `risk_proxy_ps_ind_03` | 0.0011 | TPR Δ 0.0075 / FPR Δ 0.0008 | Pass |
| `region_proxy_ps_reg_03` | 0.0419 | TPR Δ 0.0925 / FPR Δ 0.0400 | Pass |
| `vehicle_proxy_ps_car_13` | 0.0594 | TPR Δ 0.0942 / FPR Δ 0.0559 | Pass |

---

## Project Structure

```
porto-seguro/
├── app.py                          # Streamlit Model Card entrypoint
├── api_server.py                   # FastAPI + execute_guarded predict
├── record_demo.bat                 # Auto walkthrough (ffmpeg + VO; --es / --aepd)
├── run_training.py                 # MLOps pipeline (needs train.csv)
├── run_training_full.py / quick    # Full / quick training variants
├── run_production_monitor.py       # Recurring Art. 9 monitor
├── eu_ai_act_conformity_v1.json    # Demo evidence pack (not Art. 43)
├── gdpr_dpia_v1.json               # GDPR Art. 35 DPIA / EIPD demo pack
├── src/
│   ├── data_processing/            # Polars: load, FE, validation
│   ├── models/                     # EBM, evaluation, explainability
│   ├── governance/                 # Bias audit, EIPD workspace, reporting
│   ├── control_plane/              # Policies, approvals, runtime adapter
│   └── monitoring/                 # Drift, production gate, tracker
├── pages/
│   ├── 09_Governed_Decision_Demo.py
│   └── 10_AEPD_EIPD_Demo.py        # EIPD ~90 s narrative (not Art. 36)
├── docs/governance/
│   ├── DEMO_PLAYBOOK.md            # ES, AEPD-facing
│   ├── auto_record_demo.py         # ffmpeg gdigrab + muxed VO
│   └── demo_assets/                # architecture / lifecycle / hash-chain diagrams
├── tests/                          # Governance CI + optional ML unit tests
└── models/artifacts/               # Model, FE, threshold, SHA-256 (gitignored)
```

**ML path:** Polars load/validate → `ResponsibleFeatureEngineer` → EBM train/threshold → native explainability → API `predict_proba_ebm` → optional drift / production gate.

---

## Line report (bottom-up)

Operator facts first: [`docs/governance/LINE_REPORT.md`](docs/governance/LINE_REPORT.md).  
Demo playbook (Mermaid + scripts): [`docs/governance/DEMO_PLAYBOOK.md`](docs/governance/DEMO_PLAYBOOK.md) (ES) · [`DEMO_PLAYBOOK_EN.md`](docs/governance/DEMO_PLAYBOOK_EN.md) (EN).

```bash
pip install -r requirements_streamlit.txt -r requirements_api.txt
pip install pytest pandas numpy
# Same as CI job `tests` (governance + API security). Does not train; does not need train.csv.
python -m pytest tests/test_dpia_workspace.py tests/test_control_plane.py tests/test_control_plane_security.py tests/test_api_security.py tests/test_import_surface.py -q
streamlit run app.py
```

Job `ml-synthetic` (path filter, Sunday 06:00 UTC, or Actions → Run workflow) is **not** the command above. It installs `requirements-ml.lock` (or `requirements-ml.txt`) and runs the EBM/FE/drift/robustness suite. There is no `continue-on-error`.

A clean clone starts the Model Card, DPIA and EU AI Act pages without `train.csv` or `.pkl` artifacts (gitignored). Full training still needs the Kaggle file locally. `/predict` is wrapped by `execute_guarded` **in-process only**.

Optional ML suite (needs `pip install -r requirements.txt` / interpret + polars):

```bash
python -m pytest tests/test_data_processing.py tests/test_feature_engineering.py tests/test_proper_pipeline.py tests/test_governance.py -q
# EBM / explainability tests skip automatically if interpret is missing
```

Static EIPD residual scores are **estimated pending verification**. No AEPD / GDPR / AI Act certification is claimed.

---

## Quick Start

```bash
pip install -r requirements.txt
pip install -r requirements_streamlit.txt
pip install -r requirements_api.txt

# Place train.csv (Kaggle Porto Seguro) in project root
python run_training.py
python run_production_monitor.py --refresh-audit
streamlit run app.py
# optional API (artifacts required for healthy /predict)
python api_server.py
```

> **GitHub clone:** `train.csv`, model `.pkl` files, and generated local JSON reports are gitignored. After cloning, add the dataset and run the pipeline above for full ML evidence.

---

## References

- [Porto Seguro — Kaggle](https://www.kaggle.com/c/porto-seguro-safe-driver-prediction)
- [Microsoft InterpretML / EBM](https://github.com/interpretml/interpret)
- [EU AI Act — High-risk AI systems](https://artificialintelligenceact.eu/)
- [Polars](https://pola-rs.github.io/polars/)

---

## Let's Talk

This project is a **production-oriented Responsible AI reference architecture** for regulated industries — designed to support technical due diligence and AI governance assessments from compliance, actuarial, and cybersecurity stakeholders.

- **Live hub:** `streamlit run app.py` — Model Card, DPIA, EU AI Act, governed decision, AEPD EIPD
- **Walkthroughs:** [EN control room](https://tshapedconsultant.com/#projects) · [ES AEPD ~90 s](https://tshapedconsultant.com/es/#projects) (technical evidence; not a filing)
- **Evidence packs:** `eu_ai_act_conformity_v1.json` (not Art. 43) · `gdpr_dpia_v1.json` (residuals *estimated pending verification*; not Art. 36)
- **V2 service roadmap:** [`docs/ROADMAP_V2.md`](docs/ROADMAP_V2.md) (plan only; not a claim the gaps are closed)
- **Contact:** [Andrés Lage Freire on LinkedIn](https://www.linkedin.com/in/andres-lage-freire-4562a91b1) · open an issue in this repository

---

*Responsible AI demonstration project · EU AI Act & Solvency II evidence mapping · Polars + EBM architecture · no certification claimed*
