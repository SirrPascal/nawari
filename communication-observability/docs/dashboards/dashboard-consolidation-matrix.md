# Nawari Dashboard Consolidation & Rationalisation Matrix

**Rationalisation Target:** Consolidate 25 fragmented dashboards into a 9-Dashboard Progressive Drill-Down Architecture.
**Guiding Principle:** **One Operational Entry Point → Domain Overview → Technology Deep-Dive → Component Diagnostics.**

---

| Original Dashboard UID | Original Dashboard Title | Unique Functionality Preserved | Destination Consolidated Dashboard | Migration Status & Row Mapping |
|---|---|---|---|---|
| `nawari-enterprise-overview` | Enterprise Executive Overview & Fleet Availability | Global service tier health, P1/P2 incidents, outstation availability | **Enterprise Executive Overview** | Retained as Tier 1 Home Entry Point (UID: `nawari-enterprise-overview`) |
| `nawari-net-overview` | Network Infrastructure Overview | Core router/switch CPU, memory, uptime, availability | **Network Operations Overview** | Consolidated (Row: Core Infrastructure Devices) |
| `nawari-interface-health` | Interface Traffic & Performance Health | 64-bit interface counters, bandwidth, discards, CRC errors | **Network Operations Overview** | Consolidated (Row: Interface Health & Link Traffic) |
| `nawari-network-topology` | Network Topology & Service Dependencies | Cross-layer visual topology and device interconnections | **Network Operations Overview** | Consolidated (Row: Network Topology & Layer Hierarchy) |
| `nawari-global-outstations` | Global Outstation Network & WAN Telemetry | International airport hub connectivity, regional WAN latency | **WAN, Path & Outstation Observability** | Consolidated (Row: Outstation Telemetry & Regional Latency) |
| `nawari-path-analysis` | Network Path & Directional Hop Analysis | Directional hop latency, jitter, loss, path divergence | **WAN, Path & Outstation Observability** | Consolidated (Row: Directional Path & Hop Analysis) |
| `nawari-edge-fleet` | Distributed Edge Collector Fleet & Spool Storage | Store-and-forward queue depth, SQLite spool buffer health | **WAN, Path & Outstation Observability** | Consolidated (Row: Distributed Edge Collector Fleet) |
| `nawari-endpoint-fleet` | Endpoint Fleet Observability Overview | Fleet presence breakdown, active laptops, top degraded devices | **Endpoint & User Experience** | Consolidated (Row: Endpoint Fleet Health & Presence) |
| `nawari-endpoint-detail` | Endpoint Deep-Dive & Edge Experience | Forensic single-device drill-down ($endpoint selector) | **Endpoint & User Experience** | Consolidated (Row: Forensic Endpoint Investigation) |
| `nawari-eu-nem-pilot` | End-User Network Experience | Live active agent probe metrics, gateway RTT/loss, DNS latency | **Endpoint & User Experience** | Consolidated (Row: Real-Time Active Probe Diagnostics) |
| `nawari-service-catalog-sla` | Aviation Business Service Catalogue & SLA/SLO Assurance | Tiered business service SLIs/SLOs, error budget burn rates | **Network Services & Incident Assurance** | Consolidated (Row: Aviation Service Catalogue & Error Budgets) |
| `nawari-incident-operations` | Incident Operations, Escalation & Verified Recovery | Active P1/P2 timeline, automated escalation, verified recovery | **Network Services & Incident Assurance** | Consolidated (Row: Incident Lifecycle & Recovery Assurance) |
| `nawari-predictive-intelligence` | Predictive Intelligence, Dynamic Baselines & Degradation Assurance | Seasonal Holt-Winters baselines, capacity exhaustion predictions | **Network Services & Incident Assurance** | Consolidated (Row: Predictive Intelligence & Dynamic Baselines) |
| `nawari-controlled-operations` | Controlled Operational Actions & Automated Remediation | Automated remediation audit ledger, circuit breaker states | **Network Services & Incident Assurance** | Consolidated (Row: Automated Operations & Circuit Breakers) |
| `nawari-comm-overview` | Enterprise Communication Services Overview & Executive Service Assurance | Unified voice appliance status, carrier trunk health, total calls | **Communication Services Overview** | Retained as Tier 2 Voice Entry Point (UID: `nawari-comm-overview`) |
| `nawari-sbce-health` | Avaya SBCE Operational Health | SBCE CPU/memory, TLS handshakes, perimeter security limits | **Avaya Infrastructure & Signaling** | Consolidated (Row: Session Border Controller - SBCE) |
| `nawari-session-manager` | Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing | SIP entity routing matrix, ASM JVM heap, transaction rates | **Avaya Infrastructure & Signaling** | Consolidated (Row: Session Manager - ASM) |
| `nawari-communication-manager` | Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance | CM processor occupancy, registered endpoints, hourly IP voice | **Avaya Infrastructure & Signaling** | Consolidated (Row: Communication Manager - ACM) |
| `nawari-g450-gateway` | Avaya G450 Media Gateway Appliance & Physical Telephony Health | Chassis power/fans, DSP VoIP channels, E1/T1 PRI clock sync | **Avaya Infrastructure & Signaling** | Consolidated (Row: G450 Media Gateway Appliance) |
| `nawari-sip-trunks` | Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing | Carrier SIP OPTIONS latency, signaling ladder, 503 error rates | **Avaya Infrastructure & Signaling** | Consolidated (Row: Carrier SIP Trunks & Signaling) |
| `nawari-voice-intelligence` | Communications Intelligence & Voice Service Assurance | Synthetic Asterisk call probes, PESQ/POLQA, uninstrumented real MOS | **Voice Quality & Contact Centre** | Consolidated (Row: Voice Intelligence & Synthetic Testing) |
| `nawari-voice-service-assurance` | Voice Service Assurance & Media Quality | RTP packet loss, codec distribution (G.711/G.729), jitter buffer | **Voice Quality & Contact Centre** | Consolidated (Row: Voice Media Quality & Stream Diagnostics) |
| `nawari-cms-contact-centre` | Avaya Call Management System (CMS) & Contact Centre Performance | ACD split/skill queue depth, ASA, abandonment rate, agent state | **Voice Quality & Contact Centre** | Consolidated (Row: CMS Contact Centre Performance) |
| `nawari-recording-wfo` | Voice Recording & Workforce Optimisation (WFO) Operational Health | Verint recording compliance %, audio buffer, stream status | **Voice Quality & Contact Centre** | Consolidated (Row: Voice Recording & Compliance) |
| `nawari-voice-correlation` | Cross-Domain Voice & Endpoint Telemetry Correlation | Correlated endpoint Wi-Fi loss vs voice jitter, cross-domain root-cause | **Cross-Domain Correlation & Operations** | Retained as Tier 3 Correlation Hub (UID: `nawari-voice-correlation`) |

