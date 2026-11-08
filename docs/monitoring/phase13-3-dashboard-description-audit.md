# Nawari Phase 13.3 — Dashboard Description & Telemetry Integrity Audit

**Document Standard:** Nawari Enterprise Observability & Service Assurance  
**Audit Standard:** 100% Panel Operational Description Coverage & Explicit Missing Data Behavior  
**Scope:** All 24 Dashboards across Network Observability & Communication Observability (200 Visualization Panels)  
**Execution Standard:** Evidence-Backed Operational Truth & Traceable Telemetry Provenance  

---

## 1. Executive Summary & Audit Mandate

In enterprise NOC/VOC environments, an operator viewing a dashboard panel must immediately comprehend what the number represents, its measurement origin, its healthy/unhealthy boundaries, and what it means if the panel is empty. Ambiguous gauges, undocumented graphs, or deceptive zero-filling during outages cause operational confusion and delay incident remediation.

Phase 13.3 mandates that **100% of all visualization panels** across all 24 Grafana dashboards must satisfy six rigorous criteria:
1. **What it measures:** Concrete physical or logical parameter.
2. **Values and units:** Exact units of measurement (e.g. milliseconds, bits/sec, percentage, discrete state integer).
3. **Data origin/methodology:** Authoritative collection interface (SNMP OID, CLI trapper, active probe, or ODBC query).
4. **Threshold interpretation:** Clear guidance on what constitutes healthy, degraded, or critical states.
5. **Real vs. Synthetic vs. Event-derived nature:** Explicit classification to prevent confusing simulated tests with live production traffic.
6. **Explicit missing data behavior:** Unambiguous statement explaining why data might be missing, and what empty/null values represent.

---

## 2. Audit Summary & Compliance Scorecard

```
+----------------------------------------------------------------------------------------------------+
|                                DASHBOARD DESCRIPTION AUDIT SUMMARY                                 |
+----------------------------------------------------------------------------------------------------+
| Metric Scope                                        | Total Audited | Compliant | Compliance Rate  |
+-----------------------------------------------------+---------------+-----------+------------------+
| Total Monitored Dashboards                          |      24       |    24     |     100.0%       |
| Network Observability Dashboards                    |      13       |    13     |     100.0%       |
| Communication Observability Dashboards              |      11       |    11     |     100.0%       |
| Total Visualization Panels (excluding row dividers) |     200       |   200     |     100.0%       |
| Panels with Complete Descriptions                   |     200       |   200     |     100.0%       |
| Panels with Explicit Missing Data Statements        |     200       |   200     |     100.0%       |
| Panels with Zero-Filling on Outage (Forbidden)      |       0       |     0     |       0.0%       |
+-----------------------------------------------------+---------------+-----------+------------------+
```

---

## 3. Detailed Dashboard & Panel Breakdown

### 3.1 Network Observability Domain (13 Dashboards, 87 Panels)

| Dashboard File | Title | Panels | Description Coverage | Missing Data Statement Coverage |
| :--- | :--- | :---: | :---: | :---: |
| `endpoint_detail.json` | Endpoint Detail | 17 | 17 / 17 (100%) | 17 / 17 (100%) |
| `endpoint_fleet_overview.json` | Endpoint Fleet Overview | 13 | 13 / 13 (100%) | 13 / 13 (100%) |
| `interface_traffic_health.json` | Interface Traffic Health | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| `nawari_controlled_operations.json` | Nawari Controlled Operations | 5 | 5 / 5 (100%) | 5 / 5 (100%) |
| `nawari_edge_fleet.json` | Nawari Edge Fleet | 4 | 4 / 4 (100%) | 4 / 4 (100%) |
| `nawari_enterprise_overview.json` | Nawari Enterprise Overview | 5 | 5 / 5 (100%) | 5 / 5 (100%) |
| `nawari_global_outstations.json` | Nawari Global Outstations | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| `nawari_incident_operations.json` | Nawari Incident Operations | 3 | 3 / 3 (100%) | 3 / 3 (100%) |
| `nawari_predictive_intelligence.json`| Nawari Predictive Intelligence | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| `nawari_service_catalog_sla.json` | Nawari Service Catalog & SLA | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| `network_infrastructure_overview.json`| Network Infrastructure Overview | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| `network_path_analysis.json` | Network Path Analysis | 8 | 8 / 8 (100%) | 8 / 8 (100%) |
| `network_topology.json` | Network Topology | 2 | 2 / 2 (100%) | 2 / 2 (100%) |
| **Domain Subtotal** | **13 Dashboards** | **87** | **87 / 87 (100%)** | **87 / 87 (100%)** |

