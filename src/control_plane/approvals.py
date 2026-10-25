from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.control_plane.binding import action_binding
from src.governance.dpia_workspace.models import new_id, utc_now


class ApprovalError(Exception):
    pass


class ApprovalStore:
    """In-process tickets. Not SSO/RBAC. Binding hash prevents confused-deputy reuse."""

    def __init__(self) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}

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
        self._tickets[ticket["ticket_id"]] = ticket
        return ticket

    def decide(self, ticket_id: str, *, reviewer: str, approve: bool, rationale: str) -> dict[str, Any]:
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
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False
        if datetime.fromisoformat(ticket["expires_at"]) < datetime.now(timezone.utc):
            ticket["status"] = "expired"
            return False
        if ticket["status"] != "approved":
            return False
        expected = action_binding(action, payload, execution_id=execution_id, tool=tool)
        return ticket.get("action_binding") == expected

    def get(self, ticket_id: str) -> dict[str, Any] | None:
        return self._tickets.get(ticket_id)

    def list_pending(self) -> list[dict[str, Any]]:
        return [t for t in self._tickets.values() if t["status"] == "pending"]
