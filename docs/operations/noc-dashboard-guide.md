# Nawari NOC Dashboard Operator's Guide

**Scope:** Unified Grafana Dashboards for Kenya Airways Global Operations  
**Dashboards Provisioning Root:** `docker/grafana/dashboards/`  
**Operational Folders:**
- `Nawari / Network Observability` (`folderUid: nawari-network-obs`, directory: `network_observability/`) — 13 dashboards
- `Nawari / Communication Observability` (`folderUid: nawari-comm-obs`, directory: `communication_observability/`) — 4 dashboards
**Container Host:** `mon-grafana01` (Grafana port 3000)  
**Security Tier:** Multi-Site Scoped RBAC Enabled  
**Telemetry Integrity Standard:** Phase 13.1 (100% hover descriptions, zero null-as-zero coercion, signaling vs media separation)

---

## 1. Operational Domain Structure & Telemetry Integrity

Nawari enforces strict separation of operational domains into two provisioned Grafana folders:

### 1.1 Nawari / Network Observability (`nawari-network-obs`)
Dedicated to physical network topology, core switch and router telemetry, interface utilization, WAN circuits, outstation edge collectors, multi-dimensional business service SLIs, incident operations, and automated remediation playbooks.

### 1.2 Nawari / Communication Observability (`nawari-comm-obs`)
Dedicated to Avaya Aura Communication Manager (CM 8.1.0), Avaya Session Border Controllers (SBCE 8.1), Session Manager, carrier SIP trunks, call signaling ladders, and voice media quality diagnostics.

### 1.3 Telemetry Integrity Rules
1. **Mandatory Hover Tooltips:** Every visualization panel (134 total across all 17 dashboards) provides an operational description detailing its meaning, units, underlying datasource/OID, and limitations.
2. **Signaling Reachability $\neq$ Media Quality:** A green SIP OPTIONS response or registered trunk confirms only layer-5 signaling reachability. It does NOT guarantee acceptable voice audio quality, low jitter, or absence of packet loss.
3. **Synthetic Probe Isolation:** All synthetic Asterisk test calls are visibly labeled `[SYNTHETIC — ASTERISK]`. Operators must not conflate synthetic probe performance with live subscriber calls.
4. **Honest Real-Call MOS Status:** Real-call MOS is explicitly displayed as `[NOT INSTRUMENTED — RTCP XR REQUIRED]` until RFC 3611 Block 7 telemetry is provisioned. Nawari never substitutes synthetic values or decorative gauges for real customer calls.
5. **Avaya CM MIB Polling Constraints:** Avaya CM IP voice stats tables (`avCmMeasIpVoStatSumDataLstHrTable` and `avCmMeasIpVoStatHrJitterTable`) are polled at $\ge 1\text{ hour}$ intervals to protect CM call-processing CPU.
6. **Null Preservation:** Missing data is displayed as gaps (`spanNulls: False`). Null values are never coerced to zero.

Complete machine-readable and human-readable inventories are maintained in:
- `docs/observability/dashboard-metric-catalogue.yaml`
- `docs/observability/dashboard-inventory.md`

---

## 2. Overview of the Enterprise NOC Suite

The 17 dashboards across both domains give the Network Operations Centre (NOC), Station Duty Engineers, and Executive Leadership complete visibility across global flight operations, telecom trunks, WAN outstations, and business applications.

