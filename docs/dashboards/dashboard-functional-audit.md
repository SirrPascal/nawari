# Nawari Dashboard Functional Audit

**Audit Date:** 2026-11-08
**Scope:** Deep functional inspection of all 25 active Grafana dashboards in Nawari
**Operational Objective:** Establish baseline capabilities, identify functional overlap, and define consolidation boundaries without telemetry loss.

---

## 1. Domain Summary & Classification

| UID | Dashboard Title | Operational Tier | Telemetry Provenance | Primary Operational Question |
|---|---|---|---|---|
| `nawari-eu-nem-pilot` | End-User Network Experience | Pilot Dashboard | Real Active Endpoint Diagnostics | Are pilot laptops successfully reporting live diagnostic telemetry? |
| `nawari-communication-manager` | Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance | Technical Diagnostic (Tier 4) | Real Avaya CM SNMP Telemetry (Hourly Polled) | What is CM processor occupancy? |
| `nawari-session-manager` | Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing | Technical Diagnostic (Tier 4) | Real Avaya ASM SNMP Telemetry | Is Session Manager routing SIP INVITEs successfully? |
| `nawari-cms-contact-centre` | Nawari — Avaya Call Management System (CMS) & Contact Centre Performance | Domain Deep-Dive (Tier 3) | Application-Derived Contact Centre Telemetry | What is the current queue depth for customer reservations? |
| `nawari-g450-gateway` | Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health | Technical Diagnostic (Tier 4) | Real Hardware SNMP Telemetry | Is the G450 power supply redundant? |
| `nawari-sbce-health` | Nawari — Avaya SBCE Operational Health | Technical Diagnostic (Tier 4) | Real SBCE SNMP Telemetry | Is SBCE CPU or memory spiking? |
| `nawari-sip-trunks` | Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing | Domain Deep-Dive (Tier 3) | Real Signaling Telemetry (Layer 5) | Are Safaricom and Airtel SIP trunks answering OPTIONS pings? |
| `nawari-voice-intelligence` | Nawari — Communications Intelligence & Voice Service Assurance | Technical Diagnostic (Tier 3) | Synthetic Call Probe & Real SNMP (Explicitly Labeled) | What is the synthetic MOS score across internal extensions? |
| `nawari-voice-correlation` | Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation | Cross-Domain Operations (Tier 3) | Cross-Domain Correlated Analytics | Is an agent's reported voice degradation caused by their local Wi-Fi packet loss or by carrier SIP trunk congestion? |
| `nawari-comm-overview` | Nawari — Enterprise Communication Services Overview & Executive Service Assurance | Domain Overview (Tier 2 Entry Point) | Aggregated Telephony & Voice Telemetry | Are Avaya CM, SM, SBCE, and G450 operational? |
| `nawari-recording-wfo` | Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health | Compliance & Diagnostic (Tier 3) | Application & Compliance Telemetry | Are 100% of regulated calls being recorded? |
| `nawari-voice-service-assurance` | Nawari — Voice Service Assurance & Media Quality | Domain Deep-Dive (Tier 3) | Real & Synthetic Voice Media Telemetry | What audio codecs are in use? |
| `nawari-service-catalog-sla` | Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance | Business Service Tier (Tier 2/3) | Service Assurance SLI / SLA Telemetry | Are core airline services (Flight Ops, Baggage Handling, Check-in, DCS) meeting their 99.9% SLO? |
| `nawari-controlled-operations` | Nawari — Controlled Operational Actions & Automated Remediation | Automation & Remediation (Tier 3) | Operational Action Audit Telemetry | Did an automated restart trigger for a failing collector? |
| `nawari-edge-fleet` | Nawari — Distributed Edge Collector Fleet & Spool Storage | Infrastructure Support (Tier 3) | Platform Operational Telemetry | Are edge proxies/collectors running out of disk space? |
| `nawari-endpoint-detail` | Nawari — Endpoint Deep-Dive & Edge Experience | Technical Diagnostic (Tier 4) | Real Endpoint Diagnostic Telemetry | Why is Jimmy experiencing poor Zoom/Teams calls? |
| `nawari-endpoint-fleet` | Nawari — Endpoint Fleet Observability Overview | Domain Overview (Tier 3) | Real Endpoint Agent Telemetry | How many employee laptops are reporting? |
| `nawari-enterprise-overview` | Nawari — Enterprise Executive Overview & Fleet Availability | Executive Overview (Tier 1 Entry Point) | Aggregated & Calculated Zabbix Telemetry | Is the global airline infrastructure healthy? |
| `nawari-global-outstations` | Nawari — Global Outstation Network & WAN Telemetry | Domain Deep-Dive (Tier 3) | Real & Synthetic Network Telemetry | Are international outstations (LHR, DXB, JNB) reachable? |
| `nawari-incident-operations` | Nawari — Incident Operations, Escalation & Verified Recovery | Operational Assurance (Tier 3) | Event-Derived Incident Telemetry | What active P1/P2/P3 incidents exist? |
| `nawari-interface-health` | Nawari — Interface Traffic & Performance Health | Technical Diagnostic (Tier 4) | Real Zabbix SNMP 64-bit Counters | Which switch ports or uplinks are congested? |
| `nawari-net-overview` | Nawari — Network Infrastructure Overview | Domain Overview (Tier 2) | Real Zabbix SNMP Telemetry | Are core switches and distribution gateways responsive? |
| `nawari-path-analysis` | Nawari — Network Path & Directional Hop Analysis | Technical Diagnostic (Tier 4) | Synthetic & Measured Path Telemetry | Where is the bottleneck in the path between endpoints and core services? |
| `nawari-network-topology` | Nawari — Network Topology & Service Dependencies | Visual Overview / Dependency Map | Calculated Structural Topology | How do edge devices connect to core gateways and datacenters? |
| `nawari-predictive-intelligence` | Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance | Advanced Analytics (Tier 3) | Predictive Statistical Telemetry | Which links are exhibiting abnormal traffic compared to historical Thursdays? |

