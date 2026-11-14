# Nawari Phase 13 Technical Viability Assessment
## Enterprise Platform Productisation, Multi-Site Architecture & Service Expansion

**Document Version:** 1.0.0  
**Status:** ARCHITECTURAL VIABILITY ASSESSMENT FOR REVIEW  
**Author:** Antigravity Engineering (Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM)  
**Container Resource Budget:** $\le 2.20\text{ GiB}$ total container RAM on `mon-grafana01`  

---

## 1. Executive Summary

This technical viability assessment provides an engineering evaluation of the architectural designs, multi-site models, edge telemetry resilience, incident lifecycle pipelines, and governance controls specified for **Phase 13: Enterprise Platform Productisation, Multi-Site Architecture & Service Expansion**.

The core objective is proving that Nawari can operate as a cohesive enterprise aviation product across domestic, regional, and international outstations while providing closed-loop incident management, strict authorization interlocks ($|\{P, A_1, A_2\}|=3$), and verified recovery guarantees without exceeding the $\le 2.20\text{ GiB}$ container memory ceiling on `mon-grafana01`.

---

## 2. Component Technical Viability Matrix

### 2.1 Multi-Site Registry & Hierarchical Topology Engine (Workstream 13A)
* **Objective:** Model the entire Kenya Airways global airport network with site metadata, WAN circuits, local telephony breakout, and operational hours.
* **Viability Analysis:**
  - Network scale: 1 primary hub (JKIA), 4 domestic stations (MBA, KIS, EDL, MYD), 5 regional hubs (EBB, DAR, KGL, ADD, JUB), and 6+ international long-haul stations (LHR, DXB, AMS, JNB, JFK, BOM). Total sites: $\approx 20 - 30$.
  - Data structure: Python `dataclasses` with hierarchical tree navigation. Memory consumption is $< 5\text{ MiB}$ for the entire outstation registry.
  - Query speed: Direct in-memory dictionary lookups by IATA/ICAO code in $< 1\ \mu\text{s}$.
* **Verdict:** **Approved — Highly Viable and Lightweight**.

---

### 2.2 Aviation Business Service Catalogue & SLA/SLO Engine (Workstream 13B)
* **Objective:** Translate raw device/interface telemetry into real-time health scorecards and SLA tracking for airline services (DCS, Flight Ops, BHS, Cargo).
* **Viability Analysis:**
  - *Dependency Mapping:* Directed Acyclic Graph (DAG) connecting underlying switches, WAN circuits, PBX trunks, and application endpoints to top-level business services.
  - *Real-Time Health Index:* Evaluated asynchronously on status changes rather than polling in tight loops. A 3-tier weighting algorithm (Primary node 0.6, Redundant node 0.3, Backup path 0.1) computes an availability score ($0.0 - 1.0$).
  - *Error Budget Tracking:* Calculates monthly downtime budget in seconds (e.g. 99.95% availability allows 21.9 minutes of downtime per month for DCS).
  - *Memory & Compute:* Evaluator state machine consumes $\approx 8\text{ MiB}$ RAM and $< 0.2\%$ vCPU.
* **Verdict:** **Approved — High Operational Value for Airline Leadership**.

---

### 2.3 Operational Alerting, Incident Lifecycle & Notification Delivery (Workstream 13C)
* **Objective:** Establish the complete closed-loop detection-to-recovery operational pipeline.
* **Viability Analysis:**
  - *Deduplication & Suppression:* In-memory sliding window correlation clusters repeating events and suppresses downstream leaf alerts during parent router or WAN interface drops.
  - *Multi-Channel Notifications:* Asynchronous worker queues handle SMTP email formatting and SMS dispatch with exponential backoff and dead-letter retry buffers.
  - *Verified Recovery Requirement:* The engine enforces that an action execution or self-clearing alert does **not** automatically close an incident. Incidents remain in `VERIFYING` state until $\ge 3$ consecutive healthy observations are captured with telemetry freshness $< 30\text{ seconds}$.
  - *Compute & Memory:* Queue and correlation engine consume $\approx 10\text{ MiB}$ RAM and $< 0.5\%$ vCPU.
* **Verdict:** **Approved — Essential Enterprise Incident Governance**.

