# Nawari NOC Dashboard Operator's Guide

**Scope:** Unified Grafana Dashboards for Kenya Airways Global Operations  
**Dashboards Directory:** `docker/grafana/dashboards/`  
**Container Host:** `mon-grafana01` (Grafana port 3000)  
**Security Tier:** Multi-Site Scoped RBAC Enabled  

---

## 1. Overview of the NOC Suite

Phase 13 introduces five enterprise Grafana dashboards designed to give the Network Operations Centre (NOC), Station Duty Engineers, and Executive Leadership complete visibility across global flight operations, telecom trunks, WAN outstations, and business applications.

| Dashboard Title | File Name | Primary Audience | Core Focus |
| :--- | :--- | :--- | :--- |
| **Enterprise Global Overview** | `nawari_enterprise_overview.json` | Chief Information Officer, Head of IT, Central NOC Leads | Enterprise SLA compliance, global outstation status map, degraded mission-critical services, active P1/P2 incidents. |
| **Global Outstation Directory** | `nawari_global_outstations.json` | Regional Managers, Station Duty Engineers, Network Ops | Station tiering, primary/secondary circuit health, facility status, IATA/ICAO code tracking, RTT & bandwidth telemetry. |
| **Business Service Catalog & SLA** | `nawari_service_catalog_sla.json` | Service Owners, Airport Duty Managers, IT Leadership | Multi-dimensional SLIs (Availability, Performance, Quality, Coverage), Error Budget burn rates, contractual SLA breaches. |
| **Incident Operations Center** | `nawari_incident_operations.json` | NOC Shift Engineers, Incident Commanders | Incident lifecycle state (NEW $\rightarrow$ CLOSED), MTTA/MTTR metrics, escalation queue, notification dead letters. |
| **Edge Fleet & Spool Management** | `nawari_edge_fleet.json` | Edge Engineers, Systems Administrators | SQLite spool buffer sizes, priority pruning rates, replayed telemetry volume, clock drift, transmitter backoff status. |

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
