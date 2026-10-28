#!/usr/bin/env python3
"""
Bake ~2:20 ElevenLabs clips for the governed demo (untracked under _demo_audio/).

  --lang en   English script → _demo_audio/en_220/
  --lang es   Spain Castilian → _demo_audio/es_220/

Loads API key from repo .env or Desktop\\Agent fail\\.env.
Default ES voice: Sara Martín (Castilian) KHCvMklQZZo0O30ERnVn
Override: ELEVENLABS_VOICE_ID_ES / ELEVENLABS_VOICE_ID_EN

Do not commit mp3s or API keys.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIO_ROOT = ROOT / "_demo_audio"

# Rachel — clear EN default
DEFAULT_VOICE_EN = "21m00Tcm4TlvDq8ikWAM"
# Sara Martín — Spain Castilian (Agent Fail ES narrator)
DEFAULT_VOICE_ES = "KHCvMklQZZo0O30ERnVn"

BEATS: list[dict[str, str]] = [
    {
        "id": "01_intro",
        "en": "This is a governed AI decision workflow for insurance claim scoring.",
        "es": (
            "Este es un flujo de decisión de IA gobernado para la puntuación "
            "de siniestros de seguros."
        ),
    },
    {
        "id": "02_layers",
        "en": (
            "The application has three layers: an interface for operators, "
            "a deterministic control plane for policy decisions, and an audit "
            "layer that records what happened."
        ),
        "es": (
            "La aplicación tiene tres capas: una interfaz para operadores, "
            "un plano de control determinista para las decisiones de política, "
            "y una capa de auditoría que registra lo ocurrido."
        ),
    },
    {
        "id": "03_controls",
        "en": (
            "The model does not decide on its own. Every governed action passes "
            "through explicit controls before execution."
        ),
        "es": (
            "El modelo no decide por sí solo. Toda acción gobernada atraviesa "
            "controles explícitos antes de su ejecución."
        ),
    },
    {
        "id": "04_art5",
        "en": (
            "Here, a request is flagged with an Article 5 concern. The control "
            "plane evaluates the request before the model runs."
        ),
        "es": (
            "Aquí, una petición se marca con una preocupación del artículo 5. "
            "El plano de control evalúa la petición antes de que el modelo se ejecute."
        ),
    },
    {
        "id": "05_deny",
        "en": (
            "The action is denied. The model function is never invoked, and the "
            "policy decision is recorded in the audit trail."
        ),
        "es": (
            "Se deniega la acción. La función del modelo no se invoca nunca, "
            "y la decisión de política queda registrada en la pista de auditoría."
        ),
    },
    {
        "id": "06_approval",
        "en": (
            "For a legitimate scoring action with legal effect, the system requires "
            "human approval. The reviewer approves a bound, single-use ticket."
        ),
        "es": (
            "Para una acción de scoring legítima con efecto jurídico, el sistema "
            "exige aprobación humana. El revisor aprueba un ticket vinculado y de un solo uso."
        ),
    },
    {
        "id": "07_antireplay",
        "en": (
            "Once consumed, the ticket cannot be replayed. This prevents an approval "
            "from being reused for another action."
        ),
        "es": (
            "Una vez consumido, el ticket no puede reutilizarse. Así se evita que "
            "una aprobación se reutilice para otra acción."
        ),
    },
    {
        "id": "08_redact",
        "en": (
            "The model output then passes through redaction. Personal fields are "
            "removed before the result reaches the operator. If redaction fails, "
            "the action fails closed."
        ),
        "es": (
            "La salida del modelo pasa entonces por redacción. Los campos personales "
            "se eliminan antes de que el resultado llegue al operador. Si la redacción "
            "falla, la acción falla en cerrado."
        ),
    },
    {
        "id": "09_audit",
        "en": (
            "Finally, the audit trail shows the decision path: policy evaluation, "
            "approval, execution and redaction. Each event is linked in a hash chain, "
            "producing replayable technical evidence."
        ),
        "es": (
            "Por último, la pista de auditoría muestra la trayectoria de la decisión: "
            "evaluación de política, aprobación, ejecución y redacción. Cada evento "
            "queda enlazado en una cadena de hashes, produciendo evidencia técnica reproducible."
        ),
    },
    {
        "id": "10_tamper",
        "en": (
            "A clumsy rewrite of the audit file breaks the hash chain — the system "
            "detects local tampering. This is detection, not WORM storage."
        ),
        "es": (
            "Una reescritura torpe del fichero de auditoría rompe la cadena de hashes: "
            "el sistema detecta la manipulación local. Es detección, no almacenamiento WORM."
        ),
    },
    {
        "id": "11_close",
        "en": (
            "This is executable AI governance: the model proposes, controls decide, "
            "and evidence remains observable."
        ),
        "es": (
            "Esto es gobernanza de IA ejecutable: el modelo propone, los controles "
            "deciden y la evidencia permanece observable."
        ),
    },
    {
        "id": "12_disclaimer",
        "en": "Technical evidence is not AEPD, GDPR, or EU AI Act certification.",
        "es": (
            "La evidencia técnica no es una certificación AEPD, RGPD ni del "
            "Reglamento de IA de la UE."
        ),
    },
]


def _load_dotenv_files() -> None:
    candidates = [
        ROOT / ".env",
        Path(r"C:\Users\anlaf\Desktop\Agent fail\.env"),
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ and val:
                    os.environ[key] = val
        except OSError:
            continue


def api_key() -> str | None:
    return (os.getenv("ELEVENLABS_API_KEY") or os.getenv("XI_API_KEY") or "").strip() or None


def voice_id(lang: str) -> str:
    if lang == "en":
        return (
            os.getenv("ELEVENLABS_VOICE_ID_EN")
            or os.getenv("ELEVENLABS_VOICE_ID")
            or DEFAULT_VOICE_EN
        ).strip()
    return (
        os.getenv("ELEVENLABS_VOICE_ID_ES")
        or os.getenv("ELEVENLABS_VOICE_ID")
        or DEFAULT_VOICE_ES
    ).strip()


AEPD_BEATS: list[dict[str, str]] = [
    {
        "id": "01_scope",
        "en": (
            "This is a reference architecture for technical evaluation. "
            "The dataset is the anonymized Kaggle Porto Seguro file: five hundred "
            "ninety-five thousand records, no live insurance book. No AEPD "
            "certification is claimed."
        ),
        "es": (
            "Esto es una arquitectura de referencia para evaluación técnica. "
            "El conjunto de datos es el fichero anonimizado de Kaggle Porto Seguro: "
            "quinientos noventa y cinco mil registros, sin cartera real de seguros. "
            "No se reclama certificación de la AEPD."
        ),
    },
    {
        "id": "02_eipd",
        "en": (
            "The processing purpose is underwriting support: estimate claim "
            "probability. The DPIA describes necessity, proportionality, and the "
            "main risks to people's rights. Special-category data under Article 9 "
            "is not collected."
        ),
        "es": (
            "La finalidad del tratamiento es el apoyo a la suscripción: estimar la "
            "probabilidad de siniestro. La EIPD describe la necesidad, la "
            "proporcionalidad y los riesgos principales para los derechos de las "
            "personas. No se recogen categorías especiales del artículo 9."
        ),
    },
    {
        "id": "03_controls",
        "en": (
            "A risk to rights triggers a control. The plane denies the action "
            "before the model runs. A score with legal effect needs a single-use "
            "human approval. Personal fields are redacted; if redaction fails, "
            "the system fails closed."
        ),
        "es": (
            "Un riesgo para los derechos dispara un control. El plano deniega la "
            "acción antes de ejecutar el modelo. Una puntuación con efecto jurídico "
            "exige aprobación humana de un solo uso. Los campos personales se "
            "redactan; si falla, el sistema cierra en denegación."
        ),
    },
    {
        "id": "04_evidence",
        "en": (
            "The audit trail links policy, approval, execution and redaction. "
            "A local rewrite breaks the hash chain. That is detection, not "
            "immutable external storage."
        ),
        "es": (
            "La pista de auditoría enlaza política, aprobación, ejecución y "
            "redacción. Una reescritura local rompe la cadena de hashes. Es "
            "detección, no almacenamiento inmutable externo."
        ),
    },
    {
        "id": "05_register",
        "en": (
            "The risk register ties each control to a residual risk. Residual "
            "scores are estimates pending verification. Human review remains "
            "necessary."
        ),
        "es": (
            "El registro de riesgos vincula cada control a un riesgo residual. "
            "Las puntuaciones residuales son estimaciones pendientes de "
            "verificación. La revisión humana sigue siendo necesaria."
        ),
    },
    {
        "id": "06_close",
        "en": (
            "This is a technical reference architecture for evaluation, not a "
            "formal DPIA submission and not an Article 36 prior consultation. "
            "The repository is github.com/tshapedconsultant/porto-seguro-compliance-hub."
        ),
        "es": (
            "Esto es una arquitectura de referencia técnica para evaluación, "
            "no una presentación formal de EIPD ni una consulta previa del "
            "artículo 36. El repositorio está en github.com/tshapedconsultant/"
            "porto-seguro-compliance-hub."
        ),
    },
]


def out_dir(lang: str, profile: str = "governed") -> Path:
    if profile == "aepd":
        return AUDIO_ROOT / f"{lang}_aepd90"
    return AUDIO_ROOT / f"{lang}_220"


def generate_clip(
    beat: dict[str, str], lang: str, key: str, vid: str, profile: str = "governed"
) -> Path:
    dest_dir = out_dir(lang, profile)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{beat['id']}.mp3"
    text = beat[lang]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    body = json.dumps(
        {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.48,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"ElevenLabs HTTP {exc.code}: {detail}") from exc
    if len(data) < 100:
        raise SystemExit(f"Tiny payload for {beat['id']}")
    out.write_bytes(data)
    print(f"  [GEN] {out.name} ({len(data)} bytes)")
    return out


def main() -> int:
    _load_dotenv_files()
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=("en", "es"), required=True)
    parser.add_argument("--profile", choices=("governed", "aepd"), default="governed")
    args = parser.parse_args()
    key = api_key()
    if not key:
        print("ERROR: ELEVENLABS_API_KEY not set (repo .env or Agent fail .env)")
        return 2
    vid = voice_id(args.lang)
    beats = AEPD_BEATS if args.profile == "aepd" else BEATS
    print(f"profile={args.profile} lang={args.lang} voice_id={vid} -> {out_dir(args.lang, args.profile)}/")
    for beat in beats:
        generate_clip(beat, args.lang, key, vid, args.profile)
        time.sleep(0.12)
    print("Done. Do not commit _demo_audio/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
