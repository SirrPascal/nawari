"""Data models for Nawari Voice Service Assurance & Cross-Domain Incident Correlation.

Structures the formal representation of service health, multi-domain dependency graphs,
observed evidence, and ranked root-cause hypotheses.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ServiceHealthState(str, Enum):
    """Holistic health assessment of an enterprise voice service."""

    HEALTHY = "HEALTHY"     # All signaling, media, and infrastructure within SLA
    DEGRADED = "DEGRADED"   # Elevated latency, packet loss, or warning alerts; service still usable
    CRITICAL = "CRITICAL"   # Call failure, one-way audio, or core infrastructure down
    UNKNOWN = "UNKNOWN"     # Insufficient or stale telemetry


class HypothesisStatus(str, Enum):
    """Calibrated confidence status of a diagnostic incident hypothesis."""

    CONFIRMED = "CONFIRMED"         # Direct causal evidence establishes the cause (e.g. socket/protocol error)
    PROBABLE = "PROBABLE"           # Multiple independent indicators support the hypothesis (e.g. link down + timeout)
    SUSPECTED = "SUSPECTED"         # Indicator suggests possible cause, but evidence is circumstantial or single-source
    SYMPTOM = "SYMPTOM"             # Downstream effect caused by an identified root cause
    HEALTHY = "HEALTHY"             # Clean execution; no anomaly identified
    INCONCLUSIVE = "INCONCLUSIVE"   # Conflicting or insufficient data to isolate root cause


class TelemetricEnvironment(str, Enum):
    """Provenance of telemetry: distinguishes simulated/mock environments from physical appliances."""

    MOCK_SIMULATED = "MOCK_SIMULATED"           # Local mock SNMP / containerized Asterisk
    PHYSICAL_PRODUCTION = "PHYSICAL_PRODUCTION" # Real Avaya SBCE / Session Manager hardware


class RootCauseDomain(str, Enum):
    """Categorization of the isolated root cause."""

    NETWORK_LINK = "NETWORK_LINK"                       # Physical or logical interface down/flapping/errors
    APPLIANCE_OVERLOAD = "APPLIANCE_OVERLOAD"           # CPU saturation, memory exhaustion, resource starvation
    FIREWALL_NAT_ASYMMETRY = "FIREWALL_NAT_ASYMMETRY"   # One-way audio, RTP port block, asymmetric routing
    UPSTREAM_CARRIER = "UPSTREAM_CARRIER"               # Carrier / ITSP refusal (SIP 503/408) with healthy local infra
    CLIENT_ENDPOINT = "CLIENT_ENDPOINT"                 # End-user busy (486), client misconfiguration, device drop
    LOCAL_ENDPOINT = "LOCAL_ENDPOINT"                   # Local Wi-Fi PHY or first-hop edge degradation isolated to single endpoint
    DNS_INFRASTRUCTURE = "DNS_INFRASTRUCTURE"           # DNS resolution failure / NXDOMAIN / SERVFAIL across endpoints
    NETWORK_TRANSIT_PATH = "NETWORK_TRANSIT_PATH"       # Hop-by-hop WAN loss or latency jump along transit path
    VOICE_SIGNALING = "VOICE_SIGNALING"                 # SIP protocol/registration failure while transport socket is healthy
    VOICE_MEDIA = "VOICE_MEDIA"                         # Audio stream loss, high jitter, or one-way audio
    APPLICATION_SERVICE = "APPLICATION_SERVICE"         # HTTP/HTTPS 5xx errors or high TTFB while transport is healthy
    HEALTHY = "HEALTHY"                                 # Service operating normally
    UNKNOWN = "UNKNOWN"                                 # Unclassified anomaly


class EvidenceDomain(str, Enum):
    """Originating domain of observed diagnostic evidence."""

    NETWORK = "NETWORK"         # Switch / router / interface telemetry
    APPLIANCE = "APPLIANCE"     # SBCE / server hardware and OS telemetry
    SIGNALING = "SIGNALING"     # SIP protocol transactions, response codes, call setup
    MEDIA = "MEDIA"             # RTP / RTCP streams, jitter, packet loss, MOS, directionality
    ENDPOINT = "ENDPOINT"       # Edge workstation, Wi-Fi RSSI/quality, gateway reachability
    DNS = "DNS"                 # DNS query timings, RCODEs
    SERVICE = "SERVICE"         # L4/L7 probing (TCP connect, TLS handshake, HTTP status/TTFB)
    PATH = "PATH"               # Paris traceroute, hop RTT, loss, route changes


@dataclass
class EvidenceItem:
    """A distinct factual observation contributing to a root-cause hypothesis."""

    domain: EvidenceDomain
    source: str                 # e.g., "zabbix.problem", "zabbix.item", "voice.synthetic"
    identifier: str             # e.g., "Interface B1 link down", "SIP Status 503", "One-Way Audio"
    severity: str               # "INFO", "WARNING", "HIGH", "DISASTER"
    description: str
    value: Optional[Any] = None
    timestamp: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "source": self.source,
            "identifier": self.identifier,
            "severity": self.severity,
            "description": self.description,
            "value": self.value,
            "timestamp": self.timestamp,
        }


@dataclass
class IncidentHypothesis:
    """Structured diagnostic conclusion explaining a voice degradation or outage."""

    id: str = field(default_factory=lambda: f"hyp-{uuid.uuid4().hex[:8]}")
    status: HypothesisStatus = HypothesisStatus.INCONCLUSIVE
    root_cause_domain: RootCauseDomain = RootCauseDomain.UNKNOWN
    title: str = ""
    summary: str = ""
    confidence: float = 0.0     # 0.0 to 1.0 scale
    evidence: list[EvidenceItem] = field(default_factory=list)
    remediation_recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "root_cause_domain": self.root_cause_domain.value,
            "title": self.title,
            "summary": self.summary,
            "confidence": round(self.confidence, 2),
            "evidence": [e.to_dict() for e in self.evidence],
            "remediation_recommendations": self.remediation_recommendations,
        }


@dataclass
class ServiceAssuranceReport:
    """Consolidated Voice Service Assurance & Incident Correlation Report."""

    report_id: str = field(default_factory=lambda: f"sar-{uuid.uuid4().hex[:8]}")
    timestamp: float = 0.0
    service_id: str = "voice-service-default"
    target_host: str = "nawari-voice-probe-01"
    environment: TelemetricEnvironment = TelemetricEnvironment.MOCK_SIMULATED
    is_stale: bool = False
    health_state: ServiceHealthState = ServiceHealthState.UNKNOWN
    health_score: float = 0.0   # 0.0 - 100.0 index
    signaling_summary: dict[str, Any] = field(default_factory=dict)
    media_summary: dict[str, Any] = field(default_factory=dict)
    infrastructure_summary: dict[str, Any] = field(default_factory=dict)
    endpoint_summary: dict[str, Any] = field(default_factory=dict)
    path_summary: dict[str, Any] = field(default_factory=dict)
    hypotheses: list[IncidentHypothesis] = field(default_factory=list)
    active_problems: list[dict[str, Any]] = field(default_factory=list)

    @property
    def primary_hypothesis(self) -> Optional[IncidentHypothesis]:
        """Return the hypothesis with the highest confidence."""
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda h: h.confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "service_id": self.service_id,
            "target_host": self.target_host,
            "environment": self.environment.value,
            "is_stale": self.is_stale,
            "health_state": self.health_state.value,
            "health_score": round(self.health_score, 1),
            "signaling_summary": self.signaling_summary,
            "media_summary": self.media_summary,
            "infrastructure_summary": self.infrastructure_summary,
            "endpoint_summary": self.endpoint_summary,
            "path_summary": self.path_summary,
            "primary_hypothesis": self.primary_hypothesis.to_dict() if self.primary_hypothesis else None,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "active_problems": self.active_problems,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)

