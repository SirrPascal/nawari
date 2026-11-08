"""Moderate-Risk Operational Playbook: Interface Flap Dampening (Workstream 12C).

Applies hold-down timers or rate limiting to errant flapping access switch ports
to protect STP network topology stability. Enforces rollback preconditions.
"""

from __future__ import annotations

import time
from typing import Any

from services.actions.action_framework import ActionRiskTier
from services.actions.playbooks.base import BasePlaybook


class InterfaceDampeningPlaybook(BasePlaybook):
    """Playbook to dampen flapping network interfaces."""

    NAME: str = "interface_dampening"
    VERSION: str = "1.0.0"
    RISK_TIER: ActionRiskTier = ActionRiskTier.MODERATE_RISK
    DESCRIPTION: str = "Applies temporary hold-down timer and rate limit to flapping switch interface."
    IS_RECOMMENDATION_ONLY_DEFAULT: bool = False

    @classmethod
    def check_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        # Precondition: Interface must be an access port (never core backbone)
        if context.get("is_core_backbone", False):
            return False, "PRECONDITION_FAILED: Cannot dampen core backbone trunk interface"
        flap_count = context.get("flap_count_5m", 0)
        if flap_count < 3:
            return False, f"PRECONDITION_FAILED: Flap count {flap_count} < 3 threshold"
        return True, "PRECONDITIONS_MET"

    @classmethod
    def capture_pre_state(cls, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "initial_admin_status": context.get("admin_status", "UP"),
            "initial_dampened": False,
            "timestamp": time.time(),
        }

    @classmethod
    def execute(cls, context: dict[str, Any]) -> dict[str, Any]:
        # Apply dampening
        res = {
            "interface": context.get("target_interface", "GigabitEthernet1/0/24"),
            "dampening_applied": True,
            "hold_down_seconds": 300,
            "rate_limit_kbps": 1000,
            "applied_at": time.time(),
        }
        context["dampening_result"] = res
        return res

    @classmethod
    def check_postconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        # Postcondition: flap rate has dropped to 0
        if context.get("post_flap_count", 0) > 0:
            return False, "POSTCONDITION_FAILED: Interface continues to flap despite dampening"
        return True, "INTERFACE_FLAPS_DAMPENED"

    @classmethod
    def check_rollback_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        # Rollback is ONLY safe if physical carrier/link has stabilized
        if not context.get("physical_link_stable", True):
            return False, "ROLLBACK_PRECONDITION_FAILED: Physical link remains unstable; lifting dampening would re-trigger flap storm"
        return True, "ROLLBACK_PRECONDITIONS_MET"

    @classmethod
    def rollback(cls, context: dict[str, Any]) -> dict[str, Any]:
        # Remove dampening hold-down
        return {
            "interface": context.get("target_interface", "GigabitEthernet1/0/24"),
            "dampening_removed": True,
            "rate_limit_cleared": True,
            "restored_at": time.time(),
        }

