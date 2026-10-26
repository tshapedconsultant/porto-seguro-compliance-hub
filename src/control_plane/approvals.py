"""
Approval tickets with action binding.

Honest scope:
- ``requester`` / ``reviewer`` are free-text demo strings — **not** SSO / OIDC identities.
- JSON persistence (``approvals.json``) is **rewritable** and remains the authoritative
  ticket store for this build — audit trail visibility ≠ prevent ticket edit.
- Optional ``AuditLog`` appends create a local append-only trail of request/decide/consume
  events; that trail is still not legal immutability / WORM.
- Production needs Postgres/Redis transactions + append-only audit; this module only
  implements ``APPROVAL_BACKEND=memory|json`` (stub comment for future redis/postgres).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from src.control_plane.binding import action_binding
from src.governance.dpia_workspace.models import new_id, utc_now

logger = logging.getLogger(__name__)

AUTHN_NOTE = (
    "not SSO; binding only — reviewer/requester are free-text demo strings, "
    "not authenticated identities. Optional APPROVAL_API_KEY / APPROVAL_SEPARATE_ACTORS "
    "are demo separations of duties — still not OIDC."
)
STORE_NOTE = (
    "Authoritative ticket store is mutable JSON (or in-memory). Optional AuditLog "
    "appends are append-only locally with a hash chain but remain filesystem-rewritable. "
    "Audit visibility ≠ prevent ticket edit. Production needs Postgres/Redis + append-only audit."
)

# Backend selection stub: only memory|json are implemented. Redis/Postgres would need deps.
SUPPORTED_APPROVAL_BACKENDS = frozenset({"memory", "json"})


class ApprovalError(Exception):
    pass


class ApprovalDesyncError(ApprovalError):
    """JSON ticket claims approved/consumed but audit trail has no matching decide event."""


class _AuditSink(Protocol):
    def append(self, event: dict[str, Any]) -> Any: ...

    def read_all(self) -> list[dict[str, Any]]: ...


def resolve_approval_backend(explicit: str | None = None) -> str:
    """
    Select ticket persistence backend.

    ``APPROVAL_BACKEND=memory|json`` only. Values like ``redis`` / ``postgres`` are
    documented stubs — not implemented (no Redis/Postgres dependency in this build).
    """
    raw = (explicit if explicit is not None else os.getenv("APPROVAL_BACKEND", "") or "").strip().lower()
    if not raw:
        return "json"  # default when a path is used; caller may force memory
    if raw in ("redis", "postgres", "postgresql"):
        raise ApprovalError(
            f"APPROVAL_BACKEND={raw} is not implemented in this build "
            "(interface stub only). Use memory|json; production needs a real transactional store."
        )
    if raw not in SUPPORTED_APPROVAL_BACKENDS:
        raise ApprovalError(f"Unknown APPROVAL_BACKEND={raw!r}; supported: memory|json")
    return raw


class ApprovalStore:
    """
    Tickets with binding hash. Reviewer strings are not SSO.

    Authoritative store is mutable JSON / memory. Use ``verify_against_audit()`` and
    optional ``APPROVAL_AUDIT_STRICT`` to detect obvious JSON↔audit desync.
    """

    def __init__(
        self,
        path: Path | None = None,
        audit: Optional[_AuditSink] = None,
        *,
        backend: str | None = None,
        audit_strict: bool | None = None,
    ) -> None:
        env_backend = (os.getenv("APPROVAL_BACKEND") or "").strip().lower()
        if backend is not None:
            self.backend = resolve_approval_backend(backend)
        elif env_backend:
            self.backend = resolve_approval_backend(env_backend)
        elif path:
            self.backend = "json"
        else:
            self.backend = "memory"

        if self.backend == "json":
            self.path = Path(path) if path else Path("docs/governance/approvals.json")
        else:
            self.path = None

        self.audit = audit
        if audit_strict is None:
            audit_strict = os.getenv("APPROVAL_AUDIT_STRICT", "").lower() in ("1", "true", "yes")
        self.audit_strict = bool(audit_strict)
        self._tickets: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        if self.path and self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._tickets = {k: v for k, v in raw.items() if isinstance(v, dict)}
            except json.JSONDecodeError:
                self._tickets = {}

    def _append_audit(self, kind: str, ticket: dict[str, Any]) -> None:
        if self.audit is None:
            return
        self.audit.append(
            {
                "rule_triggered": f"approval_{kind}",
                "decision": ticket.get("status"),
                "ticket_id": ticket.get("ticket_id"),
                "action": ticket.get("action"),
                "action_binding": ticket.get("action_binding"),
                "requester": ticket.get("requester"),
                "reviewer": ticket.get("reviewer"),
                "worm_claimed": False,
                "store_note": STORE_NOTE,
                "authn_note": AUTHN_NOTE,
            }
        )

    def request(
        self,
        *,
        action: str,
        requester: str,
        reason: str,
        ttl_seconds: int = 3600,
        payload: dict[str, Any] | None = None,
        execution_id: str = "",
        tool: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        binding = action_binding(action, payload, execution_id=execution_id, tool=tool)
        ticket = {
            "ticket_id": new_id("APR"),
            "action": action,
            "tool": tool,
            "execution_id": execution_id,
            "requester": requester,
            "reason": reason,
            "payload": payload or {},
            "action_binding": binding,
            "status": "pending",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "reviewer": "",
            "decision_rationale": "",
            "decided_at": "",
            "authn_note": AUTHN_NOTE,
            "reviewer_auth_note": AUTHN_NOTE,
            "store_note": STORE_NOTE,
        }
        with self._lock:
            self._tickets[ticket["ticket_id"]] = ticket
            self._persist()
            self._append_audit("request", ticket)
        return dict(ticket)

    def decide(self, ticket_id: str, *, reviewer: str, approve: bool, rationale: str) -> dict[str, Any]:
        separate = os.getenv("APPROVAL_SEPARATE_ACTORS", "").lower() in ("1", "true", "yes")
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                raise ApprovalError("unknown ticket")
            if not reviewer:
                raise ApprovalError("unauthorised: empty reviewer")
            if separate and reviewer.strip().lower() == str(ticket.get("requester") or "").strip().lower():
                raise ApprovalError(
                    "APPROVAL_SEPARATE_ACTORS: reviewer must differ from requester "
                    "(demo separation of duties — not OIDC identity proof)"
                )
            if ticket["status"] != "pending":
                raise ApprovalError("ticket is not pending")
            if datetime.fromisoformat(ticket["expires_at"]) < datetime.now(timezone.utc):
                ticket["status"] = "expired"
                self._persist()
                self._append_audit("expire", ticket)
                raise ApprovalError("ticket expired")
            ticket["status"] = "approved" if approve else "rejected"
            ticket["reviewer"] = reviewer
            ticket["decision_rationale"] = rationale
            ticket["decided_at"] = utc_now()
            ticket["authn_note"] = AUTHN_NOTE
            ticket["reviewer_auth_note"] = AUTHN_NOTE
            ticket["store_note"] = STORE_NOTE
            self._persist()
            self._append_audit("decide", ticket)
            return dict(ticket)

    def verify_against_audit(self, ticket_id: str | None = None) -> tuple[bool, str]:
        """
        Compare JSON ticket state to the last matching audit binding/decide event.

        Detects obvious desync (e.g. JSON edited to ``approved`` without an
        ``approval_decide`` audit row). Does **not** make JSON immutable.
        """
        if self.audit is None or not hasattr(self.audit, "read_all"):
            return True, "no_audit_sink"
        try:
            rows = self.audit.read_all()
        except Exception as exc:  # noqa: BLE001 — best-effort integrity aid
            return False, f"audit_unreadable:{exc}"

        decide_by_ticket: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("rule_triggered") != "approval_decide":
                continue
            tid = row.get("ticket_id")
            if tid:
                decide_by_ticket[str(tid)] = row

        with self._lock:
            tickets = (
                {ticket_id: self._tickets[ticket_id]}
                if ticket_id and ticket_id in self._tickets
                else dict(self._tickets)
            )

        for tid, ticket in tickets.items():
            status = ticket.get("status")
            if status not in {"approved", "consumed"}:
                continue
            audit_row = decide_by_ticket.get(tid)
            if not audit_row:
                return False, f"missing_audit_decide:{tid}"
            # decide() records status as approved|rejected on the audit row.
            if audit_row.get("decision") != "approved":
                return False, f"audit_decision_mismatch:{tid}"
            if ticket.get("action_binding") and audit_row.get("action_binding"):
                if ticket.get("action_binding") != audit_row.get("action_binding"):
                    return False, f"binding_desync:{tid}"
            if ticket.get("action") and audit_row.get("action"):
                if ticket.get("action") != audit_row.get("action"):
                    return False, f"action_desync:{tid}"
        return True, "ok"

    def is_approved(
        self,
        ticket_id: str | None,
        *,
        action: str,
        payload: dict[str, Any] | None = None,
        execution_id: str = "",
        tool: str = "",
    ) -> bool:
        if not ticket_id:
            return False
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return False
            if datetime.fromisoformat(ticket["expires_at"]) < datetime.now(timezone.utc):
                ticket["status"] = "expired"
                self._persist()
                self._append_audit("expire", ticket)
                return False
            if ticket["status"] != "approved":
                return False
            expected = action_binding(action, payload, execution_id=execution_id, tool=tool)
            if ticket.get("action_binding") != expected:
                return False

            # Optional strict: JSON says approved but no matching audit decide → DENY.
            if self.audit_strict:
                ok, reason = self.verify_against_audit(ticket_id)
                if not ok:
                    logger.warning("APPROVAL_AUDIT_STRICT deny: %s", reason)
                    if self.audit is not None:
                        self.audit.append(
                            {
                                "rule_triggered": "approval_audit_desync",
                                "decision": "DENY",
                                "ticket_id": ticket_id,
                                "reason": reason,
                                "worm_claimed": False,
                                "store_note": STORE_NOTE,
                            }
                        )
                    raise ApprovalDesyncError(reason)

            ticket["status"] = "consumed"
            ticket["consumed_at"] = utc_now()
            self._persist()
            self._append_audit("consume", ticket)
            return True

    def get(self, ticket_id: str) -> dict[str, Any] | None:
        return self._tickets.get(ticket_id)

    def list_pending(self) -> list[dict[str, Any]]:
        return [t for t in self._tickets.values() if t["status"] == "pending"]

    def _persist(self) -> None:
        if self.backend != "json" or not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".apr_", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(self._tickets, indent=2, ensure_ascii=False))
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
