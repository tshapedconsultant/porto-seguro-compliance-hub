"""
Approval tickets with action binding.

Honest scope:
- ``requester`` / ``reviewer`` are free-text demo strings — **not** SSO / OIDC identities.
- JSON persistence (``approvals.json``) is **rewritable**, not WORM. Optional
  ``AuditLog`` appends create a local append-only trail of request/decide/consume
  events; that trail is still not legal immutability.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from src.control_plane.binding import action_binding
from src.governance.dpia_workspace.models import new_id, utc_now

AUTHN_NOTE = (
    "not SSO; binding only — reviewer/requester are free-text demo strings, "
    "not authenticated identities"
)
STORE_NOTE = (
    "JSON ticket store is rewritable (not WORM). Optional AuditLog appends are "
    "append-only locally with a hash chain but remain filesystem-rewritable."
)


class ApprovalError(Exception):
    pass


class _AuditSink(Protocol):
    def append(self, event: dict[str, Any]) -> Any: ...


class ApprovalStore:
    """Tickets with binding hash. Reviewer strings are not SSO. Optional JSON file for one process."""

    def __init__(
        self,
        path: Path | None = None,
        audit: Optional[_AuditSink] = None,
    ) -> None:
        self.path = Path(path) if path else None
        self.audit = audit
        self._tickets: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
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
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                raise ApprovalError("unknown ticket")
            if not reviewer:
                raise ApprovalError("unauthorised: empty reviewer")
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
        if not self.path:
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
