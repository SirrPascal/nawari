"""Avaya Session Border Controller Enterprise (SBCE 8.1) Service Model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SBCEStatus:
    active_sessions: int = 0
    max_licensed_sessions: int = 500
    media_utilization_pct: float = 0.0
    cpu_utilization_pct: float = 0.0
    tls_handshake_errors: int = 0
    interface_dropped_packets: int = 0
    is_reachability_up: bool = True

    @property
    def license_utilization_pct(self) -> float:
        if self.max_licensed_sessions <= 0:
            return 0.0
        return round((self.active_sessions / self.max_licensed_sessions) * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["license_utilization_pct"] = self.license_utilization_pct
        return d


class AvayaSBCEModel:
    """Operational service model and diagnostic engine for Avaya SBCE 8.1 appliances."""

    def __init__(self, appliance_id: str = "sbce-edge-01", mgmt_ip: str = "10.2.156.60") -> None:
        self.appliance_id = appliance_id
        self.mgmt_ip = mgmt_ip
        self.current_status = SBCEStatus()

    def update_telemetry(
        self,
        active_sessions: int,
        max_licensed_sessions: int = 500,
        media_utilization_pct: float = 0.0,
        cpu_utilization_pct: float = 0.0,
        tls_handshake_errors: int = 0,
        dropped_packets: int = 0,
        is_up: bool = True,
    ) -> SBCEStatus:
        self.current_status = SBCEStatus(
            active_sessions=active_sessions,
            max_licensed_sessions=max_licensed_sessions,
            media_utilization_pct=media_utilization_pct,
            cpu_utilization_pct=cpu_utilization_pct,
            tls_handshake_errors=tls_handshake_errors,
            interface_dropped_packets=dropped_packets,
            is_reachability_up=is_up,
        )
        return self.current_status

    def evaluate_health(self) -> dict[str, Any]:
        """Evaluate SBCE health against operational thresholds."""
        st = self.current_status
        anomalies = []
        severity = "HEALTHY"

        if not st.is_reachability_up:
            return {
                "status": "CRITICAL",
                "summary": "Avaya SBCE management interface is completely unreachable via SNMP/ICMP",
                "anomalies": ["Management Reachability Down"],
            }

        # License exhaustion checks
        if st.license_utilization_pct >= 98.0:
            anomalies.append(
                f"License Exhaustion Critical: Active sessions ({st.active_sessions}) reached {st.license_utilization_pct}% of licensed capacity ({st.max_licensed_sessions})"
            )
            severity = "CRITICAL"
        elif st.license_utilization_pct >= 85.0:
            anomalies.append(
                f"License Utilization High: {st.active_sessions}/{st.max_licensed_sessions} ({st.license_utilization_pct}%)"
            )
            if severity != "CRITICAL":
                severity = "WARNING"

        # CPU Saturation
        if st.cpu_utilization_pct >= 90.0:
            anomalies.append(f"SBCE CPU Saturation Critical: {st.cpu_utilization_pct}%")
            severity = "CRITICAL"
        elif st.cpu_utilization_pct >= 80.0:
            anomalies.append(f"SBCE CPU Utilization Elevated: {st.cpu_utilization_pct}%")
            if severity != "CRITICAL":
                severity = "WARNING"

        # Media Interface Saturation
        if st.media_utilization_pct >= 85.0:
            anomalies.append(f"Media Bandwidth Congestion: {st.media_utilization_pct}% utilization")
            if severity != "CRITICAL":
                severity = "WARNING"

        # TLS Errors
        if st.tls_handshake_errors > 5:
            anomalies.append(f"SIP TLS Handshake Errors Elevated: {st.tls_handshake_errors} failures")
            if severity == "HEALTHY":
                severity = "WARNING"

        return {
            "status": severity,
            "license_utilization_pct": st.license_utilization_pct,
            "anomalies": anomalies,
            "summary": "Avaya SBCE operational nominal" if not anomalies else "; ".join(anomalies),
        }

