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
| Motor de políticas | `src/control_plane/` | Código presente; singleton **por proceso**; auditoría JSONL **no** WORM/KMS; **no** SSO/OIDC; `STOP_FILE` + lease FS opcionales |
| Página Streamlit pack | `pages/08_DPIA_GDPR.py` | Pack JSON + descarga; copy AEPD en español |
| Model Card | `app.py` + `pages/*` | Arranca sin `train.csv` / `.pkl` (artefactos gitignored) |
| API predicción | `api_server.py` `/predict` y `/batch_predict` | Pasan por `execute_guarded` **en este proceso**; rate limit in-memory demo; TRUST_PROXY con allowlist |
| Pipeline ML | `src/data_processing/` → `src/models/` → `src/monitoring/` | Polars → FE → EBM → explainability → gate; scripts `run_training*.py` |
| Tests de borde | `tests/test_dpia_workspace.py`, `tests/test_control_plane.py`, `tests/test_control_plane_security.py`, `tests/test_api_security.py`, `tests/test_import_surface.py` | Mismos ficheros que el job CI `tests`; Streamlit + API (`polars`/`joblib`); REDACT anidado fail-closed; Annex III **2027-12-02** (tras 2026/1744) |
| Tests ML (opcionales) | `tests/test_*` data/EBM/drift/explainability | En repo; skip si faltan `polars`/`interpret`; **no** son el job CI de gobernanza |
| Persistencia EIPD | `docs/governance/assessments/*.json` | Local; **no** se publica en GitHub |
| Auditoría control plane | JSONL append-only + hash + checkpoint local | No es WORM; el fichero se puede reescribir |
| Threat / assurance | Packs raíz `eu_ai_act_conformity_v1.json`, `gdpr_dpia_v1.json` | Tiles ≠ conformidad. `docs/THREAT_MODEL.md` / `ASSURANCE_MODEL.md` / `examples/evidence/` **no** están en el árbol publicado (allowlist `.gitignore`) |
| Robustez sintética | `tests/test_synthetic_robustness.py` | Job CI `ml-synthetic` (filtro de rutas / cron / dispatch), **no** el job `tests` |

Comando de verificación de línea (mismo que CI de gobernanza):

```bash
pip install -r requirements_streamlit.txt -r requirements_api.txt
pip install pytest pandas numpy
python -m pytest tests/test_dpia_workspace.py tests/test_control_plane.py tests/test_control_plane_security.py tests/test_api_security.py tests/test_import_surface.py -q
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
9. Demo técnica (secuencia Mermaid + ciclo ticket + incidente 2 min + guion 90 s + tamper 15 s): [`DEMO_PLAYBOOK.md`](DEMO_PLAYBOOK.md) (ES) · [`DEMO_PLAYBOOK_EN.md`](DEMO_PLAYBOOK_EN.md) (EN).

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

### What this still is not / Lo que esto sigue sin ser

Huecos honestos (demo / laboratorio). Mitigaciones pragmáticas suben el listón; **no** cierran el modelo de amenaza de producción. **No** hay certificación RGPD / AI Act.

1. **Integridad de auditoría ≠ WORM / KMS** — Checkpoint + JSONL (+ `AUDIT_HMAC_KEY` opcional) son reescribibles en disco. Detectan manipulación torpe, no a un atacante con acceso al FS que reescriba ambos ficheros (y falsifique HMAC si conoce la clave). Producción: almacén append-only / Object Lock + firma KMS + verificación independiente. `AUDIT_HMAC_KEY` es **secreto compartido**, no KMS.
2. **`approvals.json` es autoritativo y mutable** — Ver el audit trail ≠ impedir editar el ticket. `verify_against_audit()` (+ `APPROVAL_AUDIT_STRICT`) detecta desync obvio JSON↔audit; no hace inmutables los tickets. Producción: Postgres/Redis transaccional + audit append-only. `APPROVAL_BACKEND=memory|json` solamente (stubs `redis`/`postgres` — no implementados).
3. **`STOP_FILE` es freno de emergencia, no transaccional** — Trabajo in-flight puede terminar después de crear el fichero. Predict: pre-check + post-check; si aparece a mitad, se devuelve resultado con `interrupted_by_stop=True` y audit `stop_during_execution`. Acciones export/external-effect: solo pre-check. `/predict` también pre-check en el borde API.
4. **Detección de workers / réplicas es best-effort** — `WEB_CONCURRENCY` / `UVICORN_WORKERS` / `WORKERS` no ven réplicas horizontales (1 worker × N contenedores). Opcional `INSTANCE_ID` + `CONTROL_PLANE_LEASE_DIR` (TTL ~60s); con `CONTROL_PLANE_STRICT` y >1 instance IDs recientes → refuse start. Lease de FS barato — **no Redis**.
5. **Rate limit es local** — `RATE_LIMIT_BACKEND=memory|disabled`. Sin backend compartido. Preferir disabled + gateway (nginx / Cloudflare / API Gateway / APIM).
6. **API key estática** — Sin identidad, caducidad, revocación ni scopes. `APPROVAL_API_KEY` opcional para `/approvals/decide` y `APPROVAL_SEPARATE_ACTORS=true` (rechaza reviewer==requester) son demos de SoD — **sigue sin ser OIDC**.

### Límites de despliegue / no multi-worker safe

Ver **What this still is not** arriba. Nota adicional de confianza de IP:

- **TRUST_PROXY / IP cliente** — `X-Forwarded-For` es spoofable si no hay hop de confianza. Solo se honra XFF si el peer TCP está en `TRUSTED_PROXY_IPS` / `TRUSTED_PROXY_CIDRS`. Con `TRUST_PROXY=true` sin allowlist → se **ignora** XFF (fail closed). Con peer de confianza → hop **más a la izquierda** de XFF (patrón de un reverse proxy).

### Roadmap producción (P0 — no fingir como hecho)

Detalle y orden de servicio operable: [`docs/ROADMAP_V2.md`](../ROADMAP_V2.md). Publicar ese documento **no** cierra los huecos.

| Hueco | Estado actual | Siguiente paso concreto |
|---|---|---|
| Stop / approvals compartidos | In-process; `STOP_FILE` + lease FS opcional | Redis (o equivalente) + documentación |
| Auth API | `API_KEY` / `APPROVAL_API_KEY` estáticos | OIDC/JWT con IdP |
| Auditoría inmutable | JSONL + checkpoint + HMAC opcional (no KMS) | Object Lock + KMS + verificación independiente |
| Autoridad de aprobaciones | JSON mutable + chequeo desync | Postgres/Redis + audit append-only |
| Rate limit multi-réplica | Limitador in-memory de demo | Límite en gateway; sin Redis aquí |
| Evidencia vs efectividad | Campos de assurance en packs JSON | Owners operativos + tests de control calendados |
