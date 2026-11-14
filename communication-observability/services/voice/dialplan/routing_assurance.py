"""Carrier Trunk Routing Policy & Destination Safety Assurance Engine."""

from __future__ import annotations

from typing import Any

from services.voice.dialplan.number_plan import (
    ExtensionCategory,
    KQNumberClassifier,
)


class RoutingAssuranceEngine:
    """Validates carrier trunk route selection, detects suboptimal routing fallback, and enforces safety gates."""

    TRUNK_PREFERENCE_ORDER = [
        "SAFARICOM_SIP",    # Priority 1: Primary Enterprise SIP Trunk
        "AIRTEL_SIP",       # Priority 2: Secondary Redundant SIP Trunk
        "TELKOM_ISDN",      # Priority 3: Legacy Fallback ISDN PRI
    ]

    @classmethod
    def validate_route_selection(
        cls,
        destination: str,
        selected_trunk: str,
        trunk_status_map: dict[str, str],  # trunk_name -> "UP" / "DOWN"
    ) -> dict[str, Any]:
        """Validate if the selected carrier trunk adheres to cost and reliability routing policies."""
        info = KQNumberClassifier.classify(destination)

        # Internal extensions should not route over external PSTN carrier trunks
        if info.category in (
            ExtensionCategory.PRIDE_CENTRE_HQ,
            ExtensionCategory.JKIA_TERMINAL_1A,
            ExtensionCategory.FLIGHT_OPERATIONS,
            ExtensionCategory.REGIONAL_OUTSTATIONS,
        ):
            if "SIP" in selected_trunk or "ISDN" in selected_trunk:
                # Internal calls should stay on Aura CM / SM tie-lines
                if selected_trunk not in ("INTERNAL_AURA", "TIE_LINE", "AVAYA_SM"):
                    return {
                        "is_valid": True,
                        "routing_verdict": "SUBOPTIMAL_PSTN_HAIRPINNING",
                        "severity": "WARNING",
                        "details": f"Internal extension {destination} routed over external PSTN trunk ({selected_trunk}) instead of internal Aura tie-line",
                    }

        primary_trunk = cls.TRUNK_PREFERENCE_ORDER[0]
        primary_status = trunk_status_map.get(primary_trunk, "UP")

        # Check if secondary was selected while primary was healthy
        if selected_trunk != primary_trunk and primary_status == "UP":
            return {
                "is_valid": True,
                "routing_verdict": "SUBOPTIMAL_CARRIER_ROUTE",
                "severity": "WARNING",
                "details": f"Call routed via secondary trunk ({selected_trunk}) while primary ({primary_trunk}) is operational. Possible routing table misconfiguration.",
            }

        # Check if failover is legitimate because primary is down
        if selected_trunk != primary_trunk and primary_status == "DOWN":
            return {
                "is_valid": True,
                "routing_verdict": "FAILOVER_CARRIER_ROUTE_ACTIVE",
                "severity": "INFO",
                "details": f"Legitimate carrier failover: Primary ({primary_trunk}) is DOWN; call successfully protected via {selected_trunk}.",
            }

        return {
            "is_valid": True,
            "routing_verdict": "OPTIMAL_ROUTE",
            "severity": "HEALTHY",
            "details": f"Call routed via optimal primary carrier trunk ({selected_trunk}).",
        }

    @classmethod
    def enforce_safety_gate(cls, destination: str) -> None:
        """Enforce strict pre-origination safety gate for synthetic voice test probes.

        Raises:
            ValueError: If destination is an emergency number or unallowlisted external target.
        """
        info = KQNumberClassifier.classify(destination)
        if info.is_emergency:
            raise ValueError(
                f"SAFETY VIOLATION: Dialing emergency services ({destination}) is strictly blocked by cryptography and code policy."
            )

        if not info.is_allowlisted_test:
            raise ValueError(
                f"SAFETY VIOLATION: Destination {destination} ({info.category.value}) is not in the approved diagnostic allowlist."
            )

