from __future__ import annotations

import inspect
import os
from typing import Any, Callable

from src.control_plane.approvals import ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.default_policies import DEFAULT_POLICIES, TOOL_ALLOWLIST
from src.control_plane.evaluator import (
    CLASSIFIED_INTERNAL_ACTIONS,
    EXTERNAL_EFFECT_ACTIONS,
    evaluate_policies,
    validate_policy,
)
from src.control_plane.redaction import RedactionError, apply_redaction


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
        *,
        derive_security_from_server: bool = False,
        flow_legal_effect: bool = False,
        redact_output: bool = False,
        policies_source: str = "constructor",
    ) -> None:
        self.policies = list(policies or DEFAULT_POLICIES)
        self.approvals = approvals or ApprovalStore()
        self.audit = audit or AuditLog()
        self.stop_requested = False
        self.circuit_open = False
        self.consecutive_failures = 0
        self.tool_allowlist = set(TOOL_ALLOWLIST)
        self.derive_security_from_server = derive_security_from_server
        self.flow_legal_effect = flow_legal_effect
        self.redact_output = redact_output
        self.policies_source = policies_source
        self.policy_version = "active"

    def activate_policies(self, policies: list[dict[str, Any]], *, version: str, source: str) -> None:
        for policy in policies:
            validate_policy(policy)
        self.policies = list(policies)
        self.policy_version = version
        self.policies_source = source

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
        if self.derive_security_from_server:
            ctx.pop("legal_effect_decision", None)
            ctx.pop("redact_output", None)
            ctx["legal_effect_decision"] = self.flow_legal_effect
            ctx["redact_output"] = self.redact_output
        ctx["stop_requested"] = self.stop_requested or self.circuit_open
        if action in EXTERNAL_EFFECT_ACTIONS:
            ctx["action_class"] = "external"
            ctx["side_effects"] = "external_disclosure"
        elif action in CLASSIFIED_INTERNAL_ACTIONS:
            ctx["action_class"] = "internal_inference"
            ctx["side_effects"] = ctx.get("side_effects") or "none"
        else:
            ctx["action_class"] = "unclassified"
            ctx.setdefault("side_effects", "unknown")
        if ctx.get("tool") is None and action in self.tool_allowlist:
            ctx["tool"] = action
        tool = ctx.get("tool")
        if tool is not None:
            ctx["tool_allowed"] = tool in self.tool_allowlist
        elif action in EXTERNAL_EFFECT_ACTIONS:
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

        if effect == "REDACT" and action in EXTERNAL_EFFECT_ACTIONS:
            deny = {
                **decision,
                "effect": "DENY",
                "explanation": "External disclosure cannot be made safe by post-hoc REDACT; block the call.",
            }
            self.audit.append({**event, "action_taken": "blocked_before_execution"})
            raise RuntimeBlocked(deny)

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
            except (ValueError, RedactionError):
                deny = {**decision, "effect": "DENY", "explanation": "REDACT failed closed"}
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
    """Per-process singleton. Corrupt policy files fail closed; missing files may use bundled defaults."""
    global _default_runtime
    if _default_runtime is None:
        import json

        from src.control_plane.store import ControlPlaneStore

        require = os.getenv("REQUIRE_POLICIES_FILE", "").lower() in ("1", "true", "yes")
        store = ControlPlaneStore()
        source = "store"
        try:
            policies = store.load_policies()
        except json.JSONDecodeError:
            raise
        except FileNotFoundError:
            if require:
                raise
            policies = list(DEFAULT_POLICIES)
            source = "bundled_default"
        flow = os.getenv("FLOW_LEGAL_EFFECT", "").lower() in ("1", "true", "yes")
        redact = os.getenv("REDACT_OUTPUT", "").lower() in ("1", "true", "yes")
        approvals = ApprovalStore(path="docs/governance/approvals.json")
        _default_runtime = ReferenceRuntime(
            policies=policies,
            approvals=approvals,
            derive_security_from_server=True,
            flow_legal_effect=flow,
            redact_output=redact,
            policies_source=source,
        )
        _default_runtime.policy_version = "1"
    return _default_runtime


def execute_guarded(action: str, fn: Callable[..., Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_runtime().execute_guarded(action, fn, context)