---

### 2.4 Trans-WAN Communications & Edge Telemetry Store-and-Forward (Workstream 13D)
* **Objective:** Guarantee continuous monitoring and prevent telemetry loss during frequent outstation WAN degradations or undersea fiber cuts.
* **Viability Analysis:**
  - *Store-and-Forward Buffer:* Uses embedded SQLite with WAL (Write-Ahead Logging) mode on edge proxies. Capable of buffering up to 500,000 metrics ($\approx 50\text{ MB}$ disk footprint) during offline periods.
  - *Rate-Controlled Replay:* When WAN connectivity recovers, the edge forwarder replays buffered records at a controlled rate ($\le 50\text{ items/sec}$), preventing CPU or connection spikes at the central JKIA collector.
  - *Timestamp Preservation & Drift Compensation:* Every buffered metric retains its original collection timestamp. Edge proxies record local NTP offsets; central ingestion adjusts timestamps if outstation clocks experience drift $> 1000\text{ ms}$.
  - *Trans-WAN Synthetic Voice Probes:* Probes strictly route over internal private WAN circuits; public toll PSTN breakouts are locked out to eliminate any call toll costs.
* **Verdict:** **Approved — Essential for Outstation WAN Resilience**.

---

### 2.5 Multi-Site Scoped RBAC & Three-Identity Interlock (Workstream 13E)
* **Objective:** Ensure outstation staff only access their relevant station data, while central NOC retains global oversight, enforcing the strict Three-Identity Rule.
* **Viability Analysis:**
  - *Three-Identity Rule Enforcement:* The authorization engine validates that proposer ID ($P$), first approver ID ($A_1$), and second approver ID ($A_2$) satisfy $|\{P, A_1, A_2\}| = 3$. Attempts by the proposer to self-approve or by an approver to provide dual sign-off are blocked with `INVALID_THREE_PERSON_APPROVAL`.
  - *Complete Token Binding:* HMAC-SHA256 signatures bind `incident_id`, `alert_id`, `playbook_id`, `playbook_version`, `plan_hash`, `target_env`, `risk_tier`, `change_window_id`, `parameters_hash`, `nonce`, and `expires_at`.
  - *Role Scoping:* Enforced at API and data-filtering layers. Grafana dashboard variable filtering automatically restricts visual context based on user's `site_scope`.
* **Verdict:** **Approved — Enterprise Security Foundation**.

---

### 2.6 Unified NOC Dashboards & Operational Validation (Workstream 13F)
* **Objective:** Centralized visual command of the airline network, service health, and operational remediation.
* **Viability Analysis:**
  - Dashboards are provisioned as immutable Grafana JSON configs.
  - Validation test suite checks structural JSON schema compliance and exercises data queries against simulated live, empty, stale, and failed data streams.
  - Memory footprint of dashboard provisioning is $< 12\text{ MiB}$ RAM.
* **Verdict:** **Approved — NOC Visual Operational Baseline**.

---

### 2.7 Enterprise Deployment Profiles & Packaging (Workstream 13G)
* **Objective:** Provide automated, standardized deployment packages for central data centers and distributed outstation nodes.
* **Viability Analysis:**
  - Four formal profiles: `simulation`, `staging`, `single-site-production`, `multi-site-production`.
  - Distribution packages: `hub-full` ($\approx 2.12\text{ GiB}$ container RAM), `regional-proxy` ($\approx 180\text{ MiB}$ RAM), `edge-collector` ($< 45\text{ MiB}$ RAM).
  - Standardized systemd unit templates, automated zero-touch configuration scripts, and local health watchdogs.
* **Verdict:** **Approved — Standardizes Global Rollout**.

---

### 2.8 API Governance, Audit Hardening & Crash Recovery (Workstream 13H)
* **Objective:** Stable versioned APIs, resilient execution recovery, and hardened audit ledgers.
* **Viability Analysis:**
  - *Crash Recovery:* Uses pre-execution WAL journaling. If a crash occurs mid-action, startup recovery detects pending records and sets state to `UNVERIFIED_STATE`.
  - *Post-Timeout State Inspection:* Subprocess timeouts trigger a diagnostic state probe rather than a blind rollback.
  - *Audit Ledger Hardening:* Restricted append-only file permissions (`0640` / `chattr +a`), periodic hourly external hash export, and automated chain corruption detection.
