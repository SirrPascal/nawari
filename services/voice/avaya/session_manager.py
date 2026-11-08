"""Avaya Session Manager (SM 8.1.3) Operational Model & Station State Disambiguator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class SIPEntityLink:
    name: str
    peer_ip: str
    protocol: str = "TLS"
    status: str = "UP"
    latency_ms: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AvayaSessionManagerModel:
    """Operational service model for Avaya Session Manager and Aura SIP routing."""

    def __init__(self, sm_id: str = "sm-core-01", mgmt_ip: str = "10.2.156.55") -> None:
        self.sm_id = sm_id
        self.mgmt_ip = mgmt_ip
        self.entity_links: dict[str, SIPEntityLink] = {}

    def add_or_update_link(
        self,
        name: str,
        peer_ip: str,
        protocol: str = "TLS",
        status: str = "UP",
        latency_ms: float = 2.0,
    ) -> SIPEntityLink:
        link = SIPEntityLink(
            name=name,
            peer_ip=peer_ip,
            protocol=protocol,
            status=status.upper(),
            latency_ms=latency_ms,
        )
        self.entity_links[name] = link
        return link

    def evaluate_entity_health(self) -> dict[str, Any]:
        """Evaluate status of SIP entity links between Session Manager, SBCE, CM, and Carrier."""
        down_links = [l for l in self.entity_links.values() if l.status != "UP"]
        high_latency = [l for l in self.entity_links.values() if l.status == "UP" and l.latency_ms > 50.0]

        severity = "HEALTHY"
        anomalies = []

        if down_links:
            severity = "CRITICAL"
            for dl in down_links:
                anomalies.append(f"SIP Entity Link Down: {dl.name} ({dl.peer_ip}) via {dl.protocol}")

        if high_latency:
            if severity != "CRITICAL":
                severity = "WARNING"
            for hl in high_latency:
                anomalies.append(f"SIP Entity Link Latency High: {hl.name} ({hl.latency_ms}ms)")

        return {
            "status": severity,
            "total_links": len(self.entity_links),
            "down_links_count": len(down_links),
            "anomalies": anomalies,
            "summary": "All Session Manager entity links nominal" if not anomalies else "; ".join(anomalies),
        }

    @classmethod
    def distinguish_station_from_trunk_outage(
        cls,
        sip_code: int,
        warning_header: Optional[str] = None,
        reason_header: Optional[str] = None,
    ) -> dict[str, Any]:
        """Decisively differentiate Station-State events from genuine Trunk/Core Infrastructure Outages.

        Prevents false alarms when softphones are logged out or stations are busy.
        """
        # 1. Station State Checks (CAT-5)
        if sip_code == 480:
            user_unreg = bool(warning_header and "User not registered" in warning_header)
            return {
                "category": "STATION_STATE",
                "is_trunk_failure": False,
                "is_station_offline": True,
                "reason": "Destination deskphone/softphone offline or user not logged in",
                "requires_noc_escalation": False,
                "recommended_action": "Check endpoint physical power or softphone registration schedule",
            }
        elif sip_code == 486:
            return {
                "category": "STATION_STATE",
                "is_trunk_failure": False,
                "is_station_offline": False,
                "reason": "Destination station busy on active call",
                "requires_noc_escalation": False,
                "recommended_action": "No operational action; station functioning normally",
            }
        elif sip_code == 487:
            return {
                "category": "PROBE_TEARDOWN",
                "is_trunk_failure": False,
                "is_station_offline": False,
                "reason": "Planned synthetic test probe teardown via CANCEL",
                "requires_noc_escalation": False,
                "recommended_action": "Expected test completion; discard from error totals",
            }

        # 2. True Infrastructure Outage Checks (CAT-7)
        if sip_code in (500, 502, 503, 504):
            return {
                "category": "INFRASTRUCTURE_FAILURE",
                "is_trunk_failure": True,
                "is_station_offline": False,
                "reason": f"Avaya core routing or trunk failure (SIP {sip_code})",
                "requires_noc_escalation": True,
                "recommended_action": "Inspect Session Manager entity links and SBCE carrier trunk groups immediately",
            }

        # 3. Dial Plan or Policy Defect (CAT-6)
        if sip_code in (403, 404, 484):
            return {
                "category": "DIALPLAN_DEFECT",
                "is_trunk_failure": False,
                "is_station_offline": False,
                "reason": f"Dialplan configuration or permission failure (SIP {sip_code})",
                "requires_noc_escalation": True,
                "recommended_action": "Verify Communication Manager dialplan and COR/COS toll privileges",
            }

        return {
            "category": "UNKNOWN",
            "is_trunk_failure": False,
            "is_station_offline": False,
            "reason": f"SIP response {sip_code}",
            "requires_noc_escalation": False,
            "recommended_action": "Investigate transaction logs",
        }

