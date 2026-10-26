from __future__ import annotations

from typing import Any

REDACT_MARK = "[REDACTED]"


class RedactionError(ValueError):
    """Required fields were not redacted; fail closed."""


def _match_key(key: str, fields: set[str]) -> bool:
    if key in fields:
        return True
    lowered = key.lower()
    return any(f.lower() == lowered for f in fields)


def _walk(obj: Any, fields: set[str], replacement: str, found: set[str]) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if _match_key(str(key), fields):
                found.add(next((f for f in fields if f.lower() == str(key).lower()), str(key)))
                out[key] = replacement
            else:
                out[key] = _walk(value, fields, replacement, found)
        return out
    if isinstance(obj, list):
        return [_walk(item, fields, replacement, found) for item in obj]
    return obj


def _apply_dotted(obj: Any, path: str, replacement: str) -> bool:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    leaf = parts[-1]
    if isinstance(cur, dict) and leaf in cur:
        cur[leaf] = replacement
        return True
    return False


def apply_redaction(
    result: Any,
    fields: list[str] | None,
    *,
    replacement: str = REDACT_MARK,
    require_all: bool = True,
) -> tuple[Any, list[str]]:
    """Recursive redaction by key name or dotted path. Missing required fields fail closed."""
    if not fields:
        raise RedactionError("REDACT requires parameters.redact_fields")
    if not isinstance(result, (dict, list)):
        raise RedactionError("REDACT only applies to dict or list outputs")

    simple = {f for f in fields if "." not in f}
    dotted = [f for f in fields if "." in f]
    found: set[str] = set()
    out = _walk(result, simple, replacement, found)
    for path in dotted:
        if _apply_dotted(out, path, replacement):
            found.add(path)

    missing = [f for f in fields if f not in found and f.lower() not in {x.lower() for x in found}]
    if require_all and missing:
        raise RedactionError("Required redact fields not present: " + ", ".join(missing))
    return out, sorted(found)
