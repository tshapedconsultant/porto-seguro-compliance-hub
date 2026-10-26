# LINE REPORT — Porto Seguro Compliance Hub

**Formato:** bottom-up / line-first. Primero lo que hay en el terreno, después lo que la línea puede hacer ahora, después la intención y el relato de estado mayor.  
**No es** aprobación AEPD, certificación RGPD ni certificación del Reglamento de IA.

---

## 1. TERRENO (bottom)

Hechos en disco, no intenciones.

| Pieza | Ruta | Estado |
|---|---|---|
| Pack EIPD estático | `gdpr_dpia_v1.json` | Presente |
| Motor EIPD | `src/governance/dpia_workspace/` | Código presente |
| Motor de políticas | `src/control_plane/` | Código presente |
| Página Streamlit pack | `pages/08_DPIA_GDPR.py` | Pack JSON + descarga |
| API predicción | `api_server.py` `/predict` y `/batch_predict` | Pasan por `execute_guarded` **en este proceso** |
| Tests de borde | `tests/test_dpia_workspace.py`, `tests/test_control_plane.py`, `tests/test_import_surface.py` | CI instala Streamlit+API; REDACT anidado fail-closed; hash EIPD; Annex III 2027-12-02 |
| Persistencia EIPD | `docs/governance/assessments/*.json` | Local; **no** se publica en GitHub |
| Auditoría control plane | JSONL con hash encadenado | No es WORM; el fichero se puede reescribir |

Comando de verificación de línea:

```bash
python -m pytest tests/test_dpia_workspace.py tests/test_control_plane.py -q
```

---

## 2. LÍNEA (qué se puede hacer esta hora)

1. Abrir Model Card: `streamlit run app.py` → http://localhost:8501  
2. Sidebar **DPIA GDPR**: leer EIPD de laboratorio y descargar JSON.  
3. En Python, crear/editar una EIPD: `AssessmentStore` (no aprueba sola).  
4. Simular DENY **antes** de ejecutar: `ReferenceRuntime.execute_guarded(...)`.  
5. Ticket de aprobación: sin `approve` la acción no corre; con revisor vacío, error.  
6. Stop: `request_stop` → `RuntimeStopped` en la siguiente acción que pase por el adaptador.

Lo que la línea **no** puede afirmar: que stop/aprobaciones se repliquen entre workers; el runtime es un singleton **por proceso**. `/predict` sí llama a `execute_guarded` en este proceso.

---

## 3. INTENCIÓN (por qué existe)

Cadena trazable:

**sistema IA → tratamiento → aplicabilidad → riesgo → control → política ejecutable → enforcement → test → evidencia → riesgo residual → decisión humana**

- Screening Art. 35: apoyo a decisión, no determinación jurídica.  
- Riesgo residual **no baja** porque alguien declare un control.  
- DENY/STOP mandatorios no los tumba un ALLOW de menor rango.  
- Evaluación de política que falla → **fail-closed DENY**, no ALLOW silencioso.

---

## 4. ESTADO MAYOR (mapa normativo, no certificado)

| Fuente | Uso en este repo | Tipo |
|---|---|---|
| RGPD arts. 5, 22, 35, 36 | Screening, derechos, EIPD, bandera consulta previa | Obligación **si** hay tratamiento de datos personales |
| LOPDGDD 3/2018 | Contexto español / AEPD | Ley nacional |
| Guías AEPD EIPD | Listas informativas, no exhaustivas | Orientación |
| Reglamento (UE) 2024/1689 | Biblioteca condicional Art. 5, 9–15, 26, 27, 50, 72 | Obligación **si** rol y clasificación encajan |
| Calendario de aplicación | `src/control_plane/regulatory_library.py` | Configuración versionada; re-verificar en EUR-Lex |

Clasificación de sistema: `is_legal_classification: false`. No se infiere high-risk por el nombre del modelo.

---

## 5. LIMITACIONES / ENEMIGO / METEO

- Selectores de rol en UI **no** son autenticación.  
- Límites numéricos (batch 1000, 5 EUR) son **internos**, no umbrales legales de la UE.  
- Art. 36 no se presenta solo.  
- El DPD no firma la EIPD del responsable.  
- Integración runtime en FastAPI: pendiente de cablear en `/predict`.  
- Dataset Kaggle `ps_*`: se trata como competición anonimizada salvo prueba en contrario (considerando 26).
