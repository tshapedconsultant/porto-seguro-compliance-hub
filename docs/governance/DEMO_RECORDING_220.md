# Recording guide — Governed AI demo (~2:20–2:30)

**Not** AEPD, GDPR, or EU AI Act certification. Technical evidence for lab / stakeholder review.

**Layout:** Streamlit = **control room** (page **09 · Governed Decision Demo**). Terminal = **small evidence strip** (`docs/governance/demo_90s.py`). Do **not** show Mermaid source on camera — use the rendered diagrams on the page.

**Launcher:** [`record_demo.bat`](../../record_demo.bat) (repo root). Starts Streamlit + evidence terminal only. **Does not** press Win+Alt+R — you must focus the **browser**, then start Game Bar yourself.

Related: [`DEMO_PLAYBOOK.md`](DEMO_PLAYBOOK.md) (ES) · [`DEMO_PLAYBOOK_EN.md`](DEMO_PLAYBOOK_EN.md) (EN).

---

## Prep checklist

| Item | Detail |
|------|--------|
| Do Not Disturb | On (no toast popups) |
| Resolution | 1080p (or 1440p); browser zoom ~100–110% |
| Fullscreen | F11 on the Streamlit tab after open |
| Game Bar | Settings → Gaming → Captures: record mic **off** if using ElevenLabs PC audio; record system audio **on** |
| Focus | **Browser** window focused before Win+Alt+R (not the bat, not only the evidence terminal) |
| Page | Sidebar → **Governed Decision Demo** |
| Audio EN | Optional pre-bake: `python _generate_demo_audio.py --lang en` → `_demo_audio/en_220/` (untracked) |
| Audio ES (AEPD) | **Prefer your own voice** in CapCut/DaVinci (teleprompter below). Optional Castilian ElevenLabs: `python _generate_demo_audio.py --lang es` |

---

## Exact Xbox / Game Bar steps

1. Double-click `record_demo.bat` (or run from repo root).
2. Wait for Streamlit; browser opens `http://localhost:8501`.
3. Open **Governed Decision Demo**; set sidebar to first step (Arquitectura).
4. Optional: arrange evidence terminal as a thin strip (bottom or side) — readable tags, not the hero.
5. **Click the browser** so it has focus.
6. Press **Win + Alt + R** to start.
7. Advance sidebar steps on the timeline below; let the terminal print `[DENY]` … `[TAMPER]`.
8. Press **Win + Alt + R** to stop.
9. Find the clip under `%USERPROFILE%\Videos\Captures`.

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