---

## 2. In-Depth Per-Dashboard Functional Profiles

### `nawari-eu-nem-pilot` — End-User Network Experience
- **Primary Operational Purpose:** Dedicated pilot dashboard for the End-User Network Experience Monitoring initiative, live active check validation.
- **Target Audience:** Pilot Stakeholders, Engineering Team
- **Core Questions Answered:** Are pilot laptops successfully reporting live diagnostic telemetry? What are the gateway RTT and DNS stats?
- **Telemetry Sources:** Zabbix Agent 2 master snapshot (`nawari.nem.all`) and dependent items.
- **Data Provenance:** Real Active Endpoint Diagnostics
- **Operational Tier:** Pilot Dashboard
- **Unique Capabilities:** Focused pilot fleet view with 10s auto-refresh.
- **Functional Overlaps:** 100% functionally overlaps with endpoint-fleet and endpoint-detail.
- **Consolidation Action:** Unify into the consolidated Endpoint & User Experience dashboard.

### `nawari-communication-manager` — Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance
- **Primary Operational Purpose:** Avaya Aura Communication Manager (ACM) call processing occupancy, registered IP endpoints, DSP resource utilization, and hourly voice statistics.
- **Target Audience:** Avaya Telephony Engineers, Telecoms Operations
- **Core Questions Answered:** What is CM processor occupancy? Are IP phones unregistering? Are DSP channels exhausting on media processors?
- **Telemetry Sources:** Zabbix SNMP Avaya CM MIB (avCmMeasIpVoStatSumDataLstHrTable, avCmAlarmsTable, 1-hour polling delay enforced).
- **Data Provenance:** Real Avaya CM SNMP Telemetry (Hourly Polled)
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** Registered endpoint counts, hourly voice statistics, processor occupancy.
- **Functional Overlaps:** Voice quality overlaps with nawari_voice_intelligence.
- **Consolidation Action:** Consolidate into Avaya Infrastructure & Signaling as the Communication Manager section.

### `nawari-session-manager` — Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing
- **Primary Operational Purpose:** Avaya Aura Session Manager (ASM) operational health, SIP entity routing, transaction rates, response times, and memory heap.
- **Target Audience:** Avaya Voice Engineers, Systems Administrators
- **Core Questions Answered:** Is Session Manager routing SIP INVITEs successfully? Are entity links to CM or SBCE degraded? What is the SIP response latency?
- **Telemetry Sources:** Zabbix SNMP Avaya ASM MIB, JVM heap memory, SIP message throughput counters.
- **Data Provenance:** Real Avaya ASM SNMP Telemetry
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** SIP entity routing matrix, ASM JVM metrics, SIP transaction rates.
- **Functional Overlaps:** SIP routing overlaps with nawari-sip-trunks and nawari-communication-manager.
- **Consolidation Action:** Consolidate into Avaya Infrastructure & Signaling as the Session Manager section.

