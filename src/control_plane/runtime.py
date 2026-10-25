from __future__ import annotations

import inspect
from typing import Any, Callable

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.default_policies import DEFAULT_POLICIES, TOOL_ALLOWLIST
from src.control_plane.evaluator import evaluate_policies
from src.control_plane.redaction import apply_redaction


class RuntimeBlocked(Exception):
    def __init__(self, decision: dict[str, Any]) -> None:
        super().__init__(decision.get("explanation") or decision.get("effect"))
        self.decision = decision


class RuntimeStopped(RuntimeBlocked):
    pass


class ReferenceRuntime:
    """
    Level 3 only for actions that go through execute_guarded.

    SINGLE PROCESS: stop_requested, circuit_open, consecutive_failures and
    ApprovalStore are in-memory. Streamlit/FastAPI workers do not share this
    state. Production must externalize stop, circuit, approvals, and audit.
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

    def reset_circuit(self, actor: str, reason: str) -> None:
        self.circuit_open = False
        self.consecutive_failures = 0
        self.audit.append(
            {
                "rule_triggered": "circuit_reset",
                "decision": "ALLOW",
                "actor": actor,
                "reason": reason,
            }
        )

    def execute_guarded(
        self,
        action: str,
        fn: Callable[..., Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = dict(context or {})
        ctx.pop("tool_allowed", None)
        ctx["action"] = action
        ctx["stop_requested"] = self.stop_requested or self.circuit_open
        if ctx.get("tool") is None and action in self.tool_allowlist:
            ctx["tool"] = action
        tool = ctx.get("tool")
        if tool is not None:
            ctx["tool_allowed"] = tool in self.tool_allowlist
        elif action in {"export_external", "delete", "shell", "write"}:
            ctx["tool_allowed"] = False

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
            self.audit.append(
                {
                    **event,
                    "action_taken": "quarantined_before_execution",
                    "resource_quarantined": ctx.get("execution_id") or action,
                }
            )
            raise RuntimeBlocked(decision)
        if effect == "ALERT":
            self.audit.append({**event, "action_taken": "alert_recorded", "notification": "audit_only"})
        if effect == "REQUIRE_HUMAN_APPROVAL":
            ok = self.approvals.is_approved(
                ctx.get("approval_ticket_id"),
                action=action,
                payload=ctx.get("approval_payload") or ctx.get("payload") or {},
                execution_id=str(ctx.get("execution_id") or ""),
                tool=str(ctx.get("tool") or ""),
            )
            if not ok:
                self.audit.append({**event, "action_taken": "pending_approval"})
                raise RuntimeBlocked(decision)

        call_ctx = dict(ctx)
        if effect == "LIMIT":
            max_records = int(decision.get("parameters", {}).get("max_records", 1000))
            records = call_ctx.get("records")
            if isinstance(records, list) and len(records) > max_records:
                call_ctx["records"] = records[:max_records]
                call_ctx["records_truncated"] = True
            call_ctx["record_count"] = (
                len(call_ctx["records"]) if isinstance(call_ctx.get("records"), list) else min(int(call_ctx.get("record_count") or 0), max_records)
            )
            call_ctx["limit_applied"] = max_records

        try:
            result = _invoke(fn, call_ctx)
        except (RuntimeBlocked, RuntimeStopped):
            raise
        except Exception:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 8:
                self.circuit_open = True
            self.audit.append({**event, "action_taken": "function_error"})
            raise

        self.consecutive_failures = 0
        redacted_fields: list[str] = []
        if effect == "REDACT":
            fields = decision.get("parameters", {}).get("redact_fields") or []
            try:
                result, redacted_fields = apply_redaction(result, fields)
            except ValueError:
                deny = {**decision, "effect": "DENY", "explanation": "REDACT without field policy"}
                self.audit.append({**event, "action_taken": "redact_denied"})
                raise RuntimeBlocked(deny) from None
            call_ctx["redacted_fields"] = redacted_fields
        self.audit.append(
            {
                **event,
                "action_taken": "executed",
                "verification_outcome": "ran_under_policy",
                "redacted_fields": redacted_fields,
            }
        )
        return {"status": "ok", "decision": decision, "result": result, "context": call_ctx}


def _invoke(fn: Callable[..., Any], call_ctx: dict[str, Any]) -> Any:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(call_ctx)
    if len(params) == 0:
        return fn()
    return fn(call_ctx)


_default_runtime: ReferenceRuntime | None = None


def get_runtime() -> ReferenceRuntime:
    """Per-process singleton. Loads ControlPlaneStore policies when present."""
    global _default_runtime
    if _default_runtime is None:
        from src.control_plane.store import ControlPlaneStore

        store = ControlPlaneStore()
        try:
            policies = store.load_policies()
        except Exception:
            policies = None
        _default_runtime = ReferenceRuntime(policies=policies or None)
    return _default_runtime


def execute_guarded(action: str, fn: Callable[..., Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_runtime().execute_guarded(action, fn, context)
