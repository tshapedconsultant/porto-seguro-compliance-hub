from __future__ import annotations

from typing import Any, Callable

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.default_policies import DEFAULT_POLICIES, TOOL_ALLOWLIST
from src.control_plane.evaluator import evaluate_policies


class RuntimeBlocked(Exception):
    def __init__(self, decision: dict[str, Any]) -> None:
        super().__init__(decision.get("explanation") or decision.get("effect"))
        self.decision = decision


class RuntimeStopped(RuntimeBlocked):
    pass


class ReferenceRuntime:
    """
    Level 3 only for actions that go through execute_guarded.
    Does not claim protection of traffic that never hits this adapter.
    """

    def __init__(
        self,
        policies: list[dict[str, Any]] | None = None,
        approvals: ApprovalStore | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.policies = list(policies or DEFAULT_POLICIES)
        self.approvals = approvals or ApprovalStore()
        self.audit = audit or AuditLog()
        self.stop_requested = False
        self.circuit_open = False
        self.consecutive_failures = 0
        self.tool_allowlist = set(TOOL_ALLOWLIST)

    def request_stop(self, reason: str, actor: str) -> None:
        self.stop_requested = True
        self.audit.append({"rule_triggered": "stop", "decision": "STOP", "actor": actor, "reason": reason})

    def clear_stop(self, actor: str) -> None:
        self.stop_requested = False
        self.audit.append({"rule_triggered": "stop_cleared", "decision": "ALLOW", "actor": actor})

    def execute_guarded(
        self,
        action: str,
        fn: Callable[[], Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = dict(context or {})
        ctx.setdefault("action", action)
        ctx["stop_requested"] = self.stop_requested or self.circuit_open
        tool = ctx.get("tool")
        if tool is not None:
            ctx["tool_allowed"] = tool in self.tool_allowlist

        decision = evaluate_policies(ctx, self.policies)
        event = {
            "execution_id": ctx.get("execution_id"),
            "action": action,
            "policy_version": decision.get("policy_version"),
            "rule_triggered": decision.get("policy_id"),
            "decision": decision.get("effect"),
            "explanation": decision.get("explanation"),
        }

        if ctx.get("dry_run"):
            self.audit.append({**event, "action_taken": "dry_run"})
            return {"status": "dry_run", "decision": decision, "result": None}

        effect = decision["effect"]
        if effect == "STOP":
            self.audit.append({**event, "action_taken": "blocked_before_execution"})
            raise RuntimeStopped(decision)
        if effect == "DENY":
            self.audit.append({**event, "action_taken": "blocked_before_execution"})
            raise RuntimeBlocked(decision)
        if effect == "QUARANTINE":
            self.audit.append({**event, "action_taken": "quarantined_before_execution"})
            raise RuntimeBlocked(decision)
        if effect == "REQUIRE_HUMAN_APPROVAL":
            if not self.approvals.is_approved(ctx.get("approval_ticket_id")):
                self.audit.append({**event, "action_taken": "pending_approval"})
                raise RuntimeBlocked(decision)

        call_ctx = dict(ctx)
        if effect == "LIMIT":
            max_records = int(decision.get("parameters", {}).get("max_records", 1000))
            call_ctx["record_count"] = min(int(call_ctx.get("record_count") or 0), max_records)
            call_ctx["limit_applied"] = max_records

        try:
            result = fn()
        except Exception:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 8:
                self.circuit_open = True
            self.audit.append({**event, "action_taken": "function_error"})
            raise

        self.consecutive_failures = 0
        if effect == "REDACT" and isinstance(result, dict):
            result = {**result, "redacted": True}
        self.audit.append({**event, "action_taken": "executed", "verification_outcome": "ran_under_policy"})
        return {"status": "ok", "decision": decision, "result": result, "context": call_ctx}


_default_runtime: ReferenceRuntime | None = None


def get_runtime() -> ReferenceRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ReferenceRuntime()
    return _default_runtime


def execute_guarded(action: str, fn: Callable[[], Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_runtime().execute_guarded(action, fn, context)
