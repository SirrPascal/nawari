# Nawari Enterprise Observability — Operational Dashboard & Metric Catalogue

**Generated:** `2026-11-08T11:29:24.171093+00:00`  
**Standard:** Nawari Phase 13.1 Telemetry Integrity & Operational Separation  
**Target Environment:** Kenya Airways Ground Network & Global Outstation Fleet  

---

## 1. Executive Architecture Summary

Nawari structures its operational telemetry into two top-level Grafana domain folders, eliminating ambiguity between physical transport infrastructure and real-time voice communications:

1. **`Nawari / Network Observability`** (`folderUid: nawari-network-obs`):
   - Dedicated to physical switches, routers, WAN circuits, outstation edge collectors, interface performance, BGP routing, packet loss, DNS, and automated remediation lifecycle.
   - Contains **13 dashboards**.
2. **`Nawari / Communication Observability`** (`folderUid: nawari-comm-obs`):
   - Dedicated to Avaya Aura Communication Manager, Session Border Controllers (SBCE 8.1), Session Manager, carrier SIP trunks, call signaling ladders, and voice media quality.
   - Contains **11 dashboards**.

### Telemetry Integrity Enforcements
- **Hover Descriptions:** 100% of visualization panels feature comprehensive hover descriptions detailing operational meaning, units, data source, and known bounds.
- **Signaling vs Media Separation:** SIP trunk registration and SIP OPTIONS reachability prove signaling path connectivity only. They are never conflated with voice audio quality.
- **Synthetic Probe Isolation:** Synthetic Asterisk probes are strictly labeled with `[SYNTHETIC — ASTERISK]` to prevent operators from mistaking test traffic for real passenger/agent calls.
- **Honest Real-Call MOS:** Real-call MOS is explicitly presented as `[NOT INSTRUMENTED — RTCP XR REQUIRED]` until genuine RFC 3611 Block 7 telemetry is provisioned. No decorative gauges or fabricated values are permitted.
- **Avaya CM MIB Safety:** Avaya Communication Manager IP voice statistics (`avCmMeasIpVoStatSumDataLstHrTable` and `avCmMeasIpVoStatHrJitterTable`) are polled at 1-hour intervals to protect CM call-processing CPU.
- **Null Handling:** Missing data is rendered as null/gaps (`spanNulls: False`). Null-to-zero conversion is strictly prohibited.

---

## 2. Domain & Dashboard Inventory

### Domain: Network Observability
- **Grafana Folder:** `Nawari / Network Observability` (`nawari-network-obs`)
- **Dashboard Count:** 13