| Domain | Dashboard Title | File Name | Primary Audience | Core Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Network** | **Enterprise Global Overview** | `nawari_enterprise_overview.json` | CIO, Head of IT, Central NOC Leads | Enterprise SLA compliance, global outstation status map, degraded mission-critical services, active P1/P2 incidents. |
| **Network** | **Global Outstation Directory** | `nawari_global_outstations.json` | Regional Managers, Station Duty Engineers, NetOps | Station tiering, primary/secondary circuit health, facility status, IATA/ICAO code tracking, RTT & bandwidth telemetry. |
| **Network** | **Business Service Catalog & SLA** | `nawari_service_catalog_sla.json` | Service Owners, Airport Duty Managers, IT Leadership | Multi-dimensional SLIs (Availability, Performance, Quality, Coverage), Error Budget burn rates, contractual SLA breaches. |
| **Network** | **Incident Operations Center** | `nawari_incident_operations.json` | NOC Shift Engineers, Incident Commanders | Incident lifecycle state (NEW $\rightarrow$ CLOSED), MTTA/MTTR metrics, escalation queue, notification dead letters. |
| **Network** | **Edge Fleet & Spool Management** | `nawari_edge_fleet.json` | Edge Engineers, Systems Administrators | SQLite spool buffer sizes, priority pruning rates, replayed telemetry volume, clock drift, transmitter backoff status. |
| **Network** | **Network Infrastructure Overview** | `network_infrastructure_overview.json` | NOC Engineers | Core switch SNMP status, system uptime, ICMP latency, physical/logical interface inventory, active network alarms. |
| **Network** | **Interface Traffic & Performance** | `interface_traffic_health.json` | NetOps Engineers | Interface operational/admin status, speed, ingress/egress bps, CRC error rates, packet discard rates. |
| **Network** | **Network Path & Hop Analysis** | `network_path_analysis.json` | NetOps, Troubleshooting Leads | Directional traceroute hop analysis, end-to-end latency/loss, routing shifts, bufferbloat detection. |
| **Network** | **Enterprise Network Topology** | `network_topology.json` | NetOps, Architecture | Interactive Layer 2/3 topology graph, device dependencies, link capacities. |
| **Network** | **Endpoint Fleet Observability** | `endpoint_fleet_overview.json` | Desktop Support, Systems | Enrolled vs active endpoints, OS versions, gateway latency, Wi-Fi link quality distribution. |
| **Network** | **Endpoint Deep-Dive** | `endpoint_detail.json` | Tier 2/3 Desktop Support | Single-endpoint host identity, adapter state, packet loss, local process health, network route diagnostics. |
| **Network** | **Controlled Operations & Actions** | `nawari_controlled_operations.json` | Incident Commanders, SRE | Remediation action lifecycle, approval token audits, dead-man circuit breaker, rollback history. |
| **Network** | **Predictive Intelligence & Baselines** | `nawari_predictive_intelligence.json` | Capacity Planners, Advanced Ops | Diurnal baseline deviations (|Z| >= 3.0), Time-to-Exhaustion (TTE) projections, carrier trunk latency drift. |
| **Comm** | **Avaya SBCE Operational Health** | `avaya_sbce_operational_health.json` | Voice Engineers, Telecom Leads | SBCE 8.1 appliance health (CPU/RAM/Disk/Load), interface status (A1/B1/M1/M2), voice path errors/discards. |
| **Comm** | **Voice Service Assurance & Quality** | `nawari-voice-service-assurance.json` | Voice Operations | Synthetic voice probe outcomes, ITU-T G.107 MOS/R-factor, setup latency trends, SBCE throughput. |
| **Comm** | **Communications Intelligence** | `nawari_voice_intelligence.json` | Voice Engineers, Telecom NOC | SIP signaling latencies (PDD/TTA/Setup), SIP trunk registration, real vs synthetic voice separation, Avaya CM SNMP real-call loss/jitter, uninstrumented real MOS status. |
| **Comm** | **Cross-Domain Voice & Endpoint** | `endpoint_voice_correlation.json` | Cross-Domain Escalation Teams | Correlation between endpoint Wi-Fi/NIC quality and voice audio jitter, gateway latency vs MOS. |

---

## 2. Dashboard Breakdown & Key Panels

### 2.1 Enterprise Global Overview (`nawari_enterprise_overview.json`)
- **Global Fleet Availability Gauge:** Real-time percentage of online outstations ($T_{\text{active}} / T_{\text{total}} \times 100$).
- **Active P1 / P2 Incident Counter:** Direct integration with `IncidentManager` showing unmitigated production disruptions.
- **Mission-Critical Services Status Table:** Live health index (0.0 to 1.0) and status (`HEALTHY`, `DEGRADED`, `CRITICAL_DOWN`) for Departure Control System (DCS), Flight Ops, and Baggage Sortation.
- **Top Outstations at Risk:** Ranked list of stations operating on degraded redundancy (e.g. secondary circuit active, primary failed).
- **Global Stations Status Map:** Geospatial visualization of all 54 Kenya Airways domestic, regional, and intercontinental stations.

