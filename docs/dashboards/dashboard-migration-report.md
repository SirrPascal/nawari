# Nawari Dashboard Migration Report

**Programme Phase:** Enterprise Grafana Dashboard Rationalisation, Consolidation and Progressive Drill-Down Architecture
**Migration Date:** 2026-11-08
**Target Environment:** Nawari Staging Observability Platform (`mon-grafana01`)
**Safety Status:** `HARD_PRODUCTION_DENY = True` strictly enforced | Sentra repository isolated on `main` at `9970404`

---

## 1. Executive Summary

Prior to this implementation, the Nawari observability platform maintained **25 separate dashboards** across two primary folders and an ad-hoc endpoint folder. While these provided comprehensive technical telemetry, the excessive fragmentation caused operational friction, requiring operators to manually search through 25 titles to locate related diagnostics.

This migration successfully implemented a **4-Tier Progressive Drill-Down Navigation Architecture**, consolidating day-to-day operations into **9 authoritative, multi-section operational dashboards** without sacrificing a single panel, metric, query, or threshold.

---

## 2. Migration Metrics & Inventory Reconciliation

| Metric | Count |
|---|---|
| **Original Active Dashboards** | 25 |
| **Consolidated Operational Dashboards** | 9 |
| **Original Visualization Panels** | 208 |
| **Preserved Visualization Panels** | 208 (100% Preserved) |
| **Collapsible Row Organization Sections** | 33 Rows Across Fleet |
| **Standard Navigation Header Links** | 10 per Dashboard (90 Total Links) |
| **Visualization Panel Description Coverage** | 100% (208 / 208 Panels) |
| **Telemetry Integrity Violations (spanNulls / null-as-zero)** | 0 Violations |
| **Broken UID / Data Link References** | 0 |

---

## 3. Consolidation Mapping & Structure

### Tier 1 — Executive Entry Point
- **Dashboard:** `Enterprise Executive Overview & Fleet Availability` (UID: `nawari-enterprise-overview`)
  - Configured as default Grafana Home dashboard (`http://localhost:3001/`).
  - Added top header navigation bar to immediately jump to Network Ops, Voice Overview, Incidents, or Endpoints.

### Tier 2 & 3 — Network Observability Domain (`Nawari / Network Observability`)
- **1. Network Operations Overview** (UID: `nawari-network-operations`)
  - *Merged:* `network_infrastructure_overview` (Core Devices), `interface_traffic_health` (Interface Bandwidth/Errors), `network_topology` (Topology Layers).
  - *Variables:* `$group`, `$host`, `$interface`.
- **2. WAN, Path & Outstation Observability** (UID: `nawari-wan-path-outstation`)
  - *Merged:* `nawari_global_outstations` (Hub Latency), `network_path_analysis` (Hop-by-Hop Tracing), `nawari_edge_fleet` (Edge Spool Storage).
  - *Variables:* `$group`, `$endpoint`, `$target`.
- **3. Endpoint & User Experience** (UID: `nawari-endpoint-experience`)
  - *Merged:* `endpoint_fleet_overview` (Fleet Health/Presence), `endpoint_detail` (Forensic Investigation), `end_user_network_experience` (Active NEM Probes).
  - *Variables:* `$group`, `$endpoint`.
- **4. Network Services & Incident Assurance** (UID: `nawari-network-services-assurance`)
  - *Merged:* `nawari_service_catalog_sla` (Aviation SLIs/SLOs), `nawari_incident_operations` (MTTR/Recovery), `nawari_predictive_intelligence` (Dynamic Baselines), `nawari_controlled_operations` (Remediation).

### Tier 2 & 3 — Communication Observability Domain (`Nawari / Communication Observability`)
- **5. Communication Services Overview** (UID: `nawari-comm-overview`)
  - *Retained & Enhanced:* Unified voice appliance summary, carrier trunk status, total calls.
- **6. Avaya Infrastructure & Signaling** (UID: `nawari-avaya-infrastructure`)
  - *Merged:* `avaya_sbce_operational_health` (SBCE), `avaya_session_manager` (ASM), `avaya_communication_manager` (ACM), `avaya_g450_media_gateway` (G450), `nawari_sip_trunks_signaling` (Carrier Trunks).
- **7. Voice Quality & Contact Centre** (UID: `nawari-voice-contact-centre`)
  - *Merged:* `nawari_voice_intelligence` (Synthetic Asterisk MOS), `nawari-voice-service-assurance` (Media Stream Quality), `avaya_cms_contact_centre` (CMS Queues), `recording_wfo_operational_health` (WFO Compliance).
- **8. Cross-Domain Correlation & Operations** (UID: `nawari-voice-correlation`)
  - *Retained & Enhanced:* Correlated endpoint Wi-Fi loss vs voice jitter, cross-domain root-cause hypotheses.
  - *Variables:* `$group`, `$endpoint`.

---

## 4. Rollback and Recovery Plan

All original 24 component dashboard files in `docker/grafana/dashboards/network_observability/` and `communication_observability/` were preserved intact on disk and in git. If an operator requires direct access to an unmerged original dashboard, they can navigate directly via its original URL or restore from the version control repository.