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
    seen = {}

    def fn(ctx):
        seen["n"] = len(ctx["records"])
        return ctx["records"]

    rt = _rt(tmp_path)
    records = [{"id": i} for i in range(5000)]
    out = rt.execute_guarded(
        "batch",
        fn,
        {"record_count": 5000, "records": records, "tool": "predict_ebm"},
    )
    assert out["decision"]["effect"] == "LIMIT"
    assert seen["n"] == 1000
    assert len(out["result"]) == 1000
    assert out["context"]["records_truncated"] is True


def test_budget_deny(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded("predict", lambda: 1, {"estimated_cost_eur": 9.0})
    assert exc.value.decision["policy_id"] == "POL-BUDGET"


def test_approval_gate(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked):
        rt.execute_guarded("score", lambda: 1, {"legal_effect_decision": True})

    payload = {"case": "underwriting"}
    ticket = rt.approvals.request(
        action="score", requester="u", reason="underwriting analogue", payload=payload
    )
    rt.approvals.decide(ticket["ticket_id"], reviewer="reviewer", approve=True, rationale="hitl")
    out = rt.execute_guarded(
        "score",
        lambda: 1,
        {
            "legal_effect_decision": True,
            "approval_ticket_id": ticket["ticket_id"],
            "approval_payload": payload,
        },
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
    rt.reset_circuit("andre", "lab recovery")
    out = rt.execute_guarded("predict_ebm", lambda: 1, {"tool": "predict_ebm", "record_count": 1})
    assert out["status"] == "ok"


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


def test_ticket_wrong_action_is_confused_deputy(tmp_path):
    rt = _rt(tmp_path)
    ticket = rt.approvals.request(action="score", requester="u", reason="x", payload={"a": 1})
    rt.approvals.decide(ticket["ticket_id"], reviewer="r", approve=True, rationale="ok")
    with pytest.raises(RuntimeBlocked):
        rt.execute_guarded(
            "export_external",
            lambda: 1,
            {
                "legal_effect_decision": True,
                "approval_ticket_id": ticket["ticket_id"],
                "approval_payload": {"a": 1},
            },
        )


def test_all_and_any_both_required():
    policies = [
        {
            "policy_id": "mix",
            "version": "1",
            "enabled": True,
            "priority": 1,
            "mandatory": True,
            "effect": "DENY",
            "conditions": {
                "all": [{"field": "flag", "op": "eq", "value": True}],
                "any": [
                    {"field": "tool", "op": "eq", "value": "shell"},
                    {"field": "tool", "op": "eq", "value": "curl"},
                ],
            },
        }
    ]
    assert evaluate_policies({"flag": True, "tool": "predict_ebm"}, policies)["effect"] == "ALLOW"
    assert evaluate_policies({"flag": True, "tool": "shell"}, policies)["effect"] == "DENY"


def test_redact_removes_fields(tmp_path):
    rt = _rt(tmp_path)
    out = rt.execute_guarded(
        "predict_ebm",
        lambda: {"email": "a@b.c", "score": 0.1, "name": "Ada"},
        {"tool": "predict_ebm", "record_count": 1, "redact_output": True},
    )
    assert out["result"]["email"] == "[REDACTED]"
    assert out["result"]["name"] == "[REDACTED]"
    assert out["result"]["score"] == 0.1
    assert "email" in out["context"]["redacted_fields"]


def test_redact_without_fields_denies():
    from src.control_plane.redaction import apply_redaction

    with pytest.raises(ValueError):
        apply_redaction({"email": "x"}, [])


def test_audit_chain_detects_tamper(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.append({"decision": "ALLOW"})
    log.append({"decision": "DENY"})
    ok, _ = log.verify_chain()
    assert ok is True
    lines = (tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "a.jsonl").write_text(lines[0] + "\n" + lines[0] + "\n", encoding="utf-8")
    log2 = AuditLog(tmp_path / "a.jsonl")
    ok2, reason = log2.verify_chain()
    assert ok2 is False
    assert "chain_break" in reason


def test_action_field_cannot_spoof_export(tmp_path):
    called = {"n": 0}

    def send_data(ctx):
        called["n"] += 1
        return "sent"

    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked):
        rt.execute_guarded(
            "export_external",
            send_data,
            {"action": "predict", "identifiable_personal_data": True},
        )
    assert called["n"] == 0


def test_sensitive_unmatched_defaults_to_deny(tmp_path):
    rt = _rt(tmp_path)
    with pytest.raises(RuntimeBlocked) as exc:
        rt.execute_guarded("delete", lambda: 1, {})
    assert exc.value.decision["effect"] == "DENY"


def test_calendar_annex_iii_not_2026_08_02():
    from src.control_plane.regulatory_library import APPLICATION_CALENDAR

    by_id = {m["id"]: m["date"] for m in APPLICATION_CALENDAR["milestones"]}
    assert by_id["high_risk_annex_iii"] == "2027-12-02"
    assert by_id["general_application"] == "2026-08-02"
    assert by_id["high_risk_annex_i"] == "2028-08-02"


def test_motor_not_automatically_high_risk():
    from src.control_plane.regulatory_library import classify_system

    result = classify_system(
        {
            "role": "deployer",
            "intended_purpose": "motor claims",
            "insurance_product": "motor",
            "annex_iii_point": "unknown",
        }
    )
    assert result["potential_high_risk"] is False
    assert result["is_legal_classification"] is False


def test_generated_policy_can_be_validated_and_stored(tmp_path):
    from src.control_plane.control_generator import propose_controls
    from src.control_plane.evaluator import validate_policy
    from src.control_plane.store import ControlPlaneStore

    controls = propose_controls([{"risk_id": "RSK-9", "threat_scenario": "agent tool abuse"}])
    policy = controls[0]["executable_policy"]
    validate_policy(policy)
    store = ControlPlaneStore(tmp_path)
    stored = store.append_executable_proposal(controls[0], enable=True)
    loaded = store.load_policies()
    assert stored["policy_id"] in {p["policy_id"] for p in loaded}
