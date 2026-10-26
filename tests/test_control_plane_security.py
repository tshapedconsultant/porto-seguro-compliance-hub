"""Pragmatic control-plane security hardenings (honest scope — not KMS/OIDC/Redis)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.control_plane.approvals import (
    ApprovalDesyncError,
    ApprovalError,
    ApprovalStore,
    resolve_approval_backend,
)
from src.control_plane.audit import AuditLog
from src.control_plane.default_policies import DEFAULT_POLICIES
from src.control_plane.lease import check_exclusive_or_refuse, write_heartbeat
from src.control_plane.runtime import ReferenceRuntime, RuntimeBlocked, RuntimeStopped


def _rt(tmp_path, **kwargs) -> ReferenceRuntime:
    return ReferenceRuntime(
        policies=DEFAULT_POLICIES,
        approvals=kwargs.pop("approvals", ApprovalStore()),
        audit=kwargs.pop("audit", AuditLog(tmp_path / "audit.jsonl")),
        **kwargs,
    )


def test_audit_hmac_signs_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_HMAC_KEY", "lab-secret-not-kms")
    log = AuditLog(tmp_path / "a.jsonl")
    row = log.append({"decision": "ALLOW", "rule_triggered": "t"})
    assert row.get("event_hmac")
    ok, reason = log.verify_chain()
    assert ok is True
    assert reason == "ok"
    cp = json.loads(log.checkpoint_path.read_text(encoding="utf-8"))
    assert cp["worm_claimed"] is False
    assert cp["kms_claimed"] is False
    assert "Dual-rewrite" in cp["integrity_note"] or "dual-rewrite" in cp["integrity_note"].lower() or "shared secret" in cp["integrity_note"].lower()


def test_audit_hmac_mismatch_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_HMAC_KEY", "lab-secret-not-kms")
    log = AuditLog(tmp_path / "a.jsonl")
    log.append({"decision": "ALLOW"})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["event_hmac"] = "0" * 64
    # Recompute chain hash so only HMAC fails (attacker without key).
    from src.control_plane.audit import GENESIS, _HASH_EXCLUDE, _canonical
    import hashlib

    body = {k: v for k, v in row.items() if k not in _HASH_EXCLUDE}
    row["previous_event_hash"] = GENESIS
    row["event_hash"] = hashlib.sha256((_canonical(body) + GENESIS).encode("utf-8")).hexdigest()
    log.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    ok, reason = log.verify_chain()
    assert ok is False
    assert "hmac_mismatch" in reason


def test_stop_file_mid_flight_marks_interrupted(tmp_path, monkeypatch):
    stop_path = tmp_path / "stop.flag"
    monkeypatch.setenv("STOP_FILE", str(stop_path))
    audit = AuditLog(tmp_path / "stop_audit.jsonl")
    rt = _rt(tmp_path, audit=audit)

    def fn():
        stop_path.write_text("halt\n", encoding="utf-8")
        return 42

    out = rt.execute_guarded("predict_ebm", fn, {"tool": "predict_ebm", "record_count": 1})
    assert out["status"] == "ok"
    assert out["result"] == 42
    assert out["interrupted_by_stop"] is True
    kinds = [r.get("action_taken") or r.get("rule_triggered") for r in audit.read_all()]
    assert "stop_during_execution" in kinds


def test_stop_file_blocks_before_external_effect(tmp_path, monkeypatch):
    stop_path = tmp_path / "stop.flag"
    stop_path.write_text("halt\n", encoding="utf-8")
    monkeypatch.setenv("STOP_FILE", str(stop_path))
    called = {"n": 0}

    def send():
        called["n"] += 1
        return "sent"

    rt = _rt(tmp_path)
    with pytest.raises(RuntimeStopped):
        rt.execute_guarded(
            "export_external",
            send,
            {"identifiable_personal_data": True, "tool": "export_external"},
        )
    assert called["n"] == 0


def test_instance_lease_strict_refuses_second_instance(tmp_path, monkeypatch):
    lease = tmp_path / "leases"
    monkeypatch.setenv("CONTROL_PLANE_LEASE_DIR", str(lease))
    write_heartbeat(lease, iid="instance-a")
    ok, msg = check_exclusive_or_refuse(strict=True, directory=lease, iid="instance-b")
    assert ok is False
    assert "multiple live" in msg


def test_instance_lease_single_ok(tmp_path):
    lease = tmp_path / "leases"
    ok, reason = check_exclusive_or_refuse(strict=True, directory=lease, iid="solo")
    assert ok is True
    assert reason == "ok_single_instance"


def test_approval_verify_against_audit_detects_desync(tmp_path):
    audit = AuditLog(tmp_path / "apr.jsonl")
    store = ApprovalStore(path=tmp_path / "approvals.json", audit=audit)
    ticket = store.request(action="score", requester="u", reason="r", payload={"k": 1})
    # Forge approved status in JSON without decide audit event.
    with store._lock:
        store._tickets[ticket["ticket_id"]]["status"] = "approved"
        store._tickets[ticket["ticket_id"]]["reviewer"] = "forged"
        store._persist()
    ok, reason = store.verify_against_audit(ticket["ticket_id"])
    assert ok is False
    assert "missing_audit_decide" in reason


def test_approval_audit_strict_denies_desync(tmp_path):
    audit = AuditLog(tmp_path / "apr2.jsonl")
    store = ApprovalStore(path=tmp_path / "approvals.json", audit=audit, audit_strict=True)
    ticket = store.request(action="score", requester="u", reason="r", payload={"k": 1})
    with store._lock:
        store._tickets[ticket["ticket_id"]]["status"] = "approved"
        store._tickets[ticket["ticket_id"]]["reviewer"] = "forged"
        store._persist()
    with pytest.raises(ApprovalDesyncError):
        store.is_approved(ticket["ticket_id"], action="score", payload={"k": 1})


def test_approval_separate_actors(tmp_path, monkeypatch):
    monkeypatch.setenv("APPROVAL_SEPARATE_ACTORS", "true")
    store = ApprovalStore(audit=AuditLog(tmp_path / "sod.jsonl"))
    ticket = store.request(action="score", requester="alice", reason="r", payload={})
    with pytest.raises(ApprovalError, match="SEPARATE_ACTORS"):
        store.decide(ticket["ticket_id"], reviewer="alice", approve=True, rationale="self")
    out = store.decide(ticket["ticket_id"], reviewer="bob", approve=True, rationale="ok")
    assert out["status"] == "approved"


def test_approval_backend_stub_rejects_redis():
    with pytest.raises(ApprovalError, match="not implemented"):
        resolve_approval_backend("redis")


def test_approval_decide_key_separation(monkeypatch):
    import api_server

    monkeypatch.setattr(api_server, "API_KEY", "general-key")
    monkeypatch.setattr(api_server, "APPROVAL_API_KEY", "approve-key")
    monkeypatch.setattr(api_server, "REQUIRE_AUTH", True)
    with pytest.raises(Exception) as exc:
        api_server._enforce_approval_decide_key("general-key")
    assert getattr(exc.value, "status_code", None) == 401
    api_server._enforce_approval_decide_key("approve-key")  # no raise


def test_synced_approval_passes_verify(tmp_path):
    audit = AuditLog(tmp_path / "ok.jsonl")
    store = ApprovalStore(audit=audit, audit_strict=True)
    ticket = store.request(action="score", requester="u", reason="r", payload={"k": 1})
    store.decide(ticket["ticket_id"], reviewer="rev", approve=True, rationale="ok")
    ok, reason = store.verify_against_audit(ticket["ticket_id"])
    assert ok is True
    assert reason == "ok"
    assert store.is_approved(ticket["ticket_id"], action="score", payload={"k": 1}) is True
