# LINE REPORT — Porto Seguro Compliance Hub

**Formato:** bottom-up / line-first. Primero lo que hay en el terreno, después lo que la línea puede hacer ahora, después la intención y el relato de estado mayor.  
**No es** aprobación AEPD, certificación RGPD ni certificación del Reglamento de IA.

---

## 1. TERRENO (bottom)

Hechos en disco, no intenciones.

| Pieza | Ruta | Estado |
|---|---|---|
| Pack EIPD estático | `gdpr_dpia_v1.json` | Presente (demo / laboratorio; no es expediente AEPD) |
| Motor EIPD (workspace) | `src/governance/dpia_workspace/` | Código presente; assessments en `docs/governance/assessments/` **locales, no publicadas** |
| Motor de políticas | `src/control_plane/` | Código presente; singleton **por proceso**; auditoría JSONL **no** WORM; **no** SSO; `STOP_FILE` opcional |
| Página Streamlit pack | `pages/08_DPIA_GDPR.py` | Pack JSON + descarga; copy AEPD en español |
| Model Card | `app.py` + `pages/*` | Arranca sin `train.csv` / `.pkl` (artefactos gitignored) |
| API predicción | `api_server.py` `/predict` y `/batch_predict` | Pasan por `execute_guarded` **en este proceso**; rate limit in-memory demo; TRUST_PROXY con allowlist |
| Pipeline ML | `src/data_processing/` → `src/models/` → `src/monitoring/` | Polars → FE → EBM → explainability → gate; scripts `run_training*.py` |
| Tests de borde | `tests/test_dpia_workspace.py`, `tests/test_control_plane.py`, `tests/test_import_surface.py` | CI instala Streamlit + API (`polars`/`joblib`); REDACT anidado fail-closed; hash EIPD; Annex III **2027-12-02** (tras 2026/1744) |
| Tests ML (opcionales) | `tests/test_*` data/EBM/drift/explainability | En repo; skip si faltan `polars`/`interpret`; **no** son el job CI de gobernanza |
| Persistencia EIPD | `docs/governance/assessments/*.json` | Local; **no** se publica en GitHub |
| Auditoría control plane | JSONL append-only + hash + checkpoint local | No es WORM; el fichero se puede reescribir |
| Threat / assurance | `docs/THREAT_MODEL.md`, `docs/ASSURANCE_MODEL.md` | Presentes; tiles ≠ conformidad |
| Packs sintéticos | `examples/evidence/` + `docs/schemas/` | CI valida con jsonschema |
| Robustez sintética | `tests/test_synthetic_robustness.py` | Sin `train.csv` |

Comando de verificación de línea (mismo que CI de gobernanza):

```bash
pip install -r requirements_streamlit.txt -r requirements_api.txt
pip install pytest pandas numpy jsonschema scikit-learn
python -m pytest tests/test_dpia_workspace.py tests/test_control_plane.py tests/test_api_security.py tests/test_import_surface.py tests/test_evidence_schemas.py -q
python -m pytest tests/test_synthetic_robustness.py -q
```

Calendario Art. 113 (codificado, no fetch en vivo a EUR-Lex): `src/control_plane/regulatory_library.py` + fixture `tests/fixtures/ai_act_art113_oj_2024.json`. Hitos relevantes: aplicación general **2026-08-02**; Annex III high-risk **2027-12-02** (Reglamento (UE) 2026/1744).

---

## 2. LÍNEA (qué se puede hacer esta hora)

1. Abrir Model Card: `streamlit run app.py` → http://localhost:8501  
2. Sidebar **DPIA GDPR**: leer EIPD de laboratorio y descargar JSON.  
3. En Python, crear/editar una EIPD: `AssessmentStore` (no aprueba sola).  
4. Simular DENY **antes** de ejecutar: `ReferenceRuntime.execute_guarded(...)`.  
5. Ticket de aprobación: sin `approve` la acción no corre; con revisor vacío, error; tickets de un solo uso.  
6. Stop: `request_stop` → `RuntimeStopped` en la siguiente acción que pase por el adaptador.  
7. API local: `python api_server.py` → `/predict` exige artefactos locales; sin modelo → unhealthy / 503.  
8. Entrenamiento local (necesita `train.csv` Kaggle): `python run_training.py`.

Lo que la línea **no** puede afirmar: que stop/aprobaciones se repliquen entre workers; el runtime es un singleton **por proceso**. `/predict` y `/batch_predict` **sí** llaman a `execute_guarded` en este proceso. Métricas hold-out (ROC-AUC, F1, etc.) **no** equivalen a conformidad AEPD / RGPD / AI Act.

---

## 3. INTENCIÓN (por qué existe)

Cadena trazable:

**sistema IA → tratamiento → aplicabilidad → riesgo → control → política ejecutable → enforcement → test → evidencia → riesgo residual → decisión humana**