### 2.2 Global Outstation Directory (`nawari_global_outstations.json`)
- **Station Search & Scope Selector:** Multi-variable dropdown filter by Region (`DOMESTIC`, `AFRICA_REGIONAL`, `EUROPE`, `MIDDLE_EAST_ASIA`), Country, and Station IATA (`NBO`, `MBA`, `KIS`, `LHR`, etc.).
- **Station Infrastructure Breakdown:** Counts of WAN circuits, local facilities, edge switches, and PBX/voice gateways.
- **Circuit Diversity Table:** Details on provider (Safaricom, Airtel, Liquid, Orange, BT), bandwidth capacity, current status, and measured latency vs SLA target.
- **PSTN Breakout Architecture:** Visual tag displaying whether station uses `CENTRAL_SIP_BACKHAUL`, `LOCAL_ISDN_PRI`, `LOCAL_SIP_TRUNK`, or `HYBRID`.

### 2.3 Business Service Catalog & SLA Assurance (`nawari_service_catalog_sla.json`)
- **Multi-Dimensional SLI Matrix:**
  - *Availability SLI:* Percentage of operational time service was usable.
  - *Performance SLI:* Percentage of transactions meeting latency thresholds ($< 250\text{ ms}$).
  - *Quality SLI:* Composite weighted user-experience index.
  - *Telemetry Coverage:* Percentage of intervals with verified fresh telemetry (guards against false 100% availability during probe outages).
- **Error Budget Consumption Rate:** Burn rate gauges showing 30-day budget velocity.
- **Dependency Drilldown Graph:** Real-time evaluation showing which underlying component (e.g. `CIR-MBA-01`, `SW-DC1-01`) caused a service degradation.

### 2.4 Incident Operations Center (`nawari_incident_operations.json`)
- **Live Incident Kanban:** Real-time view of incidents partitioned by lifecycle stage:
  $$\text{NEW} \longrightarrow \text{CORRELATED} \longrightarrow \text{INVESTIGATING} \longrightarrow \text{REMEDIATING} \longrightarrow \text{RESOLVED} \longrightarrow \text{CLOSED}$$
- **Mean Time to Acknowledge (MTTA) & Resolve (MTTR):** Rolling 24-hour and 7-day operational velocity.
- **Suppression Statistics:** Counts of secondary alerts suppressed by topology correlation (parent down) or scheduled maintenance windows.
- **Dead Letter Queue (DLQ) Monitor:** Alert notifications that failed SMS/Email carrier delivery and require manual NOC dispatch.

### 2.5 Edge Fleet & Spool Management (`nawari_edge_fleet.json`)
- **Fleet Spool Depth:** Megabytes used per edge appliance against the 50 MB hard budget ceiling.
- **Pruning Activity Log:** Real-time tracking of diagnostic telemetry drops during extended WAN outages.
- **Clock Drift Offset Monitor:** Milliseconds delta between edge node local clocks and central NTP server (`time.kenya-airways.com`).
- **Telemetry Ingestion Segregation:** Time-series showing ratio of Live Ingestion vs Replayed Ingestion arriving at JKIA Hub.

---

## 3. NOC Operating Procedures for Alerts & Dashboards

1. **Investigating Degraded Service Health:**
   - If `nawari_enterprise_overview` indicates a service is `DEGRADED`, open `nawari_service_catalog_sla`.
   - Review the *Dependency Evidence* panel. If a mandatory component is `DOWN`, note the `station_id` and open `nawari_incident_operations`.
2. **Handling WAN Outages:**
   - When a station transitions to single-circuit operation, verify that secondary circuit traffic is flowing.
   - If both circuits are down, confirm that edge spool depth on `nawari_edge_fleet` is increasing and not overflowing.
3. **Closing Incidents:**
   - Do NOT mark an incident resolved based on replayed telemetry. Verify that 3 consecutive live healthy observations appear in the recovery panel.
