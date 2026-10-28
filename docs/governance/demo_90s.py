#!/usr/bin/env python3
"""
Control-plane evidence strip for the governed AI demo.

Pairs with Streamlit page 09 (control room). Prints tagged terminal lines so the
recording proves the controls are real — not Mermaid on screen.

Tags (success path):
  [DENY] [TICKET] [APPROVED RUN] [ANTI-REPLAY] [REDACT] [AUDIT] [TAMPER]

Usage (from repo root):
  python docs/governance/demo_90s.py
  python docs/governance/demo_90s.py --fast
  python docs/governance/demo_90s.py --tamper-only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.runtime import ReferenceRuntime, RuntimeBlocked

AUDIT_PATH = ROOT / "docs" / "governance" / "_demo_90s_audit.jsonl"


def _pause(seconds: float, *, fast: bool) -> None:
    time.sleep(0.35 if fast else seconds)


def _clear_audit() -> None:
    cp = AUDIT_PATH.with_suffix(AUDIT_PATH.suffix + ".checkpoint.json")
    for path in (AUDIT_PATH, cp):
        if path.exists():
            path.unlink()


def _safe_print(s: str) -> None:
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


def _banner() -> None:
    print()
    print("=" * 64)
    _safe_print("  PORTO SEGURO - CONTROL PLANE EVIDENCE STRIP")
    _safe_print("  DENY -> TICKET -> APPROVED -> ANTI-REPLAY -> REDACT -> AUDIT -> TAMPER")
    print("=" * 64)
    print()


def run_tamper_demo(*, fast: bool) -> int:
    """Clumsy JSONL rewrite → verify_chain fails (local detection, not WORM)."""
    path = ROOT / "docs" / "governance" / "_demo_tamper_audit.jsonl"
    cp = path.with_suffix(path.suffix + ".checkpoint.json")
    for p in (path, cp):
        if p.exists():
            p.unlink()

    audit = AuditLog(path)
    audit.append({"rule_triggered": "demo_a", "decision": "ALLOW"})
    audit.append({"rule_triggered": "demo_b", "decision": "ALLOW"})
    ok, msg = audit.verify_chain()
    print("[TAMPER] before rewrite: verify_chain=", ok, msg)
    _pause(1.2, fast=fast)

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"demo_a"', '"demo_TAMPERED"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok2, msg2 = audit.verify_chain()
    print("[TAMPER] after rewrite:  verify_chain=", ok2, msg2)
    print("[TAMPER] note: local hash-chain detection - not WORM / not certification")
    return 0 if (ok and not ok2) else 2


def run_evidence(*, fast: bool, with_tamper: bool) -> int:
    _banner()
    _clear_audit()

    audit = AuditLog(AUDIT_PATH)
    store = ApprovalStore(audit=audit, backend="memory")
    rt = ReferenceRuntime(approvals=store, audit=audit)

    # --- DENY (Art. 5) — model never runs ---
    print("--- beat: policy DENY ---")
    _pause(0.8, fast=fast)
    try:
        rt.execute_guarded(
            "predict_ebm",
            lambda: "SHOULD_NOT_RUN",
            {"art5_concern": True, "tool": "predict_ebm"},
        )
        print("[DENY] UNEXPECTED: not blocked")
        return 1
    except RuntimeBlocked as exc:
        print("[DENY]", exc.decision.get("policy_id"), exc.decision.get("effect"))
    _pause(2.0, fast=fast)

    # --- TICKET + APPROVED RUN ---
    print("--- beat: human approval ---")
    payload = {"case": "porto_lab_score_90s"}
    ticket = rt.approvals.request(
        action="score",
        requester="demo-req",
        reason="legal_effect lab",
        payload=payload,
    )
    print("[TICKET]", ticket["ticket_id"], ticket["status"])
    _pause(1.2, fast=fast)

    rt.approvals.decide(
        ticket["ticket_id"],
        reviewer="demo-rev",
        approve=True,
        rationale="HITL ok",
    )
    decided = rt.approvals.get(ticket["ticket_id"]) or {}
    print("[TICKET]", ticket["ticket_id"], "->", decided.get("status"))

    out = rt.execute_guarded(
        "score",
        lambda: {"score": 0.31, "email": "a@b.c", "name": "Ada"},
        {
            "legal_effect_decision": True,
            "approval_ticket_id": ticket["ticket_id"],
            "approval_payload": payload,
        },
    )
    print("[APPROVED RUN]", out["status"], out["decision"].get("effect"), out.get("result"))
    _pause(1.5, fast=fast)

    # --- ANTI-REPLAY ---
    print("--- beat: anti-replay ---")
    try:
        rt.execute_guarded(
            "score",
            lambda: {"score": 0.99},
            {
                "legal_effect_decision": True,
                "approval_ticket_id": ticket["ticket_id"],
                "approval_payload": payload,
            },
        )
        print("[ANTI-REPLAY] UNEXPECTED: replay allowed")
        return 1
    except RuntimeBlocked as exc:
        consumed = rt.approvals.get(ticket["ticket_id"]) or {}
        print(
            "[ANTI-REPLAY]",
            "blocked",
            exc.decision.get("effect"),
            "ticket=",
            consumed.get("status"),
        )
    _pause(1.5, fast=fast)

    # --- REDACT ---
    print("--- beat: redaction ---")
    red = rt.execute_guarded(
        "predict_ebm",
        lambda: {"email": "a@b.c", "name": "Ada", "score": 0.31},
        {"tool": "predict_ebm", "record_count": 1, "redact_output": True},
    )
    print("[REDACT]", red["result"], "fields:", red["context"].get("redacted_fields"))
    _pause(1.5, fast=fast)

    # --- AUDIT ---
    print("--- beat: audit chain ---")
    ok, msg = audit.verify_chain()
    rows = audit.read_all()
    print("[AUDIT]", "verify_chain=", ok, msg, "events=", len(rows))
    for row in rows[-5:]:
        label = row.get("rule_triggered") or row.get("action_taken") or row.get("decision")
        h = (row.get("event_hash") or "")[:12]
        prev = (row.get("previous_event_hash") or "")[:12]
        print(" ", label, "hash=", h, "prev=", prev)
    _pause(1.2, fast=fast)

    if with_tamper:
        print("--- beat: tamper detection ---")
        rc = run_tamper_demo(fast=fast)
        if rc != 0:
            return rc

    print()
    print("=" * 64)
    print("  EVIDENCE STRIP COMPLETE")
    print("  The model proposes. Controls decide. Evidence remains observable.")
    print("  Not AEPD / GDPR / EU AI Act certification.")
    print("=" * 64)
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Control-plane evidence strip for recording")
    parser.add_argument("--fast", action="store_true", help="Minimal sleeps (CI / dry-run)")
    parser.add_argument("--tamper-only", action="store_true", help="Only the tamper mini-demo")
    parser.add_argument("--no-tamper", action="store_true", help="Skip tamper beat")
    args = parser.parse_args()

    if args.tamper_only:
        return run_tamper_demo(fast=args.fast)
    return run_evidence(fast=args.fast, with_tamper=not args.no_tamper)


if __name__ == "__main__":
    raise SystemExit(main())
