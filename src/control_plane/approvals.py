from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.control_plane.binding import action_binding
from src.governance.dpia_workspace.models import new_id, utc_now


class ApprovalError(Exception):
    pass


class ApprovalStore:
    """Tickets with binding hash. Reviewer strings are not SSO. Optional JSON file for one process."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._tickets: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._tickets = {k: v for k, v in raw.items() if isinstance(v, dict)}
            except json.JSONDecodeError:
                self._tickets = {}

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
            "authn_note": "reviewer string is not authenticated identity",
        }
        with self._lock:
            self._tickets[ticket["ticket_id"]] = ticket
            self._persist()
        return ticket

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
                raise ApprovalError("ticket expired")
            ticket["status"] = "approved" if approve else "rejected"
            ticket["reviewer"] = reviewer
            ticket["decision_rationale"] = rationale
            ticket["decided_at"] = utc_now()
            self._persist()
            return ticket

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
                return False
            if ticket["status"] != "approved":
                return False
            expected = action_binding(action, payload, execution_id=execution_id, tool=tool)
            if ticket.get("action_binding") != expected:
                return False
            ticket["status"] = "consumed"
            ticket["consumed_at"] = utc_now()
            self._persist()
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
