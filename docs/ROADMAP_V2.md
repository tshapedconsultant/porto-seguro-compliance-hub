# Porto Seguro Compliance Hub — Roadmap v2

**Fecha de evaluación:** 2026-10-29  
**Estado de este documento:** plan. Publicarlo **no** implementa ninguna fase.  
**Evaluado contra:** `api_server.py`, `src/control_plane/`, `.github/workflows/ci.yml`, `.gitignore`, `tests/`, árbol `docs/` en este working tree.

Objetivo: convertir el hub de laboratorio en un **servicio desplegable y operable**, no en una lista de pantallas nuevas.

Este roadmap **no** es una evaluación jurídica ni garantiza conformidad con RGPD, Reglamento de IA o Solvency II.

**English stub:** older links to [`V2_ROADMAP.md`](V2_ROADMAP.md) resolve here.

---

## Evaluación (qué está en el código hoy)

Hechos verificados. No son criterios de salida de producción.

| Afirmación del borrador | Código | Notas |
|-------------------------|--------|--------|
| API con validación de entradas y tope de lote | `api_server.py` `_normalize_features`, `MAX_BATCH_RECORDS` (default 1000) | Implementado |
| `/predict` y `/batch_predict` pasan por `execute_guarded` | `predict()`, `batch_predict()` | **Este proceso**; `uvicorn --workers 1` |
| Auth e integridad de artefactos configurables, **no** obligatorios | `REQUIRE_AUTH` default `false`; `REQUIRE_ARTIFACT_HASH` default `false`; si `API_KEY` está vacío, `_enforce_api_key` no exige cabecera | Confirmado |
| Estado de control local al proceso | `get_runtime()` singleton; `APPROVAL_BACKEND=memory\|json` | Stubs `redis`/`postgres` **lanzan error** |
| Log de predicción en segundo plano; fallo no bloquea la respuesta | `_schedule_audit` → FastAPI `BackgroundTasks`; `_write_audit_log_sync` captura `Exception` y hace `logger.warning` | El cliente puede recibir 200 sin fila de auditoría |
| Semántica de revisión distinta en individual vs lote | `/predict`: `review_required = uncertainty_flag or legal_effect`. `/batch_predict`: solo `uncertainty_flag` por fila, aunque el contexto lleva `legal_effect_decision` | Asimetría real; unificar es trabajo de Fase 3 |
| Binding de aprobación | `/predict` envía `approval_payload`. `/batch_predict` **no** | El ticket de lote no queda atado al payload |
| CI gobernanza vs ML | Job `tests` en cada push/PR. Job `ml-synthetic` si cambian rutas ML, cron semanal `0 6 * * 0`, o `workflow_dispatch`. **No** hay `continue-on-error` | Si `ml-synthetic` corre y falla, falla el workflow |
| Árbol publicado | `.gitignore` es deny-all (`*`) + allowlist. `docs/THREAT_MODEL.md`, `docs/ASSURANCE_MODEL.md`, `examples/evidence/`, `docs/schemas/` **no** salen en un clone de GitHub | README no debe enlazarlos como si existieran en el remoto |

**Inventario pendiente (Fase 0):** eficacia de políticas, EIPD workspace vs pack estático, monitor de deriva, hash de artefactos cuando el sidecar existe. Este documento no los da por verificados.

**No debe cambiar en v2**

- El modelo **propone**; `execute_guarded` **decide**.
- Acciones no clasificadas → default-deny. REDACT anidado → fail-closed.
- El riesgo residual **no** baja porque un control esté declarado en JSON.
- Sin LLM en inferencia ni en triaje.
- Tiles Streamlit = evidencia presente, no sello de conformidad.
- El clone público sigue en Kaggle anonimizado (`ps_*`). Una cartera real es **otro tratamiento**, con EIPD firmada propia.

---

## 1. Objetivo y alcance

Evolucionar la arquitectura de referencia hacia un servicio de inferencia y gobernanza desplegable: identidad verificable, autorización efectiva, estado compartido, evidencia duradera y procedimientos de operación.

El primer hito es un **piloto controlado** para un caso de uso definido. El paso a producción exige criterios técnicos, operativos, de modelo y de protección de datos — no solo tests en verde.

---

## 2. Punto de partida

La API actual valida entradas, limita el lote, ofrece auth e integridad de artefactos **opt-in**, y envuelve predicción con `execute_guarded`. La CI separa gobernanza/seguridad (`tests`) de ML (`ml-synthetic`).

Limitaciones relevantes (código):

