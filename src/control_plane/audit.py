from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.governance.dpia_workspace.models import new_id, utc_now


class AuditLog:
    """Append-only JSONL. Not cryptographic immutability — hash is integrity metadata only."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or "docs/governance/control_plane_audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        record = {
            "event_id": new_id("EVT"),
            "timestamp": utc_now(),
            **event,
        }
        line = json.dumps(record, ensure_ascii=False)
        record["integrity_sha256"] = hashlib.sha256(line.encode("utf-8")).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
