# Nawari — Network & Communications Observability Platform

**Nawari** is an enterprise-grade, self-hosted network and communications observability platform designed for mission-critical enterprise environments.

---

## 1. Core Architectural Principle

> **Zabbix monitors. Grafana visualizes. Nawari correlates and assures services.**

- **Zabbix 7.4 (PostgreSQL)** is the authoritative monitoring and alerting engine: SNMPv3, ICMP, TCP/DNS/HTTP probes, Low-Level Discovery (LLD), trap reception, and baseline event management.
- **Grafana 11.6+** provides visualization, executive status views, and operational troubleshooting dashboards via the official `alexanderzobnin-zabbix-app` plugin.
- **Nawari Application Layer** provides desired-state configuration reconciliation, cross-domain telemetry correlation, service dependency modeling, and evidence-based service assurance.

---

## 2. Architecture & Research Documentation Index

Detailed engineering specifications and technical baselines are maintained in `docs/`:

- [System Architecture](docs/architecture/system-architecture.md) — End-to-end component roles, data flow, and evidence states.
- [Docker Architecture](docs/architecture/docker-architecture.md) — Container topology, multi-stage overrides, volume persistence, and isolation.
- [Network Architecture](docs/architecture/network-architecture.md) — Port matrix, enterprise subnets, source IP preservation, and firewall gates.
- [Resource & Capacity Budget](docs/architecture/resource-budget.md) — RAM/CPU/Disk engineering for the 2 vCPU / 7.8 GiB RAM production VM.
- [Technology Viability Assessment](docs/research/technology-viability.md) — Component evaluation against official vendor documentation.
- [Technical Risks & Validation Gates](docs/research/technical-risks.md) — Explicit risk table and non-negotiable safety conditions.
- [Implementation Roadmap](docs/architecture/implementation-roadmap.md) — Phased rollout plan and exit criteria.
- [Local Development Guide](docs/deployment/local-development.md) — macOS ARM64 development instructions.
- [Production Deployment Guide](docs/deployment/production-deployment.md) — Ubuntu 24.04 server staging and operations runbook.

---

## 3. Technology Stack & Component Classification

| Component | Target Version | Decision | Classification |
|---|---|---|---|
| **Zabbix Server & Web** | 7.4 (Alpine, PostgreSQL) | Adopt | **Confirmed** |
| **PostgreSQL Database** | 17 (Alpine) | Adopt | **Confirmed** |
| **SNMP Trap Receiver** | Zabbix 7.4 `snmptrapd` | Adopt | **Confirmed** |
| **Grafana** | 11.6.0 | Adopt | **Confirmed** |
| **Grafana Zabbix Plugin** | `alexanderzobnin-zabbix-app` v6.x | Adopt | **Confirmed** |
| **Nawari API** | Python 3.12+ / FastAPI / Pydantic | Adopt | **Design Confirmed** |
| **Asterisk Synthetic Voice** | 22.11.0 (AMI / PJSIP) | Defer to later profile | **Confirmed Reference / Deferred Runtime** |
| **Avaya SBCE Monitoring** | SNMPv3 `authPriv` (Standard OIDs) | Adopt standard OIDs | **Standard Confirmed / Vendor OIDs Unverified** |
| **Avaya SM / CM Alarms** | SNMP Traps / Polling | Adopt reachability | **Unverified for vendor MIBs** |
| **Zabbix Agent 2** | Latest stable | Defer to later phase | **Unverified for target fleet** |
| **OpenSearch & Dashboards** | 3.8.0 | Defer (Resource constraint) | **Deferred** |
| **OpenTelemetry Collector** | 0.156.0 | Defer (No active pipeline) | **Deferred** |
| **Data Prepper** | N/A | Exclude from core | **Excluded** |
| **Alertmanager** | N/A | Exclude (Zabbix owns alerting) | **Excluded** |
| **Custom SMS Notifier** | N/A | Exclude (Replaced by native integrations) | **Excluded** |

---

## 4. Repository Layout

