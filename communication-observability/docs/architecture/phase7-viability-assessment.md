# Nawari Phase 7 Technical Viability Assessment

**Document Version:** 1.0.0  
**Status:** Architectural Baseline for Review  
**Date:** 2026-11-07  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04, 2 vCPU, 7.8 GiB RAM) & Enterprise Windows/Linux Endpoints

---

## 1. Executive Summary

This viability assessment provides an evidence-based technical evaluation of all technologies, protocols, and architectural components proposed for **Phase 7: Endpoint-to-Service Network Observability**.

Every component is evaluated against official vendor documentation, networking RFC standards, security boundaries, and strict resource budgets on the production target host.

---

## 2. Component Technical Viability Matrix

### 2.1 Zabbix 7.4 Trapper-Based Low-Level Discovery (LLD)
- **Purpose:** Dynamically discover intermediate network hops along the path to each monitored target without static configuration.
- **Official Documentation:** Zabbix 7.4 Manual: *Discovery of resources using Zabbix trapper* (`zabbix.com/documentation/7.4/manual/discovery/low_level_discovery`).
- **Compatibility:** Supported natively in Zabbix 7.4. Discovery rules of type `Zabbix trapper` (Type 2) accept JSON arrays submitted via `zabbix_sender` protocol (`ZBXD\x01`).
- **Resource Requirements:** Negligible. Trapper LLD rules are processed asynchronously by Zabbix Server discoverer and history syncer processes.
- **Security Implications:** Requires sending data to Zabbix Trapper. Mitigated by routing endpoint telemetry through the Nawari Ingestion Gateway rather than exposing port 10051 directly to client subnets.
- **Known Limitations:** If routes flap rapidly, LLD could generate many transient item prototypes. Mitigated by setting a minimum route stability threshold (route must persist for 2 consecutive measurement cycles before triggering LLD creation) and configuring LLD item lifetime to `7d` with automatic cleanup.
- **Verdict for Phase 7:** **Approved — Core Architecture Component**.

---

### 2.2 Endpoint Agent Language: Python vs Compiled Go
- **Purpose:** Cross-platform agent running on Windows 10/11 and Linux laptops.
- **Official Documentation:** Python 3.12+ Standard Library; PyInstaller documentation; Go 1.22+ runtime specification.
- **Comparison & Evaluation:**
  | Evaluation Criteria | Modular Python 3.12+ (PyInstaller) | Compiled Go (Native Static Binary) |
  |---|---|---|
  | **Memory RSS (Idle)** | 35 – 45 MiB | 10 – 15 MiB |
  | **Binary Package Size** | ~38 MB (bundled with runtime) | ~14 MB (single static executable) |
  | **Development Velocity** | Very High (reuses Nawari models & client) | Moderate (requires duplicate data models) |
  | **Platform Integration** | Windows `ctypes` (`Iphlpapi.dll`), Linux sockets | Windows `x/sys/windows`, Linux `syscall` |
  | **Maintenance Overhead** | Single language across entire Nawari repo | Dual-language codebase (Python + Go) |
  | **Subprocess / Shell Risk** | Zero (pure standard library APIs) | Zero (pure native system calls) |
- **Verdict for Phase 7:** **Approved: Python Modular Architecture for Phase 7 Reference Implementation**.
  - Python provides maximum engineering velocity, direct reuse of verified schema validation, and unified testing with the rest of Nawari.
  - If a future enterprise rollout exceeds 5,000 corporate laptops and warrants sub-15MB RAM per laptop, the clean schema specification in `docs/architecture/endpoint-telemetry-specification.md` allows a 1:1 drop-in Go rewrite without altering the backend or Zabbix pipeline.

---

### 2.3 Windows Non-Admin Probing via `Iphlpapi.dll`
- **Purpose:** Perform ICMP ping and hop-by-hop traceroute on Windows 10/11 laptops without requiring Administrator privileges.
- **Official Documentation:** Microsoft Learn: `Iphlpapi.h` — *IcmpCreateFile, IcmpSendEcho, IP_OPTION_INFORMATION* (`learn.microsoft.com/en-us/windows/win32/api/icmpapi/nf-icmpapi-icmpsendecho`).
- **Compatibility:** Universally supported across all Windows client versions (Windows 10, Windows 11, Windows Server 2016+).
- **Resource Requirements:** < 1 MiB overhead; standard Windows user-space DLL.
- **Security Implications:** Zero elevation of privilege. Can be invoked safely by standard, non-administrator user accounts. The IP Helper API is the official Microsoft-sanctioned method for user-mode ICMP.
- **Known Limitations:** Cannot craft arbitrary raw packet payloads or adjust UDP checksums. However, setting the `Ttl` field in `IP_OPTION_INFORMATION` provides full hop-by-hop traceroute functionality.
- **Verdict for Phase 7:** **Approved — Mandatory Windows Implementation Baseline**.

