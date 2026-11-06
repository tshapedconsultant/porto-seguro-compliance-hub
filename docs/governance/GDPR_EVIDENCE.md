# GDPR evidence block

Technical assessment embedded in `eu_ai_act_conformity_v1.json` and `gdpr_dpia_v1.json`. **Not** a legal determination, AEPD filing, or GDPR certification.

Generator: `src/governance/gdpr_evidence.py`  
Schema: `docs/schemas/gdpr_evidence.schema.json` (`schema_version` **1.0.0** of the block)  
Parent unified report remains `schema_version` **1.1.0** (additive `gdpr` key; existing consumers can ignore it).

## Demo scope

- Dataset: Porto Seguro Safe Driver Prediction (Kaggle), `ps_*` columns described by the publisher as anonymised.
- This software does **not** decide Recital 26 anonymity. Publisher wording ≠ GDPR non-applicability.
- Demo vs production: a live underwriting, pricing, or claims system on identifiable persons is a **distinct processing operation**.
- Fairness proxy metrics (`ps_ind_03`, `ps_reg_03`, `ps_car_13`) are listed as audit inputs only. They are **not** GDPR Art. 5(1)(a) evidence and the generator does not collect protected attributes.

## What the block records

Each evaluation uses:

| Field | Meaning |
|---|---|
| `applicability` | `unknown` \| `applicable` \| `not_applicable` |
| `evidence_status` | `missing` \| `partial` \| `available` (file exists and is readable) |
| `control_status` | `not_tested` \| `passed` \| `failed` \| `not_applicable` |
| `owner` / `reviewer` / `reviewed_at` | `null` when unknown — never invented |

Rules enforced in code:

- Evidence present ≠ control tested ≠ conformity.
- `not_applicable` requires a substantial justification; publisher anonymisation **cannot** set the Recital 26 section to `not_applicable`.
- `passed` requires `evidence_status=available` **and** at least one local `kind=test` ref inside the repo.
- Incomplete sections keep `review_required: true`.
- No `gdpr_compliant: true` or certification flags.
- Human review does **not** prove Art. 22 is inapplicable.
- Consent is **not** selected as a default Art. 6 basis.
- Evidence paths must stay inside the repository (no `..`, no absolute paths).

## Official sources (not fetched live)

This run **did not** retrieve EUR-Lex or AEPD pages. Citations are encoded:

- Regulation (EU) 2016/679 — [ELI](https://eur-lex.europa.eu/eli/reg/2016/679/oj) (OJ L 119, 4.5.2016). Recital 26; Arts. 4–6, 9, 12–22, 24–25, 28, 30, 32–37, 44–49.
- EDPB WP248 rev.01 — Guidelines on DPIA.
- AEPD practical EIPD guidance (lists of treatments are **informative**, not exhaustive — Art. 35(4)–(5)).

Re-verify the legal text on EUR-Lex / AEPD before relying on a citation in a live file.

## Pending decisions (legal / DPO — not this software)

- GDPR applicability of the demo file (identifiability / Recital 26).
- Controller, processor, DPO.
- Art. 6 basis and any Art. 9 condition (do not default to consent).
- Art. 22 (effects, exclusive automation, effective intervention, Art. 22(3) safeguards).
- Signed Art. 35 EIPD; Art. 36 only if residual high risk remains after mitigations.
- Retention, Art. 30 records, Arts. 33–34 incident procedures.
- Processors and international transfers for any hosted deployment.

## Commands

```bash
python -c "from src.governance.gdpr_evidence import merge_gdpr_into_evidence_packs; merge_gdpr_into_evidence_packs()"
python -m pytest tests/test_gdpr_evidence.py tests/test_evidence_schemas.py tests/test_governance.py tests/test_import_surface.py -q
```

The first command upserts the `gdpr` key into the two published packs **without rewriting sibling fairness metrics**.
