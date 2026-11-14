"""
services/endpoint/experience/models.py

Data models for Nawari End-User Network Experience Monitoring (EU-NEM).
Supports dual-platform (Windows 10/11 and macOS Darwin) telemetry,
lifecycle event tracking, corporate presence evaluation, and infrastructure correlation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EndpointLifecycleState(str, Enum):
    """Authoritative state machine classification for employee laptops."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    EXPECTED_SHUTDOWN = "EXPECTED_SHUTDOWN"
    SLEEPING = "SLEEPING"
    OUTSIDE_CORPORATE_NETWORK = "OUTSIDE_CORPORATE_NETWORK"
    AGENT_FAILURE = "AGENT_FAILURE"
    UNREACHABLE_UNCLASSIFIED = "UNREACHABLE_UNCLASSIFIED"
    RECOVERY_PENDING = "RECOVERY_PENDING"


class CorporatePresenceState(str, Enum):
    """Presence state within Kenya Airways corporate enterprise network."""
    CORPORATE_CONFIRMED = "CORPORATE_CONFIRMED"
    CORPORATE_DEGRADED = "CORPORATE_DEGRADED"
    OFF_NET_REMOTE = "OFF_NET_REMOTE"


class DiagnosticHypothesis(str, Enum):
    """Diagnostic root-cause hypothesis derived from multi-signal correlation."""
    LOCAL_ENDPOINT_ISSUE = "LOCAL_ENDPOINT_ISSUE"
    ACCESS_POINT_RF_ISSUE = "ACCESS_POINT_RF_ISSUE"
    VLAN_SWITCH_ISSUE = "VLAN_SWITCH_ISSUE"
    DNS_INFRASTRUCTURE_ISSUE = "DNS_INFRASTRUCTURE_ISSUE"
    SERVICE_APPLICATION_ISSUE = "SERVICE_APPLICATION_ISSUE"
    VPN_GATEWAY_ISSUE = "VPN_GATEWAY_ISSUE"
    WAN_UPSTREAM_ISSUE = "WAN_UPSTREAM_ISSUE"
    FLEET_HEALTHY = "FLEET_HEALTHY"


@dataclass
class EndpointLifecycleEvent:
    """Operating system lifecycle event (Windows EventLog / macOS power logs)."""
    event_id: int
    source: str
    description: str
    timestamp: float = field(default_factory=time.time)
    is_planned_shutdown: bool = False
    is_unexpected_shutdown: bool = False
    is_sleep: bool = False
    is_wake: bool = False


@dataclass
class NetworkDiagnostics:
    """Network-level diagnostics measured directly on the endpoint."""
    adapter_name: str
    adapter_type: str  # "WIFI", "ETHERNET", "VPN"
    gateway_ip: str
    gateway_reachable: bool
    gateway_rtt_ms: float
    gateway_loss_pct: float
    dns_server_ip: str
    dns_domain: str
    dns_success: bool
    dns_latency_ms: float
    internal_services_ok: bool
    services_tested: Dict[str, bool] = field(default_factory=dict)
    wifi_ssid: Optional[str] = None
    wifi_bssid: Optional[str] = None
    wifi_signal_pct: Optional[float] = None
    vpn_active: bool = False
    vpn_gateway: Optional[str] = None


@dataclass
class EndpointTelemetrySnapshot:
    """Complete diagnostic snapshot collected from a single endpoint."""
    endpoint_id: str
    hostname: str
    os_type: str  # "windows", "darwin", "linux"
    os_version: str
    timestamp: float = field(default_factory=time.time)
    agent_version: str = "7.4.0"
    cpu_pct: float = 0.0
    memory_pct: float = 0.0
    network: NetworkDiagnostics = field(default_factory=lambda: NetworkDiagnostics(
        adapter_name="unknown",
        adapter_type="WIFI",
        gateway_ip="0.0.0.0",
        gateway_reachable=False,
        gateway_rtt_ms=0.0,
        gateway_loss_pct=100.0,
        dns_server_ip="0.0.0.0",
        dns_domain="unknown",
        dns_success=False,
        dns_latency_ms=0.0,
        internal_services_ok=False,
    ))
    lifecycle_events: List[EndpointLifecycleEvent] = field(default_factory=list)


@dataclass
class EndpointEvaluationResult:
    """Evaluated health, presence, and lifecycle status for an endpoint."""
    endpoint_id: str
    presence_state: CorporatePresenceState
    presence_confidence: float
    lifecycle_state: EndpointLifecycleState
    primary_symptom: Optional[str] = None
    confidence_score: float = 1.0
    recommended_action: str = "None"
    evaluated_at: float = field(default_factory=time.time)


@dataclass
class FleetCorrelationResult:
    """Fleet-wide aggregation, anomaly clustering, and diagnostic hypotheses."""
    evaluated_at: float = field(default_factory=time.time)
    total_endpoints: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    network_failure_count: int = 0
    expected_shutdown_count: int = 0
    sleeping_count: int = 0
    off_net_count: int = 0
    unclassified_count: int = 0
    agent_failure_count: int = 0
    evaluations: List[EndpointEvaluationResult] = field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)

