from __future__ import annotations

from typing import Any

PRECEDENCE = (
    "STOP",
    "DENY",
    "QUARANTINE",
    "REQUIRE_HUMAN_APPROVAL",
    "REDACT",
    "LIMIT",
    "ALERT",
    "ALLOW",
)

OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in (a or []),
    "exists": lambda a, b: bool(a) if b else a is not None,
}

ALLOWED_EFFECTS = set(PRECEDENCE)


def _match_clause(context: dict[str, Any], clause: dict[str, Any]) -> bool:
    field = clause.get("field")
    op = clause.get("op", "eq")
    if op not in OPS:
        raise ValueError(f"Unknown operator: {op}")
    return bool(OPS[op](context.get(field), clause.get("value")))


def _match_policy(context: dict[str, Any], policy: dict[str, Any]) -> bool:
    """all AND any: every all-clause must hold; if any exists, at least one any-clause must hold."""
    cond = policy.get("conditions") or {}
    has_all = "all" in cond
    has_any = "any" in cond
    if not has_all and not has_any:
        return True
    ok_all = all(_match_clause(context, c) for c in cond.get("all") or []) if has_all else True
    ok_any = any(_match_clause(context, c) for c in cond.get("any") or []) if has_any else True
    return ok_all and ok_any


def validate_policy(policy: dict[str, Any]) -> None:
    effect = policy.get("effect")
    if effect not in ALLOWED_EFFECTS:
        raise ValueError(f"Invalid effect: {effect}")
    cond = policy.get("conditions") or {}
    for group in ("all", "any"):
        for clause in cond.get(group) or []:
            op = clause.get("op", "eq")
            if op not in OPS:
                raise ValueError(f"Unknown operator: {op}")
    if effect == "REDACT" and not (policy.get("parameters") or {}).get("redact_fields"):
        raise ValueError("REDACT policies must set parameters.redact_fields")
    if effect == "LIMIT" and "max_records" not in (policy.get("parameters") or {}):
        raise ValueError("LIMIT policies must set parameters.max_records")


def evaluate_policies(
    context: dict[str, Any],
    policies: list[dict[str, Any]],
    *,
    fail_closed_on_error: bool = True,
) -> dict[str, Any]:
    """Deterministic evaluation. Mandatory DENY/STOP cannot be overridden by ALLOW."""
    try:
        for policy in policies:
            if policy.get("enabled", True):
                validate_policy(policy)
        enabled = [p for p in policies if p.get("enabled", True)]
        enabled.sort(key=lambda p: int(p.get("priority", 100)))
        matched: list[dict[str, Any]] = []
        for policy in enabled:
            if _match_policy(context, policy):
                matched.append(policy)

        effects = [p.get("effect", "ALLOW") for p in matched] or ["ALLOW"]
        mandatory_block = [
            p for p in matched if p.get("mandatory") and p.get("effect") in {"DENY", "STOP", "QUARANTINE"}
        ]
        if mandatory_block:
            winner = sorted(mandatory_block, key=lambda p: PRECEDENCE.index(p["effect"]))[0]
        else:
            winner = (
                sorted(matched, key=lambda p: PRECEDENCE.index(p.get("effect", "ALLOW")))[0]
                if matched
                else {
                    "policy_id": "default-allow",
                    "version": "0",
                    "effect": "ALLOW",
                    "mandatory": False,
                }
            )

        return {
            "effect": winner.get("effect", "ALLOW"),
            "policy_id": winner.get("policy_id"),
            "policy_version": winner.get("version"),
            "mandatory": bool(winner.get("mandatory")),
            "matched_policy_ids": [p.get("policy_id") for p in matched],
            "explanation": winner.get("rationale") or winner.get("description") or "",
            "parameters": winner.get("parameters") or {},
            "enforcement_point": winner.get("enforcement_point", "pre_execution"),
            "obligation_type": winner.get("obligation_type", "internal_rule"),
            "dry_run": bool(context.get("dry_run")),
            "effects_seen": effects,
        }
    except Exception as exc:
        if fail_closed_on_error:
            return {
                "effect": "DENY",
                "policy_id": "fail-closed",
                "policy_version": "0",
                "mandatory": True,
                "matched_policy_ids": [],
                "explanation": f"Policy evaluation failed closed: {type(exc).__name__}",
                "parameters": {},
                "enforcement_point": "pre_execution",
                "obligation_type": "security_restriction",
                "dry_run": bool(context.get("dry_run")),
                "effects_seen": ["DENY"],
            }
        raise
