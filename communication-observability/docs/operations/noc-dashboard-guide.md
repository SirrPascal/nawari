# Nawari NOC Dashboard Operator's Guide

**Scope:** Unified Grafana Dashboards for Kenya Airways Global Operations  
**Dashboards Provisioning Root:** `docker/grafana/dashboards/`  
**Operational Folders:**
- `Nawari / Network Observability` (`folderUid: nawari-network-obs`, directory: `network_observability/`) — 13 dashboards (89 visualization panels)
- `Nawari / Communication Observability` (`folderUid: nawari-comm-obs`, directory: `communication_observability/`) — 11 dashboards (111 visualization panels)  
**Total Suite:** 24 dashboards, 200 visualization panels  
**Container Host:** `mon-grafana01` (Grafana port 3000)  
**Security Tier:** Multi-Site Scoped RBAC Enabled  
**Telemetry Integrity Standard:** Phase 13.1 (100% panel descriptions, zero null-as-zero coercion, signaling vs media separation, honest real-call MOS status)

---

## 1. Operational Domain Structure & Telemetry Integrity

Nawari enforces strict separation of operational domains into two provisioned Grafana folders:

### 1.1 Nawari / Network Observability (`nawari-network-obs`)
Dedicated to physical network topology, core switch and router telemetry, interface utilization, WAN circuits, outstation edge collectors, multi-dimensional business service SLIs, incident operations, and automated remediation playbooks.

### 1.2 Nawari / Communication Observability (`nawari-comm-obs`)
Dedicated to Avaya Aura Communication Manager (CM 8.1.0), Avaya Session Border Controllers (SBCE 8.1), Session Manager (ASM), G450 Media Gateways, Call Management System (CMS), Recording / Workforce Optimization (WFO), carrier SIP trunks, call signaling ladders, and voice media quality diagnostics.

### 1.3 Telemetry Integrity Rules & User Interaction

1. **Grafana Header `(i)` Info Tooltip Interaction:**
   In Grafana (tested on v11.6.0), panel descriptions are rendered strictly via the informational icon `(i)` in the top-left of the panel header. Hovering over the chart body / visualization canvas surfaces data series points, crosshairs, or legends, **NOT** the panel description. Operators seeking detailed telemetry definitions, calculation methodologies, OIDs, and vendor caveats should hover or click the header `(i)` icon directly.
2. **100% Panel Description Coverage:**
   Every single visualization panel (200 total across all 24 dashboards) includes a complete operational description detailing:
   - What the metric measures
   - How it is collected / calculated
   - Standard units of measure
   - Operational interpretation and alerting thresholds
   - Exact datasource / SNMP OID / ODBC table
   - Provenance tag (`REAL_HARDWARE`, `APPLICATION_DERIVED`, `SYNTHETIC_PROBE`, `UNINSTRUMENTED_REAL_CALL`)
   - Polling frequency and known vendor bounds
3. **Signaling Reachability $\neq$ Media Quality:**
   A green SIP OPTIONS response or registered trunk confirms only layer-5 signaling reachability. It does **NOT** guarantee acceptable voice audio quality, low jitter, or absence of packet loss.
4. **Synthetic Probe Isolation:**
   All synthetic Asterisk test calls are visibly labeled `[SYNTHETIC — ASTERISK]`. Operators must not conflate synthetic probe performance with live subscriber calls.
5. **Honest Real-Call MOS Status:**
   Real-call MOS is explicitly displayed as `[NOT INSTRUMENTED — RTCP XR REQUIRED]` until RFC 3611 Block 7 telemetry is provisioned. Nawari never substitutes synthetic values or decorative gauges for real customer calls.
6. **Avaya CM MIB Polling Constraints:**
   Avaya CM IP voice stats tables (`avCmMeasIpVoStatSumDataLstHrTable` and `avCmMeasIpVoStatHrJitterTable`) and active alarms (`avCmAlarms`) are polled at $\ge 1\text{ hour}$ intervals to protect CM call-processing CPU. Call rate counters are polled at $\ge 5\text{ minutes}$.
7. **Physical Hardware & Appliance Audits:**
   Physical telecommunications hardware states (e.g., G450 DSP/VoIP modules, candidate SBCE interface IP assignments) that have not been physically audited are explicitly marked as `Not collected (Hardware Audit Required)` / N/A, never fabricated or assumed.
8. **Null Preservation:**
   Missing data is displayed as gaps (`spanNulls: False`). Null values are never coerced to zero.