| Dashboard Title | UID | Visualization Panels | Key Focus |
| :--- | :--- | :---: | :--- |
| **Nawari — Endpoint Deep-Dive & Edge Experience** | `nawari-endpoint-detail` | 17 | Displays the agent version, hostname, and operating system build of the selected... |
| **Nawari — Endpoint Fleet Observability Overview** | `nawari-endpoint-fleet` | 13 | Measures the total inventory count of enrolled endpoint probe hosts discovered i... |
| **Nawari — Interface Traffic & Performance Health** | `nawari-interface-health` | 6 | Current operational state of the selected network interface. Values: Up (1) or D... |
| **Nawari — Controlled Operational Actions & Automated Remediation** | `nawari-controlled-operations` | 5 | Distribution of operational remediation actions across the execution lifecycle. ... |
| **Nawari — Distributed Edge Collector Fleet & Spool Storage** | `nawari-edge-fleet` | 4 | Total count of active and communicating edge collector instances across outstati... |
| **Nawari — Enterprise Executive Overview & Fleet Availability** | `nawari-enterprise-overview` | 5 | Overall proportion of Kenya Airways flight operations stations currently online ... |
| **Nawari — Global Outstation Network & WAN Telemetry** | `nawari-global-outstations` | 6 | Real-time circuit operational status across Kenya Airways core hub, domestic sta... |
| **Nawari — Incident Operations, Escalation & Verified Recovery** | `nawari-incident-operations` | 3 | Distribution of active incidents across lifecycle stages. Missing data indicates... |
| **Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance** | `nawari-predictive-intelligence` | 6 | Real-time count of active statistical deviations across domains evaluated agains... |
| **Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance** | `nawari-service-catalog-sla` | 6 | Availability SLI for Departure Control System (Amadeus Altea Core, Airport Check... |
| **Nawari — Network Infrastructure Overview** | `nawari-net-overview` | 6 | SNMP reachability status of Kenya Airways core distribution and datacenter switc... |
| **Nawari — Network Path & Directional Hop Analysis** | `nawari-path-analysis` | 8 | Measures the total round-trip time between the endpoint and the destination targ... |
| **Nawari — Network Topology & Service Dependencies** | `nawari-network-topology` | 2 | Interactive Layer 2 and Layer 3 topological graph displaying confirmed switches,... |

### Domain: Communication Observability
- **Grafana Folder:** `Nawari / Communication Observability` (`nawari-comm-obs`)
- **Dashboard Count:** 11

| Dashboard Title | UID | Visualization Panels | Key Focus |
| :--- | :--- | :---: | :--- |
| **Nawari — Avaya Call Management System (CMS) & Contact Centre Performance** | `nawari-cms-contact-centre` | 9 | Processor core utilization on the Avaya Call Management System (CMS) server host... |
| **Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance** | `nawari-communication-manager` | 11 | ICMP ping network reachability to the Avaya Communication Manager processor inte... |
| **Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health** | `nawari-g450-gateway` | 8 | Operating time of the Avaya G450 chassis processor since last reload or power cy... |
| **Nawari — Avaya SBCE Operational Health** | `nawari-sbce-health` | 15 | Operational status of the SNMPv3 monitoring agent on the Avaya Session Border Co... |
| **Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing** | `nawari-session-manager` | 9 | Processor core utilization on the Avaya Aura Session Manager appliance. Units: P... |
| **Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation** | `nawari-voice-correlation` | 9 | Architectural guidelines defining the separation between network transport and v... |
| **Nawari — Voice Service Assurance & Media Quality** | `nawari-voice-service-assurance` | 12 | Signaling outcome of the most recent synthetic voice test call (e.g., Completed ... |
| **Nawari — Enterprise Communication Services Overview & Executive Service Assurance** | `nawari-comm-overview` | 12 | Composite availability grid across all core enterprise telephony platforms: Avay... |
| **Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing** | `nawari-sip-trunks` | 7 | Operational registration state of the primary Safaricom SIP trunk terminating on... |
| **Nawari — Communications Intelligence & Voice Service Assurance** | `nawari-voice-intelligence` | 11 | Post-Dial Delay (PDD: INVITE to 18x), Time to Alerting (TTA: INVITE to 180 Ringi... |
| **Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health** | `nawari-recording-wfo` | 10 | Product specification and boundary requirements: WFO is an enterprise product ca... |

---

## 3. Detailed Metric Catalogue by Domain and Dashboard

### Nawari — Endpoint Deep-Dive & Edge Experience
- **UID:** `nawari-endpoint-detail`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/endpoint_detail.json`
- **Visualization Panels:** 17

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Agent Info & Host Identity** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Active Interface** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Authoritative Provenance** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Default Gateway RTT Latency** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 7 | **Default Gateway Packet Loss** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 9 | **Wi-Fi RSSI Gauge** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `dBm` | < 30 seconds |
| 10 | **Wi-Fi RSSI History** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `dBm` | < 30 seconds |
| 11 | **Wi-Fi Link Quality Gauge** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 12 | **Wi-Fi Link Quality History** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 14 | **DNS Query Resolution Time by Target** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 15 | **DNS Target RCODE / Status** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 17 | **Service Target Reachability** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 18 | **TCP 3-Way Handshake Latency** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 19 | **TLS Cryptographic Handshake Time** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 20 | **HTTP Time To First Byte (TTFB)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 22 | **Path Analysis Navigation** | `text` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 23 | **Voice Assurance Navigation** | `text` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Endpoint Fleet Observability Overview
- **UID:** `nawari-endpoint-fleet`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/endpoint_fleet_overview.json`
- **Visualization Panels:** 13

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Total Enrolled Endpoints** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Active Reporting Endpoints** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Degraded Edge Endpoints** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 5 | **Stale Endpoints (>15m SLA)** | `stat` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `short` | < 60 seconds |
| 7 | **Active Primary Interface Distribution** | `piechart` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 8 | **Telemetric Environment Provenance** | `piechart` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 10 | **Fleet Default Gateway Latency** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 11 | **Fleet Default Gateway Packet Loss** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 13 | **Voice Gateway (5061/tcp) Reachability** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 14 | **DNS Resolution Latency** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 15 | **Corporate HTTP Services TTFB** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 17 | **Discovered Endpoints Inventory & Operational Status** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 19 | **Endpoint Active Problem Alarms (Gateway Loss, High RTT, Stale Telemetry)** | `alexanderzobnin-zabbix-problems-panel` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Interface Traffic & Performance Health
- **UID:** `nawari-interface-health`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/interface_traffic_health.json`
- **Visualization Panels:** 6

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Interface Operational Status** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Configured Interface Speed** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `bps` | < 30 seconds |
| 4 | **Administrative State** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Bandwidth Ingress / Egress (bits/sec)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `bps` | < 30 seconds |
| 8 | **Packet Error Rates (in/out errors/sec)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `err/s` | < 30 seconds |
| 9 | **Packet Discard Rates (in/out pps)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `pps` | < 30 seconds |

### Nawari — Controlled Operational Actions & Automated Remediation
- **UID:** `nawari-controlled-operations`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_controlled_operations.json`
- **Visualization Panels:** 5

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Action Execution Lifecycle Distribution** | `bargauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Operational Dead-Man Circuit Breaker Status** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 5 | **Pending Operator Approvals & Blast-Radius Risk Board** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 7 | **Pre- vs Post-Remediation Service Health Verification** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 8 | **Cryptographically Chained Immutable Audit Stream (SHA-256)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Distributed Edge Collector Fleet & Spool Storage
- **UID:** `nawari-edge-fleet`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_edge_fleet.json`
- **Visualization Panels:** 4

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Active Edge Collectors** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Max Outstation Clock Drift** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `ms` | < 30 seconds |
| 4 | **Fleet Total Spool Backlog** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Outstation Spool Storage & Replay Queue Matrix** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Enterprise Executive Overview & Fleet Availability
- **UID:** `nawari-enterprise-overview`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_enterprise_overview.json`
- **Visualization Panels:** 5

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Global Station Availability** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 3 | **Active P1 / P2 Incidents** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Service Tier Health Summary** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Regional Health Index Trends** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 7 | **Notification Channel Health & DLQ Backlog** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Global Outstation Network & WAN Telemetry
- **UID:** `nawari-global-outstations`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_global_outstations.json`
- **Visualization Panels:** 6

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Outstation WAN Circuit Status Matrix (Primary & Secondary)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Trans-WAN Round-Trip Latency (JKIA Hub to Outstations)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `ms` | < 30 seconds |
| 5 | **Voice Quality Listening MOS by Station** | `gauge` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 6 | **Trans-WAN Voice Packet Jitter Trends** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `ms` | < 30 seconds |
| 8 | **Buffered Spool Queue Depth by Station (Offline Records)** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 9 | **Post-Restoration Spool Drain & Replay Velocity** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Incident Operations, Escalation & Verified Recovery
- **UID:** `nawari-incident-operations`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_incident_operations.json`
- **Visualization Panels:** 3

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Incidents by Lifecycle State** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Max Unacknowledged Incident Age (SLA 15m)** | `stat` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `m` | < 60 seconds |
| 5 | **Active Recovery Verification Pipelines (Consecutive Healthy Chains)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance
- **UID:** `nawari-predictive-intelligence`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_predictive_intelligence.json`
- **Visualization Panels:** 6

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Active Multi-Domain Statistical Anomalies** | `bargauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Time-to-Exhaustion (TTE) Horizon (Safe Capacity Limit)** | `bargauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `h` | < 30 seconds |
| 5 | **Dynamic Baseline Bands vs Real-Time Metric Telemetry** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Voice MOS Degradation Trajectory & Predictive Horizon** | `timeseries` | `PREDICTIVE_STATISTICAL` | Nawari Predictive Intelligence & Diurnal Base | `none` | < 60 seconds |
| 8 | **Top Evidence-Ranked Hypotheses (Supporting vs Contradicting)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 9 | **Carrier Trunk Signaling Drift (Post-Dial Delay)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `ms` | < 30 seconds |

### Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance
- **UID:** `nawari-service-catalog-sla`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/nawari_service_catalog_sla.json`
- **Visualization Panels:** 6

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Departure Control System (DCS Core) Availability SLI** | `gauge` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `percent` | < 60 seconds |
| 3 | **Flight Operations & Dispatch Availability SLI** | `gauge` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `percent` | < 60 seconds |
| 4 | **Air-to-Ground & Ramp Voice Availability SLI** | `gauge` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `percent` | < 60 seconds |
| 6 | **Error Budget Burn Rate (1x = Budget Normal, > 2x = Paging Alert)** | `timeseries` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `short` | < 60 seconds |
| 7 | **Remaining Error Budget Minutes (Tier 1: 21.6 mins / month max downtime)** | `stat` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `m` | < 60 seconds |
| 9 | **Active Business Service Incidents Stream** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Network Infrastructure Overview
- **UID:** `nawari-net-overview`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/network_infrastructure_overview.json`
- **Visualization Panels:** 6

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Core Switch SNMP Status** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **System Uptime** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 4 | **ICMP Latency** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 5 | **Active Network Problems** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 7 | **Discovered Physical & Logical Interfaces (mock-core-switch-01)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 9 | **Live Network Alert Feed (Zabbix Problems)** | `alexanderzobnin-zabbix-problems-panel` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Network Path & Directional Hop Analysis
- **UID:** `nawari-path-analysis`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/network_path_analysis.json`
- **Visualization Panels:** 8

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **End-to-End Latency** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 3 | **End-to-End Packet Loss** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 4 | **Total Path Hops** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 5 | **Path Route Stability** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 7 | **CoPP Guard Architectural Interpretation** | `text` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 9 | **Discovered Hop Details (IP, RTT, Packet Loss, CoPP Status)** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 11 | **Hop Latency Progression Waterfall (Detecting >40ms Latency Jumps)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 13 | **Route Divergence History (Path Signature Hash Transitions)** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Network Topology & Service Dependencies
- **UID:** `nawari-network-topology`
- **Domain:** `Network Observability` (`Nawari / Network Observability`)
- **Path:** `docker/grafana/dashboards/network_observability/network_topology.json`
- **Visualization Panels:** 2

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Enterprise Network Topology (Node Graph)** | `nodeGraph` | `CORRELATED_ANALYTICS` | Nawari Unified Analytics & Correlation Engine | `short` | < 15 seconds |
| 4 | **Topology Change Audit Log** | `table` | `CORRELATED_ANALYTICS` | Nawari Unified Analytics & Correlation Engine | `short` | < 15 seconds |

### Nawari — Avaya Call Management System (CMS) & Contact Centre Performance
- **UID:** `nawari-cms-contact-centre`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/avaya_cms_contact_centre.json`
- **Visualization Panels:** 9

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **CMS Host CPU Utilization [REAL — HARDWARE]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 3 | **Informix Database Engine Status [APPLICATION — CMS]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **CMS Archiving Interval Configuration [APPLICATION — CMS]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 6 | **Service Level Attainment (% in SLA) [APPLICATION — CMS]** | `gauge` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `percent` | < 60 seconds |
| 7 | **Average Speed of Answer (ASA, sec) [APPLICATION — CMS]** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 8 | **Calls Waiting in Queue [APPLICATION — CMS]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `calls` | < 30 seconds |
| 9 | **Oldest Call Waiting (sec) [APPLICATION — CMS]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 11 | **Calls Offered vs Answered vs Abandoned [APPLICATION — CMS]** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `calls` | < 30 seconds |
| 12 | **Skill Group & Split Performance Breakdown [APPLICATION — CMS]** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance
- **UID:** `nawari-communication-manager`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/avaya_communication_manager.json`
- **Visualization Panels:** 11

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **CM Processor Reachability [REAL — ZABBIX]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Active Telephony Alarms (Hourly Scan) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `alarms` | 1–2 hours (CM internal hourly measurement bucket) |
| 4 | **Call Processing Hourly Status [REAL — AVAYA SNMP]** | `timeseries` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `calls` | 1–2 hours (CM internal hourly measurement bucket) |
| 5 | **Call Rate Completed Calls (Hourly Measurement) [REAL — AVAYA SNMP]** | `timeseries` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `calls` | 1–2 hours (CM internal hourly measurement bucket) |
| 7 | **Real-Call Packet Loss % (Last Hour) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `percent` | 1–2 hours (CM internal hourly measurement bucket) |
| 8 | **Real-Call Peak Jitter (Last Hour) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `ms` | 1–2 hours (CM internal hourly measurement bucket) |
| 9 | **Real-Call Peak Delay (Last Hour) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `ms` | 1–2 hours (CM internal hourly measurement bucket) |
| 10 | **Hourly Average Jitter [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `ms` | 1–2 hours (CM internal hourly measurement bucket) |
| 12 | **Negotiated Audio Codec [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `short` | 1–2 hours (CM internal hourly measurement bucket) |
| 13 | **Echo Cancellation Status [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `short` | 1–2 hours (CM internal hourly measurement bucket) |
| 14 | **Evaluated Calls Count in Last Hour [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `calls` | 1–2 hours (CM internal hourly measurement bucket) |

### Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health
- **UID:** `nawari-g450-gateway`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/avaya_g450_media_gateway.json`
- **Visualization Panels:** 8

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **G450 System Uptime [REAL — HARDWARE]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 3 | **CM Gateway Registration [CONFIGURED — G450 MGP]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Chassis Thermal State [EVENT TRAP — G450 MGP]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 5 | **Power Supply Status (PSU 1 & 2) [CONFIGURED — EVENT TRAP]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 7 | **E1 / ISDN PRI Physical Trunk State [CONFIGURED — IF-MIB]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 8 | **DSP Media Resource Channels [NOT COLLECTED — REQUIRES AUDIT]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 9 | **Chassis Fan Tray Operational State [CONFIGURED — EVENT TRAP]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 11 | **Installed Media Module Slot Inventory (V1-V8) [REAL — HARDWARE]** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Avaya SBCE Operational Health
- **UID:** `nawari-sbce-health`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/avaya_sbce_operational_health.json`
- **Visualization Panels:** 15

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **SNMPv3 Status** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 3 | **System Uptime** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `s` | < 30 seconds |
| 4 | **CPU Utilization** | `gauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `percent` | < 30 seconds |
| 5 | **RAM Utilization** | `gauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `percent` | < 30 seconds |
| 6 | **Root Disk Utilization** | `gauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `percent` | < 30 seconds |
| 7 | **Load Average (1m)** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 9 | **A1 — External DMZ (SIP Signaling)** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 10 | **B1 — Internal Media & Core Signaling** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 11 | **M1 — Primary Management** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 12 | **M2 — Secondary / HA Heartbeat** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 14 | **A1 Carrier DMZ Traffic (bps)** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `bps` | < 30 seconds |
| 15 | **B1 Internal Media & Core Signaling Traffic (bps)** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `bps` | < 30 seconds |
| 17 | **Voice Path Packet Errors (rate)** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `pps` | < 30 seconds |
| 18 | **Voice Path Packet Discards (rate)** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `pps` | < 30 seconds |
| 19 | **Avaya SBCE Active Alarms & Problems Feed** | `alexanderzobnin-zabbix-problems-panel` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |

### Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing
- **UID:** `nawari-session-manager`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/avaya_session_manager.json`
- **Visualization Panels:** 9

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **SM Host CPU Utilization [REAL — HARDWARE]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 3 | **SM Host RAM Utilization [REAL — HARDWARE]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 4 | **SM System Uptime [REAL — HARDWARE]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 5 | **TCP Established Sockets [REAL — HARDWARE]** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `sockets` | < 30 seconds |
| 7 | **SIP Entity State — Avaya CM [CONFIGURED — ASM API/CLI]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 8 | **SIP Entity State — Avaya SBCE [CONFIGURED — ASM API/CLI]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 9 | **SIP OPTIONS Heartbeat Response Time [NAWARI SIP PROBE]** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `ms` | < 30 seconds |
| 11 | **Configured SIP Entity Topology & Link Status [CONFIGURED — ASM MODEL]** | `table` | `CORRELATED_ANALYTICS` | Nawari Unified Analytics & Correlation Engine | `short` | < 15 seconds |
| 12 | **Session Manager Active Alarms [EVENT TRAP — AV-TRAP-MIB]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `alarms` | < 30 seconds |

### Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation
- **UID:** `nawari-voice-correlation`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/endpoint_voice_correlation.json`
- **Visualization Panels:** 9

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Voice Observability Domain Boundary** | `text` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Voice Call Outcome** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 5 | **Estimated MOS Score** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 6 | **SBCE Port 5061 L4 Transport Socket** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 7 | **Endpoint Gateway Loss** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 9 | **Dual-Axis Correlation: Gateway Edge Latency vs Voice MOS** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `s` | < 60 seconds (Probe Cycle Interval) |
| 11 | **Cross-Domain Packet Loss: Edge vs Path vs Voice Audio Stream** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `percent` | < 60 seconds (Probe Cycle Interval) |
| 13 | **Wi-Fi Quality vs Audio RTCP Jitter** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `percent` | < 60 seconds (Probe Cycle Interval) |
| 14 | **Avaya SBCE Active Audio Calls** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `none` | < 30 seconds |

### Nawari — Voice Service Assurance & Media Quality
- **UID:** `nawari-voice-service-assurance`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/nawari-voice-service-assurance.json`
- **Visualization Panels:** 12

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Call Transaction Outcome** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 3 | **Estimated MOS (ITU-T G.107) [SYNTHETIC — ASTERISK]** | `gauge` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 4 | **Media Path Directionality** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 5 | **Call Setup Latency** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `ms` | < 60 seconds (Probe Cycle Interval) |
| 6 | **R-Factor (Transmission Quality) [SYNTHETIC — ASTERISK]** | `gauge` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 16 | **Telemetry Provenance Mode** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 8 | **Call Setup Latency History** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `ms` | < 60 seconds (Probe Cycle Interval) |
| 9 | **SIP Response Code History** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 11 | **Estimated MOS Trend & SLA Thresholds [SYNTHETIC — ASTERISK]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 12 | **RTP Jitter & Packet Loss Impairments [SYNTHETIC — ASTERISK]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 14 | **SBCE Signaling (A1) & Media (B1) Traffic Throughput [REAL — SBCE SNMP]** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `bps` | < 30 seconds |
| 15 | **SBCE CPU Utilization [REAL — SBCE SNMP]** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `percent` | < 30 seconds |

### Nawari — Enterprise Communication Services Overview & Executive Service Assurance
- **UID:** `nawari-comm-overview`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/nawari_communication_overview.json`
- **Visualization Panels:** 12

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Avaya Core Telephony Platform Availability Grid [REAL — ZABBIX]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 3 | **Active Telephony Alarms (CM & SM) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `alarms` | 1–2 hours (CM internal hourly measurement bucket) |
| 5 | **Active SIP Calls on Perimeter SBCE [REAL — SBCE SNMP]** | `gauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `calls` | < 30 seconds |
| 6 | **Carrier SIP Trunk Registration Status [REAL — ZABBIX]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 7 | **5-Minute Call Processing Rate (CM) [REAL — AVAYA SNMP]** | `timeseries` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `calls` | 1–2 hours (CM internal hourly measurement bucket) |
| 9 | **Contact Centre Service Level (% in SLA) [APPLICATION — CMS]** | `gauge` | `SERVICE_ASSURANCE_SLI` | Nawari Business Service SLI Engine (13B Stand | `percent` | < 60 seconds |
| 10 | **Queue Depth & Oldest Waiting Call [APPLICATION — CMS]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 11 | **Agent Staffing State Distribution [APPLICATION — CMS]** | `piechart` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 13 | **Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]** | `stat` | `NOT_INSTRUMENTED` | None — Telemetry Not Instrumented (Requires R | `short` | N/A (Uninstrumented) |
| 14 | **Real-Call Packet Loss % (CM Last Hour) [REAL — AVAYA SNMP]** | `stat` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `percent` | 1–2 hours (CM internal hourly measurement bucket) |
| 15 | **Synthetic Voice MOS [SYNTHETIC — ASTERISK]** | `gauge` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 16 | **Voice Telemetry Source Freshness & Instrumentation Inventory [AUDIT]** | `table` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |

### Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing
- **UID:** `nawari-sip-trunks`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/nawari_sip_trunks_signaling.json`
- **Visualization Panels:** 7

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Safaricom Primary SIP Trunk [REAL — ZABBIX]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 3 | **Airtel Secondary SIP Trunk [REAL — ZABBIX]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 4 | **Carrier SIP OPTIONS Round-Trip Latency [REAL — ZABBIX]** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `ms` | < 30 seconds |
| 6 | **Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `ms` | < 60 seconds (Probe Cycle Interval) |
| 7 | **SIP Response Distribution (Station vs Trunk Outage) [SYNTHETIC — ASTERISK PROBE]** | `piechart` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 9 | **A1 Carrier DMZ Bandwidth (bps) [REAL — SBCE SNMP]** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `bps` | < 30 seconds |
| 10 | **Carrier Interface Packet Errors (Errors/sec) [REAL — SBCE SNMP]** | `timeseries` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `errors/s` | < 30 seconds |

### Nawari — Communications Intelligence & Voice Service Assurance
- **UID:** `nawari-voice-intelligence`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/nawari_voice_intelligence.json`
- **Visualization Panels:** 11

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `ms` | < 60 seconds (Probe Cycle Interval) |
| 3 | **SIP Response Distribution (Station vs Trunk) [SYNTHETIC — ASTERISK PROBE]** | `piechart` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `short` | < 60 seconds (Probe Cycle Interval) |
| 11 | **SIP Trunk Registration Status [REAL — ZABBIX]** | `stat` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 14 | **Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]** | `stat` | `NOT_INSTRUMENTED` | None — Telemetry Not Instrumented (Requires R | `short` | N/A (Uninstrumented) |
| 9 | **Synthetic Voice Quality Index (MOS) [SYNTHETIC — ASTERISK]** | `stat` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `none` | < 60 seconds (Probe Cycle Interval) |
| 12 | **Real-Call Packet Loss (CM SNMP) [REAL — AVAYA SNMP]** | `timeseries` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `percent` | 1–2 hours (CM internal hourly measurement bucket) |
| 13 | **Real-Call Peak Jitter & Delay [REAL — AVAYA SNMP]** | `timeseries` | `REAL_AVAYA_SNMP` | Avaya Communication Manager 8.1.0 MIB (avCmMe | `ms` | 1–2 hours (CM internal hourly measurement bucket) |
| 5 | **Network Packet Loss vs Jitter Buffer Discards [SYNTHETIC — ASTERISK]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `percent` | < 60 seconds (Probe Cycle Interval) |
| 6 | **Mouth-to-Ear Voice Latency (RTT) [SYNTHETIC — ASTERISK]** | `timeseries` | `SYNTHETIC_PROBE` | Synthetic Asterisk Call Engine (AMI / RTCP Te | `ms` | < 60 seconds (Probe Cycle Interval) |
| 8 | **SBCE Active Concurrent Sessions (Max 500) [REAL — SBCE SNMP]** | `gauge` | `REAL_SBCE_SNMP` | Avaya SBCE 8.1 SNMPv3 Agent (IF-MIB / HOST-RE | `short` | < 30 seconds |
| 10 | **Recent Correlated Voice Call Sessions [CORRELATED PROBES]** | `table` | `CORRELATED_ANALYTICS` | Nawari Unified Analytics & Correlation Engine | `short` | < 15 seconds |

### Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health
- **UID:** `nawari-recording-wfo`
- **Domain:** `Communication Observability` (`Nawari / Communication Observability`)
- **Path:** `docker/grafana/dashboards/communication_observability/recording_wfo_operational_health.json`
- **Visualization Panels:** 10

| ID | Panel Title | Type | Provenance | Telemetry Source | Unit | Freshness |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| 2 | **WFO Product Specification Status [PENDING VENDOR CONFIRMATION]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 3 | **Recorder-to-CM CTI Link State [APPLICATION — WFO]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `short` | < 30 seconds |
| 4 | **Recording Host Uptime [REAL — HARDWARE]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `s` | < 30 seconds |
| 6 | **Active Recording Sessions [APPLICATION — WFO]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `calls` | < 30 seconds |
| 7 | **Ingestion Rate (Calls/min) [APPLICATION — WFO]** | `timeseries` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `cpm` | < 30 seconds |
| 8 | **Recording Failures Count [APPLICATION — WFO]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `calls` | < 30 seconds |
| 9 | **Ingestion Queue Depth [APPLICATION — WFO]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `calls` | < 30 seconds |
| 11 | **Recording Storage Utilization (%) [REAL — HARDWARE]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
| 12 | **Projected Days-to-Full (Storage TTE) [PREDICTIVE]** | `stat` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `d` | < 30 seconds |
| 13 | **Daily Archival Success Rate (%) [APPLICATION — WFO]** | `gauge` | `REAL_ZABBIX_TELEMETRY` | Zabbix Telemetry Engine (SNMPv2c/v3, ICMP pin | `percent` | < 30 seconds |
