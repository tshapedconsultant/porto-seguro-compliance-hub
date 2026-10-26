from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.control_plane.default_policies import DEFAULT_POLICIES
from src.control_plane.evaluator import validate_policy


class ControlPlaneStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or "docs/governance")
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy_path = self.root / "policies.json"
        if not self.policy_path.exists():
            self.policy_path.write_text(
                json.dumps({"version": 1, "policies": DEFAULT_POLICIES}, indent=2),
                encoding="utf-8",
            )

    def load_policies(self) -> list[dict[str, Any]]:
        if not self.policy_path.exists():
            raise FileNotFoundError(str(self.policy_path))
        payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        policies = payload.get("policies")
        if not isinstance(policies, list) or not policies:
            raise ValueError("policies.json has no policies")
        for policy in policies:
            validate_policy(policy)
        return policies

    def save_policies(self, policies: list[dict[str, Any]]) -> None:
        for policy in policies:
            validate_policy(policy)
        payload = json.dumps({"version": 1, "policies": policies}, indent=2, ensure_ascii=False)
        self.policy_path.write_text(payload, encoding="utf-8")

    def append_executable_proposal(self, control: dict[str, Any], *, enable: bool = False) -> dict[str, Any]:
        policy = dict(control.get("executable_policy") or {})
        if not policy:
            raise ValueError("control has no executable_policy")
        policy["enabled"] = bool(enable)
        validate_policy(policy)
        policies = self.load_policies()
        policies.append(policy)
        self.save_policies(policies)
        return policy
