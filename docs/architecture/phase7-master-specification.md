# Nawari Phase 7 Master Implementation Specification
## Endpoint-to-Service Network Observability & Cross-Domain Service Assurance

**Document Version:** 1.0.0  
**Status:** Approved Master Specification  
**Date:** 2026-11-07  
**Baseline Commit:** [`bf42176`](file:///Users/madeira/Desktop/Projects/nawari) (Stage 7A Completed)  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04, 2 vCPU, 7.8 GiB RAM) & Enterprise Endpoints

---

## 1. Executive Summary & Problem Statement

Nawari's earlier phases established authoritative infrastructure monitoring (Zabbix 7.4 + PostgreSQL 17), Avaya SBCE appliance telemetry (SNMPv3), controlled synthetic voice testing (Asterisk 22 AMI), and cross-domain incident correlation (ITU-T G.107 E-model).

However, core infrastructure monitoring cannot determine the true experience of the user at the network edge. When an employee reports poor softphone call quality (one-way audio, robotic distortion, or SIP registration timeouts), the root cause may reside anywhere along the distributed delivery chain:
- **Local Endpoint:** High CPU load, local Wi-Fi channel interference, saturated default gateway.
- **Local LAN:** Switch port congestion, DHCP/DNS delays.
- **Transit WAN/MPLS:** ISP packet drops, route flaps, asymmetrical bufferbloat.
- **Enterprise Edge:** SBCE interface discards, firewall state exhaustion.
- **Signaling & Media:** SIP registration timeouts, asymmetric RTP streams.

**Phase 7 turns Nawari into a ThousandEyes-like endpoint-to-service observability platform.** By deploying lightweight, non-privileged probe sensors to user laptops and enterprise workstations, Nawari measures connectivity and service health from the edge through intermediate network hops directly to enterprise communications services.

```
+----------------------------------------------------------------------------------------------------+
|                                  THE ENDPOINT-TO-SERVICE PIPELINE                                  |
|                                                                                                    |
|  [ User Endpoint ]                                                                                 |
|         │                                                                                          |
|         ├─► [ 7A: Agent Core ]       (UUID identity, lifecycle, scheduler, OS abstraction)         |
|         ├─► [ 7B: Connectivity ]     (DNS resolution, TCP handshake, TLS timing, HTTP TTFB)        |
|         └─► [ 7C: Path Analysis ]    (Paris traceroute, CoPP guard, hop latency/loss)              |
|                     │                                                                              |
|                     ▼ (HTTPS / mTLS / Port 8443)                                                   |
|  [ 7D: Secure Ingestion Gateway ]    (FastAPI, token auth, schema validation, trusted provenance)  |
|         │                                                                                          |
|         ▼ (Zabbix Sender ZBXD\x01 / Port 10051)                                                    |
|  [ Zabbix 7.4 Engine ]               (Trapper items, Low-Level Discovery (LLD), history, triggers) |
|         │                                                                                          |
|         ▼                                                                                          |
|  [ 7E: Grafana 11.6 Dashboards ]     (Fleet health, endpoint drill-downs, hop-by-hop path matrix)  |
|         │                                                                                          |
|         ▼                                                                                          |
|  [ 7F: Cross-Domain Assurance ]      (Correlates Endpoint + Path + SBCE + SIP + RTP quality)       |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Stage-by-Stage Implementation Roadmap

### Stage 7A: Endpoint Agent Foundation *(Completed in `bf42176`)*
- **Objective:** Establish the modular, non-privileged agent framework with persistent identity and scheduling.
- **Deliverables:**
  - OS abstraction layer (`services/endpoint/os_platform/`) across Darwin, Linux, and Windows.
  - Persistent UUIDv4 identity management with atomic storage and corruption recovery.
  - Resource-conscious asyncio scheduler with jitter, per-probe timeouts, and duplicate execution guards.
  - Bounded offline JSONL disk spooler with `0600` permissions.
  - Benchmarked footprint: **0.93 ms** internal initialization latency, **29.55 MiB RSS**, and **0.39% CPU**.

---

### Stage 7B: Endpoint Connectivity, DNS and Service Probing *(Current Milestone)*
- **Objective:** Measure health and performance of the foundational network services an endpoint depends on.
- **Components:**
  1. **DNS Monitoring Engine (`services/endpoint/probes/dns.py`):**
     - Measures resolution time with sub-millisecond precision.
     - Supports query types: `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `SRV`.
     - Tracks resolver used (system default vs explicitly configured resolver).
     - Robust failure classification: `NOERROR`, `NXDOMAIN`, `SERVFAIL`, `REFUSED`, `TIMEOUT`, `NOERROR_EMPTY`.
     - Supports DNS-over-TCP fallback when UDP response is truncated (TC bit set).
     - *Invariant:* A DNS failure must never be misclassified as a total network outage.
  2. **TCP Connectivity Engine (`services/endpoint/probes/tcp.py`):**
     - Measures 3-way handshake time (SYN $\to$ SYN-ACK RTT).
     - Configurable ports: 443 (HTTPS), 5061 (SIP TLS), 22 (SSH), 53 (DNS TCP), 8088 (Web UI).
     - Classification: `SUCCESS`, `TIMEOUT`, `CONNECTION_REFUSED`, `HOST_UNREACHABLE`, `NETWORK_UNREACHABLE`, `CONNECTION_RESET`.
     - *Invariant:* Successful TCP connect to port 5061 proves transport reachability, NOT SIP registration or call success.
  3. **TLS Monitoring Engine (`services/endpoint/probes/tls.py`):**
     - Measures TLS handshake duration.
     - Records negotiated TLS version (TLSv1.2, TLSv1.3) and cipher suite.
     - Validates certificate validity, expiration dates, and hostname matches.
     - *Invariant:* Certificate verification remains enabled by default; never silently disabled.
  4. **HTTP and HTTPS Monitoring Engine (`services/endpoint/probes/http.py`):**
     - Decomposes request timing: DNS lookup, TCP connect, TLS handshake, TTFB, and total duration.
     - Records HTTP status codes and response sizes.
     - Enforces response size limits and redirect policies.
     - *Invariant:* Strict data privacy; zero collection of cookies, auth tokens, or browsing history.

---

### Stage 7C: Network Path Discovery and Analysis
- **Objective:** Decompose the network path into discrete hops between endpoint and destination service (ThousandEyes model).
- **Components:**
  1. **Cross-Platform Traceroute Engine (`services/endpoint/path/`):**
     - Supports Windows, Linux, and macOS using unprivileged OS capabilities.
     - Measures per-hop RTT (min, avg, max, stddev) and response ratio.
  2. **Paris Traceroute Flow-Consistency:**
     - Holds 5-tuple flow identifier constant to prevent Equal-Cost Multi-Path (ECMP) artificial route flapping.
  3. **Hop-by-Hop Loss & CoPP Guard:**
     - Distinguishes router Control Plane Policing (ICMP rate-limiting) from genuine transit packet loss.
     - Intermediate `* * *` is classified as `TIMEOUT_COPP` if downstream hops and destination are responsive.
     - True loss onset is localized to the hop where persistent loss initiates through to destination.
  4. **Route Change & Latency Jump Detection:**
     - Flags latency onset when $\Delta RTT_k > 40\text{ ms}$.
     - Detects route divergence via SHA-256 path hashing.
  5. **Advanced Path Metadata:**
     - RFC 4950 MPLS label stack extraction where supported.
     - RFC 1918 NAT boundary tagging.

---

### Stage 7D: Secure Telemetry Ingestion and Zabbix Integration
- **Objective:** Connect endpoint agents securely to Nawari and ingest telemetry into Zabbix without exposing internal ports.
- **Components:**
  1. **HTTPS / mTLS Ingestion Gateway:**
     - Dedicated FastAPI service on port 8443.
     - Mutual TLS certificate authentication and HMAC token validation.
     - Strict JSON schema validation (`nawari.endpoint.telemetry.v1`).
     - Rate-limiting and replay protection.
  2. **Authoritative Provenance Stamping:**
     - Server-side assignment of `environment` (`PHYSICAL_PRODUCTION` vs `MOCK_SIMULATED`).
     - Endpoints cannot spoof production provenance.
  3. **Zabbix Trapper & Low-Level Discovery (LLD):**
     - LLD Trapper rule `nawari.endpoint.path.discovery[{#TARGET}]`.
     - Dynamic item prototypes for hop RTT, loss, status, and IP with 7-day retention.
     - Zabbix Server Trapper port 10051 remains strictly internal, never exposed to user subnets.

---

### Stage 7E: Grafana Endpoint and Network Experience Dashboards
- **Objective:** Deliver actionable operational visibility for network and telephony engineers.
- **Dashboards:**
  1. **Endpoint Fleet Overview:** Total, online, degraded, mock vs production counts, location filters.
  2. **Individual Endpoint Health:** Active NIC, Wi-Fi RSSI/quality, gateway latency, DNS timing, TCP connects.
  3. **DNS Performance Dashboard:** Query latency, resolver comparison, NXDOMAIN/SERVFAIL distributions.
  4. **Network Path Dashboard:** Hop-by-hop latency matrix, CoPP indicator, route change timeline.
  5. **Service Experience Dashboard:** Target availability, TTFB, status codes, affected endpoint counts.
  6. **Endpoint Alert Dashboard:** Active alarms, severity, duration, and root-cause links.
- **Reliability:** All panels feature `"noValue": "STALE / NO DATA"` guards and provenance badges.

---

### Stage 7F: Cross-Domain Correlation and Service Assurance
- **Objective:** Combine endpoint, network path, SBCE infrastructure, SIP signaling, and RTP media telemetry into unified root-cause service assurance.
- **Six Failure Scenarios Tested:**
  1. *Local Endpoint Problem:* Isolated high latency; gateway and other subnet endpoints healthy.
  2. *DNS Problem:* Multiple endpoints fail DNS queries; IP transport to other services succeeds.
  3. *Network Infrastructure Problem:* Shared WAN hop packet loss coinciding with Zabbix interface alarm.
  4. *Avaya Signaling Problem:* Network/TCP healthy; synthetic SIP registration or INVITE fails.
  5. *Voice Media Problem:* SIP succeeds; RTP one-way audio or RTCP jitter exceeds threshold.
  6. *Application Problem:* DNS, TCP, and TLS succeed; HTTP response time high or 5xx returned.
- **Hypothesis Calibration:** Strict enforcement of `CONFIRMED` vs `PROBABLE` vs `SUSPECTED`.

---

## 3. Mandatory Implementation Rules

1. **One Stage at a Time:** Do not begin the next stage until the current stage passes all acceptance criteria and is committed cleanly.
2. **Preserve Sentra:** `/Users/madeira/Desktop/Projects/sentra` remains clean and untouched.
3. **Local Testing First:** Use local Docker containers (`nawari-asterisk`, `nawari-zabbix-web`, `nawari-postgres`) and controlled mocks; never probe physical Avaya appliances while away from the enterprise network.
4. **Zero-RCE Guarantee:** Purely declarative configuration; no shell command evaluation.
5. **No Fabricated Data:** Missing or unsupported measurements strictly yield `None` / `UNKNOWN`.
6. **Production Headroom:** Target VM (`mon-grafana01`, 2 vCPU, 7.8 GiB RAM) must retain >5.0 GiB free RAM.
