# Nawari Resource & Capacity Budget Specification

**Status:** Technical Baseline  
**Date:** 2026-11-07  
**Target Environment:** Production Host `mon-grafana01` (2 vCPU, 7.8 GiB RAM, 4 GiB Swap, ~17 GB Free Disk)

---

## 1. Executive Summary & Design Rationale

The Sentra architecture encountered significant operational strain on the production VM `mon-grafana01` because Java-based services (OpenSearch 3.8.0, OpenSearch Dashboards, Data Prepper, OpenTelemetry Collector) consumed more than 4.5 GiB of RAM and required aggressive 7-day index lifecycle rollover to prevent disk exhaustion.

Nawari replaces the heavy telemetry engine with **Zabbix 7.4 + PostgreSQL 17 + Grafana 11.6+**, drastically cutting baseline memory consumption from ~4.5 GiB down to **~920 MiB** while maintaining high telemetry fidelity.

---

## 2. Memory Budget by Container Service

| Container Service | Base Tech | Baseline RSS (Normal) | Peak Operating RAM | Hard Limit (`mem_limit`) | Swap Policy |
|---|---|---|---|---|---|
| `postgres` | C / PostgreSQL 17 | 180 MiB | 320 MiB | **512 MiB** | Standard |
| `zabbix-server` | C / Alpine | 160 MiB | 280 MiB | **512 MiB** | No-swap priority |
| `zabbix-web` | PHP 8.2-FPM + Nginx | 90 MiB | 180 MiB | **256 MiB** | Standard |
| `zabbix-snmptraps` | C / Net-SNMP | 25 MiB | 45 MiB | **64 MiB** | Standard |
| `grafana` | Go / Grafana 11.6 | 130 MiB | 220 MiB | **300 MiB** | Standard |
| `nawari-api` | Python 3.12 / Uvicorn | 85 MiB | 150 MiB | **256 MiB** | Standard |
| **Core Baseline Total** | — | **~670 MiB** | **~1,195 MiB** | **~1,900 MiB (~1.9 GiB)** | — |
| `asterisk` *(Deferred Profile)* | C / Asterisk 22 | 140 MiB | 220 MiB | **300 MiB** | Standard |
| **Total with Voice Profile** | — | **~810 MiB** | **~1,415 MiB** | **~2,200 MiB (~2.2 GiB)** | — |

### Headroom on Production Host (7.8 GiB Total):
- Host OS & Kernel Page Cache: ~1.5 GiB
- Nawari Core Stack (Normal): ~1.0 GiB
- **Guaranteed Free Unallocated RAM**: **~5.3 GiB** (ensures zero OOM-killer risks and avoids thrashing).

---

## 3. CPU Budget & Polling Scheduling

The production VM has **2 vCPUs**. Inefficient polling intervals (e.g. 5-second polling of 5,000 SNMP OIDs) can saturate CPU cores and cause packet drops.

### Polling Cadence Standards:
1. **ICMP Availability & Ping RTT**: Every **15 to 30 seconds** (high-frequency reachability).
2. **Standard Interface Counters (64-bit HC Octets, Errors, Discards)**: Every **60 seconds**.
3. **Appliance OS Metrics (CPU, Memory, Disk Space)**: Every **120 to 300 seconds** (slow-moving telemetry).
4. **Low-Level Discovery (LLD) Rules**: Every **1 hour** (3600s) (interfaces rarely change dynamically).
5. **Synthetic Call Assurance**: Controlled execution every **15 to 60 minutes** with strict cooldown gates.

### Expected CPU Utilization:
- **Idle / Baseline Polling**: < 8% of 1 vCPU (< 4% total VM CPU).
- **Discovery / Batch Polling Bursts**: Up to 35% of 1 vCPU for 2–3 seconds.
- **Service Quotas**: Docker Compose limits total CPU quota to `1.5` vCPUs, leaving 0.5 vCPU reserved exclusively for the host OS and SSH sessions.

---

## 4. Disk Storage Growth & Retention Budget

The target server reported **~17 GB free root disk**. Storage growth must be modeled over a 12-month horizon:

### A. Telemetry Sizing Model (Estimated 50 Devices / 2,500 Monitored Items)
- **Item History (Raw numeric floats/integers)**:
  - 2,500 items polled at average 60s = 3.6 million values / day.
  - At ~50 bytes per stored record in PostgreSQL = **~180 MB / day**.
  - **History Retention Policy**: **7 Days** = **1.26 GB**.
- **Trends (1-hour min/avg/max/count rollups)**:
  - 2,500 items * 24 hours = 60,000 trend records / day.
  - At ~128 bytes per trend record = **~7.7 MB / day**.
  - **Trend Retention Policy**: **365 Days** (1 Year) = **~2.8 GB**.
- **SNMP Traps & Events**:
  - Estimated 5,000 events / month = **~250 MB / year**.
- **PostgreSQL Database Total Steady-State**: **~4.3 GB**.

### B. Container Images & Logs:
- Docker Image Footprint (Alpine bases): ~1.2 GB.
- Container Log Rotation: `max-size: "10m"`, `max-file: "3"` per service (~180 MB total max).

### C. Backup Retention:
- Daily compressed `pg_dump` (`.sql.gz`): ~250 MB per backup.
- Rolling retention of **7 daily backups**: **1.75 GB**.

### Overall Disk Budget Summary:
| Item | Allocated Storage |
|---|---|
| PostgreSQL Database (7d history + 365d trends) | 4.30 GB |
| Docker Images & Base Layers | 1.20 GB |
| Container Log Buffers | 0.18 GB |
| Rolling Backups (7 Days) | 1.75 GB |
| Safety Buffer / Upgrade Headroom | 4.50 GB |
| **Total Projected Consumption** | **11.93 GB** |
| **Available Disk on Host** | **17.00 GB** |
| **Surplus Disk Remaining** | **+5.07 GB** |

---

## 5. TimescaleDB Assessment

- **Finding**: TimescaleDB provides Hypertables and automated chunk-based compression for time-series data.
- **Decision**: **Deferred**.
- **Justification**: At ~2,500 items and a 7-day raw history window, standard PostgreSQL 17 handles the query volume easily with negligible write amplification. Adding TimescaleDB would require custom image builds, memory overhead for chunk caching, and potential version-locking risks during future Zabbix upgrades.

