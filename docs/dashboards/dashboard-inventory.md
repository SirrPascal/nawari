# Nawari Dashboard Inventory & Technical Registry

**Audit Date:** 2026-11-08
**Environment:** Nawari Staging Observability Platform (`mon-grafana01`)
**Total Dashboards Audited:** 25

---

## 1. Executive Summary of Active Dashboards

| # | Dashboard Title | UID | Folder | Panels (Viz/Row) | Variables | Provisioning Source |
|---|---|---|---|---|---|---|
| 1 | End-User Network Experience | `nawari-eu-nem-pilot` | Nawari | 11 (8/3) | None | Direct API |
| 2 | Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance | `nawari-communication-manager` | Nawari / Communication Observability | 14 (11/3) | None | Direct API |
| 3 | Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing | `nawari-session-manager` | Nawari / Communication Observability | 12 (9/3) | None | Direct API |
| 4 | Nawari — Avaya Call Management System (CMS) & Contact Centre Performance | `nawari-cms-contact-centre` | Nawari / Communication Observability | 12 (9/3) | None | Direct API |
| 5 | Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health | `nawari-g450-gateway` | Nawari / Communication Observability | 11 (8/3) | None | Direct API |
| 6 | Nawari — Avaya SBCE Operational Health | `nawari-sbce-health` | Nawari / Communication Observability | 19 (15/4) | None | Direct API |
| 7 | Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing | `nawari-sip-trunks` | Nawari / Communication Observability | 10 (7/3) | None | Direct API |
| 8 | Nawari — Communications Intelligence & Voice Service Assurance | `nawari-voice-intelligence` | Nawari / Communication Observability | 15 (11/4) | None | Direct API |
| 9 | Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation | `nawari-voice-correlation` | Nawari / Communication Observability | 14 (9/5) | group, endpoint | Direct API |
| 10 | Nawari — Enterprise Communication Services Overview & Executive Service Assurance | `nawari-comm-overview` | Nawari / Communication Observability | 16 (12/4) | None | Direct API |
| 11 | Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health | `nawari-recording-wfo` | Nawari / Communication Observability | 13 (10/3) | None | Direct API |
| 12 | Nawari — Voice Service Assurance & Media Quality | `nawari-voice-service-assurance` | Nawari / Communication Observability | 16 (12/4) | None | Direct API |
| 13 | Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance | `nawari-service-catalog-sla` | Nawari / Network Observability | 9 (6/3) | None | Direct API |
| 14 | Nawari — Controlled Operational Actions & Automated Remediation | `nawari-controlled-operations` | Nawari / Network Observability | 8 (5/3) | None | Direct API |
| 15 | Nawari — Distributed Edge Collector Fleet & Spool Storage | `nawari-edge-fleet` | Nawari / Network Observability | 6 (4/2) | None | Direct API |
| 16 | Nawari — Endpoint Deep-Dive & Edge Experience | `nawari-endpoint-detail` | Nawari / Network Observability | 23 (17/6) | group, endpoint | Direct API |
| 17 | Nawari — Endpoint Fleet Observability Overview | `nawari-endpoint-fleet` | Nawari / Network Observability | 19 (13/6) | None | Direct API |
| 18 | Nawari — Enterprise Executive Overview & Fleet Availability | `nawari-enterprise-overview` | Nawari / Network Observability | 7 (5/2) | None | Direct API |
| 19 | Nawari — Global Outstation Network & WAN Telemetry | `nawari-global-outstations` | Nawari / Network Observability | 9 (6/3) | None | Direct API |
| 20 | Nawari — Incident Operations, Escalation & Verified Recovery | `nawari-incident-operations` | Nawari / Network Observability | 5 (3/2) | None | Direct API |
| 21 | Nawari — Interface Traffic & Performance Health | `nawari-interface-health` | Nawari / Network Observability | 9 (6/3) | group, host, interface | Direct API |
| 22 | Nawari — Network Infrastructure Overview | `nawari-net-overview` | Nawari / Network Observability | 9 (6/3) | None | Direct API |
| 23 | Nawari — Network Path & Directional Hop Analysis | `nawari-path-analysis` | Nawari / Network Observability | 13 (8/5) | group, endpoint, target | Direct API |
| 24 | Nawari — Network Topology & Service Dependencies | `nawari-network-topology` | Nawari / Network Observability | 4 (2/2) | None | Direct API |
| 25 | Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance | `nawari-predictive-intelligence` | Nawari / Network Observability | 9 (6/3) | None | Direct API |

---

## 2. Granular Per-Dashboard Technical Specification

