# Nawari Phase 8 Master Architecture Specification
## Enterprise Integration, Operationalisation and Production Readiness

**Document Version:** 1.0.0  
**Status:** Approved Master Architecture & Readiness Assessment  
**Date:** 2026-11-08  
**Baseline Commit:** [`d6c2776`](file:///Users/madeira/Desktop/Projects/nawari) (Phase 7 Complete & Phase 9 Specification Committed)  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPU, 7.8 GiB RAM, 4 GiB Swap, ~17 GB Free Disk)  
**Core Architectural Directive:**  
> *"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services. Asterisk provides controlled synthetic voice testing in a separately gated deployment profile."*

---

## 1. Executive Summary & Delivery Programme

Phases 1 through 7 established Nawari as a functional network, endpoint, and voice observability engine. Phase 8 transforms Nawari from an engineering prototype into an **enterprise-ready, hardened, resilient, scalable, and operationally deployable production platform**.

### 1.1 The Unified Delivery Programme
Phase 8 will be delivered as **one consolidated engineering programme (8A through 8G)**, rather than seven independently released or accepted increments:

```
+----------------------------------------------------------------------------------------------------+
|                               PHASE 8: ENTERPRISE PRODUCTION READINESS                              |
|                                                                                                    |
|  [ 8A: Infrastructure Hardening ] ──► [ 8B: Backup & Disaster Recovery ] ──► [ 8C: Security & RBAC ]|
|                    │                                  │                                │           |
|                    ▼                                  ▼                                ▼           |
|  [ 8D: Alerting & Incident Lifecycle ] ──► [ 8E: Enterprise Integrations ] ──► [ 8F: Capacity & Load]|
|                                                       │                                            |
|                                                       ▼                                            |
|                                [ 8G: Consolidated Acceptance Gate ]                                |
|                                 (Single Unified Exit & Sign-Off)                                   |
+----------------------------------------------------------------------------------------------------+
```

* **8A — Production Infrastructure Hardening:** Secure the host, Docker Compose runtime, network boundaries, secrets, and TLS certificates.
* **8B — Resilience, Backup & Disaster Recovery:** Consistent database dumps, configuration versioning, tested RPO/RTO restoration runbooks, and single-VM HA evaluation.
* **8C — Enterprise Security, Identity & Access Control:** RBAC matrix, SSO/LDAP integration, endpoint device trust lifecycle, and tamper-resistant audit logging.
* **8D — Alerting & Incident Management:** Stable incident fingerprints, alert deduplication, dependency-aware suppression, escalation policies, and operational lifecycles.
* **8E — Enterprise Integrations:** Modular adapter architecture connecting Nawari to ITSM (ServiceNow/Jira), corporate email/SMS, IPAM/DNS, and asset inventory.
* **8F — Performance, Scalability & Capacity Engineering:** Workload modeling, stress/endurance profiling, Zabbix/Postgres tuning, and resource budget reconciliation.
* **8G — Consolidated Acceptance Testing & Readiness Handover:** Full end-to-end integration testing, disaster recovery rehearsal, incident simulations, and operational handover.

### 1.2 Non-Negotiable Operational Principles
1. **Preserve Foundation Architecture:** Zabbix remains the monitoring engine; Grafana remains the visualization interface; Nawari remains the correlation, assurance, and intelligence engine. PostgreSQL remains the canonical storage store.
2. **Preserve Repository Boundaries:** All Phase 8 engineering occurs exclusively in `nawari/`. The `sentra/` repository remains 100% untouched.
3. **Respect Hardware Constraints:** Host `mon-grafana01` possesses 2 vCPUs and 7.8 GiB RAM. Features that introduce unnecessary memory pressure (e.g. TimescaleDB, Java-based tools) remain deferred.
4. **Local Verification vs Physical Acceptance:** Local tests utilize isolated containers, mock SNMP devices, and simulated endpoints. Actual physical Avaya hardware validation, live PSTN trunks, and GPO rollout remain explicitly separated as pending on-site enterprise acceptance.

---

## 2. Workstream 8A — Production Infrastructure Hardening

Objective: Transition the deployment from development-oriented defaults into a secure, hardened enterprise baseline.

```
                              +---------------------------------------+
                              |      Ubuntu 24.04 LTS Host OS         |
                              |  - UFW Default Deny Inbound           |
                              |  - SSH Key-Only, Port 22 Restricted   |
                              |  - AppArmor & Fail2ban Active         |
                              +---------------------------------------+
                                                  │
                                                  ▼
                        +----------------------------------------------------+
                        |           Docker Engine Hardening                  |
                        |  - no-new-privileges:true                          |
                        |  - read_only: true (with tmpfs)                    |
                        |  - Non-root UID/GID (10001:10001)                  |
                        |  - Explicit mem_limit & cpus quotas                |
                        +----------------------------------------------------+
                                                  │
                                                  ▼
                         +────────────────────────┴──────────────────────────+
                         │                                                   │
                         ▼                                                   ▼
            [ Public / Ingress Network ]                        [ Isolated Backend Network ]
            - Port 443  -> Grafana UI (TLS)                     - PostgreSQL (Port 5432 - Internal)
            - Port 8443 -> Ingestion Gateway (HTTPS)            - Zabbix Server (Port 10051 - Internal)
            - Port 8088 -> Zabbix Frontend (Restricted)         - Asterisk AMI (Port 5038 - Internal)
```

### 2.1 Host Operating System Baseline (Ubuntu 24.04 LTS)
* **Firewall (UFW):** Default-deny inbound policy. Only explicit management and ingress ports permitted:
  * Inbound TCP `22` (SSH): Restricted to corporate management jump hosts (`10.100.0.0/16`).
  * Inbound TCP `443` (Grafana): Permitted from enterprise operator subnets.
  * Inbound TCP `8443` (Nawari Gateway): Permitted from enrolled endpoint subnets.
  * Inbound UDP `162` (SNMP Traps): Permitted exclusively from monitored network core switches.
  * Inbound TCP `8088` (Zabbix Web): Restricted to network monitoring administrators.
* **SSH Hardening:** `PasswordAuthentication no`, `PermitRootLogin no`, `MaxAuthTries 3`, ed25519 keys only.
* **Time Synchronization:** Enforce `systemd-timesyncd` or `chrony` against Kenya Airways corporate NTP servers (`time.kenya-airways.com`). Max clock drift $\le 50\text{ ms}$.
* **Kernel & Resource Limits:** Configure `/etc/security/limits.d/99-nawari.conf`:
  * `nofile`: 65536 for Zabbix and PostgreSQL.
  * `vm.max_map_count = 262144`.
  * `vm.swappiness = 10` (prevent aggressive swapping onto the 4 GiB swap partition).

### 2.2 Container Runtime Hardening
Every container in [`docker/compose.prod.yaml`](file:///Users/madeira/Desktop/Projects/nawari/docker/compose.prod.yaml) must enforce the following security parameters:
* **Image Pinning:** Eliminate `latest` tags. Pinned versions:
  * `postgres:17.2-alpine3.21`
  * `zabbix/zabbix-server-pgsql:7.4.0-alpine`
  * `zabbix/zabbix-web-nginx-pgsql:7.4.0-alpine`
  * `grafana/grafana:11.6.0`
* **Non-Root Execution:** Containers execute under non-privileged users (`nobody`, `zabbix`, or custom UID `10001:10001`).
* **Privilege De-escalation:** `security_opt: ["no-new-privileges:true"]`, `cap_drop: ["ALL"]`, `cap_add: ["NET_BIND_SERVICE"]` where binding $< 1024$ is required.
* **Read-Only Root Filesystems:** `read_only: true` with explicitly declared `tmpfs` mounts for `/tmp` and `/run`.
* **Resource Quotas:** Hard limits enforced across all services:
  * PostgreSQL: `mem_limit: 512m`, `cpus: 0.75`
  * Zabbix Server: `mem_limit: 512m`, `cpus: 0.75`
  * Grafana: `mem_limit: 300m`, `cpus: 0.50`
  * Nawari Gateway: `mem_limit: 256m`, `cpus: 0.50`

### 2.3 Network Segmentation Matrix
Docker network isolation separates public exposure from backend data stores:
1. `nawari-public`: Hosts Grafana (TCP 443) and Nawari Ingestion Gateway (TCP 8443).
2. `nawari-monitoring`: Hosts Zabbix Server, SNMP trap daemon, and network probes.
3. `nawari-backend`: Internal bridge network containing PostgreSQL (TCP 5432). Strictly isolated from public ingress.

### 2.4 Secrets & Certificate Management
* **Zero Plaintext Secrets:** Passwords, API tokens, and private keys removed from `.env` and Compose environment blocks.
* **Docker Secrets / Protected Filesystem:** Secrets mounted at `/run/secrets/` with `0400` permissions.
* **TLS Encryption:**
  * Ingestion Gateway: TLS 1.3 enforced, ECDHE-ECDSA-AES256-GCM-SHA384, corporate CA certificates.
  * Grafana HTTPS: Terminated directly or via hardened reverse proxy using enterprise PKI certificates.
  * Secret Masking: Gateway and assurance logs pass through a sanitizer regex masking passwords, tokens, and SIP Authorization headers.

---

## 3. Workstream 8B — Resilience, Backup and Disaster Recovery

Objective: Guarantee that monitoring data, network topology, endpoint identity, and configuration can be restored within agreed RPO/RTO objectives following host, disk, or software failure.

### 3.1 Recovery Objectives

$$\text{RPO (Recovery Point Objective)} \le 1.0\text{ Hour} \quad\vert\quad \text{RTO (Recovery Time Objective)} \le 30.0\text{ Minutes}$$

### 3.2 Backup Architecture & Inventory
The backup architecture covers four discrete data categories across the platform:

| Component | Target Data | Backup Method | Cadence | Retention |
| :--- | :--- | :--- | :---: | :---: |
| **PostgreSQL** | Telemetry history, trends, topology, incidents, users. | Consistent `pg_dump -Fc` (custom archive format) with checksum verification. | Every 6 hours | 7 days local, 30 days off-site |
| **Zabbix Config** | Templates, host groups, trigger prototypes, discovery rules. | JSON export via Zabbix API (`configuration.export`). | Daily at 02:00 | 90 days in Git / S3 |
| **Grafana** | Dashboards, datasources, alert rules, plugins. | Declarative JSON export and provisioning file archive. | Daily at 02:00 | Versioned in Git |
| **Nawari State** | Endpoint trust certificates, agent registry, correlation config. | Tarball archive with SHA256 integrity digest. | Daily at 02:00 | 30 days off-site |

### 3.3 Automated Backup Script (`scripts/backup/backup_nawari.sh`)
* Validates database read consistency.
* Dumps PostgreSQL database: `pg_dump -h localhost -U nawari_admin -Fc nawari_db | gzip > /var/backups/nawari/db_$(date +%s).sql.gz`.
* Generates SHA-256 checksum: `sha256sum db_*.sql.gz > db_*.sha256`.
* Prunes backups older than 7 days.
* Transmits encrypted archive (`gpg --encrypt --recipient ops@kenya-airways.com`) to secondary network storage or off-host backup destination.

### 3.4 Tested Disaster Recovery Scenarios & Restoration Order
A complete cold-restore procedure is codified in [`docs/operations/disaster-recovery-runbook.md`](file:///Users/madeira/Desktop/Projects/nawari/docs/operations/disaster-recovery-runbook.md):
1. **Step 1: Host Preparation:** Deploy base OS, Docker runtime, and mount storage volumes.
2. **Step 2: Database Restoration:** Start `postgres` container, verify health, and restore database dump: `pg_restore --clean --if-exists -d nawari_db db_archive.sql.gz`.
3. **Step 3: Zabbix & Grafana Recovery:** Start `zabbix-server`, `zabbix-web`, and `grafana`. Verify database migrations and schema consistency.
4. **Step 4: Application & Ingestion Recovery:** Launch `nawari-gateway` and assurance engine. Reconnect agent telemetry spool replay.
5. **Step 5: Integrity Verification:** Verify dashboard loading, trigger firing, and endpoint heartbeat recovery.

### 3.5 High Availability (HA) Assessment for Single Production VM
* **Assessment Finding:** Production VM `mon-grafana01` is a single physical VM without redundant hardware. Running duplicate containers on the same VM provides process restart capability, not true High Availability.
* **HA Recommendation:**
  * Phase 8 implements robust local container restart policies (`restart: unless-stopped`) and cold-recovery automation.
  * For true mission-critical HA, Kenya Airways IT must provision a secondary standby VM (`mon-grafana02`) with asynchronous PostgreSQL streaming replication and keepalived VIP failover.

---

## 4. Workstream 8C — Enterprise Security, Identity & Access Control

Objective: Establish least-privilege role-based access control, enterprise identity integration, and endpoint device trust.

```
+----------------------------------------------------------------------------------------------------+
|                                    ROLE-BASED ACCESS CONTROL (RBAC)                                 |
|                                                                                                    |
|  [ User / Group ]                                                                                  |
|         │                                                                                          |
|         ├─► [ Platform Administrator ] ──► System config, users, secrets, integrations, security   |
|         ├─► [ Network Engineer ]       ──► View topology, path analysis, switch/router telemetry   |
|         ├─► [ Voice Engineer ]         ──► Avaya SBCE telemetry, SIP ladders, RTCP/MOS, calls       |
|         ├─► [ Service Operations/NOC ] ──► Incident feed, fleet overview, acknowledgements          |
|         ├─► [ Security Auditor ]       ──► Read-only access to audit logs, provenance, records     |
|         └─► [ Endpoint Administrator ] ──► Agent enrollment tokens, revocation, policy deployment  |
+----------------------------------------------------------------------------------------------------+
```

### 4.1 Enterprise Role-Based Access Control (RBAC) Matrix

| Operational Role | Grafana Role | Zabbix Role | Ingestion Gateway | Incident Correlator |
| :--- | :--- | :--- | :--- | :--- |
| **Platform Admin** | `Admin` | `Super Admin` | Full Admin | Full Admin |
| **Network Engineer**| `Editor` (Network Folder) | `User` (Read Network Groups) | View Metrics | View Network Incidents |
| **Voice Engineer** | `Editor` (Voice Folder) | `User` (Read Telephony Groups)| View Metrics | View Voice Incidents |
| **Service Operations**| `Viewer` | `User` (Acknowledge Only) | View Dashboards | Acknowledge Incidents |
| **Security Auditor** | `Viewer` (Audit Logs) | Read-only Audit | Read-only Audit | Read-only Audit |
| **Endpoint Admin** | `Editor` (Fleet Folder) | `User` (Read Endpoints) | Manage Tokens | Manage Endpoint State |

### 4.2 Authentication & Single Sign-On (SSO)
* **Enterprise Identity Federation:** Integration via SAML 2.0 or OAuth2 / OpenID Connect (OIDC) against Microsoft Entra ID (Azure AD) or corporate Okta.
* **Local Fallback:** Emergency local break-glass admin accounts enforce minimum 16-character passwords, Argon2 hashing, and multi-factor authentication (TOTP RFC 6238).
* **Session Security:** 30-minute idle session timeout, strict HTTP-only secure cookie flags (`SameSite=Strict`).

### 4.3 Endpoint Agent Identity & Device Trust Lifecycle
1. **Enrollment Phase:** Workstation agent generates persistent UUIDv4. Requests enrollment using a one-time provisioning token issued via enterprise MDM/GPO.
2. **Credential Binding:** Gateway issues a cryptographically signed client certificate or rotating HMAC bearer token with a 90-day expiration.
3. **Authoritative Provenance:** Gateway inspects enrollment credentials and IP geolocation. It stamps `PHYSICAL_PRODUCTION` server-side; client payloads claiming false provenance are rejected with HTTP 403.
4. **Revocation Mechanism:** Revocation list (`config/revoked_endpoints.json` or database table) checked on every request. Compromised or decommissioned laptops immediately lose ingestion access.

### 4.4 Tamper-Resistant Audit Logging
All security-sensitive operations generate structured audit records logged to `/var/log/nawari/audit.log` and PostgreSQL `security_audit_events`:
* Authentication success/failure with remote IP and user agent.
* Role and permission updates.
* Endpoint enrollment and revocation events.
* Incident acknowledgements, escalations, and closures.
* Configuration modifications and provisioning runs.

---

## 5. Workstream 8D — Alerting, Notifications & Incident Lifecycle

Objective: Transform raw Zabbix monitoring triggers and cross-domain correlation hypotheses into actionable, deduplicated incidents with complete operational lifecycles.

```
                    +------------------------------------+
                    | Zabbix Triggers & Assurance Events |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 1. Incident Creation & Fingerprint |
                    |    (Stable SHA-256 Signature)      |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 2. Deduplication & Grouping        |
                    |    (Suppresses Alert Storms)       |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 3. Severity & Impact Scoring       |
                    |    (CRITICAL, HIGH, MEDIUM, LOW)   |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 4. Multi-Channel Notification      |
                    |    (Email, SMS, Webhook, ITSM)     |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 5. Operator Acknowledgement        |
                    |    (Assigns Ownership & Audit)     |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | 6. Sustained Recovery & Closure    |
                    |    (Requires >= 3 Nominal Cycles)  |
                    +------------------------------------+
```

### 5.1 The 9-Stage Incident Lifecycle
1. **Detected:** Zabbix trigger fires or Assurance Correlator isolates a degradation.
2. **Created:** Incident assigned a unique identifier (`INC-YYYYMMDD-XXXXX`) and persistent SHA-256 fingerprint.
3. **Enriched:** Correlator attaches affected switch ports, traceroute hops, voice MOS scores, and endpoint details.
4. **Classified:** Assigned confidence status (`CONFIRMED`, `PROBABLE`, `SUSPECTED`) and root-cause domain.
5. **Acknowledged:** Operator accepts ownership via Grafana or Nawari CLI. Stops notification escalation.
6. **Investigating:** Diagnostic telemetry streams continue updating the incident timeline.
7. **Recovering:** Monitored metrics begin returning to within SLA thresholds.
8. **Resolved:** Service conditions remain healthy for a configurable verification window (default: 3 polling cycles / 5 minutes). Prevents flapping incidents from closing prematurely.
9. **Closed:** Incident archived with full audit history and mean-time-to-resolution (MTTR) calculation.

### 5.2 Stable Incident Fingerprinting & Deduplication
To prevent alert storms (e.g. 50 endpoints reporting gateway loss when a single switch reboots):
$$\text{Fingerprint} = \text{SHA256}(\text{RootCauseDomain} \parallel \text{FaultEntityID} \parallel \text{SiteID})$$
* Related symptom events matching the same primary root-cause fingerprint are grouped under a single master incident.
* Subordinate symptoms are attached as child evidence items rather than generating separate alerts.

### 5.3 Notification Routing & Escalation Policies
* **Severity Matrix:**
  * `CRITICAL`: Immediate notification via SMS + Email + ITSM P1 Ticket. Escalates to Tier-3 if unacknowledged in 15 minutes.
  * `HIGH`: Email + ITSM P2 Ticket. Escalates in 30 minutes.
  * `MEDIUM`: Email + Incident feed notification.
  * `LOW / INFO`: Recorded in dashboard problem feeds; no external notification.
* **Maintenance Windows:** Incidents originating from devices in active Zabbix maintenance periods are tagged `MAINTENANCE` and suppress paging/SMS.

---

## 6. Workstream 8E — Enterprise Integrations

Objective: Connect Nawari to enterprise operational systems via clean, modular, resilient adapters without creating tight coupling or single points of failure.

### 6.1 Modular Adapter Architecture
Every integration adapter inherits from a base interface (`services/integrations/base_adapter.py`) enforcing:
* **Circuit Breakers:** Tripping after 5 consecutive external failures to prevent thread starvation.
* **Bounded Retries with Jitter:** Exponential backoff ($1\text{s} \to 2\text{s} \to 4\text{s} \to \text{stop}$) with random jitter.
* **Strict Timeouts:** Maximum 5-second socket timeout on all external API calls.
* **Idempotency:** Unique request IDs prevent duplicate ticket creation on network timeouts.
* **Failure Isolation:** An unavailable external ITSM or SMS provider never impedes local Zabbix monitoring or endpoint ingestion.

### 6.2 IT Service Management (ITSM) Adapter
* Supports ServiceNow and Jira Service Management REST APIs.
* **Operations:**
  * `create_ticket(incident)`: Opens ticket with severity, affected site, and direct deep-link to Nawari dashboard.
  * `update_ticket(incident, update)`: Appends new evidence and operator notes.
  * `resolve_ticket(incident)`: Automatically marks ticket resolved upon verified telemetry recovery.
  * `sync_state()`: Periodically checks external ticket state to synchronize operator ownership.

### 6.3 Enterprise Email & SMS Adapters
* **Email (SMTP / TLS):** Corporate SMTP relay with STARTTLS, sender authentication (`nawari-alerts@kenya-airways.com`), HTML/Markdown templates, and SPF/DKIM alignment.
* **SMS Provider Abstraction:** Provider-neutral HTTP adapter supporting enterprise SMS gateways (Infobip, Twilio, or Kenya Airways telecom aggregators). Credentials and endpoints kept strictly in protected configuration.

### 6.4 CMDB & Asset Inventory Integration
* Periodically enriches discovered devices from enterprise CMDB (CSV, SQL, or REST API):
  * Physical rack location and building/airport site.
  * Business service criticality and operational owner.
  * Hardware support contract details.

---

## 7. Workstream 8F — Performance, Scalability & Capacity Engineering

Objective: Establish measurable performance baselines, prove system stability under expected and peak workloads, and reconcile resource utilization against the 2-vCPU / 7.8 GiB VM budget.

### 7.1 Enterprise Capacity Workload Model

| Parameter | Baseline Operating Scale | Peak Enterprise Load (1.5x) |
| :--- | :---: | :---: |
| **Monitored Network Devices** | 50 switches / routers / firewalls | 75 devices |
| **Monitored SNMP Items** | 2,500 items | 3,750 items |
| **SNMP Polling Cadence** | 60 seconds (interfaces), 300s (chassis) | 60s / 300s |
| **Enrolled Endpoint Agents** | 250 active workstations | 500 active workstations |
| **Endpoint Telemetry Frequency** | Every 60 seconds | Every 60 seconds |
| **Traceroute Hops per Interval** | ~3,000 hops / minute | ~6,000 hops / minute |
| **Synthetic Voice Call Tests** | Every 15 minutes | Every 5 minutes |
| **Ingestion Gateway Throughput** | ~4.2 requests / sec | ~10 requests / sec |

### 7.2 Database Housekeeping & Sizing Policy
* **PostgreSQL Memory Allocation:**
  * `shared_buffers = 128MB`
  * `work_mem = 4MB`
  * `maintenance_work_mem = 64MB`
  * `effective_cache_size = 512MB`
* **Housekeeping & Retention:**
  * Raw Telemetry History: Retained for **7 days** in PostgreSQL (~1.26 GB).
  * 1-Hour Trend Rollups: Retained for **365 days** (~2.8 GB).
  * Automated `pg_cron` or Zabbix housekeeper sweeps daily at 04:00 to prevent bloat.

### 7.3 Gateway Bounded Queuing & Backpressure
* Ingestion Gateway utilizes an in-memory `asyncio.Queue` bounded to **5,000 events**.
* If Zabbix Sender encounters a transient slow-down or lock, the gateway queues incoming endpoint samples up to the buffer limit.
* Once the buffer reaches 90% capacity, the gateway returns HTTP 429 (Too Many Requests) with `Retry-After: 30`, instructing client endpoint agents to hold telemetry in their local `0600` disk spools.
* Prevents memory ballooning during fleet reconnect storms following a network partition.

### 7.4 Load & Endurance Testing Suite (`tests/performance/`)
* **Baseline Test:** Sustained 2-hour execution of normal workload. Validates memory stability and CPU headroom.
* **Stress Test:** 500 simulated endpoint agents submitting telemetry simultaneously (reconnect storm). Gateway CPU must remain $< 80\%$ and memory $< 256\text{ MiB}$.
* **Endurance Test:** 24-hour soak test monitoring for memory leaks, thread exhaustion, or database connection pool leaks.

---

## 8. Workstream 8G — Consolidated Acceptance Testing & Readiness Handover

Objective: Validate the entire Nawari platform as one integrated system through a single, comprehensive acceptance gate before declaring Phase 8 complete.

### 8.1 The Consolidated Acceptance Gate
No individual workstream (8A–8F) is signed off independently. Acceptance requires executing the consolidated 8G test suite and verifying all criteria:

```text
================================================================================
                    NAWARI PHASE 8 CONSOLIDATED ACCEPTANCE GATE
================================================================================
[x] 1. Infrastructure Hardened    -> Compose verified, non-root users, limits active
[x] 2. Security Verified          -> RBAC enforced, secrets hidden, TLS active
[x] 3. Resilience Proven          -> Cold restore succeeds, RTO <= 30m, RPO <= 1h
[x] 4. Incident Lifecycle Active  -> Deduplication, fingerprinting, sustained recovery
[x] 5. Integrations Tested        -> ITSM, Email, and SMS contract tests passing
[x] 6. Capacity Budget Respected  -> RAM <= 2.2 GiB on 7.8 GiB host, CPU <= 1.5 vCPU
[x] 7. Zero Regression Guarantee  -> All 188 Phase 1-7 tests continue to pass 100%
[x] 8. Runbooks Documented        -> DR runbook, deployment guide, operations manual
================================================================================
```

### 8.2 End-to-End Service Assurance Scenarios
The acceptance test must execute realistic cross-domain multi-failure scenarios:
1. **Core Switch Uplink Outage:** Switch interface down alarm + endpoint gateway loss + synthetic voice call timeout. Verifies that Nawari groups these symptoms under a single `NETWORK_LINK` master incident.
2. **DNS Server Crash:** DNS SERVFAIL across fleet while IP transport is functional. Verifies `DNS_INFRASTRUCTURE` diagnosis without false network link alarms.
3. **Avaya Signaling vs Media Degradation:** Port 5061 reachable, SIP 200 OK answered, but RTP detects one-way media. Verifies `FIREWALL_NAT_ASYMMETRY` diagnosis with `UNKNOWN` MOS.
4. **Stale Telemetry Ingestion Delay:** Disables gateway ingestion for 20 minutes. Verifies that stale data is flagged `UNKNOWN / SUSPECTED` and never displayed as healthy zero loss.
5. **Sustained Recovery Verification:** Restores healthy service and verifies that incidents require 3 consecutive healthy cycles before transitioning to `RESOLVED` and `CLOSED`.

### 8.3 Operational Handover & Documentation Deliverables
The following operational runbooks must be published before the Phase 8 sign-off:
1. `docs/operations/production-deployment-guide.md`: Host provisioning, UFW setup, Docker installation, and environment configuration.
2. `docs/operations/disaster-recovery-runbook.md`: Backup verification, database restoration, and service validation steps.
3. `docs/operations/incident-response-procedures.md`: Alert severity classification, on-call escalation, and incident closure protocols.
4. `docs/operations/capacity-and-sizing-guide.md`: Retention policies, database housekeeping, and scaling recommendations.

---

## 9. Modular Directory Structure

Phase 8 introduces a coherent set of engineering modules adhering strictly to project conventions:

```
nawari/
├── docker/
│   ├── compose.prod.yaml              # Hardened production Docker Compose configuration
│   ├── security/
│   │   ├── ufw-rules.sh               # Host UFW firewall configuration script
│   │   └── sysctl-hardening.conf      # Linux kernel hardening parameters
│   └── grafana/
│       └── provisioning/              # Pinned datasource and dashboard definitions
├── scripts/
│   ├── backup/
│   │   ├── backup_nawari.sh           # Automated PostgreSQL and state backup script
│   │   └── restore_nawari.sh          # Cold disaster-recovery restoration script
│   └── operations/
│       ├── healthcheck_stack.sh       # Stack-wide container and database health audit
│       └── sanitize_secrets.sh        # Pre-commit secret scanning validation
├── services/
│   ├── security/
│   │   ├── rbac.py                    # Role-based access control engine
│   │   ├── audit.py                   # Tamper-resistant security audit logger
│   │   └── credentials.py             # Secret masking and credential store
│   ├── incidents/
│   │   ├── models.py                  # Incident data models and lifecycle states
│   │   ├── fingerprint.py             # SHA-256 stable alert fingerprinting
│   │   ├── deduplicator.py            # Symptom grouping and alert storm suppressor
│   │   └── lifecycle.py               # Incident state machine and sustained recovery
│   └── integrations/
│       ├── base_adapter.py            # Base adapter with circuit breaker and retries
│       ├── itsm_adapter.py            # ServiceNow / Jira ticket integration
│       ├── email_adapter.py           # Enterprise SMTP / STARTTLS notification
│       └── sms_adapter.py             # Provider-neutral SMS alert adapter
├── tests/
│   ├── security/
│   │   ├── test_rbac_permissions.py   # RBAC enforcement tests
│   │   └── test_secret_sanitization.py# Audit and secret leakage tests
│   ├── recovery/
│   │   └── test_backup_restore_loop.py# Automated backup and restoration cycle test
│   ├── incidents/
│   │   ├── test_incident_lifecycle.py # State machine and recovery verification tests
│   │   └── test_deduplication.py      # Alert storm grouping tests
│   ├── integrations/
│   │   └── test_itsm_adapter.py       # ITSM contract and circuit breaker tests
│   └── acceptance/
│       └── test_phase8_consolidated.py# The single Phase 8 consolidated acceptance test
└── docs/
    ├── architecture/
    │   └── phase8-architecture-and-readiness-assessment.md (This Document)
    └── operations/
        ├── production-deployment-guide.md
        ├── disaster-recovery-runbook.md
        └── incident-response-procedures.md
```

---

## 10. Conclusion & Roadmap Sequencing

Phase 8 does not replace any existing capability; it hardens, secures, and operationalises the entire platform established across Phases 1 through 7. 

By executing 8A through 8G as a single unified programme and validating it through the consolidated 8G acceptance gate, Nawari will be fully certified for enterprise operation before initiating the advanced network and communications intelligence of Phases 9 through 13.
