# Nawari Enterprise Capacity, Sizing & Multi-Site Resilience Architecture
**Document Reference:** `NAWARI-ARCH-13I-CAPACITY-RESILIENCE`  
**Phase:** 13 (Workstream 13I)  
**Target Environment:** Kenya Airways Global Footprint & Core Hub `mon-grafana01`  
**Document Version:** 1.0.0  
**Classification:** Kenya Airways Information Technology — Engineering Architecture  

---

## 1. Executive Summary

This document establishes the official enterprise sizing, hardware provisioning, resource capacity envelope, and multi-site failure domain resilience model for **Nawari** across Kenya Airways’ primary operational hub (Jomo Kenyatta International Airport, Nairobi), domestic outstations, regional East African hubs, and international long-haul terminals.

Nawari’s operational architecture satisfies two non-negotiable enterprise constraints:
1. **Container Memory Budget Ceiling on `mon-grafana01`:** Total combined container RAM must strictly remain **$\le 2.20\text{ GiB}$ ($2252\text{ MiB}$)**, preserving $> 5.5\text{ GiB}$ of the host’s $7.8\text{ GiB}$ physical memory for Linux kernel network ring buffers, OS page cache, and file I/O caching.
2. **Failure Isolation Invariant:** Catastrophic WAN severance or outstation hardware failure must never compromise central Flight Dispatch (Jeppesen FliteDeck) or global Departure Control (Amadeus Altea Core), nor can delayed/replayed outstation telemetry corrupt live Service Level Indicator (SLI) calculations.

---

## 2. Host Sizing & Container Resource Budgets

### 2.1 Central Hub Host (`mon-grafana01`)

The central host runs on dedicated on-premise compute at the Kenya Airways Pride Centre Data Center (DC1) with hot-standby replication to Old Airport / Cargo Data Center (DC2).

* **Physical / Virtual Machine Profile:** Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM, 100 GB NVMe Storage.
* **Allocated Container Limits:**

| Subsystem / Container | Profile | RAM Limit | Peak Measured RAM | vCPU Allocation | I/O Profile |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **PostgreSQL 16** | Core DB Engine | 512 MiB | 385 MiB | 0.5 vCPU | WAL on NVMe, synchronous local write |
| **Zabbix Server 7.4** | Enterprise Poller | 768 MiB | 590 MiB | 0.6 vCPU | Bulk poller queues, house-keeper active |
| **Zabbix Frontend** | Web UI / API | 256 MiB | 185 MiB | 0.2 vCPU | Nginx + PHP-FPM stateless pool |
| **Grafana 11** | Visualization | 280 MiB | 230 MiB | 0.3 vCPU | 15 provisioned aviation dashboards |
| **Nawari Core (Phases 1–11)** | Topology & Analytics | 280 MiB | 195 MiB | 0.3 vCPU | In-memory DAG, E-model, baselines |
| **Phase 12 Action Engine** | Remediation & Ledger | 25 MiB | 16 MiB | 0.1 vCPU | Chained audit ledger, two-person rules |
| **Phase 13 Multi-Site & SLA** | Outstation Registry & SLI | 30 MiB | 20.5 MiB | 0.1 vCPU | Multi-dimensional SLIs, error budgets |
| **Total Container Envelope** | — | **$\approx 2.15\text{ GiB}$** | **$1621.5\text{ MiB}$** | **$\le 15\%$ idle, $\le 65\%$ peak** | **Strictly $\le 2.20\text{ GiB}$ ($2252\text{ MiB}$)** |

> [!NOTE]
> Even under simulated 100-service multi-site loads with 5,000 intervals, Phase 13 consumes only **20.5 MiB RSS** and **8.58 ms CPU time**, fitting comfortably within the allocated 30 MiB boundary.

---

### 2.2 Regional Concentrator & Proxy Sizing (`regional-proxy`)

Deployed in regional hubs (e.g. Mombasa MBA, Entebbe EBB, London Heathrow LHR) to aggregate metrics from local and neighboring outstations before forwarding to JKIA.

* **Target Hardware:** Virtual Micro-Appliance (1 vCPU, 512 MiB RAM, 10 GB Disk).
* **Container Resource Ceiling:** `MemoryMax=256M`, `CPUQuota=40%`.
* **Components:** Active Zabbix Proxy 7.4, Local SQLite store-and-forward proxy, Trans-WAN synthetic voice prober.

---

### 2.3 Outstation Edge Collector Sizing (`edge-collector`)

Deployed on lightweight edge gateways or terminal LAN switches at remote outstations (e.g. Kisumu KIS, Eldoret EDL, Malindi MYD, Juba JUB).

* **Target Hardware:** Embedded Edge Gateway / Micro-VM (1 vCPU, 512 MiB RAM, 5 GB Disk).
* **Container / Service Ceiling:** `MemoryMax=128M`, `CPUQuota=25%`.
* **Components:** Local persistent SQLite spool database (`edge_telemetry_spool`), SNMP poller, and rate-limited drain forwarder.

