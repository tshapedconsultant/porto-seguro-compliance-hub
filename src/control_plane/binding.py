from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def action_binding(
    action: str,
    payload: dict[str, Any] | None = None,
    *,
    execution_id: str = "",
    tool: str = "",
) -> str:
    blob = canonical_json(
        {
            "action": action,
            "payload": payload or {},
            "execution_id": execution_id or "",
            "tool": tool or "",
        }
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
