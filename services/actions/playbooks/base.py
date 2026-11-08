"""Base Playbook Architecture for Nawari Controlled Remediation (Workstream 12C).

Enforces strict lifecycle definitions: preconditions, pre-state capture, execution,
postconditions, rollback preconditions, rollback execution, and escalation behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.actions.action_framework import ActionRiskTier


class BasePlaybook(ABC):
    """Abstract Base Class for all operational remediation playbooks."""

    NAME: str = "base_playbook"
    VERSION: str = "1.0.0"
    RISK_TIER: ActionRiskTier = ActionRiskTier.LOW_RISK
    DESCRIPTION: str = "Base operational playbook contract"
    IS_RECOMMENDATION_ONLY_DEFAULT: bool = False

    @classmethod
    @abstractmethod
    def check_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        """Asserts required system preconditions before any mutation can begin."""
        pass

    @classmethod
    @abstractmethod
    def capture_pre_state(cls, context: dict[str, Any]) -> dict[str, Any]:
        """Snapshots target state prior to execution for deterministic rollback."""
        pass

    @classmethod
    @abstractmethod
    def execute(cls, context: dict[str, Any]) -> dict[str, Any]:
        """Executes forward operational changes against target."""
        pass

    @classmethod
    @abstractmethod
    def check_postconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        """Independent verification of service restoration after execution."""
        pass

    @classmethod
    @abstractmethod
    def check_rollback_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        """Verifies whether rolling back is safe; halts if rollback would cause harm."""
        pass

    @classmethod
    @abstractmethod
    def rollback(cls, context: dict[str, Any]) -> dict[str, Any]:
        """Reverts changes executed during forward execution."""
        pass

    @classmethod
    def escalate(cls, context: dict[str, Any], reason: str) -> dict[str, Any]:
        """Default escalation behavior when execution or rollback cannot proceed safely."""
        return {
            "escalation_status": "ESCALATED_TO_TIER3",
            "reason": reason,
            "playbook": cls.NAME,
            "context_snapshot": dict(context),
        }

