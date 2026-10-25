from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.governance.dpia_workspace.models import new_id, utc_now

GENESIS = "0" * 64


def _canonical(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


class AuditLog:
    """
    Append-only JSONL with hash chain: event_hash_n = SHA256(canonical(event_n) + previous_event_hash).
    Still not WORM / legal immutability — the file can be rewritten on disk.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or "docs/governance/control_plane_audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = self._load_tail_hash()

    def _load_tail_hash(self) -> str:
        rows = self.read_all()
        if not rows:
            return GENESIS
        return rows[-1].get("event_hash") or GENESIS

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        record = {
            "event_id": new_id("EVT"),
            "timestamp": utc_now(),
            **event,
        }
        previous = self._prev
        body = {k: v for k, v in record.items() if k not in {"event_hash", "previous_event_hash", "integrity_sha256"}}
        digest = hashlib.sha256((_canonical(body) + previous).encode("utf-8")).hexdigest()
        record["previous_event_hash"] = previous
        record["event_hash"] = digest
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._prev = digest
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def verify_chain(self) -> tuple[bool, str]:
        prev = GENESIS
        for i, row in enumerate(self.read_all()):
            body = {k: v for k, v in row.items() if k not in {"event_hash", "previous_event_hash", "integrity_sha256"}}
            expected = hashlib.sha256((_canonical(body) + prev).encode("utf-8")).hexdigest()
            if row.get("previous_event_hash") != prev or row.get("event_hash") != expected:
                return False, f"chain_break_at_{i}"
            prev = row["event_hash"]
        return True, "ok"
