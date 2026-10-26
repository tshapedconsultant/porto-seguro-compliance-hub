from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from pathlib import Path
from typing import Any

from src.governance.dpia_workspace.models import new_id, utc_now

GENESIS = "0" * 64

# Honest scope: append + hash chain + checkpoint (+ optional HMAC) detect *some* rewrites.
# True WORM needs S3 Object Lock / external immutable store + KMS — not this local file.
# Dual-rewrite of JSONL + checkpoint (and forging HMAC if the shared secret is known)
# defeats local verification. AUDIT_HMAC_KEY is a shared secret, not KMS.

_HASH_EXCLUDE = frozenset({"event_hash", "previous_event_hash", "integrity_sha256", "event_hmac"})

INTEGRITY_NOTE = (
    "Local checkpoint + hash chain only. Dual-rewrite of JSONL and checkpoint "
    "defeats this check. Optional AUDIT_HMAC_KEY raises the bar vs casual rewrite "
    "but is a shared secret — not KMS, not external WORM / Object Lock."
)


def _canonical(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _hmac_key_bytes() -> bytes | None:
    raw = (os.getenv("AUDIT_HMAC_KEY") or "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def _sign_body(body: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical(body).encode("utf-8"), hashlib.sha256).hexdigest()


class AuditLog:
    """
    Append-only JSONL with hash chain: event_hash_n = SHA256(canonical(event_n) + previous_event_hash).

    After each append, a checkpoint sidecar records tail hash + content digest so operators
    can spot post-hoc truncation/rewrite relative to the last write. Optional ``AUDIT_HMAC_KEY``
    attaches an HMAC per event (shared secret ≠ KMS). This is **not** WORM / legal immutability —
    anyone with filesystem access (and the HMAC key, if set) can still replace both files.
    """

    def __init__(self, path: Path | None = None, *, checkpoint_every: int = 1) -> None:
        self.path = Path(path or "docs/governance/control_plane_audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.path.with_suffix(self.path.suffix + ".checkpoint.json")
        self.checkpoint_every = max(1, int(checkpoint_every))
        self._lock = threading.Lock()
        self._prev = self._load_tail_hash()
        self._appends_since_checkpoint = 0
        self._hmac_key = _hmac_key_bytes()

    def _load_tail_hash(self) -> str:
        rows = self.read_all()
        if not rows:
            return GENESIS
        return rows[-1].get("event_hash") or GENESIS

    def _file_digest(self) -> str:
        if not self.path.exists():
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def write_checkpoint(self) -> dict[str, Any]:
        """Persist a local integrity snapshot (detection aid, not cryptographic WORM)."""
        rows = self.read_all()
        payload = {
            "audit_path": str(self.path).replace("\\", "/"),
            "event_count": len(rows),
            "tail_event_hash": rows[-1]["event_hash"] if rows else GENESIS,
            "content_sha256": self._file_digest(),
            "signed_at": utc_now(),
            "integrity_note": INTEGRITY_NOTE,
            "hmac_enabled": bool(self._hmac_key),
            "worm_claimed": False,
            "kms_claimed": False,
        }
        self.checkpoint_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return payload

    def verify_checkpoint(self) -> tuple[bool, str]:
        if not self.checkpoint_path.exists():
            return False, "checkpoint_missing"
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, "checkpoint_corrupt"
        rows = self.read_all()
        if len(rows) != int(payload.get("event_count", -1)):
            return False, "event_count_mismatch"
        if rows and "event_hash" not in rows[-1]:
            return False, "tail_hash_mismatch"
        expected_tail = rows[-1]["event_hash"] if rows else GENESIS
        if payload.get("tail_event_hash") != expected_tail:
            return False, "tail_hash_mismatch"
        if payload.get("content_sha256") != self._file_digest():
            return False, "content_digest_mismatch"
        return True, "ok"

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            # Refresh key each append so tests can monkeypatch env mid-process.
            self._hmac_key = _hmac_key_bytes()
            record = {
                "event_id": new_id("EVT"),
                "timestamp": utc_now(),
                **event,
            }
            previous = self._prev
            body = {k: v for k, v in record.items() if k not in _HASH_EXCLUDE}
            if self._hmac_key:
                record["event_hmac"] = _sign_body(body, self._hmac_key)
                body = {k: v for k, v in record.items() if k not in _HASH_EXCLUDE}
            digest = hashlib.sha256((_canonical(body) + previous).encode("utf-8")).hexdigest()
            record["previous_event_hash"] = previous
            record["event_hash"] = digest
            # Append-only: never truncate/rewrite the JSONL in this path.
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._prev = digest
            self._appends_since_checkpoint += 1
            if self._appends_since_checkpoint >= self.checkpoint_every:
                self.write_checkpoint()
                self._appends_since_checkpoint = 0
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
        key = _hmac_key_bytes()
        for i, row in enumerate(self.read_all()):
            body = {k: v for k, v in row.items() if k not in _HASH_EXCLUDE}
            expected = hashlib.sha256((_canonical(body) + prev).encode("utf-8")).hexdigest()
            if row.get("previous_event_hash") != prev or row.get("event_hash") != expected:
                return False, f"chain_break_at_{i}"
            if key:
                expected_mac = _sign_body(body, key)
                got = row.get("event_hmac") or ""
                if not got or not hmac.compare_digest(got, expected_mac):
                    return False, f"hmac_mismatch_at_{i}"
            prev = row["event_hash"]
        return True, "ok"