---

### 2.4 Linux Unprivileged ICMP & Capabilities
- **Purpose:** Perform ICMP and network path probing on Linux endpoints without running as `root`.
- **Official Documentation:** Linux Kernel Documentation: *Ping Socket Documentation* (`kernel.org/doc/html/latest/networking/ping-sysctl.html`); `capabilities(7)`.
- **Compatibility:** Supported on all modern Linux kernels (version 3.0+). Default on Ubuntu 20.04+, Debian 11+, and Fedora.
- **Resource Requirements:** Standard Linux kernel datagram sockets.
- **Security Implications:** Eliminates root execution. Governed by sysctl `net.ipv4.ping_group_range = 0 2147483647`. If Paris traceroute custom UDP checksum adjustment is required, an isolated file capability `setcap cap_net_raw+ep` is granted to the binary, leaving all other privileges disabled.
- **Known Limitations:** Some hardened container environments disable `ping_group_range`. Mitigated by detecting available socket types at agent startup and gracefully falling back to TCP connect probing.
- **Verdict for Phase 7:** **Approved — Mandatory Linux Implementation Baseline**.

---

### 2.5 Paris Traceroute Flow-Hashing (RFC Standard)
- **Purpose:** Prevent false route flapping and phantom packet loss caused by Equal-Cost Multi-Path (ECMP) load balancers.
- **Official Documentation:** RFC 792 (ICMP), RFC 4884 / RFC 4950 (MPLS extensions in ICMP), *Paris Traceroute: Catching Route Flaps in Load-Balanced Networks* (ACM SIGCOMM).
- **Compatibility:** Universally compatible with all standard IP routers.
- **Resource Requirements:** Negligible. Requires calculating a static checksum adjustment for UDP probes or maintaining a fixed ICMP sequence/ID.
- **Security Implications:** Standard outbound UDP/ICMP traffic; no special network permissions required.
- **Known Limitations:** Egress corporate firewalls may drop high-port UDP. Mitigated by providing TCP SYN probing on allowed ports (443, 5061) as an alternate path tracing mode.
- **Verdict for Phase 7:** **Approved — Core Path Analysis Algorithm**.

---

### 2.6 Autonomous System (ASN) Attribution
- **Purpose:** Map intermediate public IP addresses to their network owner (e.g. AS36940 Kenya Airways, AS37061 Safaricom).
- **Official Documentation:** MaxMind GeoLite2 ASN specification; Team Cymru IP-to-ASN Mapping service (`team-cymru.com/community-services/ip-asn-mapping/`).
- **Compatibility:** MaxMind reader is cross-platform; Team Cymru uses standard DNS TXT records.
- **Resource Requirements:** MaxMind database file is ~8 MB. In-memory trie query takes $< 5\mu\text{s}$ per lookup.
- **Security Implications:** MaxMind database operates completely offline with zero outbound network calls, ideal for air-gapped enterprise environments.
- **Known Limitations:** GeoLite2 databases require periodic monthly updates.
- **Verdict for Phase 7:** **Approved: Offline MaxMind/Mock Lookup for Phase 7 Baseline**. No external DNS queries initiated by endpoint agents.

---

### 2.7 Grafana 11.6 Visualization Strategy
- **Purpose:** Render intuitive user network experience and hop-by-hop path visualizations.
- **Official Documentation:** Grafana 11.x Documentation: *Node Graph Panel, State Timeline Panel, Bar Chart Panel, Canvas Panel*.
- **Evaluation of Visualization Panels:**
  1. **Node Graph Panel:** Excellent for directed graphs and topological trees. Requires two specific data frames (`nodes` and `edges`). Can be populated via PostgreSQL SQL queries against Zabbix LLD tables.
  2. **State Timeline Panel:** Native, highly performant panel showing latency/loss state per hop over time. Displays discrete colors (Green: <20ms, Yellow: 20-50ms, Red: >50ms, Grey: CoPP Timeout).
  3. **Bar Chart / Multi-Series Time Series:** Visualizes per-hop latency progression ($\Delta RTT$) across the path distance (TTL 1..N).
  4. **Custom Grafana Plugin:** Highly complex, creates external build dependencies, and increases maintenance overhead.
