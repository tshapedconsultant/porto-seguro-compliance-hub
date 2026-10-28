# Recording guide — walkthrough captures

**Not** AEPD, GDPR, or EU AI Act certification. Technical evidence for lab / stakeholder review.

**What to record**

| Cut | Page | Launcher |
|-----|------|----------|
| Control room (~2:20) | **09 · Governed Decision Demo** | `record_demo.bat` (EN) · `record_demo.bat --es` |
| AEPD EIPD (~90 s) | **10 · AEPD EIPD Demo** | `record_demo.bat --aepd` |

Do **not** show Mermaid source on camera. Use the diagrams on the Streamlit page.

**Capture (current orchestrator):** [`record_demo.bat`](../../record_demo.bat) → [`auto_record_demo.py`](auto_record_demo.py). Edge fullscreen, Cursor minimized, ffmpeg desktop grab, VO muxed into the MP4. Xbox Game Bar is **not** used (it captured the IDE and dropped audio).

Outputs: `%USERPROFILE%\Videos\Captures\` (`governed-ai-en.mp4`, `governed-ai-es.mp4`, `aepd-eipd-es.mp4`).

Related: [`DEMO_PLAYBOOK.md`](DEMO_PLAYBOOK.md) (ES) · [`DEMO_PLAYBOOK_EN.md`](DEMO_PLAYBOOK_EN.md) (EN).

---

## Prep checklist

| Item | Detail |
|------|--------|
| Do Not Disturb | On (no toast popups) |
| Resolution | 1080p (or 1440p); browser zoom ~100–110% |
| ffmpeg | On `PATH` (orchestrator will abort without it) |
| Audio | Optional pre-bake: `python _generate_demo_audio.py --lang en` or `--lang es` → `_demo_audio/` (untracked). Needs `ELEVENLABS_API_KEY` in env, not in the repo |
| AEPD VO | Castilian clip for `--aepd`; same generator |

---

## Exact steps

1. From repo root: `record_demo.bat`, `record_demo.bat --es`, or `record_demo.bat --aepd`.
2. Wait for Streamlit; the orchestrator opens the demo page, fullscreen, and starts capture.
3. Do not switch to Cursor while ffmpeg is running.
4. When it finishes, check the MP4 under `%USERPROFILE%\Videos\Captures`.
5. Manual / silent: `record_demo.bat --no-record` or `--no-voice` (see the bat header).

---

## Timeline (0:00–2:30)

| Time | Streamlit step | Terminal / beat | CapCut label (optional) |
|------|----------------|-----------------|-------------------------|
| 0:00–0:20 | Arquitectura | Banner / layers | ARCHITECTURE |
| 0:20–0:45 | Decisión de política | `[DENY]` | DENY |
| 0:45–1:15 | Ciclo de aprobación | `[TICKET]` → `[APPROVED RUN]` | HUMAN APPROVAL |
| 1:15–1:35 | Anti-replay | `[ANTI-REPLAY]` | ANTI-REPLAY |
| 1:35–1:55 | Salida + redacción | `[REDACT]` | REDACT |
| 1:55–2:15 | Pista de auditoría | `[AUDIT]` | AUDIT CHAIN |
| 2:15–2:25 | Tamper | `[TAMPER]` before/after | TAMPER |
| 2:25–2:30 | Cierre + esquemas | Final line on screen | CLOSE |

---

## English narration script (~2:20) — ElevenLabs EN

Use exactly (light polish for timing only):

> This is a governed AI decision workflow for insurance claim scoring.
>
> The application has three layers: an interface for operators, a deterministic control plane for policy decisions, and an audit layer that records what happened.
>
> The model does not decide on its own. Every governed action passes through explicit controls before execution.
>
> Here, a request is flagged with an Article 5 concern. The control plane evaluates the request before the model runs.
>
> The action is denied. The model function is never invoked, and the policy decision is recorded in the audit trail.
>
> For a legitimate scoring action with legal effect, the system requires human approval. The reviewer approves a bound, single-use ticket.
>
> Once consumed, the ticket cannot be replayed. This prevents an approval from being reused for another action.
>
> The model output then passes through redaction. Personal fields are removed before the result reaches the operator. If redaction fails, the action fails closed.
>
> Finally, the audit trail shows the decision path: policy evaluation, approval, execution and redaction. Each event is linked in a hash chain, producing replayable technical evidence.
>
> A clumsy rewrite of the audit file breaks the hash chain — the system detects local tampering. This is detection, not WORM storage.
>
> This is executable AI governance: the model proposes, controls decide, and evidence remains observable.
>
> Technical evidence is not AEPD, GDPR, or EU AI Act certification.

Generate clips:

```text
python _generate_demo_audio.py --lang en
```

Output: `_demo_audio/en_220/` (gitignored). Play during edit or over the take with PC audio capture.

---

## Spanish Castilian teleprompter (AEPD — preferred: your voice)

Spain wording (`ordenador`/`aplicación` OK; avoid LatAm *ustedes* tone; use *se deniega*, *evidencia técnica*, *no es una certificación*):

> Este es un flujo de decisión de IA gobernado para la puntuación de siniestros de seguros.
>
> La aplicación tiene tres capas: una interfaz para operadores, un plano de control determinista para las decisiones de política, y una capa de auditoría que registra lo ocurrido.
>
> El modelo no decide por sí solo. Toda acción gobernada atraviesa controles explícitos antes de su ejecución.
>
> Aquí, una petición se marca con una preocupación del artículo 5. El plano de control evalúa la petición antes de que el modelo se ejecute.
>
> Se deniega la acción. La función del modelo no se invoca nunca, y la decisión de política queda registrada en la pista de auditoría.
>
> Para una acción de scoring legítima con efecto jurídico, el sistema exige aprobación humana. El revisor aprueba un ticket vinculado y de un solo uso.
>
> Una vez consumido, el ticket no puede reutilizarse. Así se evita que una aprobación se reutilice para otra acción.
>
> La salida del modelo pasa entonces por redacción. Los campos personales se eliminan antes de que el resultado llegue al operador. Si la redacción falla, la acción falla en cerrado.
>
> Por último, la pista de auditoría muestra la trayectoria de la decisión: evaluación de política, aprobación, ejecución y redacción. Cada evento queda enlazado en una cadena de hashes, produciendo evidencia técnica reproducible.
>
> Una reescritura torpe del fichero de auditoría rompe la cadena de hashes: el sistema detecta la manipulación local. Es detección, no almacenamiento WORM.
>
> Esto es gobernanza de IA ejecutable: el modelo propone, los controles deciden y la evidencia permanece observable.
>
> La evidencia técnica no es una certificación AEPD, RGPD ni del Reglamento de IA de la UE.

Optional convenience track (Spain Castilian voice, e.g. Sara Martín `KHCvMklQZZo0O30ERnVn` via `ELEVENLABS_VOICE_ID_ES`):

```text
python _generate_demo_audio.py --lang es
```

→ `_demo_audio/es_220/` (untracked). For AEPD delivery, dubbing with your own voice usually reads better.

---

## Edit notes (CapCut / Premiere / DaVinci)

- Lower-thirds / labels: **DENY**, **HUMAN APPROVAL**, **ANTI-REPLAY**, **REDACT**, **AUDIT**, **TAMPER**.
- Keep Streamlit dominant; crop terminal to a strip if needed.
- Sync cut points to terminal tags when possible.
- Optional 20–30 s **tamper-only** clip: `python docs/governance/demo_90s.py --tamper-only`.

### Final card (on screen)

> **The model proposes. Controls decide. Evidence remains observable.**
>
> Technical evidence is not AEPD, GDPR, or EU AI Act certification.

---

## Honest limits (say aloud or caption)

1. Enforcement only in-process via `execute_guarded`.
2. Approvals = mutable JSON + demo strings (not SSO).
3. Audit = local hash chain (not WORM / KMS).
4. Prediction HTTP audit ≠ control-plane audit.
5. Evidence ≠ certification.
