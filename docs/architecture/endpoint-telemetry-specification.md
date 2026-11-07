# Nawari Endpoint Telemetry Specification

**Document Version:** 1.0.0  
**Status:** Architectural Baseline for Review  
**Date:** 2026-11-07  
**Schema Identifier:** `nawari.endpoint.telemetry.v1`

---

## 1. Scope & Design Authority

This specification defines the canonical data models, measurement methodologies, Zabbix trapper mappings, and invariant integrity rules for endpoint network telemetry within the Nawari observability platform.

Every metric collected by the Nawari Endpoint Agent and ingested into Zabbix conforms to the contracts defined herein.

---

## 2. Canonical Data Models

### 2.1 Agent Metadata & Provenance Envelope
Every telemetry transmission includes an authoritative metadata header:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict

class TelemetricEnvironment(str, Enum):
    MOCK_SIMULATED = "MOCK_SIMULATED"
    PHYSICAL_PRODUCTION = "PHYSICAL_PRODUCTION"

@dataclass(frozen=True)
class AgentMetadata:
    agent_id: str                      # Unique UUID v4 generated at registration
    hostname: str                      # Endpoint OS hostname
    os_name: str                       # "Windows", "Linux", "Darwin"
    os_version: str                    # OS kernel/build version string
    agent_version: str                 # Nawari probe version (e.g. "1.0.0")
    timestamp_ns: int                  # Nanosecond epoch clock timestamp (time.time_ns())
    environment: TelemetricEnvironment # Enforced by Ingestion Gateway
```

---

### 2.2 Local Network Telemetry
Measures edge connectivity from the endpoint to its immediate local network infrastructure.

```python
class InterfaceType(str, Enum):
    ETHERNET = "ETHERNET"
    WIFI = "WIFI"
    VPN = "VPN"
    LOOPBACK = "LOOPBACK"
    OTHER = "OTHER"

class InterfaceState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class WifiMetrics:
    ssid: Optional[str] = None         # Connected Wi-Fi SSID
    bssid: Optional[str] = None        # Access Point BSSID MAC
    rssi_dbm: Optional[int] = None     # Signal strength in dBm (-30 to -90)
    signal_quality_pct: Optional[float] = None  # Link quality 0.0% to 100.0%
    channel: Optional[int] = None      # 2.4 GHz or 5/6 GHz channel number
    band_ghz: Optional[float] = None   # 2.4, 5.0, or 6.0
    tx_rate_mbps: Optional[float] = None # Current Wi-Fi PHY transmit rate

@dataclass(frozen=True)
class LocalNetworkTelemetry:
    default_gateway_ip: Optional[str]
    default_gateway_mac: Optional[str]
    gateway_is_reachable: bool
    gateway_rtt_ms: Optional[float]    # ICMP ping round-trip time to gateway
    gateway_loss_pct: float            # Packet loss to default gateway (0.0 to 100.0)
    interface_name: str                # e.g., "eth0", "Wi-Fi", "en0"
    interface_type: InterfaceType
    interface_state: InterfaceState
    local_ip: str                      # Current IPv4 address
    subnet_cidr: int                   # Subnet mask length (e.g. 24)
    dhcp_enabled: bool
    configured_dns_servers: List[str]  # Configured DNS resolvers in order
    wifi: Optional[WifiMetrics] = None # Populated only if interface_type == WIFI
```

---

### 2.3 DNS Resolution Telemetry
Measures enterprise and external name resolution health.

```python
class DnsResolutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NXDOMAIN = "NXDOMAIN"
    SERVFAIL = "SERVFAIL"
    TIMEOUT = "TIMEOUT"
    REFUSED = "REFUSED"
    ERROR = "ERROR"

@dataclass(frozen=True)
class DnsProbeTelemetry:
    query_name: str                    # e.g. "sbce-a1.kq.internal" or "voice.nawari.local"
    record_type: str                   # "A", "AAAA", "SRV"
    resolver_ip: str                   # The DNS server that answered or timed out
    status: DnsResolutionStatus
    resolution_time_ms: float          # Time taken for query completion
    resolved_ips: List[str]            # Resolved IP addresses
    error_message: Optional[str] = None
```

---

### 2.4 Service Connectivity Telemetry
Measures transport, handshake, and application response times to critical business targets (Avaya SBCE, SIP proxy, Web services).

```python
class ServiceProtocol(str, Enum):
    ICMP = "ICMP"
    TCP = "TCP"
    TLS = "TLS"
    HTTP = "HTTP"
    HTTPS = "HTTPS"