Complete machine-readable and human-readable inventories are maintained in:
- `docs/observability/dashboard-metric-catalogue.yaml`
- `docs/observability/dashboard-inventory.md`

---

## 2. Overview of the Enterprise NOC Suite

The 24 dashboards across both domains give the Network Operations Centre (NOC), Station Duty Engineers, and Executive Leadership complete visibility across global flight operations, telecom trunks, WAN outstations, and business applications.

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
| **Network** | **Predictive Intelligence & Baselines** | `nawari_predictive_intelligence.json` | Capacity Planners, Advanced Ops | Diurnal baseline deviations (\|Z\| >= 3.0), Time-to-Exhaustion (TTE) projections, carrier trunk latency drift. |
| **Comm** | **Enterprise Communication Overview** | `nawari_communication_overview.json` | CIO, Head of Voice, Telecom Leads | Executive telephony health, SIP trunk availability, synthetic voice SLA, Avaya core platform status. |
| **Comm** | **Avaya Session Manager (ASM)** | `avaya_session_manager.json` | Voice Engineers, Telecom NOC | ASM SIP entity links (CM, SBCE), SIP OPTIONS RTT, session throughput, CPU/RAM utilization. |
| **Comm** | **Avaya Communication Manager (CM)** | `avaya_communication_manager.json` | Voice Operations, Avaya Engineers | CM 8.1 processor health, hourly IP voice summary, active alarms, call rate counters, DSP media regions. |
| **Comm** | **Avaya SBCE Operational Health** | `avaya_sbce_operational_health.json` | Voice Engineers, Telecom Leads | SBCE 8.1 appliance health (CPU/RAM/Disk/Load), interface status (A1/B1/M1/M2), voice path errors/discards. |
| **Comm** | **Avaya G450 Media Gateway** | `avaya_g450_media_gateway.json` | Telecom Field Engineers, NetOps | G450 chassis uptime, power supply redundancy, fan trays, temperature, E1 link state, DSP capacity notes. |
| **Comm** | **Avaya CMS Contact Centre** | `avaya_cms_contact_centre.json` | Contact Centre Operations, CX Leads | CMS host health, split/skill queues, calls offered/answered/abandoned, ASA, service level compliance. |
| **Comm** | **Recording & WFO Health** | `recording_wfo_operational_health.json` | Compliance Officers, Voice Operations | Recording buffer depth, ingestion rate, storage TTE, audio content boundary enforcement. |
| **Comm** | **Carrier SIP Trunks & Signaling** | `nawari_sip_trunks_signaling.json` | Carrier Interconnect Leads, NOC | Safaricom, Airtel, Liquid, Orange, BT SIP trunks, OPTIONS RTT, registration status, session counts. |
| **Comm** | **Voice Service Assurance & Quality** | `nawari-voice-service-assurance.json` | Voice Operations | Synthetic voice probe outcomes, ITU-T G.107 MOS/R-factor, setup latency trends, SBCE throughput. |
| **Comm** | **Communications Intelligence** | `nawari_voice_intelligence.json` | Voice Engineers, Telecom NOC | SIP signaling latencies (PDD/TTA/Setup), SIP trunk registration, real vs synthetic voice separation, Avaya CM SNMP real-call loss/jitter, uninstrumented real MOS status. |
| **Comm** | **Cross-Domain Voice & Endpoint** | `endpoint_voice_correlation.json` | Cross-Domain Escalation Teams | Correlation between endpoint Wi-Fi/NIC quality and voice audio jitter, gateway latency vs MOS. |

---

## 3. Communication Observability Dashboards Breakdown

### 3.1 Enterprise Communication Services Overview (`nawari_communication_overview.json`)
- **Avaya Platform Status Grid:** Real-time operational state across Communication Manager, Session Manager, SBCE, G450 Gateway, CMS, and Recording platforms.
- **Active Carrier SIP Trunks:** Live count and operational ratio of carrier interconnects (Safaricom, Airtel, Liquid Telecom, Orange, BT).
- **Synthetic Voice SLA Index:** Proportion of automated synthetic Asterisk calls meeting MOS $\ge 4.0$ and PDD $< 1500\text{ ms}$.
- **Hourly Real-Call Audio Quality Indicator:** Summary of CM IP voice network region performance from hourly SNMP collections.
- **Real-Call Telemetry Instrumentation Gate:** Operational alert reminding operators that real-time live MOS requires endpoint RTCP-XR instrumentation.

