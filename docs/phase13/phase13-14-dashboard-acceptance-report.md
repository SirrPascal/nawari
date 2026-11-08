# Phase 13.14 — Dashboard & Reporting Operational Acceptance Report

## Executive Summary

Phase 13.14 delivers the authoritative operational audit and acceptance verification for the complete visualization tier of the Nawari platform. Across Grafana 11.6, 24 dashboards containing 282 individual visualization panels were inspected, classified, and validated against strict enterprise standards.

Key achievements:
- **Strict Folder Isolation**: All dashboards are segmented into two distinct folders: `Nawari / Communication Observability` (11 dashboards) and `Nawari / Network Observability` (13 dashboards), with 0 cross-folder contamination.
- **Data Provenance Guarantee**: All 282 panels are classified into definitive provenance categories: `PHYSICAL_LIVE` (219 panels), `SYNTHETIC_PROBE` (42 panels), and `CALCULATED` (21 panels), with 0 untracked or ambiguous panels.
- **Datasource Integrity**: Every panel query maps cleanly to either the official Zabbix 7.4 plugin (`alexanderzobnin-zabbix-datasource`) or PostgreSQL 17 (`postgres`).

---

## 1. Dashboard Catalogue by Operational Folder

### A. Communication Observability Folder (`nawari-comm-obs`)

| Dashboard UID | Dashboard Title | Panel Count | Primary Scope |
| :--- | :--- | :--- | :--- |
| `nawari-cms-contact-centre` | Avaya Call Management System (CMS) & Contact Centre | 12 | Elite ACD queues, split/skill stats |
| `nawari-communication-manager` | Avaya Aura Communication Manager (CM) Call Processing | 14 | Active calls, IP voice codec usage, DSP |
| `nawari-g450-gateway` | Avaya G450 Media Gateway Appliance & Physical Telephony | 11 | Power supplies, fan trays, thermal state |
| `nawari-sbce-health` | Avaya SBCE Operational Health | 19 | Dual HA cluster, licensing, perimeter SIP |
| `nawari-session-manager` | Avaya Aura Session Manager (ASM) Operational Health | 12 | SIP entity routing, TLS certificates |
| `endpoint-voice-correlation` | Cross-Domain Voice & Endpoint Telemetry Correlation | 14 | Call-ID to IP path correlation |
| `nawari-voice-service-assurance`| Voice Service Assurance & Media Quality | 16 | Extended E-model R-factor & MOS |
| `nawari_communication_overview`| Enterprise Communication Services Overview | 16 | Executive SLA/SLO telecommunications |
| `nawari-sip-trunks` | Carrier SIP Trunks & Signaling Ladders | 10 | Safaricom/Airtel trunk utilization |
| `nawari-voice-intelligence` | Communications Intelligence & Voice Assurance | 15 | RTCP-XR stream analytics |
| `nawari-recording-wfo` | Voice Recording & Workforce Optimisation (WFO) | 13 | Verint recording spool, disk storage |

### B. Network Observability Folder (`nawari-network-obs`)

| Dashboard UID | Dashboard Title | Panel Count | Primary Scope |
| :--- | :--- | :--- | :--- |
| `endpoint_detail` | Endpoint Deep-Dive & Edge Experience Analysis | 23 | Wi-Fi vs Ethernet, synthetic probes |
| `endpoint_fleet_overview` | Endpoint Fleet Observability Overview | 19 | Fleet health across airport terminals |
| `nawari-interface-health` | Interface Traffic & Performance Health | 9 | 64-bit HC octets, interface utilization |
| `nawari_controlled_operations` | Controlled Operational Actions & Automation Playbooks | 8 | Action logs, spool flusher execution |
| `nawari_edge_fleet` | Distributed Edge Collector Fleet & Sidecar Runtime | 6 | Edge collector heartbeat & telemetry sync |
| `nawari-enterprise-overview` | Enterprise Executive Overview & Fleet Reliability | 7 | High-level KQ enterprise health |
| `nawari-global-outstations` | Global Outstation Network & WAN Telemetry | 9 | Domestic & international station links |
| `nawari-incident-operations` | Incident Operations, Escalation & Verified Recovery | 5 | Incident lifecycle & MTTR tracking |
| `nawari-predictive-intelligence`| Predictive Intelligence & Dynamic Baselines | 9 | Time-series forecasting & anomaly score |
| `nawari-service-catalog-sla` | Aviation Business Service Catalogue & SLA/SLO | 9 | Google SRE error budgets & burn rates |
| `nawari-net-overview` | Network Infrastructure Overview | 9 | Core/distribution switch availability |
| `nawari-path-analysis` | Network Path & Directional Hop Analysis | 13 | Paris traceroute, CoPP guard, MPLS labels |
| `nawari-network-topology` | Network Topology & Service Dependencies | 4 | L2/L3 topology graph & node links |