---

## Consolidated 9-Dashboard Architecture Overview

### Tier 1 — Executive Overview
1. **Enterprise Executive Overview** (`nawari-enterprise-overview`): Default Grafana Home dashboard. Overall service health, outstation availability, active incidents.

### Tier 2 — Domain Overviews & Tier 3 Technology Deep-Dives
#### Network Observability Folder (`Nawari / Network Observability`)
2. **Network Operations Overview** (`nawari-network-operations`): Unifies Core Infrastructure, Interface Traffic, and Topology.
3. **WAN, Path & Outstation Observability** (`nawari-wan-path-outstation`): Unifies Global Outstations, Hop-by-Hop Path Tracing, and Edge Collector Fleet.
4. **Endpoint & User Experience** (`nawari-endpoint-experience`): Unifies Fleet Health, Single-Device Forensics, and Real-Time Active NEM Probes.
5. **Network Services & Incident Assurance** (`nawari-network-services-assurance`): Unifies Business Service SLIs/SLOs, Incident Operations, Predictive Baselines, and Controlled Operations.

#### Communication Observability Folder (`Nawari / Communication Observability`)
6. **Communication Services Overview** (`nawari-comm-overview`): Unifies Executive Voice Assurance, Carrier Trunk summary, and Core Appliance health.
7. **Avaya Infrastructure & Signaling** (`nawari-avaya-infrastructure`): Unifies SBCE, Session Manager, Communication Manager, G450 Media Gateway, and Carrier SIP Trunks.
8. **Voice Quality & Contact Centre** (`nawari-voice-contact-centre`): Unifies Voice Intelligence Synthetic Probes, Media Stream Quality, CMS ACD Queues, and Verint WFO Compliance.
9. **Cross-Domain Correlation & Operations** (`nawari-voice-correlation`): Unifies Endpoint Wi-Fi Correlation, Voice Degradation Hypotheses, and Cross-Domain Incident Escalation.