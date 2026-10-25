"""Advisory control proposals from EIPD risks. Marked as proposals — never auto-verified."""

from __future__ import annotations

from typing import Any

from src.governance.dpia_workspace.models import new_id, utc_now

LIBRARY = {
    "human_oversight": {
        "name": "Human oversight / Art. 22 analogue",
        "enforcement": "REQUIRE_HUMAN_APPROVAL",
        "obligation_type": "risk_based_recommendation",
        "source": "GDPR Art. 22; EU AI Act Art. 14 (if high-risk deployer/provider duties apply)",
    },
    "minimisation": {
        "name": "Data minimisation",
        "enforcement": "LIMIT",
        "obligation_type": "legal_principle",
        "source": "GDPR Art. 5(1)(c)",
    },
    "logging": {
        "name": "Audit logging",
        "enforcement": "ALERT",
        "obligation_type": "legal_principle",
        "source": "GDPR Art. 5(2); EU AI Act Art. 12 if high-risk provider duties apply",
    },
    "tool_allowlist": {
        "name": "Tool allowlist",
        "enforcement": "DENY",
        "obligation_type": "internal_security_restriction",
        "source": "internal policy",
    },
}


def propose_controls(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for risk in risks:
        key = "human_oversight"
        text = (risk.get("threat_scenario") or "").lower()
        if "export" in text or "disclosure" in text:
            key = "minimisation"
        if "tool" in text or "agent" in text:
            key = "tool_allowlist"
        tmpl = LIBRARY[key]
        cid = new_id("CTL")
        executable = {
            "policy_id": f"POL-GEN-{cid}",
            "version": "1",
            "enabled": False,
            "priority": 80,
            "mandatory": False,
            "effect": tmpl["enforcement"],
            "enforcement_point": "pre_execution",
            "obligation_type": tmpl["obligation_type"],
            "rationale": f"Generated from {risk.get('risk_id')} — proposal only until enabled.",
            "conditions": {"all": [{"field": "risk_id", "op": "eq", "value": risk.get("risk_id")}]},
            "parameters": {"max_records": 1000} if tmpl["enforcement"] == "LIMIT" else (
                {"redact_fields": ["email", "name"]} if tmpl["enforcement"] == "REDACT" else {}
            ),
        }
        out.append(
            {
                "control_id": cid,
                "name": tmpl["name"],
                "description": f"Proposed from {risk.get('risk_id')}: {risk.get('threat_scenario')}",
                "addresses_risks": [risk.get("risk_id")],
                "obligation_type": tmpl["obligation_type"],
                "source": tmpl["source"],
                "enforcement_effect": tmpl["enforcement"],
                "executable_policy": executable,
                "status": "proposed",
                "verification_state": "unverified",
                "owner": "",
                "evidence_reference": "",
                "verification_date": None,
                "generated_at": utc_now(),
                "is_proposal": True,
                "not_universally_required_by_ai_act": True,
            }
        )
    return out