### 3.2 Avaya Aura Session Manager (ASM) (`avaya_session_manager.json`)
- **ASM Processor & Memory Utilization:** 1-minute CPU load and physical memory consumption on the Session Manager appliance.
- **SIP Entity Monitoring Table:** Operational status of SIP links to Communication Manager, SBCE, and subscriber endpoints.
- **SIP OPTIONS Response Latency:** Measured round-trip time for SIP OPTIONS keep-alive heartbeats to linked entities.
- **Active SIP Registrations & Sockets:** Live count of registered SIP user agents and open TCP/UDP transport sockets.
- **Session Routing Throughput:** Aggregate SIP INVITEs routed per minute across enterprise dial plan domains.

### 3.3 Avaya Aura Communication Manager (CM) (`avaya_communication_manager.json`)
- **Processor Status & Active Alarms:** CM processor reachability and active alarm count from `avCmAlarms` table (polled hourly).
- **Call Rate Monitoring:** Busy Hour Call Attempts (BHCA), completed calls, and abandoned calls from `avCmListMeasCallRateTotal` (polled every 5 minutes).
- **Hourly IP Voice Loss & Jitter:** 1-hour rolling network region audio statistics from `avCmMeasIpVoStatSumDataLstHrTable` and `avCmMeasIpVoStatHrJitterTable` (polled hourly to safeguard CM CPU).
- **Media Region Echo Cancellation & Codecs:** Distribution of active audio codecs (G.711, G.729) and echo cancellation performance across KQ media regions.

### 3.4 Avaya SBCE Operational Health (`avaya_sbce_operational_health.json`)
- **Appliance Resource Health:** CPU core utilization, 1-minute load average, real memory consumption, and root partition disk space.
- **Physical & Logical Interfaces:** Ingress/egress throughput, CRC errors, and drop rates on carrier (A1), internal (B1), and management (M1) interfaces.
- **EMS SIP Session Statistics:** Live active SIP calls, registrations, SRTP encrypted media sessions, and direct-media bypass calls from SBCE EMS.
- **Dynamic License Utilization:** Hourly capacity utilization percentage of SBCE concurrent session licenses.

### 3.5 Avaya G450 Media Gateway Appliance (`avaya_g450_media_gateway.json`)
- **Chassis & MGP Controller Status:** System uptime, chassis temperature, and registration state to primary Communication Manager.
- **Hardware Environmental Sensors:** Dual redundant power supply (PSU 1 & PSU 2) health and multi-fan tray operational status.
- **E1 Telephony Link State:** Physical layer-1 and layer-2 operational status of onboard E1/ISDN-PRI trunk interfaces.
- **DSP Media Resource Capacity Note:** Hardware audit gate explaining that DSP voice channel utilization (MP80/MP160) requires physical module verification.

### 3.6 Avaya CMS Contact Centre Performance (`avaya_cms_contact_centre.json`)
- **CMS Server Health:** Appliance CPU, memory, and database filesystem utilization for the Call Management System host.
- **ACD Split / Skill Queue Performance:** Real-time calls offered, calls answered, and calls abandoned across Kenya Airways customer service queues.
- **Average Speed of Answer (ASA) & Handle Time (ATT):** Queue response metrics evaluated against the 20-second service level target.
- **Agent Staffing & State Breakdown:** Count of agents in Available, On Call, After-Call Work (ACW), and AUX/Break states.
- **Informix ODBC Collection Integrity:** Freshness indicator confirming automated query intervals (15m, 30m, 60m) via the read-only `nawari_ro` account.

### 3.7 Recording & WFO Operational Health (`recording_wfo_operational_health.json`)
- **Ingestion Pipeline Rate:** Live audio stream ingestion rate across active customer service and flight dispatch interactions.
- **Archival Spool & Buffer Depth:** Local storage queue depth tracking audio files awaiting long-term compliance storage offload.
- **Storage Time-to-Exhaustion (TTE):** Predictive disk capacity depletion forecasting based on current interaction recording volume.
- **Operational Metadata Boundary Gate:** Compliance notice certifying that only recording system telemetry (queue size, latency, packet drop) is monitored; audio call contents and customer PII are strictly excluded.

### 3.8 Carrier SIP Trunks & Signaling (`nawari_sip_trunks_signaling.json`)
- **Carrier Interconnect Status Grid:** Real-time status of Kenya Airways telecom carrier trunks: Safaricom, Airtel Kenya, Liquid Telecom, Orange, and British Telecom.
- **SIP OPTIONS Round-Trip Latency:** Millisecond signaling ping latency per carrier to detect early trunk degradation.
- **Trunk Registration Status:** Registration and challenge response state across all active SIP peer groups.
- **Active Trunk Sessions:** Concurrent call capacity and channel utilization per carrier connection.