- `REQUIRE_AUTH` / `REQUIRE_ARTIFACT_HASH` no son obligatorios por defecto.
- Stop, circuit breaker y tickets viven en el proceso (JSON mutable / memoria).
- La escritura del log de predicción es asíncrona y **no** falla la petición si el disco falla.
- `/predict` y `/batch_predict` no comparten la misma regla de `review_required` ni el mismo binding de ticket.
- Documentación y comandos han divergido del árbol y de la CI (Fase 0).

---

## 3. Principios de implementación

1. Un único caso de uso y entorno objetivo para la primera versión.
2. Identidad y autorización fuera del modelo y de campos que envía el cliente (`requester` / `reviewer` de formulario no cuentan).
3. Límites y políticas aplicados en el servidor.
4. Denegación o degradación **explícita** cuando falta un control obligatorio.
5. Evidencia de pruebas **antes** de ampliar garantías en el README.
6. CI verde o un dashboard **no** equivalen a “listo para producción”.

---

## Fase 0 — Base verificable

### Objetivo

Que un tercero clone un commit, instale, ejecute **solo** los comandos publicados y sepa qué funciona.

### Trabajo

- README alineado con CI y con ficheros que el allowlist de `.gitignore` **sí** publica.
- Separar comandos de demo, pruebas de gobernanza y entrenamiento ML.
- Describir cuándo corre `ml-synthetic` (rutas / cron / `workflow_dispatch`), no `continue-on-error`.
- Crear [`docs/STATUS.md`](STATUS.md) *(aún no existe)*: capacidad, estado (implementada / parcial / planificada), archivo, test, límite.
- Fijar versión de Python (CI usa **3.12**) y locks por servicio.
- Prueba de arranque en entorno limpio (sin `train.csv` / `.pkl`).
- Comprobación automática de enlaces internos de documentación.
- Etiqueta git de laboratorio (`lab-vX`), no “production”.

### Criterios de salida

- Los comandos publicados corren en un clone limpio.
- No hay enlaces internos conocidos a rutas inexistentes **en el árbol publicado**.
- CI ejecuta las comprobaciones obligatorias y conserva logs.
- Se distinguen tests ejecutados, omitidos (`skip`) y fallidos.
- Las métricas Kaggle del README no se presentan como resultado de una ejecución nueva sin artefactos.

**Hoy:** Fase 0 **no** está cerrada. Corregir el README quita inconsistencias; **no** demuestra que `streamlit` o `/predict` arranquen en un runner limpio.

---

## Fase 1 — Definir el servicio que se va a operar

### Objetivo

No construir “producción” sin quién, para qué y con qué consecuencias.

### Trabajo

Crear `docs/PRODUCTION_SCOPE.md` *(aún no existe; no confundir con el checklist local `PRODUCTION_READINESS.md`, que son rangos Kaggle y no está en el allowlist)*.

Concretar: usuario y organización; finalidad de la predicción; decisión que informa y quién la toma; datos, procedencia y restricciones; individual vs lote; tráfico y concurrencia; uno o varios clientes; región; responsables (ops, modelo, seguridad, riesgo); comportamiento si el servicio no está.

Indicadores a **acordar** (sin valores inventados aquí):

| Indicador | Valor a fijar |
|-----------|----------------|
| Disponibilidad | Según criticidad y contrato |
| Latencia de inferencia | Carga representativa |
| Tamaño máximo de lote | Hoy el default de código es 1000; el piloto puede ser menor |
| RTO / RPO | Según tolerancia |
| Plazo de revisión humana | Según el flujo de negocio |

### Criterios de salida

Alcance y exclusiones aprobados; responsables; arquitectura de despliegue; métricas de aceptación. El dataset Kaggle **no** se da por representativo del libro del cliente.

---

## Fase 2 — Identidad, autorización y configuración segura

### Objetivo

Sustituir `API_KEY` estática y strings `requester`/`reviewer` por acceso verificable.

### Trabajo

- OIDC/JWT: firma, emisor, audiencia, caducidad, algoritmos permitidos.
- Identidad y org desde claims, no desde el body.
- Permisos por acción: inferencia, evidencia, request/decide de aprobaciones, políticas, stop/recover.
- Autorización en **cada** endpoint (también Streamlit).
- SoD de aprobaciones desde el token (`APPROVAL_SEPARATE_ACTORS` hoy compara strings).
- Secretos fuera del repo.
- Perfil de despliegue: **no arrancar** si faltan IdP, almacenes o `REQUIRE_ARTIFACT_HASH` cuando el perfil es `production`. El modo demo no debe quedar expuesto.
- TLS, CORS, `TRUST_PROXY` + allowlist (el fail-closed de XFF **ya** está; mantenerlo).