```text
nawari/
├── docker/
│   ├── compose.yaml              # Core services definition
│   ├── compose.dev.yaml          # Local development overrides
│   ├── compose.prod.yaml         # Production resource limits & overrides
│   ├── zabbix/
│   │   ├── server/               # Zabbix server configs
│   │   ├── snmptraps/            # snmptrapd configs & handlers
│   │   └── mibs/                 # Standard & vendor MIB files
│   ├── grafana/
│   │   ├── provisioning/         # Datasource & plugin provisioning
│   │   └── dashboards/           # Reusable dashboard definitions
│   └── postgres/                 # DB init scripts & tuning
├── services/
│   └── api/                      # Nawari FastAPI modular application
│       ├── api/                  # Routes and API schemas
│       ├── config/               # Settings and secrets loader
│       ├── zabbix/               # Zabbix JSON-RPC client & reconciliation
│       ├── correlation/          # Cross-domain evidence correlator
│       ├── services/             # Service dependency model
│       └── observability/        # Structured logging & metrics
├── provisioning/
│   └── zabbix/                   # Declarative YAML monitoring templates
├── docs/                         # Architecture, research & deployment specs
├── tests/
│   ├── unit/                     # Fast in-memory unit tests
│   ├── integration/              # Container and API integration tests
│   └── mocks/                    # Mock SNMP agents and fixtures
├── scripts/                      # Operational & backup scripts
├── .env.example                  # Template configuration (no committed secrets)
├── .gitignore                    # Robust exclusion patterns
└── README.md
```

---

## 5. Non-Negotiable Safety & Operational Rules

1. **No Secrets in Git**: Passwords, API tokens, and SNMPv3 passphrases exist strictly in runtime `.env` or secret files.
2. **Read-Only by Default**: Monitoring systems must never modify Avaya appliance configurations or network device states.
3. **Evidence Before Root Cause**: Missing telemetry is reported as `unknown`, never as healthy or zero.
4. **No Premature Dialing**: Asterisk synthetic call testing is isolated behind explicit stakeholder sign-off and safety gates (`LIVE_CALLS_ENABLED=false`).
5. **Preserve Sentra as Reference**: Sentra code and databases remain untouched.

---

## 6. Local Quickstart (Phase 1 Stack)

### Prerequisites
- macOS with Apple Silicon (or Linux amd64)
- Docker Desktop 4.30+ with Docker Compose v2
- Python 3.12+ (for automated tests)

### Startup Instructions
1. Clone repository and initialize `.env`:
   ```bash
   cp .env.example .env
   ```
2. Build and launch the Core Phase 1 stack:
   ```bash
   docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml up -d
   ```
3. Verify running containers:
   ```bash
   docker ps --filter "name=nawari-"
   ```

### Service Access & Credentials (Local Development)

| Service | Local URL / Port | Credentials | Purpose |
| :--- | :--- | :--- | :--- |
| **Grafana 11.6** | [http://localhost:3001](http://localhost:3001) | Set via `GRAFANA_ADMIN_*` in `.env` | Visualizations & Dashboards |
| **Zabbix Web 7.4** | [http://localhost:8088](http://localhost:8088) | Set via `ZBX_API_*` in `.env` | Primary Monitoring Console |
| **Zabbix Server** | `127.0.0.1:10051` | Native Zabbix Protocol | Active Agent & Trapper port |
| **PostgreSQL 17** | `127.0.0.1:5433` | Set via `POSTGRES_*` in `.env` | Relational Telemetry Store |
| **SNMP Traps** | `127.0.0.1:162/udp` | SNMP Trap Spooler | Inbound Trap Receiver |

---

## 7. Acceptance Verification

Run the automated acceptance test suite:

```bash
# Run pytest integration tests (12 automated checks)
python3 -m pytest tests/integration/test_core_infrastructure.py -v

# OR run standalone verification script (14 automated checks)
./scripts/verify_phase1.sh
```

Detailed Phase 1 results and benchmarks: [Phase 1 Implementation Report](docs/deployment/phase-1-implementation.md).