### `nawari-cms-contact-centre` — Nawari — Avaya Call Management System (CMS) & Contact Centre Performance
- **Primary Operational Purpose:** Avaya Call Management System (CMS) contact centre ACD split/skill queue performance: depth, Average Speed of Answer (ASA), abandonment rate, agent states.
- **Target Audience:** Contact Centre Operations, Customer Service Managers
- **Core Questions Answered:** What is the current queue depth for customer reservations? Is call abandonment spiking above 5%? How many agents are staffed vs idle?
- **Telemetry Sources:** Zabbix CMS integration items, ACD queue statistics, agent state counters.
- **Data Provenance:** Application-Derived Contact Centre Telemetry
- **Operational Tier:** Domain Deep-Dive (Tier 3)
- **Unique Capabilities:** ACD split/skill metrics, queue abandonment rate, agent staffing levels.
- **Functional Overlaps:** Call volume overlaps with CM total calls.
- **Consolidation Action:** Consolidate into Voice Quality & Contact Centre as the Contact Centre Performance section.

### `nawari-g450-gateway` — Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health
- **Primary Operational Purpose:** Avaya G450 Media Gateway chassis health, power supplies, fans, temperature, DSP VoIP media channels, and E1/T1 PRI sync.
- **Target Audience:** Hardware Telecoms Engineers, Datacenter Support
- **Core Questions Answered:** Is the G450 power supply redundant? Are DSP VoIP resources depleted? Is the E1 ISDN PRI clock synchronization locked?
- **Telemetry Sources:** Zabbix SNMP G450 MIB (chassis environment, VoIP channel occupancy, DS1 sync).
- **Data Provenance:** Real Hardware SNMP Telemetry
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** Physical appliance chassis monitoring, E1/T1 PRI sync status, DSP VoIP channels.
- **Functional Overlaps:** DSP metrics overlap with CM media resource allocation.
- **Consolidation Action:** Consolidate into Avaya Infrastructure & Signaling as the G450 Media Gateway section.

### `nawari-sbce-health` — Nawari — Avaya SBCE Operational Health
- **Primary Operational Purpose:** Avaya Session Border Controller Enterprise (SBCE) appliance resources, TLS handshakes, SIP entity reachability, active sessions, and security limits.
- **Target Audience:** Telephony Engineers, Voice Security Specialists
- **Core Questions Answered:** Is SBCE CPU or memory spiking? Are TLS connections negotiating properly? What is the concurrent SIP session load?
- **Telemetry Sources:** Zabbix SNMP SBCE MIB (avSbceSystemCpuUtil, avSbceTotalCalls, avSbceTlsHandshakeErrors).
- **Data Provenance:** Real SBCE SNMP Telemetry
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** SBCE deep metrics, perimeter security limits, TLS handshake performance.
- **Functional Overlaps:** Perimeter status overlaps with nawari-sip-trunks.
- **Consolidation Action:** Consolidate into Avaya Infrastructure & Signaling as the SBCE section.

### `nawari-sip-trunks` — Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing
- **Primary Operational Purpose:** Carrier SIP trunk signaling ladders, SIP OPTIONS round-trip time, carrier response codes (200 OK vs 503 Service Unavailable), and perimeter session routing.
- **Target Audience:** Voice Network Engineers, Telecom Carrier Managers
- **Core Questions Answered:** Are Safaricom and Airtel SIP trunks answering OPTIONS pings? What is the carrier signaling response time? Are calls rejecting with 503?
- **Telemetry Sources:** Zabbix SIP OPTIONS response time, SIP ladder status, carrier link availability.
- **Data Provenance:** Real Signaling Telemetry (Layer 5)
- **Operational Tier:** Domain Deep-Dive (Tier 3)
- **Unique Capabilities:** Carrier signaling ladders, SIP OPTIONS latency comparison across telcos.
- **Functional Overlaps:** Signaling reachability overlaps with SBCE active calls.
- **Consolidation Action:** Consolidate into Avaya Infrastructure & Signaling as the Carrier SIP Trunks section.