* **Verdict:** **Approved — High-Assurance Resilience**.

---

## 3. Host Resource Budget Analysis (`mon-grafana01`)

Evaluated against the target host environment: Ubuntu 24.04 LTS (2 vCPUs, 7.8 GiB RAM):

| Subsystem / Container | Phase 12 Allocated RAM | Phase 13 Projected RAM | Delta | CPU Impact (% of 2 vCPUs) |
| :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | 512 MiB | 512 MiB | 0 MiB | $1.0 - 3.0\%$ |
| **Zabbix Server 7.4** | 768 MiB | 768 MiB | 0 MiB | $2.0 - 5.0\%$ |
| **Zabbix Frontend** | 256 MiB | 256 MiB | 0 MiB | $< 1.0\%$ |
| **Grafana 11** | 268 MiB | 280 MiB | +12 MiB (multi-site dashboards) | $1.0 - 2.0\%$ |
| **Nawari Services (Phases 1-11)** | 280 MiB | 280 MiB | 0 MiB | $< 2.0\%$ |
| **Phase 12 Action Engine** | 25 MiB | 25 MiB | 0 MiB | $< 0.5\%$ |
| **Phase 13 Multi-Site & SLA Engine**| — | **$\approx 30\text{ MiB}$** | **+30 MiB** | **$< 1.0\%$** |
| **Total Container Envelope** | **$\approx 2.10\text{ GiB}$** | **$\approx 2.15\text{ GiB}$** | **+42 MiB** | **$\le 15\%$ peak vCPU** |

> [!NOTE]
> Even with the multi-site registry, edge proxy coordination, and aviation SLA evaluators running, the total container stack memory consumption ($\approx 2.15\text{ GiB}$) remains safely within the **$\le 2.20\text{ GiB}$ hard limit**, leaving $> 5.5\text{ GiB}$ host memory available for the Linux kernel, network buffers, and OS page cache.

---

## 4. Operational Failure Modes & Architectural Mitigations

| Failure Mode | Risk Level | Architectural Mitigation |
| :--- | :---: | :--- |
| **Prolonged Outstation WAN Outage** | High | **FIFO Disk Spooling & Priority Tiering:** Edge forwarders spool up to 50 MB locally. If spool reaches capacity, non-critical interface stats are pruned first, preserving critical alarms and DCS telemetry. |
| **WAN Restoration Thundering Herd** | High | **Rate-Limited Replay Queue:** Outstation proxies flush queued records in batches at $\le 50\text{ items/sec}$ with exponential backoff if central queue latency increases. |
| **Outstation Clock Drift** | Medium | **Relative Timestamping & NTP Drift Check:** Telemetry packets carry UTC timestamps and relative offset $\Delta t$. Ingestion verifies NTP sync status before committing to time series. |
| **Process Crash Mid-Remediation** | High | **Pre-Action WAL Journaling:** Action steps are journaled before execution; recovery routines detect unverified post-crash states and escalate. |
| **Premature Incident Closure** | High | **Mandatory Verified Recovery:** Incidents remain open until $\ge 3$ consecutive healthy telemetry samples are observed with freshness $< 30\text{s}$. |
| **Audit Log Tampering** | Critical | **Append-Only OS Flags & External Anchoring:** OS-level write restrictions and hourly export of block hashes to external syslog/cold storage. |
| **Premature Production Mutation** | Critical | **Phase 8.2 Commissioning Gating:** Multi-site actions enforce simulation sandbox mode; live production physical mutations remain strictly blocked pending Phase 8.2 physical sign-offs. |

---

## 5. Viability Conclusion & Sign-Off Recommendation

Phase 13 is **technically viable, resource-compliant, and operationally rigorous**.

It establishes the definitive productisation framework for Nawari, transforming the system into an enterprise-ready aviation platform that bridges physical infrastructure, edge telemetry, business services, and human governance.

Proceeding to Phase 13 implementation across Workstreams 13A through 13J is strongly recommended.