- Screening Art. 35: apoyo a decisión, no determinación jurídica.  
- Riesgo residual **no baja** porque alguien declare un control.  
- DENY/STOP mandatorios no los tumba un ALLOW de menor rango.  
- Evaluación de política que falla → **fail-closed DENY**, no ALLOW silencioso.  
- Acciones no clasificadas → **default-deny**.

---

## 4. ESTADO MAYOR (mapa normativo, no certificado)

| Fuente | Uso en este repo | Tipo |
|---|---|---|
| RGPD arts. 5, 22, 35, 36 | Screening, derechos, EIPD, bandera consulta previa | Obligación **si** hay tratamiento de datos personales |
| LOPDGDD 3/2018 | Contexto español / AEPD | Ley nacional |
| Guías AEPD EIPD | Listas informativas, no exhaustivas | Orientación |
| Reglamento (UE) 2024/1689 | Biblioteca condicional Art. 5, 9–15, 26, 27, 50, 72 | Obligación **si** rol y clasificación encajan |
| Reglamento (UE) 2026/1744 | Calendario Art. 113 (p. ej. Annex III **2027-12-02**) | Enmienda de calendario; re-verificar en EUR-Lex |
| Calendario de aplicación | `src/control_plane/regulatory_library.py` | Configuración versionada; `encoded_at` no es verificación en vivo |

Clasificación de sistema: `is_legal_classification: false`. No se infiere high-risk por el nombre del modelo. Motor claim scoring **no** es automáticamente Annex III 5(c) (vida/salud).

---

## 5. LIMITACIONES / ENEMIGO / METEO

- Selectores de rol en UI **no** son autenticación / SSO.  
- Límites numéricos (batch 1000, 5 EUR) son **internos**, no umbrales legales de la UE.  
- Art. 36 no se presenta solo.  
- El DPD no firma la EIPD del responsable.  
- Control plane: un proceso, memoria + JSONL reescribible — **no** es WORM ni multi-worker.  
- Dataset Kaggle `ps_*`: se trata como competición anonimizada salvo prueba en contrario (considerando 26).  
- Demo vs producción: clone limpio = UI + control plane + tests de gobernanza; predicción y métricas “de producción” requieren datos/artefactos locales no versionados.  
- Pack estático `gdpr_dpia_v1.json` ≠ workspace EIPD editable; scores residuales del pack estático son **estimated pending verification**.

### Límites de despliegue / no multi-worker safe

Restricciones operativas honestas (demo / laboratorio — **no** SSO, Redis ni WORM de producción):

1. **Rate limit** — contador en memoria **por proceso** (`RATE_LIMIT_BACKEND=memory`). Ineficaz con varias réplicas/workers. En multi-réplica: `RATE_LIMIT_BACKEND=disabled` + límite en gateway (nginx / Cloudflare). Este build **no** incluye backend Redis.
2. **TRUST_PROXY / IP cliente** — `X-Forwarded-For` es spoofable si no hay hop de confianza. Solo se honra XFF si el peer TCP está en `TRUSTED_PROXY_IPS` / `TRUSTED_PROXY_CIDRS`. Con `TRUST_PROXY=true` sin allowlist → se **ignora** XFF (fail closed). Con peer de confianza → hop **más a la izquierda** de XFF (patrón de un reverse proxy).
3. **Identidad en aprobaciones** — `requester` / `reviewer` siguen siendo strings de demo (binding only, **no** SSO). `REQUIRE_AUTH=true` + `API_KEY` obliga clave estática en `/approvals/*` y predict. Respuestas llevan `reviewer_auth_note` / `authn_note`.
4. **Persistencia de tickets** — `approvals.json` es JSON **reescribible**, no log WORM. request/decide/consume también hacen `audit.append` al JSONL hash-encadenado (rastro append-only local; **sigue sin ser** WORM).
5. **`get_runtime()`** — singleton **por proceso**. Con uvicorn multi-worker, stop / approvals / circuit **no** son globales. Usar `uvicorn --workers 1`. Opcional `STOP_FILE`: cada worker mira `Path.exists()` en cada `execute_guarded`. `CONTROL_PLANE_STRICT=true` rechaza init si `WEB_CONCURRENCY` / `UVICORN_WORKERS` / `WORKERS` > 1.

### Roadmap producción (P0 — no fingir como hecho)

| Hueco | Estado actual | Siguiente paso concreto |
|---|---|---|
| Stop / approvals compartidos | Singleton in-process; `STOP_FILE` opcional | Redis (o equivalente) + documentación |
| Auth API | `API_KEY` opcional (+ `REQUIRE_AUTH`) | OIDC/JWT con IdP |
| Auditoría inmutable | JSONL + hash + checkpoint local (JSON de tickets sigue reescribible) | Object Lock / almacén externo + verificación independiente |
| Rate limit multi-réplica | Limitador in-memory de demo | Límite en gateway; sin Redis aquí |
| Evidencia vs efectividad | Campos + `ASSURANCE_MODEL.md` | Owners operativos + tests de control calendados |