### `nawari-voice-intelligence` — Nawari — Communications Intelligence & Voice Service Assurance
- **Primary Operational Purpose:** Synthetic voice probing via Asterisk test calls, PESQ/POLQA scoring, media delay, jitter, and real-call uninstrumented indicators.
- **Target Audience:** Voice Quality Specialists, SLA Managers
- **Core Questions Answered:** What is the synthetic MOS score across internal extensions? Are synthetic calls completing? Is jitter elevated on voice VLANs?
- **Telemetry Sources:** Synthetic Asterisk call probes, RFC 3611 RTCP-XR placeholders (honest uninstrumented indicators), Avaya hourly summary.
- **Data Provenance:** Synthetic Call Probe & Real SNMP (Explicitly Labeled)
- **Operational Tier:** Technical Diagnostic (Tier 3)
- **Unique Capabilities:** Synthetic call PESQ/MOS metrics, strict distinction between synthetic probes and customer calls.
- **Functional Overlaps:** Media quality overlaps with nawari-voice-service-assurance.
- **Consolidation Action:** Consolidate into Voice Quality & Contact Centre as the Voice Quality & Synthetic Testing section.

### `nawari-voice-correlation` — Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation
- **Primary Operational Purpose:** Cross-domain correlation linking endpoint Wi-Fi/network health with voice call quality and network incidents affecting telephony.
- **Target Audience:** Cross-Functional NOC, Tier 3 Incident Escalation
- **Core Questions Answered:** Is an agent's reported voice degradation caused by their local Wi-Fi packet loss or by carrier SIP trunk congestion?
- **Telemetry Sources:** Correlated metrics joining endpoint diagnostics with voice call quality streams.
- **Data Provenance:** Cross-Domain Correlated Analytics
- **Operational Tier:** Cross-Domain Operations (Tier 3)
- **Unique Capabilities:** Side-by-side time-correlated Wi-Fi and voice jitter telemetry, automated cross-domain root-cause hypotheses.
- **Functional Overlaps:** Draws from endpoint-detail and voice-service-assurance.
- **Consolidation Action:** Consolidate into Cross-Domain Correlation & Operations as the primary cross-domain dashboard.

### `nawari-comm-overview` — Nawari — Enterprise Communication Services Overview & Executive Service Assurance
- **Primary Operational Purpose:** Executive summary of communication infrastructure: core Avaya appliances, SIP trunks, call volume, and overall voice assurance.
- **Target Audience:** Head of Telecoms, Voice Engineers, Executive NOC
- **Core Questions Answered:** Are Avaya CM, SM, SBCE, and G450 operational? Are SIP trunks up? What is the current active call volume across the enterprise?
- **Telemetry Sources:** Zabbix aggregate telephony items, SIP OPTIONS status, SNMP appliance summaries.
- **Data Provenance:** Aggregated Telephony & Voice Telemetry
- **Operational Tier:** Domain Overview (Tier 2 Entry Point)
- **Unique Capabilities:** Unified multi-appliance voice overview, carrier trunk status summary.
- **Functional Overlaps:** Appliance statuses overlap with individual component dashboards.
- **Consolidation Action:** Retain as primary Communication Services Overview with drill-down links to Avaya and Voice Quality dashboards.

### `nawari-recording-wfo` — Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health
- **Primary Operational Purpose:** Voice recording (Verint / WFO) operational health, compliance recording percentage, audio capture buffer, and recording pipeline status.
- **Target Audience:** Compliance Officers, Quality Assurance Leads, Telecoms Engineers
- **Core Questions Answered:** Are 100% of regulated calls being recorded? Is the recording buffer filling? Are any audio capture streams dropping?
- **Telemetry Sources:** Zabbix Verint/WFO health items, recording stream active flags.
- **Data Provenance:** Application & Compliance Telemetry
- **Operational Tier:** Compliance & Diagnostic (Tier 3)
- **Unique Capabilities:** Audio recording compliance rate, recording buffer queue depth.
- **Functional Overlaps:** Correlates with contact centre active calls.
- **Consolidation Action:** Consolidate into Voice Quality & Contact Centre as the Recording & Compliance section.