---

## 3. Multi-Site Resilience & Failure Domain Modes

### 3.1 Scenario 1: Total Outstation WAN Partition (Fiber Cut / Telco Outage)

```
[ Mombasa Outstation LAN ]            [ Trans-WAN Network ]             [ JKIA Head Office Core ]
Check-in Desks  ---.                                                 
Gate Scanners   ---+-> [ Edge Spool DB ] ---X [ WAN Partition ] X---> [ Central Zabbix & Nawari ]
Local PBX Gate  ---'    (Buffered Locally)                            (Circuit Marked DOWN)
```

1. **Detection:** Central hub monitoring detects missed heartbeats from Mombasa primary circuit `CIR-MBA-01` and secondary circuit `CIR-MBA-02`.
2. **Central Hub Isolation:**
   - MultiSiteRegistry updates circuit state to `DOWN`.
   - Service Catalog isolates impact: Mombasa Station-Local DCS `SVC-DCS-MBA` is marked `CRITICAL_DOWN`.
   - Global DCS Core `SVC-DCS-GLOBAL` and Flight Ops `SVC-FLIGHT-OPS` remain **100% HEALTHY** with zero cross-station contamination.
3. **Outstation Edge Survivability:**
   - Edge Collector detects socket failure and transitions to `BUFFERING_OFFLINE`.
   - Telemetry points, local alerts, and SNMP logs are written to SQLite disk spool (`PRAGMA journal_mode=WAL`).
   - If local PBX voice path to JKIA is severed, local PSTN breakout routes emergency air-to-ground calls to local airport frequencies.

---

### 3.2 Scenario 2: Circuit Restoration & Rate-Limited Store-and-Forward Replay

1. **Recovery Detection:** Edge Collector verifies 3 consecutive successful TCP handshakes to central hub endpoint.
2. **Rate-Limited Draining:**
   - To avoid saturating low-bandwidth outstation links (e.g. 2 Mbps VSAT in Juba or 10 Mbps LTE in Kisumu), the forwarder limits transmission velocity to **50 records/second**.
3. **Data Quality Integrity & Clock Drift Compensation:**
   - Every replayed record is explicitly annotated with `telemetry_quality="REPLAYED"`, `is_replayed=True`, `clock_drift_ms`, and `compensated_hub_timestamp`.
   - **Critical Invariant:** Nawari’s Central SLI Engine rejects replayed data as proof of current live service availability. Replayed records are indexed into cold historical archives for retrospective root-cause analysis without distorting the active 30-day rolling SLA.

---

### 3.3 Scenario 3: Primary Hub Disaster Recovery (DC1 to DC2 Failover)

* **Data Centers:** DC1 (Pride Centre) and DC2 (Old Airport / Cargo).
* **Replication Architecture:** PostgreSQL synchronous replication for audit ledgers and incident states; semi-synchronous replication for time-series telemetry.
* **Failover Time:** RPO = 0 seconds (zero audit ledger data loss); RTO $\le 90$ seconds (automated virtual IP migration and Zabbix HA cluster takeover).

---

## 4. Storage Capacity & Retention Modeling

| Data Tier | Retention Window | Storage Medium | Sizing Estimate (1 Year) | Pruning Policy |
| :--- | :---: | :---: | :---: | :--- |
| **Real-Time Telemetry (Zabbix)** | 7 Days Raw | PostgreSQL (NVMe) | $\approx 22\text{ GB}$ | Automatic partitioned table drop |
| **Aggregated Trends (Hourly/Daily)** | 365 Days | PostgreSQL (NVMe) | $\approx 15\text{ GB}$ | Downsampled averages/min/max |
| **Outstation Edge Spool** | Max 50,000 records | SQLite WAL (Disk) | $\approx 50\text{ MB}$ per station | Oldest unacknowledged FIFO prune on overflow |
| **Chained Audit Ledger** | 7 Years (Regulatory) | JSON + Syslog Append | $\approx 4\text{ GB}$ | Immutable append-only; hourly external anchor |
| **Voice Call Quality Records** | 90 Days | PostgreSQL | $\approx 8\text{ GB}$ | Rolling partition purge |
| **Total Central Storage Demand** | — | — | **$\approx 49\text{ GB}$** | **Fits in 100 GB NVMe allocation** |

---

## 5. Summary of Operational Invariants

1. **Memory Budget:** Total container stack memory on `mon-grafana01` must not exceed $2.20\text{ GiB}$.
2. **Freshness Invariant:** Recovery requires $\ge 3$ consecutive fresh healthy observations (freshness $< 30\text{s}$). Replayed outstation data cannot prove recovery.
3. **Isolation Invariant:** Local outstation failures must not impact global core services.
4. **Three-Identity Rule:** $|\{P, A_1, A_2\}| = 3$ for all Tier-3 remediation actions.
5. **Physical Gating:** Live mutations against Kenya Airways infrastructure remain locked behind Phase 8.2 physical commissioning.

