from __future__ import annotations

from typing import Any

REDACT_MARK = "[REDACTED]"


def apply_redaction(
    result: Any,
    fields: list[str] | None,
    *,
    replacement: str = REDACT_MARK,
) -> tuple[Any, list[str]]:
    """Deterministic field redaction. Empty field list is a policy failure, not a no-op."""
    if not fields:
        raise ValueError("REDACT requires parameters.redact_fields")
    if not isinstance(result, dict):
        raise ValueError("REDACT only applies to dict outputs")
    out = dict(result)
    transformed: list[str] = []
    for field in fields:
        if field in out and out[field] != replacement:
            out[field] = replacement
            transformed.append(field)
    return out, transformed