### `nawari-voice-service-assurance` — Nawari — Voice Service Assurance & Media Quality
- **Primary Operational Purpose:** Comprehensive voice media quality: RTP packet loss, codec utilization (G.711 vs G.729), audio jitter buffer, and voice service SLIs.
- **Target Audience:** Voice Operations, Telecoms NOC
- **Core Questions Answered:** What audio codecs are in use? What is the aggregate voice packet loss? Are voice calls experiencing clipping?
- **Telemetry Sources:** Zabbix media stream telemetry, RTP loss metrics, codec counters.
- **Data Provenance:** Real & Synthetic Voice Media Telemetry
- **Operational Tier:** Domain Deep-Dive (Tier 3)
- **Unique Capabilities:** Codec distribution, media stream jitter buffer analysis.
- **Functional Overlaps:** Overlap with nawari_voice_intelligence.
- **Consolidation Action:** Consolidate into Voice Quality & Contact Centre.

### `nawari-service-catalog-sla` — Nawari — Aviation Business Service Catalogue & SLA/SLO Assurance
- **Primary Operational Purpose:** Aviation business service reliability, multi-dimensional SLIs (latency, availability, error rate), SLO compliance, and error budgets.
- **Target Audience:** IT Service Management, Business Relationship Managers, Operations Directors
- **Core Questions Answered:** Are core airline services (Flight Ops, Baggage Handling, Check-in, DCS) meeting their 99.9% SLO? How much error budget remains?
- **Telemetry Sources:** Zabbix SLA service items, SLI calculators, error budget burn rates.
- **Data Provenance:** Service Assurance SLI / SLA Telemetry
- **Operational Tier:** Business Service Tier (Tier 2/3)
- **Unique Capabilities:** Multi-dimensional service catalogue, error budget burn rates, tiered SLA compliance.
- **Functional Overlaps:** Service status overlaps with nawari-enterprise-overview.
- **Consolidation Action:** Consolidate into Network Services & Incident Assurance.

### `nawari-controlled-operations` — Nawari — Controlled Operational Actions & Automated Remediation
- **Primary Operational Purpose:** Audit log and status of automated remediation actions, circuit breakers, and controlled operational scripts.
- **Target Audience:** NOC Operations, Platform Engineers
- **Core Questions Answered:** Did an automated restart trigger for a failing collector? Is any circuit breaker currently tripped?
- **Telemetry Sources:** Zabbix action execution logs, remediation state flags.
- **Data Provenance:** Operational Action Audit Telemetry
- **Operational Tier:** Automation & Remediation (Tier 3)
- **Unique Capabilities:** Automated action execution ledger and circuit breaker state.
- **Functional Overlaps:** Actions correlate with incidents in nawari-incident-operations.
- **Consolidation Action:** Consolidate into Network Services & Incident Assurance.

### `nawari-edge-fleet` — Nawari — Distributed Edge Collector Fleet & Spool Storage
- **Primary Operational Purpose:** Distributed edge collector fleet health, SQLite spool storage buffers, and telemetry sync state.
- **Target Audience:** Observability Engineers, Platform Administrators
- **Core Questions Answered:** Are edge proxies/collectors running out of disk space? Is edge telemetry buffering or failing to sync upstream?
- **Telemetry Sources:** Edge spool storage gauge, store-and-forward queue depth, agent buffer status.
- **Data Provenance:** Platform Operational Telemetry
- **Operational Tier:** Infrastructure Support (Tier 3)
- **Unique Capabilities:** Store-and-forward buffer monitoring, spool disk capacity metrics.
- **Functional Overlaps:** Collector reachability overlaps with general infrastructure monitoring.
- **Consolidation Action:** Consolidate into WAN, Path & Outstation Observability as the edge telemetry reliability section.

### `nawari-endpoint-detail` — Nawari — Endpoint Deep-Dive & Edge Experience
- **Primary Operational Purpose:** Single-laptop forensic investigation: gateway loss, DNS latency, Wi-Fi RSSI/BSSID, OS lifecycle events, battery status.
- **Target Audience:** Desktop Support Specialists, Incident Responders
- **Core Questions Answered:** Why is Jimmy experiencing poor Zoom/Teams calls? Is it his local Wi-Fi signal, gateway loss, or DNS?
- **Telemetry Sources:** Zabbix Agent 2 active diagnostic probes (`nawari.nem.all`), Windows EventLog / macOS power logs.
- **Data Provenance:** Real Endpoint Diagnostic Telemetry
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** Granular single-device drill-down with $endpoint variable selector.
- **Functional Overlaps:** Probes overlap with nawari-eu-nem-pilot.
- **Consolidation Action:** Consolidate into Endpoint & User Experience as the single-device deep-dive section.