@dataclass(frozen=True)
class ServiceConnectivityTelemetry:
    target_id: str                     # e.g. "avaya-sbce-sig-a1"
    target_name: str                   # Human-readable label
    destination_ip: str
    destination_port: Optional[int]
    protocol: ServiceProtocol
    is_reachable: bool
    icmp_rtt_ms: Optional[float]       # ICMP Echo latency
    icmp_loss_pct: Optional[float]     # ICMP packet loss (0.0% to 100.0%)
    tcp_connect_time_ms: Optional[float]   # 3-way handshake duration (SYN -> SYN-ACK)
    tls_handshake_time_ms: Optional[float] # TLS negotiation duration
    http_status_code: Optional[int]    # HTTP response code (200, 503, etc.)
    http_ttfb_ms: Optional[float]      # Time to first byte
    http_total_time_ms: Optional[float]
```

---

### 2.5 Hop-by-Hop Network Path Telemetry (ThousandEyes Model)
Captures directional path performance across intermediate routers between endpoint and service.

```python
class HopResponseStatus(str, Enum):
    RESPONSIVE = "RESPONSIVE"          # Router returned ICMP Time Exceeded with valid RTT
    TIMEOUT_COPP = "TIMEOUT_COPP"      # Router dropped ICMP TTL Expired (Control Plane Policing)
    UNREACHABLE = "UNREACHABLE"        # Destination or network unreachable
    ANONYMOUS_MPLS = "ANONYMOUS_MPLS"  # MPLS core router without IP response

@dataclass(frozen=True)
class HopTelemetry:
    hop_index: int                     # TTL distance (1, 2, 3... 30)
    ip_address: Optional[str]          # Resolved IP or None if non-responsive
    rdns_hostname: Optional[str]       # Reverse DNS PTR or None
    asn: Optional[int]                 # Autonomous System Number (e.g. 36940)
    as_org: Optional[str]              # AS Organization (e.g. "Kenya Airways Ltd")
    rtt_min_ms: Optional[float]        # Min RTT across probe iterations
    rtt_avg_ms: Optional[float]        # Mean RTT
    rtt_max_ms: Optional[float]        # Max RTT
    rtt_stddev_ms: Optional[float]     # Latency jitter across probe bursts
    loss_pct: float                    # Loss percentage across probe burst (0-100%)
    status: HopResponseStatus
    mpls_labels: List[int] = field(default_factory=list) # Extracted RFC 4950 MPLS labels

@dataclass(frozen=True)
class PathTelemetry:
    target_id: str                     # Associated target identifier
    target_ip: str
    protocol: str                      # "ICMP", "UDP_PARIS", "TCP_SYN"
    total_hops: int
    end_to_end_rtt_ms: Optional[float]
    end_to_end_loss_pct: float
    path_hash: str                     # SHA-256 hash of ordered responsive hop IPs
    has_route_changed: bool            # True if path_hash != previous measurement
    hops: List[HopTelemetry] = field(default_factory=list)