### Pruebas

Token inválido / caducado / otra audiencia; usuario sin permiso; manipulación de tenant; endpoints admin por API directa; aprobación no autorizada; arranque sin config obligatoria.

### Criterios de salida

Ninguna acción protegida depende de identidad declarada por el cliente. Sin credenciales de demo en el entorno objetivo. Las pruebas negativas demuestran denegación.

---

## Fase 3 — Estado compartido y ejecución consistente

### Objetivo

Que aprobaciones, paradas y políticas signifiquen lo mismo entre procesos, reinicios y réplicas.

### Arquitectura mínima propuesta

- PostgreSQL para tickets y políticas versionadas (transaccional).
- Gateway para rate limit (el limiter in-process es demo; `RATE_LIMIT_BACKEND=disabled` + gateway).
- Redis **solo** si hace falta para stop/circuit/membership — no como sistema de registro de tickets.
- Object storage para evidencias y artefactos.

No hace falta montar todo el primer día; sí hace falta no fingir que el JSON local escala.

### Trabajo

- Sustituir `approvals.json` por filas INSERT-only (request / decide / consume). `UPDATE` in-place no autoriza.
- Ciclo: pending → approved | rejected | expired → consumed/revoked.
- Vincular: identidad IdP, acción, hash de payload, versión de política, caducidad. Hoy `/batch_predict` omite `approval_payload`.
- Consumo atómico (dos réplicas, un ticket).
- Stop compartido; documentar el trabajo **in-flight** (`interrupted_by_stop` ya existe en predict; no es cancelación instantánea).
- Idempotencia en reintentos.
- Unificar `review_required` entre `/predict` y `/batch_predict` (hoy el lote ignora `FLOW_LEGAL_EFFECT` en el flag por fila).
- Versionar políticas y registrar la versión aplicada.

### Pruebas

Dos réplicas consumiendo el mismo ticket; reinicio a mitad de transición; replay con otros parámetros; stop desde otra réplica; almacén caído; reintentos; paridad individual/lote.

### Criterios de salida

Réplicas sin decisiones incompatibles por estado local. Un ticket no autoriza otra acción. Pérdida de estado: comportamiento definido y **probado**. Stop documentado sin prometer aborto inmediato.

---

## Fase 4 — Evidencia duradera y auditable

### Objetivo

Que la evidencia sobreviva a fallos y permita reconstruir una decisión. Un JSONL local **no** es inmutabilidad.

Hoy hay **dos** pistas fáciles de confundir: `AuditLog` del control plane (hash + checkpoint) y `logs/prediction_audit.jsonl` de la API. Ninguna es WORM. La de predicción se escribe en background y el fallo se traga.

### Trabajo

- Esquema versionado: request id, actor, acción, versión de modelo y política, resultado del control, referencia de aprobación, estado de ejecución, timestamps.
- Minimizar PII; cero secretos en logs.
- Persistencia duradera; permisos de ops ≠ admin de evidencia; retención y borrado.
- Integridad + verificación **independiente** (KMS / Object Lock según amenaza). HMAC en env (`AUDIT_HMAC_KEY`) es secreto compartido, no KMS.
- Decidir qué operaciones exigen evidencia persistida **antes** del 200. Hoy el 200 no espera al log.
- Si hay cola, que sea duradera y se monitorice. SIEM es copia, no único registro.

### Pruebas

Caída del destino de logs; saturación; alteración o borrado; reconstrucción de una decisión; verificador separado; ausencia de secretos.

### Criterios de salida

No se pierde evidencia obligatoria en silencio. Política explícita de bloqueo o degradación. Recuperación y verificación ensayadas. La documentación distingue: integridad detectable ≠ control de acceso ≠ retención protegida.

---

## Fase 5 — Validación del modelo para el caso de uso

### Objetivo

Utilidad y límites en el **entorno objetivo**, no reproducir el ROC-AUC 0.639 de Kaggle como si fuera el libro del cliente.

### Trabajo

Procedencia y licencia; leakage y corte temporal; train/val/test; umbral en validación y test ciego; baselines; discriminación, calibración, precision/recall operativos, coste FP/FN, incertidumbre, subgrupos. Proxies (`ps_ind_03`, …) = evidencia **limitada**, no prueba de no discriminación. Criterio de derivación a humano. Versionar dataset, FE, modelo, umbral. El esquema de inferencia debe coincidir con el de entrenamiento (`REQUIRE_ARTIFACT_HASH` on en el perfil production). Política de reentrenamiento y promoción — una alerta de drift **no** promociona sola.