### `nawari-endpoint-fleet` — Nawari — Endpoint Fleet Observability Overview
- **Primary Operational Purpose:** High-level overview of enrolled corporate laptops, active reporting endpoints, presence breakdown, and top degraded devices.
- **Target Audience:** End-User Computing (EUC) Team, Service Desk, Desktop Support
- **Core Questions Answered:** How many employee laptops are reporting? What percentage are on corporate Wi-Fi vs remote? Which laptops are experiencing edge issues?
- **Telemetry Sources:** Zabbix Agent 2 active metrics, Presence Detector states, Lifecycle Classifier.
- **Data Provenance:** Real Endpoint Agent Telemetry
- **Operational Tier:** Domain Overview (Tier 3)
- **Unique Capabilities:** Fleet presence breakdown, anti-false-positive lifecycle counts (sleep, shutdown, off-net).
- **Functional Overlaps:** Metrics overlap with nawari-eu-nem-pilot and nawari-endpoint-detail.
- **Consolidation Action:** Consolidate into Endpoint & User Experience as the fleet summary section.

### `nawari-enterprise-overview` — Nawari — Enterprise Executive Overview & Fleet Availability
- **Primary Operational Purpose:** Global enterprise-wide health, aviation station availability, active P1/P2 incidents, service tier status, and notification delivery.
- **Target Audience:** Executive Leadership, Head of IT, Senior NOC Management
- **Core Questions Answered:** Is the global airline infrastructure healthy? Are any stations offline? Are there active P1/P2 incidents impacting operations? What is the regional availability trend?
- **Telemetry Sources:** Calculated Zabbix synthetic items, aggregate operational metrics, service health matrix.
- **Data Provenance:** Aggregated & Calculated Zabbix Telemetry
- **Operational Tier:** Executive Overview (Tier 1 Entry Point)
- **Unique Capabilities:** Enterprise service tier health matrix, regional health trends, global outstation availability rate.
- **Functional Overlaps:** Outstation metrics overlap with nawari-global-outstations; incident counts overlap with nawari-incident-operations.
- **Consolidation Action:** Retain as primary Grafana Home Dashboard with direct drill-down links to domain overviews.

### `nawari-global-outstations` — Nawari — Global Outstation Network & WAN Telemetry
- **Primary Operational Purpose:** Worldwide outstation connectivity, regional latency (Domestic, East Africa, International), and outstation SLA compliance.
- **Target Audience:** Global Operations Center, Airport IT Support
- **Core Questions Answered:** Are international outstations (LHR, DXB, JNB) reachable? Is trans-regional WAN latency within acceptable limits?
- **Telemetry Sources:** Zabbix ICMP ping, WAN probe latency, outstation availability status.
- **Data Provenance:** Real & Synthetic Network Telemetry
- **Operational Tier:** Domain Deep-Dive (Tier 3)
- **Unique Capabilities:** Regional station grouping, airport hub connectivity indicators, WAN SLA.
- **Functional Overlaps:** Regional health trends overlap with nawari-enterprise-overview.
- **Consolidation Action:** Consolidate into WAN, Path & Outstation Observability.

### `nawari-incident-operations` — Nawari — Incident Operations, Escalation & Verified Recovery
- **Primary Operational Purpose:** Active incident lifecycle tracking, MTTR metrics, automated escalation triggers, and verified recovery states.
- **Target Audience:** Incident Managers, NOC Shift Leads
- **Core Questions Answered:** What active P1/P2/P3 incidents exist? Are incidents escalating according to policy? Has a service truly recovered or is it flapping?
- **Telemetry Sources:** Zabbix problem events, recovery events, incident lifecycle state machine.
- **Data Provenance:** Event-Derived Incident Telemetry
- **Operational Tier:** Operational Assurance (Tier 3)
- **Unique Capabilities:** Recovery verification logic, MTTR tracking, escalation phase tracking.
- **Functional Overlaps:** Incident count overlaps with nawari-enterprise-overview.
- **Consolidation Action:** Consolidate into Network Services & Incident Assurance.