- **Verdict for Phase 7:** **Approved: Native Grafana Panels (State Timeline + Bar Chart + PostgreSQL/Zabbix Node Graph)**.
  - Zero custom plugin dependencies required.
  - Fully compatible with Grafana 11.6+ out-of-the-box.

---

## 3. Production Resource Footprint Verification

### Target Host: `mon-grafana01` (2 vCPU, 7.8 GiB RAM, ~17 GB Free Disk)

```
+----------------------------------------------------------------------------------------------------+
|                               HOST MEMORY ALLOCATION (7.8 GiB TOTAL)                               |
|                                                                                                    |
|  [ Nawari Baseline Stack: ~810 MiB ]  [ Phase 7 Additions: ~85 MiB ]                               |
|  ==================================   =============================                               |
|  * Postgres:      180 MiB             * Ingestion Gateway:  55 MiB                                 |
|  * Zabbix Server: 160 MiB             * LLD Memory Buffer:  30 MiB                                 |
|  * Zabbix Web:     90 MiB                                                                          |
|  * Grafana:       130 MiB                                                                          |
|  * Asterisk:      140 MiB                                                                          |
|  * SNMP Traps:     25 MiB                                                                          |
|  * Nawari Core:    85 MiB                                                                          |
|                                                                                                    |
|  [ Host OS & Page Cache: ~1,500 MiB ]                                                              |
|                                                                                                    |
|  [ GUARANTEED FREE HEADROOM: ~5,400 MiB (~5.4 GiB) ]                                               |
+----------------------------------------------------------------------------------------------------+
```

### Telemetry Sizing Model (50 Monitored Endpoints / 2 Targets per Endpoint):
- **Dynamic Hop Items:** 50 endpoints $\times$ 2 targets $\times$ 8 hops (avg) = **800 dynamic items**.
- **Ingestion Cadence:** Path trace every 5 minutes (300s); reachability every 60s.
- **Daily History Records:** $\sim 350,000$ records / day in PostgreSQL.
- **Daily Storage Ingress:** $\approx 18\text{ MB / day}$.
- **7-Day Retention Footprint:** $\approx 126\text{ MB}$.
- **CPU Overhead:** $< 2\%$ CPU utilization for Zabbix history syncer and gateway validation.

*Conclusion:* The Phase 7 architecture is exceptionally lightweight and comfortably within all physical VM constraints.

---

## 4. Risk Assessment & Mitigation Strategies

| Risk | Impact | Likelihood | Mitigation Strategy |
|---|---|---|---|
| **Intermediate Router CoPP Misinterpreted as Loss** | High (false alarms) | High | Implement the CoPP Guard algorithm: intermediate packet loss is only an alarm if loss persists to downstream hops and destination. |
| **Route Churn Overloading Zabbix LLD Engine** | Medium (Zabbix cache churn) | Low | Route change dampening: require path change to persist for 2 consecutive cycles before firing LLD update. |
| **Endpoint Antivirus / EDR Flags Agent** | High (agent blocked) | Medium | 1. Zero raw packet injection on Windows; use official `Iphlpapi.dll`.<br/>2. Zero shell execution (`shell=False`).<br/>3. Code-sign binaries with enterprise certificate. |
| **Employee Laptop Wi-Fi Roaming Produces Spikes** | Medium (noise in trends) | High | Filter transient roaming disconnects (<5s); evaluate Wi-Fi link quality metrics (`signal_quality_pct`) before flagging network infrastructure. |
| **Simulated Telemetry Inadvertently Tagged as Production** | High (data contamination) | Low | Ingestion Gateway enforces provenance tags server-side; client cannot claim production status on a test gateway. |

---

## 5. Explicitly Deferred Features for Phase 8

To maintain strict delivery focus and protect system stability, the following capabilities are explicitly deferred from Phase 7:
1. **Full BGP Route Collector Peering:** Real-time BGP routing table feeds (BGP monitoring protocols like BMP) are deferred; static/offline ASN mapping is used.
2. **Deep Packet Capture (PCAP):** Continuous packet capture at the endpoint is out of scope; only layer-3/4 latency and loss metrics are captured.
3. **Endpoint Remediation Actions:** The agent remains strictly read-only and diagnostic; automated endpoint changes (e.g. resetting Wi-Fi adapter or changing DNS) are out of scope.
4. **Native Go Agent Compilation:** The Python modular probe serves as the primary implementation; a Go native port is deferred until enterprise fleet scale (>5,000 laptops) warrants it.
