#!/usr/bin/env python3
"""Generate EN/ES PNG diagrams for the governed-decision Streamlit demo."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent
NAVY = "#0B1F33"
SLATE = "#1A3348"
AMBER = "#D4A017"
TEAL = "#2A9D8F"
DENY = "#C44536"
ALLOW = "#3D8B6E"
TEXT = "#E8EEF4"
MUTED = "#9BB0C3"

COPY = {
    "es": {
        "arch_title": "Arquitectura — decisión gobernada (5 capas)",
        "arch_sub": "Interfaz → API → Plano de control → Modelo → Auditoría",
        "layers": [
            ("Interfaz", "Operadores / Streamlit"),
            ("API", "FastAPI / predict"),
            ("Plano de control", "Políticas deterministas"),
            ("Modelo", "fn / EBM (propuesta)"),
            ("Auditoría", "JSONL + cadena hash"),
        ],
        "arch_footer": "El modelo propone · Los controles deciden · La evidencia permanece observable",
        "ticket_title": "Ciclo de vida del ticket (anti-replay)",
        "ticket_states": [
            ("pendiente", "request()"),
            ("aprobado", "decide(true)"),
            ("consumido", "is_approved()"),
            ("replay DENY", "mismo ticket_id"),
        ],
        "ticket_footer": "Un ticket aprobado se consume una sola vez · el reintento se deniega",
        "hash_title": "Cadena de hashes — AuditLog",
        "hash_footer": "verify_chain() · evidencia técnica local (no WORM / no certificación)",
        "evt": [
            ("GÉNESIS", "000…000"),
            ("EVT-1", "política / DENY"),
            ("EVT-2", "aprobación"),
            ("EVT-3", "ejecutado"),
            ("EVT-4", "redacción"),
        ],
    },
    "en": {
        "arch_title": "Architecture — governed decision (5 layers)",
        "arch_sub": "Interface → API → Control Plane → Model → Audit",
        "layers": [
            ("Interface", "Operators / Streamlit"),
            ("API", "FastAPI / predict"),
            ("Control Plane", "Deterministic policies"),
            ("Model", "fn / EBM (proposal)"),
            ("Audit", "JSONL + hash chain"),
        ],
        "arch_footer": "The model proposes · Controls decide · Evidence remains observable",
        "ticket_title": "Ticket lifecycle (anti-replay)",
        "ticket_states": [
            ("pending", "request()"),
            ("approved", "decide(true)"),
            ("consumed", "is_approved()"),
            ("replay DENY", "same ticket_id"),
        ],
        "ticket_footer": "An approved ticket is consumed once · retry is denied",
        "hash_title": "Hash chain — AuditLog",
        "hash_footer": "verify_chain() · local technical evidence (not WORM / not certification)",
        "evt": [
            ("GENESIS", "000…000"),
            ("EVT-1", "policy / DENY"),
            ("EVT-2", "approval"),
            ("EVT-3", "executed"),
            ("EVT-4", "redact"),
        ],
    },
}


def _fig(w: float = 12.0, h: float = 4.8):
    fig, ax = plt.subplots(figsize=(w, h), dpi=160)
    fig.patch.set_facecolor(NAVY)
    ax.set_facecolor(NAVY)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _box(ax, x, y, w, h, face, edge, title, subtitle=""):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.6,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h * 0.62,
        title,
        ha="center",
        va="center",
        color=TEXT,
        fontsize=11,
        fontweight="bold",
    )
    if subtitle:
        ax.text(
            x + w / 2,
            y + h * 0.28,
            subtitle,
            ha="center",
            va="center",
            color=MUTED,
            fontsize=8,
        )


def _arrow(ax, x1, y1, x2, y2, color=AMBER):
    arr = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.8,
        color=color,
    )
    ax.add_patch(arr)


def architecture(lang: str) -> None:
    t = COPY[lang]
    fig, ax = _fig(12.5, 3.8)
    ax.text(0.5, 0.92, t["arch_title"], ha="center", color=TEXT, fontsize=14, fontweight="bold")
    ax.text(0.5, 0.84, t["arch_sub"], ha="center", color=MUTED, fontsize=9)
    faces = [SLATE, SLATE, "#243B53", SLATE, "#243B53"]
    edges = [TEAL, TEAL, AMBER, MUTED, ALLOW]
    xs = [0.03, 0.22, 0.41, 0.60, 0.79]
    for x, (title, sub), face, edge in zip(xs, t["layers"], faces, edges):
        _box(ax, x, 0.28, 0.17, 0.42, face, edge, title, sub)
    for i in range(4):
        x1 = 0.03 + 0.17 + i * 0.19
        _arrow(ax, x1 + 0.005, 0.49, x1 + 0.035, 0.49)
    ax.text(0.5, 0.12, t["arch_footer"], ha="center", color=AMBER, fontsize=9)
    fig.savefig(OUT / f"architecture_layers_{lang}.png", bbox_inches="tight", facecolor=NAVY)
    plt.close(fig)


def ticket_lifecycle(lang: str) -> None:
    t = COPY[lang]
    fig, ax = _fig(12.5, 3.6)
    ax.text(0.5, 0.90, t["ticket_title"], ha="center", color=TEXT, fontsize=14, fontweight="bold")
    edges = [MUTED, TEAL, ALLOW, DENY]
    xs = [0.05, 0.28, 0.51, 0.74]
    for x, (title, sub), edge in zip(xs, t["ticket_states"], edges):
        _box(ax, x, 0.30, 0.18, 0.40, SLATE, edge, title, sub)
    for i in range(3):
        x1 = 0.05 + 0.18 + i * 0.23
        _arrow(ax, x1 + 0.005, 0.50, x1 + 0.04, 0.50, color=AMBER if i < 2 else DENY)
    ax.text(0.5, 0.12, t["ticket_footer"], ha="center", color=MUTED, fontsize=9)
    fig.savefig(OUT / f"ticket_lifecycle_{lang}.png", bbox_inches="tight", facecolor=NAVY)
    plt.close(fig)


def hash_chain(lang: str) -> None:
    t = COPY[lang]
    fig, ax = _fig(12.5, 3.8)
    ax.text(0.5, 0.92, t["hash_title"], ha="center", color=TEXT, fontsize=14, fontweight="bold")
    ax.text(
        0.5,
        0.84,
        "event_hash_n = SHA256(canonical(event_n) + previous_event_hash)",
        ha="center",
        color=MUTED,
        fontsize=8,
    )
    edges = [MUTED, DENY, TEAL, ALLOW, AMBER]
    xs = [0.04, 0.24, 0.44, 0.64, 0.84]
    for x, (title, sub), edge in zip(xs, t["evt"], edges):
        _box(ax, x, 0.32, 0.14, 0.36, SLATE, edge, title, sub)
    for i in range(4):
        x1 = 0.04 + 0.14 + i * 0.20
        _arrow(ax, x1 + 0.005, 0.50, x1 + 0.05, 0.50)
    ax.text(0.5, 0.12, t["hash_footer"], ha="center", color=MUTED, fontsize=9)
    fig.savefig(OUT / f"hash_chain_{lang}.png", bbox_inches="tight", facecolor=NAVY)
    plt.close(fig)


def main() -> int:
    for lang in ("es", "en"):
        architecture(lang)
        ticket_lifecycle(lang)
        hash_chain(lang)
        for stem in ("architecture_layers", "ticket_lifecycle", "hash_chain"):
            p = OUT / f"{stem}_{lang}.png"
            print(f"wrote {p} ({p.stat().st_size} bytes)")
            # keep unprefixed aliases for ES (legacy)
            if lang == "es":
                (OUT / f"{stem}.png").write_bytes(p.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