### `nawari-interface-health` — Nawari — Interface Traffic & Performance Health
- **Primary Operational Purpose:** Interface throughput, traffic rates, error counters, discard rates, and utilization percentages.
- **Target Audience:** Network Engineers, Capacity Planners
- **Core Questions Answered:** Which switch ports or uplinks are congested? Are there packet discards or CRC errors on network interfaces?
- **Telemetry Sources:** Zabbix SNMP ifHCInOctets, ifHCOutOctets, ifInErrors, ifOutErrors, ifInDiscards, ifOutDiscards.
- **Data Provenance:** Real Zabbix SNMP 64-bit Counters
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** Deep-dive interface traffic analysis with variable filtering for device and interface.
- **Functional Overlaps:** Core link bandwidth indicators overlap with nawari-net-overview.
- **Consolidation Action:** Integrate as detailed diagnostic row in Network Operations Overview with variables ($group, $host, $interface).

### `nawari-net-overview` — Nawari — Network Infrastructure Overview
- **Primary Operational Purpose:** Core network infrastructure device inventory, CPU, memory, uptime, and device availability.
- **Target Audience:** NOC Network Engineers, Infrastructure Administrators
- **Core Questions Answered:** Are core switches and distribution gateways responsive? Are CPU/memory resources strained? Which network devices are down?
- **Telemetry Sources:** Zabbix SNMP (sysUpTime, hrProcessorLoad, hrStorageUsed), ICMP ping.
- **Data Provenance:** Real Zabbix SNMP Telemetry
- **Operational Tier:** Domain Overview (Tier 2)
- **Unique Capabilities:** Core distribution gateway and lab switch resource metrics, SNMP availability.
- **Functional Overlaps:** Device availability overlaps with nawari-network-topology and nawari-interface-health.
- **Consolidation Action:** Consolidate into Network Operations Overview as core infrastructure section.

### `nawari-path-analysis` — Nawari — Network Path & Directional Hop Analysis
- **Primary Operational Purpose:** Hop-by-hop path tracing, directional latency, jitter, loss, and route divergence analysis.
- **Target Audience:** Senior Network Engineers, Telecommunications Specialists
- **Core Questions Answered:** Where is the bottleneck in the path between endpoints and core services? Which intermediate hop is dropping packets?
- **Telemetry Sources:** Zabbix traceroute synthetic items, directional ICMP hop probes.
- **Data Provenance:** Synthetic & Measured Path Telemetry
- **Operational Tier:** Technical Diagnostic (Tier 4)
- **Unique Capabilities:** Hop-by-hop breakdown, directional asymmetry analysis.
- **Functional Overlaps:** Path latency overlaps with nawari-global-outstations WAN latency.
- **Consolidation Action:** Consolidate into WAN, Path & Outstation Observability.

### `nawari-network-topology` — Nawari — Network Topology & Service Dependencies
- **Primary Operational Purpose:** Visualization of network topology layers, device interconnections, and service dependencies.
- **Target Audience:** NOC Operators, System Architects
- **Core Questions Answered:** How do edge devices connect to core gateways and datacenters? What path does traffic take across core layers?
- **Telemetry Sources:** Zabbix host dependencies, network topology map definitions.
- **Data Provenance:** Calculated Structural Topology
- **Operational Tier:** Visual Overview / Dependency Map
- **Unique Capabilities:** Topology layer hierarchy and cross-layer structural links.
- **Functional Overlaps:** Topology relationships overlap with nawari-service-catalog-sla dependencies.
- **Consolidation Action:** Embed as visual topology row in Network Operations Overview.

### `nawari-predictive-intelligence` — Nawari — Predictive Intelligence, Dynamic Baselines & Degradation Assurance
- **Primary Operational Purpose:** Dynamic baseline calculation, seasonal anomaly detection, predictive bandwidth exhaustion, and early warning degradation indicators.
- **Target Audience:** Capacity Planners, Observability Engineers
- **Core Questions Answered:** Which links are exhibiting abnormal traffic compared to historical Thursdays? Is a capacity exhaustion predicted in the next 14 days?
- **Telemetry Sources:** Statistical Zabbix trend functions, Holt-Winters baseline projections.
- **Data Provenance:** Predictive Statistical Telemetry
- **Operational Tier:** Advanced Analytics (Tier 3)
- **Unique Capabilities:** Dynamic threshold baselines, degradation assurance indicators.
- **Functional Overlaps:** Metric sources are network links and services.
- **Consolidation Action:** Consolidate into Network Services & Incident Assurance.
