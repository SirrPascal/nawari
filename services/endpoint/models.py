"""Nawari Endpoint Telemetry Data Models.

Conforms to schema identifier 'nawari.endpoint.telemetry.v1' as defined in
docs/architecture/endpoint-telemetry-specification.md.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TelemetricEnvironment(str, Enum):
    """Authoritative environment provenance for telemetry."""
    MOCK_SIMULATED = "MOCK_SIMULATED"
    PHYSICAL_PRODUCTION = "PHYSICAL_PRODUCTION"


class InterfaceType(str, Enum):
    """Network interface hardware or virtual classification."""
    ETHERNET = "ETHERNET"
    WIFI = "WIFI"
    VPN = "VPN"
    LOOPBACK = "LOOPBACK"
    OTHER = "OTHER"


class InterfaceState(str, Enum):
    """Network interface administrative and link state."""
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class DnsResolutionStatus(str, Enum):
    """Classification of DNS query results."""
    SUCCESS = "SUCCESS"
    NXDOMAIN = "NXDOMAIN"
    SERVFAIL = "SERVFAIL"
    TIMEOUT = "TIMEOUT"
    REFUSED = "REFUSED"
    ERROR = "ERROR"


class ServiceProtocol(str, Enum):
    """Protocols used for service reachability probing."""
    ICMP = "ICMP"
    TCP = "TCP"
    TLS = "TLS"
    HTTP = "HTTP"
    HTTPS = "HTTPS"


class HopResponseStatus(str, Enum):
    """Classification of intermediate router response in path tracing."""
    RESPONSIVE = "RESPONSIVE"          # Returned ICMP Time Exceeded with valid RTT
    TIMEOUT_COPP = "TIMEOUT_COPP"      # Router dropped ICMP TTL Expired (Control Plane Policing)
    UNREACHABLE = "UNREACHABLE"        # Destination or network unreachable
    ANONYMOUS_MPLS = "ANONYMOUS_MPLS"  # MPLS core router without IP response


@dataclass(frozen=True)
class AgentMetadata:
    """Immutable identity and runtime envelope for the endpoint agent."""
    agent_id: str
    hostname: str
    os_name: str
    os_version: str
    agent_version: str
    timestamp_ns: int = field(default_factory=time.time_ns)
    environment: TelemetricEnvironment = TelemetricEnvironment.MOCK_SIMULATED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "hostname": self.hostname,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "agent_version": self.agent_version,
            "timestamp_ns": self.timestamp_ns,
            "environment": self.environment.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentMetadata:
        return cls(
            agent_id=data["agent_id"],
            hostname=data["hostname"],
            os_name=data["os_name"],
            os_version=data["os_version"],
            agent_version=data["agent_version"],
            timestamp_ns=data.get("timestamp_ns", time.time_ns()),
            environment=TelemetricEnvironment(data.get("environment", TelemetricEnvironment.MOCK_SIMULATED.value)),
        )


@dataclass(frozen=True)
class WifiMetrics:
    """Wi-Fi link and PHY layer performance indicators."""
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    rssi_dbm: Optional[int] = None
    signal_quality_pct: Optional[float] = None
    channel: Optional[int] = None
    band_ghz: Optional[float] = None
    tx_rate_mbps: Optional[float] = None

    def __post_init__(self) -> None:
        if self.rssi_dbm is not None and not (-120 <= self.rssi_dbm <= 0):
            raise ValueError(f"RSSI dBm out of valid range [-120, 0]: {self.rssi_dbm}")
        if self.signal_quality_pct is not None and not (0.0 <= self.signal_quality_pct <= 100.0):
            raise ValueError(f"Signal quality percentage out of range [0.0, 100.0]: {self.signal_quality_pct}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WifiMetrics:
        return cls(**data)


@dataclass(frozen=True)
class LocalNetworkTelemetry:
    """Local edge connectivity from the endpoint to its default gateway."""
    default_gateway_ip: Optional[str]
    default_gateway_mac: Optional[str]
    gateway_is_reachable: bool
    gateway_rtt_ms: Optional[float]
    gateway_loss_pct: float
    interface_name: str
    interface_type: InterfaceType
    interface_state: InterfaceState
    local_ip: str
    subnet_cidr: int
    dhcp_enabled: bool
    configured_dns_servers: List[str] = field(default_factory=list)
    wifi: Optional[WifiMetrics] = None

    def __post_init__(self) -> None:
        # Invariant 2: Wi-Fi metric isolation
        if self.interface_type != InterfaceType.WIFI and self.wifi is not None:
            raise ValueError(
                f"Wi-Fi metrics must be None when interface_type is {self.interface_type.value}"
            )
        if not (0.0 <= self.gateway_loss_pct <= 100.0):
            raise ValueError(f"Gateway loss percentage out of range [0.0, 100.0]: {self.gateway_loss_pct}")
        if not self.gateway_is_reachable and self.gateway_loss_pct < 100.0:
            raise ValueError("When gateway_is_reachable is False, gateway_loss_pct must be 100.0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_gateway_ip": self.default_gateway_ip,
            "default_gateway_mac": self.default_gateway_mac,
            "gateway_is_reachable": self.gateway_is_reachable,
            "gateway_rtt_ms": self.gateway_rtt_ms,
            "gateway_loss_pct": self.gateway_loss_pct,
            "interface_name": self.interface_name,
            "interface_type": self.interface_type.value,
            "interface_state": self.interface_state.value,
            "local_ip": self.local_ip,
            "subnet_cidr": self.subnet_cidr,
            "dhcp_enabled": self.dhcp_enabled,
            "configured_dns_servers": list(self.configured_dns_servers),
            "wifi": self.wifi.to_dict() if self.wifi else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LocalNetworkTelemetry:
        wifi = WifiMetrics.from_dict(data["wifi"]) if data.get("wifi") else None
        return cls(
            default_gateway_ip=data.get("default_gateway_ip"),
            default_gateway_mac=data.get("default_gateway_mac"),
            gateway_is_reachable=data["gateway_is_reachable"],
            gateway_rtt_ms=data.get("gateway_rtt_ms"),
            gateway_loss_pct=float(data["gateway_loss_pct"]),
            interface_name=data["interface_name"],
            interface_type=InterfaceType(data["interface_type"]),
            interface_state=InterfaceState(data["interface_state"]),
            local_ip=data["local_ip"],
            subnet_cidr=int(data["subnet_cidr"]),
            dhcp_enabled=bool(data["dhcp_enabled"]),
            configured_dns_servers=list(data.get("configured_dns_servers", [])),
            wifi=wifi,
        )


@dataclass(frozen=True)
class DnsProbeTelemetry:
    """DNS query execution timing and resolution results."""
    query_name: str
    record_type: str
    resolver_ip: str
    status: DnsResolutionStatus
    resolution_time_ms: float
    resolved_ips: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_name": self.query_name,
            "record_type": self.record_type,
            "resolver_ip": self.resolver_ip,
            "status": self.status.value,
            "resolution_time_ms": self.resolution_time_ms,
            "resolved_ips": list(self.resolved_ips),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DnsProbeTelemetry:
        return cls(
            query_name=data["query_name"],
            record_type=data["record_type"],
            resolver_ip=data["resolver_ip"],
            status=DnsResolutionStatus(data["status"]),
            resolution_time_ms=float(data["resolution_time_ms"]),
            resolved_ips=list(data.get("resolved_ips", [])),
            error_message=data.get("error_message"),
        )


@dataclass(frozen=True)
class ServiceConnectivityTelemetry:
    """Transport and handshake performance to business service endpoints."""
    target_id: str
    target_name: str
    destination_ip: str
    destination_port: Optional[int]
    protocol: ServiceProtocol
    is_reachable: bool
    icmp_rtt_ms: Optional[float] = None
    icmp_loss_pct: Optional[float] = None
    tcp_connect_time_ms: Optional[float] = None
    tls_handshake_time_ms: Optional[float] = None
    http_status_code: Optional[int] = None
    http_ttfb_ms: Optional[float] = None
    http_total_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "destination_ip": self.destination_ip,
            "destination_port": self.destination_port,
            "protocol": self.protocol.value,
            "is_reachable": self.is_reachable,
            "icmp_rtt_ms": self.icmp_rtt_ms,
            "icmp_loss_pct": self.icmp_loss_pct,
            "tcp_connect_time_ms": self.tcp_connect_time_ms,
            "tls_handshake_time_ms": self.tls_handshake_time_ms,
            "http_status_code": self.http_status_code,
            "http_ttfb_ms": self.http_ttfb_ms,
            "http_total_time_ms": self.http_total_time_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ServiceConnectivityTelemetry:
        return cls(
            target_id=data["target_id"],
            target_name=data["target_name"],
            destination_ip=data["destination_ip"],
            destination_port=data.get("destination_port"),
            protocol=ServiceProtocol(data["protocol"]),
            is_reachable=bool(data["is_reachable"]),
            icmp_rtt_ms=data.get("icmp_rtt_ms"),
            icmp_loss_pct=data.get("icmp_loss_pct"),
            tcp_connect_time_ms=data.get("tcp_connect_time_ms"),
            tls_handshake_time_ms=data.get("tls_handshake_time_ms"),
            http_status_code=data.get("http_status_code"),
            http_ttfb_ms=data.get("http_ttfb_ms"),
            http_total_time_ms=data.get("http_total_time_ms"),
        )


@dataclass(frozen=True)
class HopTelemetry:
    """Individual intermediate router performance along a network path."""
    hop_index: int
    ip_address: Optional[str]
    rdns_hostname: Optional[str]
    asn: Optional[int]
    as_org: Optional[str]
    rtt_min_ms: Optional[float]
    rtt_avg_ms: Optional[float]
    rtt_max_ms: Optional[float]
    rtt_stddev_ms: Optional[float]
    loss_pct: float
    status: HopResponseStatus
    mpls_labels: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (1 <= self.hop_index <= 64):
            raise ValueError(f"Hop index out of valid range [1, 64]: {self.hop_index}")
        if not (0.0 <= self.loss_pct <= 100.0):
            raise ValueError(f"Hop loss percentage out of range [0.0, 100.0]: {self.loss_pct}")
        # Invariant 1: If status is TIMEOUT_COPP, rtt must be None
        if self.status == HopResponseStatus.TIMEOUT_COPP and self.rtt_avg_ms is not None:
            raise ValueError("Hop with status TIMEOUT_COPP must not have a valid RTT measurement")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hop_index": self.hop_index,
            "ip_address": self.ip_address,
            "rdns_hostname": self.rdns_hostname,
            "asn": self.asn,
            "as_org": self.as_org,
            "rtt_min_ms": self.rtt_min_ms,
            "rtt_avg_ms": self.rtt_avg_ms,
            "rtt_max_ms": self.rtt_max_ms,
            "rtt_stddev_ms": self.rtt_stddev_ms,
            "loss_pct": self.loss_pct,
            "status": self.status.value,
            "mpls_labels": list(self.mpls_labels),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HopTelemetry:
        return cls(
            hop_index=int(data["hop_index"]),
            ip_address=data.get("ip_address"),
            rdns_hostname=data.get("rdns_hostname"),
            asn=data.get("asn"),
            as_org=data.get("as_org"),
            rtt_min_ms=data.get("rtt_min_ms"),
            rtt_avg_ms=data.get("rtt_avg_ms"),
            rtt_max_ms=data.get("rtt_max_ms"),
            rtt_stddev_ms=data.get("rtt_stddev_ms"),
            loss_pct=float(data["loss_pct"]),
            status=HopResponseStatus(data["status"]),
            mpls_labels=list(data.get("mpls_labels", [])),
        )


@dataclass(frozen=True)
class PathTelemetry:
    """Hop-by-hop directional network path trace from endpoint to service."""
    target_id: str
    target_ip: str
    protocol: str
    total_hops: int
    end_to_end_rtt_ms: Optional[float]
    end_to_end_loss_pct: float
    path_hash: str
    has_route_changed: bool
    hops: List[HopTelemetry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_ip": self.target_ip,
            "protocol": self.protocol,
            "total_hops": self.total_hops,
            "end_to_end_rtt_ms": self.end_to_end_rtt_ms,
            "end_to_end_loss_pct": self.end_to_end_loss_pct,
            "path_hash": self.path_hash,
            "has_route_changed": self.has_route_changed,
            "hops": [h.to_dict() for h in self.hops],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PathTelemetry:
        hops = [HopTelemetry.from_dict(h) for h in data.get("hops", [])]
        return cls(
            target_id=data["target_id"],
            target_ip=data["target_ip"],
            protocol=data["protocol"],
            total_hops=int(data["total_hops"]),
            end_to_end_rtt_ms=data.get("end_to_end_rtt_ms"),
            end_to_end_loss_pct=float(data["end_to_end_loss_pct"]),
            path_hash=data["path_hash"],
            has_route_changed=bool(data["has_route_changed"]),
            hops=hops,
        )


@dataclass(frozen=True)
class EndpointTelemetryReport:
    """Top-level canonical telemetry report submitted by the endpoint agent."""
    metadata: AgentMetadata
    local_network: LocalNetworkTelemetry
    dns_probes: List[DnsProbeTelemetry] = field(default_factory=list)
    service_probes: List[ServiceConnectivityTelemetry] = field(default_factory=list)
    path_traces: List[PathTelemetry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "nawari.endpoint.telemetry.v1",
            "metadata": self.metadata.to_dict(),
            "local_network": self.local_network.to_dict(),
            "dns_probes": [d.to_dict() for d in self.dns_probes],
            "service_probes": [s.to_dict() for s in self.service_probes],
            "path_traces": [p.to_dict() for p in self.path_traces],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EndpointTelemetryReport:
        schema = data.get("schema_version")
        if schema != "nawari.endpoint.telemetry.v1":
            raise ValueError(f"Unsupported schema version: {schema}")
        return cls(
            metadata=AgentMetadata.from_dict(data["metadata"]),
            local_network=LocalNetworkTelemetry.from_dict(data["local_network"]),
            dns_probes=[DnsProbeTelemetry.from_dict(d) for d in data.get("dns_probes", [])],
            service_probes=[ServiceConnectivityTelemetry.from_dict(s) for s in data.get("service_probes", [])],
            path_traces=[PathTelemetry.from_dict(p) for p in data.get("path_traces", [])],
        )

    @classmethod
    def from_json(cls, json_str: str) -> EndpointTelemetryReport:
        return cls.from_dict(json.loads(json_str))
