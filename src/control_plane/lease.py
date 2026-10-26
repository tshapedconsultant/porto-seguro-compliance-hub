"""
Filesystem instance leases for multi-replica detection (not Redis).

Honest scope:
- ``WEB_CONCURRENCY`` / ``UVICORN_WORKERS`` / ``WORKERS`` only see launcher env —
  they miss horizontal replicas (1 worker per container × N pods).
- Cheap FS heartbeats under ``CONTROL_PLANE_LEASE_DIR`` with ``INSTANCE_ID``.
- When ``CONTROL_PLANE_STRICT`` and >1 recent heartbeats from different instance IDs
  → refuse start. TTL ~60s. Not a distributed lock / Redis lease.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LEASE_TTL_SECONDS = 60


def instance_id() -> str:
    raw = (os.getenv("INSTANCE_ID") or "").strip()
    if raw:
        return raw
    # Stable-enough for a process lifetime; regenerated each process if unset.
    return f"pid-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def lease_dir() -> Path | None:
    raw = (os.getenv("CONTROL_PLANE_LEASE_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw)


def write_heartbeat(
    directory: Path,
    *,
    iid: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    iid = iid or instance_id()
    path = directory / f"lease-{_safe_name(iid)}.json"
    payload = {
        "instance_id": iid,
        "pid": os.getpid(),
        "updated_at": time.time(),
        "ttl_seconds": int(ttl_seconds),
        "note": (
            "Filesystem heartbeat only — not Redis. Detects co-located replicas "
            "sharing CONTROL_PLANE_LEASE_DIR; misses isolated filesystems."
        ),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def recent_heartbeats(
    directory: Path,
    *,
    now: float | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> list[dict[str, Any]]:
    now = time.time() if now is None else now
    if not directory.exists():
        return []
    live: list[dict[str, Any]] = []
    for path in directory.glob("lease-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        updated = float(payload.get("updated_at") or 0)
        ttl = int(payload.get("ttl_seconds") or ttl_seconds)
        if now - updated <= ttl:
            live.append(payload)
    return live


def distinct_live_instances(
    directory: Path,
    *,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> list[str]:
    ids = sorted(
        {
            str(row.get("instance_id"))
            for row in recent_heartbeats(directory, ttl_seconds=ttl_seconds)
            if row.get("instance_id")
        }
    )
    return ids


def check_exclusive_or_refuse(
    *,
    strict: bool,
    directory: Path | None = None,
    iid: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> tuple[bool, str]:
    """
    Write our heartbeat, then if strict and >1 distinct live instance IDs → fail.

    Returns (ok, message). When not strict, logs a warning on multi-instance.
    """
    directory = directory if directory is not None else lease_dir()
    if directory is None:
        return True, "lease_dir_unset"
    iid = iid or instance_id()
    write_heartbeat(directory, iid=iid, ttl_seconds=ttl_seconds)
    others = [x for x in distinct_live_instances(directory, ttl_seconds=ttl_seconds) if x != iid]
    live = distinct_live_instances(directory, ttl_seconds=ttl_seconds)
    if len(live) <= 1:
        return True, "ok_single_instance"
    msg = (
        f"multiple live control-plane instance heartbeats under {directory}: {live}. "
        "WEB_CONCURRENCY misses horizontal replicas; this FS lease is best-effort only "
        "(shared volume required). Not Redis."
    )
    if strict:
        return False, msg
    logger.warning("CONTROL_PLANE_STRICT not set but %s", msg)
    return True, "ok_multi_warned"


def _safe_name(iid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in iid)[:120]