### 1. End-User Network Experience
- **UID:** `nawari-eu-nem-pilot`
- **Folder:** Nawari (Folder UID: `bg3lknu8id5ogd`)
- **Provisioned Source:** `N/A`
- **Tags:** network-observability, end-user-experience, pilot, nawari
- **Variables:** None
- **Total Panels:** 11 (8 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | End-User Network Experience & Pilot Fleet Overview | `row` | No | 0 |
| 2 | Pilot Laptops Enrolled | `stat` | Yes | 0 |
| 3 | Active Reporting Laptops | `stat` | Yes | 0 |
| 4 | Default Gateway Reachability | `stat` | Yes | 0 |
| 5 | Corporate DNS Health | `stat` | Yes | 0 |
| 6 | Gateway Latency & Edge Packet Loss | `row` | No | 0 |
| 7 | Default Gateway Latency (RTT) | `timeseries` | Yes | 0 |
| 8 | Default Gateway Packet Loss (%) | `timeseries` | Yes | 0 |
| 9 | Corporate DNS & Application Reachability | `row` | No | 0 |
| 10 | Corporate DNS Resolution Latency | `timeseries` | Yes | 0 |
| 11 | Wi-Fi Signal Quality (%) | `timeseries` | Yes | 0 |

---

### 2. Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance
- **UID:** `nawari-communication-manager`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, avaya, communication-manager, call-processing
- **Variables:** None
- **Total Panels:** 14 (11 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Communication Manager Call Processing & Telephony Alarms | `row` | No | 0 |
| 2 | CM Processor Reachability [REAL — ZABBIX] | `stat` | Yes | 0 |
| 3 | Active Telephony Alarms (Hourly Scan) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 4 | Call Processing Hourly Status [REAL — AVAYA SNMP] | `timeseries` | Yes | 0 |
| 5 | Call Rate Completed Calls (Hourly Measurement) [REAL — AVAYA SNMP] | `timeseries` | Yes | 0 |
| 6 | Hourly IP Voice Quality Telemetry (avCmMeasIpVoStatHrData) | `row` | No | 0 |
| 7 | Real-Call Packet Loss % (Last Hour) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 8 | Real-Call Peak Jitter (Last Hour) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 9 | Real-Call Peak Delay (Last Hour) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 10 | Hourly Average Jitter [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 11 | Codec Negotiation, Echo Cancellation & Media Regions | `row` | No | 0 |
| 12 | Negotiated Audio Codec [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 13 | Echo Cancellation Status [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 14 | Evaluated Calls Count in Last Hour [REAL — AVAYA SNMP] | `stat` | Yes | 0 |

---

### 3. Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing
- **UID:** `nawari-session-manager`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, avaya, session-manager, sip-routing
- **Variables:** None
- **Total Panels:** 12 (9 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Session Manager Host Platform Health & Transport Sockets | `row` | No | 0 |
| 2 | SM Host CPU Utilization [REAL — HARDWARE] | `gauge` | Yes | 0 |
| 3 | SM Host RAM Utilization [REAL — HARDWARE] | `gauge` | Yes | 0 |
| 4 | SM System Uptime [REAL — HARDWARE] | `stat` | Yes | 0 |
| 5 | TCP Established Sockets [REAL — HARDWARE] | `timeseries` | Yes | 0 |
| 6 | SIP Entity Monitoring & OPTIONS Reachability | `row` | No | 0 |
| 7 | SIP Entity State — Avaya CM [CONFIGURED — ASM API/CLI] | `stat` | Yes | 0 |
| 8 | SIP Entity State — Avaya SBCE [CONFIGURED — ASM API/CLI] | `stat` | Yes | 0 |
| 9 | SIP OPTIONS Heartbeat Response Time [NAWARI SIP PROBE] | `timeseries` | Yes | 0 |
| 10 | SIP Entity Inventory & Enterprise Alarm Feed | `row` | No | 0 |
| 11 | Configured SIP Entity Topology & Link Status [CONFIGURED — ASM MODEL] | `table` | Yes | 0 |
| 12 | Session Manager Active Alarms [EVENT TRAP — AV-TRAP-MIB] | `stat` | Yes | 0 |

---

### 4. Nawari — Avaya Call Management System (CMS) & Contact Centre Performance
- **UID:** `nawari-cms-contact-centre`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, avaya, cms, contact-centre, informix
- **Variables:** None
- **Total Panels:** 12 (9 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | CMS Host Infrastructure & Informix Database Engine Health | `row` | No | 0 |
| 2 | CMS Host CPU Utilization [REAL — HARDWARE] | `gauge` | Yes | 0 |
| 3 | Informix Database Engine Status [APPLICATION — CMS] | `stat` | Yes | 0 |
| 4 | CMS Archiving Interval Configuration [APPLICATION — CMS] | `stat` | Yes | 0 |
| 5 | Queue Dynamics, Wait Times & Customer Experience | `row` | No | 0 |
| 6 | Service Level Attainment (% in SLA) [APPLICATION — CMS] | `gauge` | Yes | 0 |
| 7 | Average Speed of Answer (ASA, sec) [APPLICATION — CMS] | `timeseries` | Yes | 0 |
| 8 | Calls Waiting in Queue [APPLICATION — CMS] | `stat` | Yes | 0 |
| 9 | Oldest Call Waiting (sec) [APPLICATION — CMS] | `stat` | Yes | 0 |
| 10 | Inbound Volume Trends, Abandonment & Split/Skill Performance | `row` | No | 0 |
| 11 | Calls Offered vs Answered vs Abandoned [APPLICATION — CMS] | `timeseries` | Yes | 0 |
| 12 | Skill Group & Split Performance Breakdown [APPLICATION — CMS] | `table` | Yes | 0 |

---

### 5. Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health
- **UID:** `nawari-g450-gateway`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, avaya, g450, media-gateway
- **Variables:** None
- **Total Panels:** 11 (8 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | G450 Media Gateway Appliance & Controller Registration | `row` | No | 0 |
| 2 | G450 System Uptime [REAL — HARDWARE] | `stat` | Yes | 0 |
| 3 | CM Gateway Registration [CONFIGURED — G450 MGP] | `stat` | Yes | 0 |
| 4 | Chassis Thermal State [EVENT TRAP — G450 MGP] | `stat` | Yes | 0 |
| 5 | Power Supply Status (PSU 1 & 2) [CONFIGURED — EVENT TRAP] | `stat` | Yes | 0 |
| 6 | Media Modules, Trunk Ports & Media Resources | `row` | No | 0 |
| 7 | E1 / ISDN PRI Physical Trunk State [CONFIGURED — IF-MIB] | `stat` | Yes | 0 |
| 8 | DSP Media Resource Channels [NOT COLLECTED — REQUIRES AUDIT] | `stat` | Yes | 0 |
| 9 | Chassis Fan Tray Operational State [CONFIGURED — EVENT TRAP] | `stat` | Yes | 0 |
| 10 | Media Module Inventory & Slot Architecture | `row` | No | 0 |
| 11 | Installed Media Module Slot Inventory (V1-V8) [REAL — HARDWARE] | `table` | Yes | 0 |

---

### 6. Nawari — Avaya SBCE Operational Health
- **UID:** `nawari-sbce-health`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, avaya, sbce, voice, phase4
- **Variables:** None
- **Total Panels:** 19 (15 visualization panels, 4 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Avaya SBCE — Appliance Health & System Resources | `row` | No | 0 |
| 2 | SNMPv3 Status | `stat` | Yes | 0 |
| 3 | System Uptime | `stat` | Yes | 0 |
| 4 | CPU Utilization | `gauge` | Yes | 0 |
| 5 | RAM Utilization | `gauge` | Yes | 0 |
| 6 | Root Disk Utilization | `gauge` | Yes | 0 |
| 7 | Load Average (1m) | `stat` | Yes | 0 |
| 8 | Voice Signaling & Media Interface Matrix (A1 / B1 / M1 / M2) | `row` | No | 0 |
| 9 | A1 — External DMZ (SIP Signaling) | `stat` | Yes | 0 |
| 10 | B1 — Internal Media & Core Signaling | `stat` | Yes | 0 |
| 11 | M1 — Primary Management | `stat` | Yes | 0 |
| 12 | M2 — Secondary / HA Heartbeat | `stat` | Yes | 0 |
| 13 | Voice Path Traffic & Bandwidth Utilization (64-bit HC Counters) | `row` | No | 0 |
| 14 | A1 Carrier DMZ Traffic (bps) | `timeseries` | Yes | 0 |
| 15 | B1 Internal Media & Core Signaling Traffic (bps) | `timeseries` | Yes | 0 |
| 16 | Voice Path Errors, Discards & Active SBCE Problem Feed | `row` | No | 0 |
| 17 | Voice Path Packet Errors (rate) | `timeseries` | Yes | 0 |
| 18 | Voice Path Packet Discards (rate) | `timeseries` | Yes | 0 |
| 19 | Avaya SBCE Active Alarms & Problems Feed | `alexanderzobnin-zabbix-problems-panel` | Yes | 0 |

---

### 7. Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing
- **UID:** `nawari-sip-trunks`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, avaya, sip-trunks, carrier, safaricom, airtel
- **Variables:** None
- **Total Panels:** 10 (7 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Carrier SIP Trunk Operational Registration & Keepalive Health | `row` | No | 0 |
| 2 | Safaricom Primary SIP Trunk [REAL — ZABBIX] | `stat` | Yes | 0 |
| 3 | Airtel Secondary SIP Trunk [REAL — ZABBIX] | `stat` | Yes | 0 |
| 4 | Carrier SIP OPTIONS Round-Trip Latency [REAL — ZABBIX] | `timeseries` | Yes | 0 |
| 5 | SIP Transaction Latencies & Signaling Ladder Breakdown | `row` | No | 0 |
| 6 | Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE] | `timeseries` | Yes | 0 |
| 7 | SIP Response Distribution (Station vs Trunk Outage) [SYNTHETIC — ASTERISK PROBE] | `piechart` | Yes | 0 |
| 8 | Perimeter Interface Traffic & Voice Path Errors | `row` | No | 0 |
| 9 | A1 Carrier DMZ Bandwidth (bps) [REAL — SBCE SNMP] | `timeseries` | Yes | 0 |
| 10 | Carrier Interface Packet Errors (Errors/sec) [REAL — SBCE SNMP] | `timeseries` | Yes | 0 |

---

### 8. Nawari — Communications Intelligence & Voice Service Assurance
- **UID:** `nawari-voice-intelligence`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, voice, sip, avaya, rtcp-xr, media, asterisk, kenya-airways
- **Variables:** None
- **Total Panels:** 15 (11 visualization panels, 4 collapsible rows)
- **Description:** Nawari Advanced Communications Intelligence, SIP Transaction Signaling, RTCP-XR VoIP Metrics, and Carrier Route Assurance for Kenya Airways

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | SIP Signaling Reachability & Transaction Latency Breakdown | `row` | No | 0 |
| 2 | Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE] | `timeseries` | Yes | 0 |
| 3 | SIP Response Distribution (Station vs Trunk) [SYNTHETIC — ASTERISK PROBE] | `piechart` | Yes | 0 |
| 11 | SIP Trunk Registration Status [REAL — ZABBIX] | `stat` | Yes | 0 |
| 4 | Voice Media Quality & Acoustic Telemetry (Real vs Synthetic Separation) | `row` | No | 0 |
| 14 | Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED] | `stat` | Yes | 0 |
| 9 | Synthetic Voice Quality Index (MOS) [SYNTHETIC — ASTERISK] | `stat` | Yes | 0 |
| 12 | Real-Call Packet Loss (CM SNMP) [REAL — AVAYA SNMP] | `timeseries` | Yes | 0 |
| 13 | Real-Call Peak Jitter & Delay [REAL — AVAYA SNMP] | `timeseries` | Yes | 0 |
| 15 | Synthetic Audio Stream Impairments & Acoustic Analysis | `row` | No | 0 |
| 5 | Network Packet Loss vs Jitter Buffer Discards [SYNTHETIC — ASTERISK] | `timeseries` | Yes | 0 |
| 6 | Mouth-to-Ear Voice Latency (RTT) [SYNTHETIC — ASTERISK] | `timeseries` | Yes | 0 |
| 7 | Carrier Trunk Capacity & Cross-Domain Correlated Probes | `row` | No | 0 |
| 8 | SBCE Active Concurrent Sessions (Max 500) [REAL — SBCE SNMP] | `gauge` | Yes | 0 |
| 10 | Recent Correlated Voice Call Sessions [CORRELATED PROBES] | `table` | Yes | 0 |

---

### 9. Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation
- **UID:** `nawari-voice-correlation`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, voice, endpoint, correlation, mos, rtcp, phase7
- **Variables:** group, endpoint
- **Total Panels:** 14 (9 visualization panels, 5 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Architectural Domain Separation & Transport Distinction | `row` | No | 0 |
| 2 | Voice Observability Domain Boundary | `text` | Yes | 0 |
| 3 | Real-Time Service Assurance & Status Overview | `row` | No | 0 |
| 4 | Voice Call Outcome | `stat` | Yes | 0 |
| 5 | Estimated MOS Score | `stat` | Yes | 0 |
| 6 | SBCE Port 5061 L4 Transport Socket | `stat` | Yes | 0 |
| 7 | Endpoint Gateway Loss | `stat` | Yes | 0 |
| 8 | Cross-Domain Correlation: Network Latency vs Voice MOS | `row` | No | 0 |
| 9 | Dual-Axis Correlation: Gateway Edge Latency vs Voice MOS | `timeseries` | Yes | 0 |
| 10 | Packet Loss Localization: Edge vs WAN vs Audio Stream | `row` | No | 0 |
| 11 | Cross-Domain Packet Loss: Edge vs Path vs Voice Audio Stream | `timeseries` | Yes | 0 |
| 12 | Jitter & Physical Layer Media Impact | `row` | No | 0 |
| 13 | Wi-Fi Quality vs Audio RTCP Jitter | `timeseries` | Yes | 0 |
| 14 | Avaya SBCE Active Audio Calls | `timeseries` | Yes | 0 |

---

### 10. Nawari — Enterprise Communication Services Overview & Executive Service Assurance
- **UID:** `nawari-comm-overview`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, service-assurance, executive, avaya
- **Variables:** None
- **Total Panels:** 16 (12 visualization panels, 4 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Avaya Core Telephony Platform Availability & Alarm State | `row` | No | 0 |
| 2 | Avaya Core Telephony Platform Availability Grid [REAL — ZABBIX] | `stat` | Yes | 0 |
| 3 | Active Telephony Alarms (CM & SM) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 4 | SIP Signaling Reachability & Session Dynamics | `row` | No | 0 |
| 5 | Active SIP Calls on Perimeter SBCE [REAL — SBCE SNMP] | `gauge` | Yes | 0 |
| 6 | Carrier SIP Trunk Registration Status [REAL — ZABBIX] | `stat` | Yes | 0 |
| 7 | 5-Minute Call Processing Rate (CM) [REAL — AVAYA SNMP] | `timeseries` | Yes | 0 |
| 8 | Contact Centre Health & Business Queue Performance (Avaya CMS) | `row` | No | 0 |
| 9 | Contact Centre Service Level (% in SLA) [APPLICATION — CMS] | `gauge` | Yes | 0 |
| 10 | Queue Depth & Oldest Waiting Call [APPLICATION — CMS] | `stat` | Yes | 0 |
| 11 | Agent Staffing State Distribution [APPLICATION — CMS] | `piechart` | Yes | 0 |
| 12 | Voice Media Quality & Synthetic Probe Assurance (Real vs Synthetic Separation) | `row` | No | 0 |
| 13 | Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED] | `stat` | Yes | 0 |
| 14 | Real-Call Packet Loss % (CM Last Hour) [REAL — AVAYA SNMP] | `stat` | Yes | 0 |
| 15 | Synthetic Voice MOS [SYNTHETIC — ASTERISK] | `gauge` | Yes | 0 |
| 16 | Active Voice Infrastructure Problems [ZABBIX NATIVE EVENT ENGINE] | `alexanderzobnin-zabbix-problems-panel` | Yes | 0 |

---

### 11. Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health
- **UID:** `nawari-recording-wfo`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, communication-observability, recording, wfo, compliance
- **Variables:** None
- **Total Panels:** 13 (10 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Recording & WFO Architecture Boundary & Platform Health | `row` | No | 0 |
| 2 | WFO Product Specification Status [PENDING VENDOR CONFIRMATION] | `stat` | Yes | 0 |
| 3 | Recorder-to-CM CTI Link State [APPLICATION — WFO] | `stat` | Yes | 0 |
| 4 | Recording Host Uptime [REAL — HARDWARE] | `stat` | Yes | 0 |
| 5 | Recording Ingestion Rate, Queue Depth & Failures | `row` | No | 0 |
| 6 | Active Recording Sessions [APPLICATION — WFO] | `stat` | Yes | 0 |
| 7 | Ingestion Rate (Calls/min) [APPLICATION — WFO] | `timeseries` | Yes | 0 |
| 8 | Recording Failures Count [APPLICATION — WFO] | `stat` | Yes | 0 |
| 9 | Ingestion Queue Depth [APPLICATION — WFO] | `gauge` | Yes | 0 |
| 10 | Storage Partition Capacity, Retention & Archival Horizon | `row` | No | 0 |
| 11 | Recording Storage Utilization (%) [REAL — HARDWARE] | `gauge` | Yes | 0 |
| 12 | Projected Days-to-Full (Storage TTE) [PREDICTIVE] | `stat` | Yes | 0 |
| 13 | Daily Archival Success Rate (%) [APPLICATION — WFO] | `gauge` | Yes | 0 |

---

### 12. Nawari — Voice Service Assurance & Media Quality
- **UID:** `nawari-voice-service-assurance`
- **Folder:** Nawari / Communication Observability (Folder UID: `nawari-comm-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, voice, assurance, telemetry, sbce
- **Variables:** None
- **Total Panels:** 16 (12 visualization panels, 4 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Voice Service Assurance — Real-Time Health & Operational Status | `row` | No | 0 |
| 2 | Call Transaction Outcome | `stat` | Yes | 0 |
| 3 | Estimated MOS (ITU-T G.107) [SYNTHETIC — ASTERISK] | `gauge` | Yes | 0 |
| 4 | Media Path Directionality | `stat` | Yes | 0 |
| 5 | Call Setup Latency | `stat` | Yes | 0 |
| 6 | R-Factor (Transmission Quality) [SYNTHETIC — ASTERISK] | `gauge` | Yes | 0 |
| 16 | Telemetry Provenance Mode | `stat` | Yes | 0 |
| 7 | Signaling Performance & Teardown Dynamics | `row` | No | 0 |
| 8 | Call Setup Latency History | `timeseries` | Yes | 0 |
| 9 | SIP Response Code History | `timeseries` | Yes | 0 |
| 10 | RTP Media Quality & Acoustic Impairment Analysis | `row` | No | 0 |
| 11 | Estimated MOS Trend & SLA Thresholds [SYNTHETIC — ASTERISK] | `timeseries` | Yes | 0 |
| 12 | RTP Jitter & Packet Loss Impairments [SYNTHETIC — ASTERISK] | `timeseries` | Yes | 0 |
| 13 | Cross-Domain Infrastructure & SBC Operational Correlation | `row` | No | 0 |
| 14 | SBCE Signaling (A1) & Media (B1) Traffic Throughput [REAL — SBCE SNMP] | `timeseries` | Yes | 0 |
| 15 | SBCE CPU Utilization [REAL — SBCE SNMP] | `timeseries` | Yes | 0 |

---

### 13. Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance
- **UID:** `nawari-service-catalog-sla`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, services, sla, slo, aviation, kenya-airways
- **Variables:** None
- **Total Panels:** 9 (6 visualization panels, 3 collapsible rows)
- **Description:** Nawari Aviation Business Service Catalogue, Multi-Dimensional SLA/SLO Assurance (Availability, Performance, Quality, Coverage), Error Budget Burn Rate Surveillance, and Incident MTTR.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Tier 1 Mission-Critical Aviation Services SLA/SLO (Target: 99.95%) | `row` | No | 0 |
| 2 | Departure Control System (DCS Core) Availability SLI | `gauge` | Yes | 0 |
| 3 | Flight Operations & Dispatch Availability SLI | `gauge` | Yes | 0 |
| 4 | Air-to-Ground & Ramp Voice Availability SLI | `gauge` | Yes | 0 |
| 5 | Error Budget Consumption & Burn Rate Surveillance (30-Day Window) | `row` | No | 0 |
| 6 | Error Budget Burn Rate (1x = Budget Normal, > 2x = Paging Alert) | `timeseries` | Yes | 0 |
| 7 | Remaining Error Budget Minutes (Tier 1: 21.6 mins / month max downtime) | `stat` | Yes | 0 |
| 8 | Active Correlated Incidents & Resolution Lifecycle | `row` | No | 0 |
| 9 | Active Business Service Incidents Stream | `table` | Yes | 0 |

---

### 14. Nawari — Controlled Operational Actions & Automated Remediation
- **UID:** `nawari-controlled-operations`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, actions, remediation, governance, kenya-airways
- **Variables:** None
- **Total Panels:** 8 (5 visualization panels, 3 collapsible rows)
- **Description:** Nawari Controlled Operational Actions, Human-in-the-Loop Approval Queue, Automated Remediation Playbooks, Rollback Safety, and Chained Audit Ledger.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Operational Action Pipeline & Concurrency Health | `row` | No | 0 |
| 2 | Action Execution Lifecycle Distribution | `bargauge` | Yes | 0 |
| 3 | Operational Dead-Man Circuit Breaker Status | `stat` | Yes | 0 |
| 4 | Human-in-the-Loop (HITL) Authorisation & Two-Person Queue | `row` | No | 0 |
| 5 | Pending Operator Approvals & Blast-Radius Risk Board | `table` | Yes | 0 |
| 6 | Independent Verification & Tamper-Evident Audit Ledger | `row` | No | 0 |
| 7 | Pre- vs Post-Remediation Service Health Verification | `timeseries` | Yes | 0 |
| 8 | Cryptographically Chained Immutable Audit Stream (SHA-256) | `table` | Yes | 0 |

---

### 15. Nawari — Distributed Edge Collector Fleet & Spool Storage
- **UID:** `nawari-edge-fleet`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, edge, spool, fleet, outstations, kenya-airways
- **Variables:** None
- **Total Panels:** 6 (4 visualization panels, 2 collapsible rows)
- **Description:** Nawari Distributed Edge Fleet Diagnostics: Outstation Spool Utilization, Store-and-Forward Replay Backlog, Clock Drift Skew, and Collector Authentication.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Outstation Edge Collector Fleet Availability & Health | `row` | No | 0 |
| 2 | Active Edge Collectors | `stat` | Yes | 0 |
| 3 | Max Outstation Clock Drift | `stat` | Yes | 0 |
| 4 | Fleet Total Spool Backlog | `stat` | Yes | 0 |
| 5 | Outstation Spool Disk Utilization & Replay Health | `row` | No | 0 |
| 6 | Outstation Spool Storage & Replay Queue Matrix | `table` | Yes | 0 |

---

### 16. Nawari — Endpoint Deep-Dive & Edge Experience
- **UID:** `nawari-endpoint-detail`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, endpoint, detail, wifi, dns, phase7
- **Variables:** group, endpoint
- **Total Panels:** 23 (17 visualization panels, 6 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Endpoint Identification & Telemetric Metadata | `row` | No | 0 |
| 2 | Agent Info & Host Identity | `stat` | Yes | 0 |
| 3 | Active Interface | `stat` | Yes | 0 |
| 4 | Authoritative Provenance | `stat` | Yes | 0 |
| 5 | First-Hop Edge Network Quality (Default Gateway) | `row` | No | 0 |
| 6 | Default Gateway RTT Latency | `timeseries` | Yes | 0 |
| 7 | Default Gateway Packet Loss | `timeseries` | Yes | 0 |
| 8 | Physical Wi-Fi Health (Isolated — Active Only for Wi-Fi Interfaces) | `row` | No | 0 |
| 9 | Wi-Fi RSSI Gauge | `gauge` | Yes | 0 |
| 10 | Wi-Fi RSSI History | `timeseries` | Yes | 0 |
| 11 | Wi-Fi Link Quality Gauge | `gauge` | Yes | 0 |
| 12 | Wi-Fi Link Quality History | `timeseries` | Yes | 0 |
| 13 | Edge DNS Resolution Diagnostics | `row` | No | 0 |
| 14 | DNS Query Resolution Time by Target | `timeseries` | Yes | 0 |
| 15 | DNS Target RCODE / Status | `stat` | Yes | 0 |
| 16 | Multi-Protocol Service Connectivity & Latency Decomposition | `row` | No | 0 |
| 17 | Service Target Reachability | `stat` | Yes | 0 |
| 18 | TCP 3-Way Handshake Latency | `timeseries` | Yes | 0 |
| 19 | TLS Cryptographic Handshake Time | `timeseries` | Yes | 0 |
| 20 | HTTP Time To First Byte (TTFB) | `timeseries` | Yes | 0 |
| 21 | Quick Investigation & Cross-Domain Navigation Links | `row` | No | 0 |
| 22 | Path Analysis Navigation | `text` | Yes | 0 |
| 23 | Voice Assurance Navigation | `text` | Yes | 0 |

---

### 17. Nawari — Endpoint Fleet Observability Overview
- **UID:** `nawari-endpoint-fleet`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, endpoint, fleet, overview, phase7
- **Variables:** None
- **Total Panels:** 19 (13 visualization panels, 6 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Endpoint Fleet Health & Inventory Summary | `row` | No | 0 |
| 2 | Total Enrolled Endpoints | `stat` | Yes | 0 |
| 3 | Active Reporting Endpoints | `stat` | Yes | 0 |
| 4 | Degraded Edge Endpoints | `stat` | Yes | 0 |
| 5 | Stale Endpoints (>15m SLA) | `stat` | Yes | 0 |
| 6 | Fleet Composition & Provenance Distribution | `row` | No | 0 |
| 7 | Active Primary Interface Distribution | `piechart` | Yes | 0 |
| 8 | Telemetric Environment Provenance | `piechart` | Yes | 0 |
| 9 | Fleet Edge Network Performance (Aggregated) | `row` | No | 0 |
| 10 | Fleet Default Gateway Latency | `timeseries` | Yes | 0 |
| 11 | Fleet Default Gateway Packet Loss | `timeseries` | Yes | 0 |
| 12 | Probed Core Services Reachability Matrix | `row` | No | 0 |
| 13 | Voice Gateway (5061/tcp) Reachability | `stat` | Yes | 0 |
| 14 | DNS Resolution Latency | `timeseries` | Yes | 0 |
| 15 | Corporate HTTP Services TTFB | `timeseries` | Yes | 0 |
| 16 | Fleet Endpoint Inventory & Degradation Drill-Down | `row` | No | 0 |
| 17 | Discovered Endpoints Inventory & Operational Status | `table` | Yes | 1 |
| 18 | Active Endpoint Incidents & Problem Feed | `row` | No | 0 |
| 19 | Endpoint Active Problem Alarms (Gateway Loss, High RTT, Stale Telemetry) | `alexanderzobnin-zabbix-problems-panel` | Yes | 0 |

---

### 18. Nawari — Enterprise Executive Overview & Fleet Availability
- **UID:** `nawari-enterprise-overview`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, enterprise, overview, multisite, kenya-airways
- **Variables:** None
- **Total Panels:** 7 (5 visualization panels, 2 collapsible rows)
- **Description:** Nawari Enterprise Global Overview: Fleet Site Availability, Regional Health Matrix, Service Tier Health, Active P1/P2 Outages, and Multi-Site SLA Compliance.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Global Airline Operational Health & Outstation Availability | `row` | No | 0 |
| 2 | Global Station Availability | `gauge` | Yes | 0 |
| 3 | Active P1 / P2 Incidents | `stat` | Yes | 0 |
| 4 | Service Tier Health Summary | `table` | Yes | 0 |
| 5 | Regional Health & Notification Delivery Pipeline | `row` | No | 0 |
| 6 | Regional Health Index Trends | `timeseries` | Yes | 0 |
| 7 | Notification Channel Health & DLQ Backlog | `table` | Yes | 0 |

---

### 19. Nawari — Global Outstation Network & WAN Telemetry
- **UID:** `nawari-global-outstations`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, multisite, outstations, wan, voice, kenya-airways
- **Variables:** None
- **Total Panels:** 9 (6 visualization panels, 3 collapsible rows)
- **Description:** Nawari Multi-Site Enterprise Outstation Network Overview: WAN Circuit Telemetry, Trans-WAN Synthetic Voice Probing, ITU-T G.107 MOS, and Edge Store-and-Forward Spool Buffers.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Global Outstation Fleet Topology & WAN Health | `row` | No | 0 |
| 2 | Outstation WAN Circuit Status Matrix (Primary & Secondary) | `table` | Yes | 0 |
| 3 | Trans-WAN Round-Trip Latency (JKIA Hub to Outstations) | `timeseries` | Yes | 0 |
| 4 | Trans-WAN Voice Quality & Trunk Survivability (ITU-T G.107) | `row` | No | 0 |
| 5 | Voice Quality Listening MOS by Station | `gauge` | Yes | 0 |
| 6 | Trans-WAN Voice Packet Jitter Trends | `timeseries` | Yes | 0 |
| 7 | Edge Telemetry Store-and-Forward Spool Diagnostics | `row` | No | 0 |
| 8 | Buffered Spool Queue Depth by Station (Offline Records) | `stat` | Yes | 0 |
| 9 | Post-Restoration Spool Drain & Replay Velocity | `timeseries` | Yes | 0 |

---

### 20. Nawari — Incident Operations, Escalation & Verified Recovery
- **UID:** `nawari-incident-operations`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, incidents, escalation, verification, kenya-airways
- **Variables:** None
- **Total Panels:** 5 (3 visualization panels, 2 collapsible rows)
- **Description:** Nawari Incident Operations: Closed-Loop Lifecycle Management, Escalation Timers, Notification Delivery Receipts, and Multi-Observation Recovery Verification.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Incident Lifecycle & Closed-Loop Resolution State | `row` | No | 0 |
| 2 | Incidents by Lifecycle State | `stat` | Yes | 0 |
| 3 | Max Unacknowledged Incident Age (SLA 15m) | `stat` | Yes | 0 |
| 4 | Multi-Observation Recovery Verification & Resolution Audit | `row` | No | 0 |
| 5 | Active Recovery Verification Pipelines (Consecutive Healthy Chains) | `table` | Yes | 0 |

---

### 21. Nawari — Interface Traffic & Performance Health
- **UID:** `nawari-interface-health`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, network, interfaces, traffic
- **Variables:** group, host, interface
- **Total Panels:** 9 (6 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Selected Interface Telemetry & Operational State | `row` | No | 0 |
| 2 | Interface Operational Status | `stat` | Yes | 0 |
| 3 | Configured Interface Speed | `stat` | Yes | 0 |
| 4 | Administrative State | `stat` | Yes | 0 |
| 5 | Bandwidth Utilization & Throughput | `row` | No | 0 |
| 6 | Bandwidth Ingress / Egress (bits/sec) | `timeseries` | Yes | 0 |
| 7 | Interface Quality & Packet Loss (Errors & Discards) | `row` | No | 0 |
| 8 | Packet Error Rates (in/out errors/sec) | `timeseries` | Yes | 0 |
| 9 | Packet Discard Rates (in/out pps) | `timeseries` | Yes | 0 |

---

### 22. Nawari — Network Infrastructure Overview
- **UID:** `nawari-net-overview`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, network, overview, phase3
- **Variables:** None
- **Total Panels:** 9 (6 visualization panels, 3 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Network Health & Availability Overview | `row` | No | 0 |
| 2 | Core Switch SNMP Status | `stat` | Yes | 0 |
| 3 | System Uptime | `stat` | Yes | 0 |
| 4 | ICMP Latency | `stat` | Yes | 0 |
| 5 | Active Network Problems | `stat` | Yes | 0 |
| 6 | Interface Operational Status Matrix | `row` | No | 0 |
| 7 | Discovered Physical & Logical Interfaces (mock-core-switch-01) | `table` | Yes | 0 |
| 8 | Active Problem Incidents | `row` | No | 0 |
| 9 | Live Network Alert Feed (Zabbix Problems) | `alexanderzobnin-zabbix-problems-panel` | Yes | 0 |

---

### 23. Nawari — Network Path & Directional Hop Analysis
- **UID:** `nawari-path-analysis`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, network, path, traceroute, copp, phase7
- **Variables:** group, endpoint, target
- **Total Panels:** 13 (8 visualization panels, 5 collapsible rows)
- **Description:** No top-level description provided

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | End-to-End Path Performance Metrics | `row` | No | 0 |
| 2 | End-to-End Latency | `stat` | Yes | 0 |
| 3 | End-to-End Packet Loss | `stat` | Yes | 0 |
| 4 | Total Path Hops | `stat` | Yes | 0 |
| 5 | Path Route Stability | `stat` | Yes | 0 |
| 6 | Control Plane Policing (CoPP) Guard & Interpretation Notice | `row` | No | 0 |
| 7 | CoPP Guard Architectural Interpretation | `text` | Yes | 0 |
| 8 | Hop-by-Hop Topology & Performance Waterfall | `row` | No | 0 |
| 9 | Discovered Hop Details (IP, RTT, Packet Loss, CoPP Status) | `table` | Yes | 0 |
| 10 | Hop Latency Progression & Bottleneck Detection | `row` | No | 0 |
| 11 | Hop Latency Progression Waterfall (Detecting >40ms Latency Jumps) | `timeseries` | Yes | 0 |
| 12 | Route Stability & Path Change Timeline | `row` | No | 0 |
| 13 | Route Divergence History (Path Signature Hash Transitions) | `timeseries` | Yes | 0 |

---

### 24. Nawari — Network Topology & Service Dependencies
- **UID:** `nawari-network-topology`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, network, topology, cisco, avaya, layer2, layer3
- **Variables:** None
- **Total Panels:** 4 (2 visualization panels, 2 collapsible rows)
- **Description:** Nawari Dynamic Network Topology, Layer 2 Switching, Layer 3 Routing, and Service Dependencies for Kenya Airways

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Network Topology & Physical Adjacencies | `row` | No | 0 |
| 2 | Enterprise Network Topology (Node Graph) | `nodeGraph` | Yes | 0 |
| 3 | Recent Topology State Changes & Flaps | `row` | No | 0 |
| 4 | Topology Change Audit Log | `table` | Yes | 0 |

---

### 25. Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance
- **UID:** `nawari-predictive-intelligence`
- **Folder:** Nawari / Network Observability (Folder UID: `nawari-network-obs`)
- **Provisioned Source:** `N/A`
- **Tags:** nawari, predictive, analytics, baselines, kenya-airways
- **Variables:** None
- **Total Panels:** 9 (6 visualization panels, 3 collapsible rows)
- **Description:** Nawari Evidence-Driven Predictive Intelligence: Dynamic Diurnal Baselines, Statistical Anomaly Radar, Time-to-Exhaustion (TTE) Projections, and Evidence-Ranked Root-Cause Hypotheses.

#### Panel Inventory:
| Panel ID | Title | Type | Has Description | Data Links |
|---|---|---|---|---|
| 1 | Predictive Health Radar & Active Statistical Deviations | `row` | No | 0 |
| 2 | Active Multi-Domain Statistical Anomalies | `bargauge` | Yes | 0 |
| 3 | Time-to-Exhaustion (TTE) Horizon (Safe Capacity Limit) | `bargauge` | Yes | 0 |
| 4 | Dynamic Diurnal Baseline Corridors & Trajectory Tracking | `row` | No | 0 |
| 5 | Dynamic Baseline Bands vs Real-Time Metric Telemetry | `timeseries` | Yes | 0 |
| 6 | Voice MOS Degradation Trajectory & Predictive Horizon | `timeseries` | Yes | 0 |
| 7 | Intelligent Diagnosis & Evidence-Ranked Root Cause Hypotheses | `row` | No | 0 |
| 8 | Top Evidence-Ranked Hypotheses (Supporting vs Contradicting) | `table` | Yes | 0 |
| 9 | Carrier Trunk Signaling Drift (Post-Dial Delay) | `timeseries` | Yes | 0 |

---