### 3.2 Communication Observability Domain (11 Dashboards, 113 Panels)

| Dashboard File | Title | Panels | Description Coverage | Missing Data Statement Coverage |
| :--- | :--- | :---: | :---: | :---: |
| `avaya_cms_contact_centre.json` | Avaya CMS Contact Centre Analytics | 9 | 9 / 9 (100%) | 9 / 9 (100%) |
| `avaya_communication_manager.json`| Avaya Communication Manager Core | 11 | 11 / 11 (100%) | 11 / 11 (100%) |
| `avaya_g450_media_gateway.json` | Avaya G450 Media Gateway Operations | 8 | 8 / 8 (100%) | 8 / 8 (100%) |
| `avaya_sbce_operational_health.json`| Avaya SBCE Operational Health | 15 | 15 / 15 (100%) | 15 / 15 (100%) |
| `avaya_session_manager.json` | Avaya Session Manager Routing & Core | 9 | 9 / 9 (100%) | 9 / 9 (100%) |
| `endpoint_voice_correlation.json` | Endpoint & Voice Correlation | 9 | 9 / 9 (100%) | 9 / 9 (100%) |
| `nawari-voice-service-assurance.json`| Voice Service Assurance SLI/SLO | 12 | 12 / 12 (100%) | 12 / 12 (100%) |
| `nawari_communication_overview.json`| Unified Communication Overview | 12 | 12 / 12 (100%) | 12 / 12 (100%) |
| `nawari_sip_trunks_signaling.json`| SIP Trunks & Carrier Signalling | 7 | 7 / 7 (100%) | 7 / 7 (100%) |
| `nawari_voice_intelligence.json` | Voice Quality & Media Intelligence | 11 | 11 / 11 (100%) | 11 / 11 (100%) |
| `recording_wfo_operational_health.json`| Recording & WFO Platform Health | 10 | 10 / 10 (100%) | 10 / 10 (100%) |
| **Domain Subtotal** | **11 Dashboards** | **113** | **113 / 113 (100%)** | **113 / 113 (100%)** |

---

## 4. Null Integrity & Missing Data Verification

### 4.1 Strict Prohibition of False Zero-Filling
A critical flaw in monitoring design is using Grafana transformations or Prometheus functions (e.g. `or on() vector(0)`) to substitute zero when an endpoint stops responding.
- In network monitoring: Substituting `0 ms` latency during an outage makes a down circuit appear infinitely fast.
- In voice monitoring: Substituting `0%` packet loss or `0` call attempts hides carrier trunk disconnects.

### 4.2 End-to-End Null Preservation
Nawari enforces null integrity at every layer:
1. **Collector Layer:** When an SNMP query times out or an endpoint is unreachable, Zabbix records no item value or marks the item unsupported.
2. **Database Layer:** TimescaleDB / PostgreSQL stores NULL without default-zero coercions.
3. **Visualization Layer:** Grafana panel configurations employ `"nullValueMode": "null"` (or `"connectNulls": false`). Panels render an empty gap or explicit "No Data" label.
4. **Description Layer:** Every panel's operational description contains an explicit explanation:
   > *"If no data is displayed or the panel renders empty, telemetry collection is disrupted, the monitored endpoint is unreachable, or the polling interval has not completed. Empty states must not be interpreted as zero."*