### Criterios de salida

Rendimiento aceptado para una finalidad concreta; umbral justificado; limitaciones comunicadas; dueño de modelo y negocio firman la promoción. Las métricas **no** son una decisión de conformidad.

---

## Fase 6 — Empaquetado, seguridad y despliegue

### Objetivo

Una unidad de despliegue reproducible. Hoy se arranca a mano (`python api_server.py` / Streamlit) desde una máquina de desarrollo.

### Trabajo

Imagen con usuario no root; config/secretos/artefactos separados; SBOM; no cargar `.pkl` sin hash; migraciones si hay Postgres; dev/staging/prod; aprobación de release; tests de integración y seguridad antes de promover; liveness/readiness (hoy `/health` solo dice si el modelo está en RAM); rollback de app y modelo; carga representativa.

### Criterios de salida

Un release se reconstruye desde su versión. No se despliega con pasos manuales no documentados desde un portátil. Rollback ensayado. Vulnerabilidades incompatibles con el riesgo aceptado: cerradas. Capacidad medida.

---

## Fase 7 — Operación y respuesta a incidentes

### Objetivo

El servicio sigue gobernable después del deploy.

### Trabajo

Monitorizar latencia, errores, saturación, denegaciones, fallos de evidencia, drift. Runbooks: modelo ausente, store de approvals caído, auditoría fallida, degradación, acceso no autorizado, stop/recover. Backups y restauración **ensayada**. Escalado y soporte que no dependan solo del autor del repo.

### Criterios de salida

Alertas con dueños reales. Restore probado. Stop/degradación controlada. No hay bus factor 1.

---

## Fase 8 — Piloto y autorización de producción

### Secuencia

1. Staging con datos sintéticos.  
2. Integración con datos **autorizados** y accesos limitados.  
3. Shadow (sin efecto de negocio).  
4. Piloto con revisión humana y volumen acotado.  
5. Evaluación de resultados e incidentes.  
6. Aprobación explícita o retorno de fase.

### Evidencias exigidas

Alcance y responsables; threat model; arquitectura desplegada; resultados de pruebas; evaluación del modelo; limitaciones y riesgos aceptados; evaluación de protección de datos si hay datos personales; formación de operadores; recovery/rollback; criterios para suspender el piloto.

La etiqueta “producción” **no** es certificación ni sustituye supervisión.

---

## 4. Prioridades

| Prioridad | Trabajo | Qué desbloquea |
|-----------|---------|----------------|
| P0 | README, inventario, instalación reproducible, alcance (Fases 0–1) | Base verificable |
| P0 | Identidad, autorización, perfil restrictivo (Fase 2) | Acceso controlado |
| P0 | Estado transaccional y evidencia duradera (Fases 3–4) | Operación consistente |
| P0 | Validación del modelo y criterios de aceptación (Fase 5) | Utilidad para el caso real |
| P1 | Despliegue, recuperación, monitorización (Fases 6–7) | Piloto operable |
| P1 | Carga, fallos, seguridad | Confianza operativa |
| P2 | Multitenancy y automatizaciones extra | Solo con demanda demostrada |

No priorizar pantallas, integraciones o marcos regulatorios nuevos por delante de los P0.

---

## 5. Definition of Done para solicitar autorización de producción

- [ ] Caso de uso, finalidad y límites aprobados.
- [ ] Identidad verificable y permisos en servidor.
- [ ] Estado crítico duradero y consistente con el despliegue.
- [ ] Evidencia obligatoria persistida y verificable.
- [ ] Modelo con criterios acordados sobre datos representativos.
- [ ] Pruebas negativas, de integración y de recuperación superadas.
- [ ] Despliegue y rollback reproducibles.
- [ ] Responsables, alertas y runbooks.
- [ ] Obligaciones aplicables al caso evaluadas (proceso, no un JSON).
- [ ] Riesgos residuales con aceptación explícita.
- [ ] Piloto con criterios de salida cumplidos.

Ningún checkbox se marca porque exista este archivo.

---

## 6. Estrategia de entrega

Primera versión:

> Una organización, un caso de uso, un IdP, un almacén transaccional, un modelo aprobado, una infraestructura gestionada.

Añadir clientes, regiones o modelos solo con necesidad demostrada. El salto de calidad no es parecer una plataforma más grande: es que cada garantía publicada tenga **implementación, prueba y responsable**.
