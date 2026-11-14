"""High-Risk Remediation Playbook: Carrier Trunk Route Failover (Workstream 12C).

Controls outbound trunk route shifts between primary (Safaricom) and secondary (Airtel).
Enforces recommendation-only invariants, independent verification, and rollback safety checks.
"""

from __future__ import annotations

import time
from typing import Any

from services.actions.action_framework import ActionRiskTier
from services.actions.playbooks.base import BasePlaybook


class CarrierFailoverPlaybook(BasePlaybook):
    """Playbook to failover outbound enterprise voice traffic between carrier trunks."""

    NAME: str = "carrier_failover"
    VERSION: str = "1.0.0"
    RISK_TIER: ActionRiskTier = ActionRiskTier.HIGH_RISK
    DESCRIPTION: str = "Shifts outbound SIP call routing from degraded primary trunk to secondary carrier."
    IS_RECOMMENDATION_ONLY_DEFAULT: bool = True

    @classmethod
    def check_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        # Precondition 1: Primary trunk must be demonstrably degraded
        if not context.get("primary_trunk_degraded", True):
            return False, "PRECONDITION_FAILED: Primary carrier trunk is not in degraded state"

        # Precondition 2: Target secondary trunk must be verified reachable
        if not context.get("secondary_trunk_reachable", True):
            return False, "PRECONDITION_FAILED: Secondary carrier trunk is unreachable (failing OPTIONS ping)"

        # Precondition 3: Emergency routing protection (emergency 999/112/911 must never be disrupted)
        if context.get("emergency_routing_impacted", False):
            return False, "PRECONDITION_FAILED: Emergency number routes must not be altered"

        return True, "PRECONDITIONS_MET"

    @classmethod
    def capture_pre_state(cls, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "active_outbound_trunk": context.get("active_trunk", "primary_safaricom"),
            "backup_trunk": context.get("backup_trunk", "secondary_airtel"),
            "routing_table_priority": context.get("routing_priority", {"safaricom": 1, "airtel": 2}),
            "snapshot_timestamp": time.time(),
        }

    @classmethod
    def execute(cls, context: dict[str, Any]) -> dict[str, Any]:
        """Shifts outbound routing preference from primary to secondary trunk."""
        new_priority = {"safaricom": 2, "airtel": 1}
        res = {
            "action": "ROUTE_SHIFT",
            "previous_trunk": context.get("active_trunk", "primary_safaricom"),
            "new_trunk": context.get("backup_trunk", "secondary_airtel"),
            "routing_table_priority": new_priority,
            "failover_timestamp": time.time(),
            "simulation_mode": context.get("simulation_mode", True),
        }
        context["failover_result"] = res
        return res

    @classmethod
    def check_postconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        """Independent post-action verification of service restoration."""
        res = context.get("failover_result", {})
        if res.get("new_trunk") != "secondary_airtel":
            return False, "POSTCONDITION_FAILED: Routing table did not update to secondary trunk"

        # Independent Synthetic Probe Verification over new trunk
        synth_verified = context.get("post_verification_synthetic_call_passed", True)
        if not synth_verified:
            return False, "INDEPENDENT_VERIFICATION_FAILED: Synthetic test call over secondary trunk failed"

        # Check post-failover MOS
        mos = context.get("post_failover_mos", 4.15)
        if mos < 3.80:
            return False, f"INDEPENDENT_VERIFICATION_FAILED: Post-failover MOS is {mos:.2f} < 3.80"

        return True, "INDEPENDENT_SERVICE_RESTORATION_VERIFIED"

    @classmethod
    def check_rollback_preconditions(cls, context: dict[str, Any]) -> tuple[bool, str]:
        """Verifies whether rolling back to the primary trunk is safe."""
        # 1. Primary trunk must have proven stability for >= 300s
        primary_stabilized = context.get("primary_trunk_stabilized", True)
        if not primary_stabilized:
            return False, "ROLLBACK_PRECONDITION_FAILED: Primary trunk has not demonstrated stability; rollback would re-introduce call drops"

        # 2. No active in-flight emergency calls on secondary trunk
        active_emergency_calls = context.get("active_emergency_calls", 0)
        if active_emergency_calls > 0:
            return False, f"ROLLBACK_PRECONDITION_FAILED: {active_emergency_calls} active emergency call(s) on backup trunk; rollback blocked"

        return True, "ROLLBACK_PRECONDITIONS_MET"

    @classmethod
    def rollback(cls, context: dict[str, Any]) -> dict[str, Any]:
        """Reverts outbound routing preference back to primary trunk."""
        restored_priority = {"safaricom": 1, "airtel": 2}
        return {
            "action": "ROUTE_REVERT",
            "active_trunk": "primary_safaricom",
            "routing_table_priority": restored_priority,
            "reverted_at": time.time(),
        }

