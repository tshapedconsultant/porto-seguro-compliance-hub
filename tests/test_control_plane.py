"""Edge cases for policy evaluator and reference runtime."""

from __future__ import annotations

import time

import pytest

from src.control_plane.approvals import ApprovalError, ApprovalStore
from src.control_plane.audit import AuditLog
from src.control_plane.control_generator import propose_controls
from src.control_plane.default_policies import DEFAULT_POLICIES
from src.control_plane.evaluator import evaluate_policies
from src.control_plane.regulatory_library import classify_system
from src.control_plane.runtime import ReferenceRuntime, RuntimeBlocked, RuntimeStopped


def _rt(tmp_path) -> ReferenceRuntime:
    return ReferenceRuntime(
        policies=DEFAULT_POLICIES,
        approvals=ApprovalStore(),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )


def test_deny_runs_before_function(tmp_path):
    called = {"n": 0}

    def fn():
        called["n"] += 1
        return "ran"

    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded("predict", fn, {"tool": "shell", "tool_allowed": False})
    assert called["n"] == 0
    assert exc.value.decision["effect"] == "DENY"


def test_stop_switch(tmp_path):
    rt = _rt(tmp_path)
    rt.request_stop("lab halt", "andre")
    with pytest.raises(RuntimeStopped):
        rt.execute_guarded("predict", lambda: 1, {})


def test_limit_caps_records(tmp_path):
    rt = _rt(tmp_path)
    out = rt.execute_guarded("batch", lambda: "ok", {"record_count": 5000})
    assert out["context"]["record_count"] == 1000
    assert out["decision"]["effect"] == "LIMIT"


def test_budget_deny(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded("predict", lambda: 1, {"estimated_cost_eur": 9.0})
    assert exc.value.decision["policy_id"] == "POL-BUDGET"


def test_approval_gate(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked):
        rt.execute_guarded("score", lambda: 1, {"legal_effect_decision": True})

    ticket = rt.approvals.request(action="score", requester="u", reason="underwriting analogue")
    rt.approvals.decide(ticket["ticket_id"], reviewer="reviewer", approve=True, rationale="hitl")
    out = rt.execute_guarded(
        "score",
        lambda: 1,
        {"legal_effect_decision": True, "approval_ticket_id": ticket["ticket_id"]},
    )
    assert out["status"] == "ok"


def test_rejected_ticket_blocks(tmp_path):
    rt = _rt(tmp_path)
    ticket = rt.approvals.request(action="score", requester="u", reason="x")
    rt.approvals.decide(ticket["ticket_id"], reviewer="r", approve=False, rationale="no")
    with pytest.raises(RuntimeBlocked):
        rt.execute_guarded(
            "score",
            lambda: 1,
            {"legal_effect_decision": True, "approval_ticket_id": ticket["ticket_id"]},
        )


def test_expired_ticket(tmp_path):
    rt = _rt(tmp_path)
    ticket = rt.approvals.request(action="score", requester="u", reason="x", ttl_seconds=0)
    time.sleep(0.01)
    with pytest.raises(ApprovalError):
        rt.approvals.decide(ticket["ticket_id"], reviewer="r", approve=True, rationale="late")


def test_empty_reviewer_rejected():
    store = ApprovalStore()
    ticket = store.request(action="x", requester="u", reason="r")
    with pytest.raises(ApprovalError):
        store.decide(ticket["ticket_id"], reviewer="", approve=True, rationale="x")


def test_fail_closed_unknown_operator():
    policies = [
        {
            "policy_id": "bad",
            "version": "1",
            "enabled": True,
            "priority": 1,
            "effect": "ALLOW",
            "conditions": {"all": [{"field": "a", "op": "nope", "value": 1}]},
        }
    ]
    decision = evaluate_policies({"a": 1}, policies)
    assert decision["effect"] == "DENY"
    assert decision["policy_id"] == "fail-closed"


def test_mandatory_deny_not_overridden_by_allow():
    policies = [
        {
            "policy_id": "deny",
            "version": "1",
            "enabled": True,
            "priority": 50,
            "mandatory": True,
            "effect": "DENY",
            "conditions": {"all": [{"field": "x", "op": "eq", "value": 1}]},
        },
        {
            "policy_id": "allow",
            "version": "1",
            "enabled": True,
            "priority": 1,
            "mandatory": False,
            "effect": "ALLOW",
            "conditions": {"all": [{"field": "x", "op": "eq", "value": 1}]},
        },
    ]
    decision = evaluate_policies({"x": 1}, policies)
    assert decision["effect"] == "DENY"
    assert decision["policy_id"] == "deny"


def test_dry_run_does_not_execute(tmp_path):
    called = {"n": 0}
    rt = _rt(tmp_path)
    out = rt.execute_guarded("predict", lambda: called.__setitem__("n", 1), {"dry_run": True})
    assert out["status"] == "dry_run"
    assert called["n"] == 0


def test_circuit_breaker(tmp_path):
    rt = _rt(tmp_path)

    def boom():
        raise RuntimeError("fail")

    for _ in range(8):
        with pytest.raises(RuntimeError):
            rt.execute_guarded("predict", boom, {})
    with pytest.raises(RuntimeStopped):
        rt.execute_guarded("predict", lambda: 1, {})


def test_control_proposals_are_unverified():
    risks = [{"risk_id": "RSK-1", "threat_scenario": "agent tool abuse"}]
    controls = propose_controls(risks)
    assert controls[0]["is_proposal"] is True
    assert controls[0]["verification_state"] == "unverified"
    assert controls[0]["status"] == "proposed"


def test_classification_not_legal():
    result = classify_system({"role": "unknown"})
    assert result["is_legal_classification"] is False


def test_export_personal_data_denied(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded(
            "export_external",
            lambda: "sent",
            {"action": "export_external", "identifiable_personal_data": True},
        )
    assert exc.value.decision["effect"] == "DENY"


def test_default_allow_when_no_match(tmp_path):
    rt = _rt(tmp_path)
    out = rt.execute_guarded("predict_ebm", lambda: 42, {"tool": "predict_ebm", "record_count": 1})
    assert out["status"] == "ok"
    assert out["result"] == 42


def test_art5_screening_deny(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded("run", lambda: 1, {"art5_concern": True})
    assert exc.value.decision["policy_id"] == "POL-ART5-SCREEN"
