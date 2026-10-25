from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.governance.dpia_workspace.models import new_id, utc_now


class ApprovalError(Exception):
    pass


class ApprovalStore:
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
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        ticket = {
            "ticket_id": new_id("APR"),
            "action": action,
            "requester": requester,
            "reason": reason,
            "payload": payload or {},
            "status": "pending",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "reviewer": "",
            "decision_rationale": "",
            "decided_at": "",
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

    def is_approved(self, ticket_id: str | None) -> bool:
        if not ticket_id:
            return False
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False
        if datetime.fromisoformat(ticket["expires_at"]) < datetime.now(timezone.utc):
            ticket["status"] = "expired"
            return False
        return ticket["status"] == "approved"

    def get(self, ticket_id: str) -> dict[str, Any] | None:
        return self._tickets.get(ticket_id)

    def list_pending(self) -> list[dict[str, Any]]:
        return [t for t in self._tickets.values() if t["status"] == "pending"]