```

---

## 3. Zabbix Trapper Item Specifications

Endpoint metrics are mapped to dedicated Zabbix Trapper items and Low-Level Discovery (LLD) prototypes.

### 3.1 Static Endpoint Items (`Template Nawari Endpoint Probe`)

| Item Key | Name | Type | Value Type | Unit | Value Map / Range | Retention |
|---|---|---|---|---|---|---|
| `endpoint.info` | Endpoint Registration Info | Trapper | Character | Text | JSON Metadata | 30d |
| `endpoint.environment` | Telemetry Provenance Mode | Trapper | Numeric (unsigned) | — | `0=Mock, 1=Physical Production` | 365d |
| `endpoint.network.interface.type` | Active Network Interface Type | Trapper | Numeric (unsigned) | — | `0=Ethernet, 1=Wi-Fi, 2=VPN, 3=Other` | 90d |
| `endpoint.network.gateway.rtt` | Default Gateway Latency | Trapper | Numeric (float) | `s` | Seconds (e.g. `0.0024` for 2.4ms) | 7d (trends: 365d) |
| `endpoint.network.gateway.loss` | Default Gateway Packet Loss | Trapper | Numeric (float) | `%` | `0.00` to `100.00` | 7d (trends: 365d) |
| `endpoint.network.wifi.rssi` | Wi-Fi Signal Strength (RSSI) | Trapper | Numeric (float) | `dBm` | `-100.0` to `-20.0` | 7d (trends: 365d) |
| `endpoint.network.wifi.quality` | Wi-Fi Link Quality | Trapper | Numeric (float) | `%` | `0.0` to `100.0` | 7d (trends: 365d) |
| `endpoint.dns.latency[{#TARGET}]` | DNS Resolution Time | Trapper | Numeric (float) | `s` | Seconds | 7d (trends: 365d) |
| `endpoint.dns.status[{#TARGET}]` | DNS Resolution Status | Trapper | Numeric (unsigned) | — | `0=Success, 1=NXDomain, 2=ServFail, 3=Timeout` | 30d |
| `endpoint.service.tcp_connect[{#TARGET}]` | Target TCP Connect Time | Trapper | Numeric (float) | `s` | Seconds (3-way handshake) | 7d (trends: 365d) |
| `endpoint.service.tls_handshake[{#TARGET}]` | Target TLS Handshake Time | Trapper | Numeric (float) | `s` | Seconds | 7d (trends: 365d) |
| `endpoint.service.http_status[{#TARGET}]` | Target HTTP Status Code | Trapper | Numeric (unsigned) | — | `200`, `503`, etc. | 30d |
| `endpoint.path.e2e_rtt[{#TARGET}]` | Path End-to-End Latency | Trapper | Numeric (float) | `s` | Seconds | 7d (trends: 365d) |
| `endpoint.path.e2e_loss[{#TARGET}]` | Path End-to-End Packet Loss | Trapper | Numeric (float) | `%` | `0.00` to `100.00` | 7d (trends: 365d) |
| `endpoint.path.route_changed[{#TARGET}]` | Path Route Change Detected | Trapper | Numeric (unsigned) | — | `0=Baseline Match, 1=Route Changed` | 90d |

---

### 3.2 Dynamic Hop Item Prototypes (`LLD Rule: nawari.endpoint.path.discovery[{#TARGET}]`)

| Prototype Item Key | Name | Type | Value Type | Unit | Description |
|---|---|---|---|---|---|
| `nawari.path.hop.rtt[{#TARGET},{#HOP_INDEX}]` | Hop #{#HOP_INDEX} Latency [{#TARGET}] | Trapper | Numeric (float) | `s` | Mean round-trip latency to hop |
| `nawari.path.hop.loss[{#TARGET},{#HOP_INDEX}]` | Hop #{#HOP_INDEX} Packet Loss [{#TARGET}] | Trapper | Numeric (float) | `%` | Observed packet loss at hop |
| `nawari.path.hop.status[{#TARGET},{#HOP_INDEX}]` | Hop #{#HOP_INDEX} Status [{#TARGET}] | Trapper | Numeric (unsigned) | — | `0=Responsive, 1=CoPP Rate-Limited, 2=Unreachable` |
| `nawari.path.hop.ip[{#TARGET},{#HOP_INDEX}]` | Hop #{#HOP_INDEX} IP [{#TARGET}] | Trapper | Character | Text | IP address of router at this hop |

---

## 4. Telemetry Integrity Invariants & Ingestion Rules

### Invariant 1: Unresponsive Intermediate Hop vs Real Loss (The CoPP Guard)
- **Problem:** Many enterprise and transit routers do not generate ICMP Time Exceeded packets (or rate-limit them heavily to protect the control plane via CoPP).
- **Rule:** If Hop $K$ shows 100% loss (`* * *`), but Hop $K+1$ responds with valid RTT and low loss, and the Destination responds normally:
  - Hop $K$ `loss_pct` MUST NOT trigger an alarm.
  - Hop $K$ `status` MUST be set to `TIMEOUT_COPP` (`1`), not `UNREACHABLE`.
  - Hop $K$ `rtt` MUST be set to `None` (omitted from Zabbix float items).
- **True Loss Invariant:** Packet loss at Hop $K$ is considered genuine network impairment **if and only if** packet loss persists or increases at subsequent hops ($K+1, K+2, \dots$) through to the Destination.

### Invariant 2: Wi-Fi Metric Isolation
- If `interface_type != InterfaceType.WIFI`:
  - `wifi_metrics` MUST be `None`.
  - Zabbix items `endpoint.network.wifi.rssi` and `endpoint.network.wifi.quality` MUST NOT be sent or populated.
  - No synthetic zeroes (e.g. `0 dBm`) may be submitted.

### Invariant 3: Authoritative Telemetry Provenance
- The field `environment` (`MOCK_SIMULATED` vs `PHYSICAL_PRODUCTION`) CANNOT be overridden by an endpoint agent payload.
- The **Nawari Ingestion Gateway** injects the authoritative provenance based on its verified collector certificate and server configuration.
- Any attempt by a test agent or compromised endpoint to submit `PHYSICAL_PRODUCTION` on a simulated collector is rejected with HTTP 403.

### Invariant 4: Telemetry Staleness & Dead Agent Guard
- Endpoint heartbeats and reachability tests occur at a defined interval (default: 60 seconds).
- A Zabbix trigger `nodata(15m)=1` is attached to `endpoint.network.gateway.rtt`.
- If an endpoint ceases transmitting telemetry for >15 minutes:
  - Trigger fires: `Endpoint probe telemetry is stale (>15m)`.
  - Service assurance correlator marks the endpoint health as `UNKNOWN`.
  - Missing metrics NEVER display as 0ms latency or 0% packet loss.