### 3.9 Voice Service Assurance & Media Quality (`nawari-voice-service-assurance.json`)
- **Synthetic Test Probe Health:** End-to-end synthetic call results executed between Kenya Airways hub and outstations.
- **ITU-T G.107 MOS & R-Factor:** Synthetic probe speech quality score calculated using the standardized E-Model.
- **Post-Dial Delay (PDD):** Latency from SIP INVITE transmission to receiving first 180 Ringing response.
- **Audio Stream Discards & Packet Loss:** Synthetic RTP media stream degradation metrics.

### 3.10 Communications Intelligence (`nawari_voice_intelligence.json`)
- **SIP Transaction Ladder Explorer:** Step-by-step ladder analysis for call setup, in-dialog re-INVITEs, and teardown.
- **Q.850 Release Cause Breakdown:** Distribution of standard termination cause codes (e.g., `16 Normal Clearing`, `17 User Busy`, `34 No Circuit Available`).
- **Time-to-Alerting (TTA) Trends:** Measured duration from session dispatch to remote alerting state.
- **Uninstrumented Real-Call MOS Status:** Explicit indicator confirming that real subscriber call MOS is uncollected until RTCP-XR is provisioned.

### 3.11 Cross-Domain Voice & Endpoint Telemetry Correlation (`endpoint_voice_correlation.json`)
- **Wi-Fi Signal Strength (RSSI) vs Jitter:** Correlates endpoint wireless link quality with voice audio packet jitter.
- **Default Gateway Latency vs Voice PDD:** Correlates LAN transport delays with telephony call setup time.
- **Host CPU Load vs Audio Packet Loss:** Identifies instances where endpoint CPU starvation induces local audio buffer underruns.

---

## 4. NOC Operating Procedures for Alerts & Dashboards

### 4.1 Investigating Degraded Business Services
1. If `nawari_enterprise_overview` indicates a service is `DEGRADED`, open `nawari_service_catalog_sla`.
2. Review the *Dependency Evidence* panel. If a mandatory component is `DOWN`, note the `station_id` and open `nawari_incident_operations`.
3. Check whether the degradation is caused by network transport (high circuit loss) or voice application servers (CMS / Session Manager).

### 4.2 Managing WAN Outages & Edge Spool Saturation
1. When a station transitions to single-circuit operation, verify that secondary circuit traffic is flowing on `nawari_global_outstations`.
2. If both circuits are down, confirm that edge spool depth on `nawari_edge_fleet` is increasing and not overflowing (50 MB hard cap).
3. Do **NOT** mark an incident resolved based on replayed telemetry. Verify that 3 consecutive live healthy observations appear in the recovery panel.

### 4.3 Triaging Carrier SIP Trunk Signaling vs Audio Quality
1. If carrier trunk alarms trigger on `nawari_sip_trunks_signaling`, check SIP OPTIONS latency and registration status.
2. If SIP OPTIONS is UP but call failures are reported, inspect `nawari_voice_intelligence` for Q.850 release causes (`34 No Circuit`, `41 Temporary Failure`).
3. Note that SIP OPTIONS reachability does **NOT** prove audio quality; verify synthetic probe MOS on `nawari-voice-service-assurance`.

### 4.4 Interpreting Avaya CM Hourly IP Voice Telemetry
1. Avaya CM IP voice stats (`avCmMeasIpVoStatSumDataLstHrTable`) update on an **hourly summary** cycle to protect the Communication Manager processor.
2. Do not expect real-time second-by-second updates on `avaya_communication_manager.json` IP voice panels. Use the hourly summary to detect multi-region trends and codec distribution.
3. For immediate call rate changes, reference the 5-minute call rate panel (`avaya.cm.call_rate.attempts`).

### 4.5 Managing Avaya CMS Contact Center Queue & Abandonment Spikes
1. If call abandonment exceeds 5% on `avaya_cms_contact_centre`, check the Average Speed of Answer (ASA) and staffed agent counts.
2. Verify whether agent workstations are experiencing endpoint network issues using `endpoint_voice_correlation`.
3. If CMS data collection stops, verify ODBC network connectivity to the Informix host on port 50000.

### 4.6 Handling Recording & WFO Archival Buffer Saturation
1. If the archival buffer depth on `recording_wfo_operational_health` approaches the 80% warning threshold, check storage Time-to-Exhaustion (TTE).
2. Verify long-term compliance storage network reachability.
3. Remember that Nawari monitors operational pipeline metadata only; raw audio recordings are never accessed or stored by the monitoring platform.
