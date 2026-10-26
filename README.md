# Porto Seguro — Responsible AI Compliance Hub

> **Production-oriented Responsible AI vendor-agnostic reference architecture** for highly regulated industries. Designed to support technical due diligence and AI governance assessments under the **EU AI Act** and **Solvency II** frameworks.  
> **Not** an AEPD filing, GDPR certification, or EU AI Act conformity decision. Hold-out metrics alone do not prove regulatory compliance.

## Executive Architecture

Single-stack view for C-suite, compliance, and risk committees — five layers, one audit trail (demo evidence packs + in-process control plane).

```mermaid
flowchart TB
    subgraph DATA["① DATA LAYER"]
        direction LR
        D1["Porto Seguro · 595K policies"]
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
| **Inference API** | `python api_server.py` → `:8000` | `/predict` & `/batch_predict` wrapped by `execute_guarded` **in-process**; needs local artifacts for healthy inference |
| **ML pipeline** | `run_training.py` / `run_training_full.py` | Polars → feature engineering → EBM → explainability → monitoring; needs Kaggle `train.csv` locally |
| **CI governance job** | `.github/workflows/ci.yml` | Installs Streamlit + API deps; runs DPIA / control-plane / import-surface pytest only |

### Control plane limits (honest scope)

- **Single-process** singleton (`src/control_plane/`) — stop / approvals / circuit breaker do **not** replicate across workers.
- Audit JSONL is hash-chained but **not WORM** (file can be rewritten).
- Reviewer / requester strings are **not SSO** / authentication.
- Unclassified actions → **default-deny**; nested REDACT failures → fail-closed.
- Application calendar (Art. 113 after **2026/1744**): general application **2026-08-02**; Annex III high-risk duties **2027-12-02** — see `src/control_plane/regulatory_library.py` (encoded dates, not a live EUR-Lex fetch).

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

---

![Model Overview and Metadata Card](porto9.png)

---

## Endpoints

| Service | Command | URL |
|---------|---------|-----|
| **Model Card Dashboard** | `streamlit run app.py` | `http://localhost:8501` |
| **DPIA / EIPD (GDPR Art. 35)** | sidebar **DPIA GDPR** | `http://localhost:8501` |
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
| `eu_ai_act_conformity_v1.json` | Exportable evidence pack (demo; **not** a completed Art. 43 procedure) |
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
├── pages/                          # Overview, Performance, Compliance, DPIA…
├── tests/                          # Governance CI + optional ML unit tests
└── models/artifacts/               # Model, FE, threshold, SHA-256 (gitignored)
```

**ML path:** Polars load/validate → `ResponsibleFeatureEngineer` → EBM train/threshold → native explainability → API `predict_proba_ebm` → optional drift / production gate.

---

## Line report (bottom-up)

Operator facts first: [`docs/governance/LINE_REPORT.md`](docs/governance/LINE_REPORT.md).

```bash
pip install -r requirements_streamlit.txt -r requirements_api.txt
pip install pytest pandas numpy
python -m pytest tests/test_dpia_workspace.py tests/test_control_plane.py tests/test_import_surface.py -q
streamlit run app.py
```

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

- **Demo:** `streamlit run app.py` — walk through the Compliance Hub live
- **Evidence pack:** `eu_ai_act_conformity_v1.json` (technical evidence; not a conformity certificate)
- **Contact:** [Andrés Lage Freire on LinkedIn](https://www.linkedin.com/in/andres-lage-freire-4562a91b1) · open an issue in this repository

---

*Responsible AI demonstration project · EU AI Act & Solvency II evidence mapping · Polars + EBM architecture · no certification claimed*
