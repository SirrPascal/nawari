# Nawari Docker Architecture Specification

**Status:** Technical Baseline  
**Date:** 2026-11-07  
**Target Environments:** macOS (Apple Silicon ARM64, Local Dev) & Ubuntu 24.04 LTS (x86_64, Production Host `mon-grafana01`)

---

## 1. Architectural Overview

Nawari uses a layered, multi-container Docker Compose architecture designed for strict service isolation, deterministic startup ordering, persistent storage integrity, and minimal resource overhead on resource-constrained production VMs (2 vCPU, 7.8 GiB RAM).

```mermaid
flowchart TD
    subgraph Host Network Boundaries
        TRAP_IN["Incoming SNMP Traps (UDP 162)"]
        WEB_USER["Operator / Engineer Browser"]
        REST_API["API Clients / Integrations"]
    end

    subgraph "Nawari Internal Bridge Network (172.28.0.0/16)"
        DB[(PostgreSQL 17)]
        Z_TRAPS["zabbix-snmptraps (7.4)"]
        Z_SRV["zabbix-server-pgsql (7.4)"]
        Z_WEB["zabbix-web-nginx-pgsql (7.4)"]
        GRAFANA["Grafana (11.6+) + Zabbix App"]
        API["Nawari API (FastAPI)"]
        
        subgraph Profile: Voice (Deferred)
            AST["Asterisk (22.11.0)"]
        end
    end

    subgraph Named Persistent Volumes
        VOL_PG[("postgres-data")]
        VOL_TRAP[("snmptrap-spool")]
        VOL_GRAF[("grafana-data")]
        VOL_MIB[("zabbix-mibs")]
    end

    TRAP_IN -->|UDP 162| Z_TRAPS
    Z_TRAPS -->|write snmptraps.log| VOL_TRAP
    VOL_TRAP -->|read snmptraps.log| Z_SRV

    Z_SRV <--> DB
    Z_WEB <--> DB
    Z_WEB <--> Z_SRV

    VOL_PG <--> DB
    VOL_MIB --> Z_SRV
    VOL_MIB --> Z_TRAPS

    API -->|JSON-RPC API (port 8080)| Z_WEB
    GRAFANA -->|JSON-RPC API (port 8080)| Z_WEB
    VOL_GRAF <--> GRAFANA

    WEB_USER -->|127.0.0.1:3001| GRAFANA
    WEB_USER -->|127.0.0.1:8080| Z_WEB
    REST_API -->|127.0.0.1:8000| API

    API -.->|AMI port 5038 (Local)| AST
    AST -.->|Zabbix Sender (port 10051)| Z_SRV
```

---

## 2. Core Service Topology & Responsibilities

| Container Service | Base Image | Pinned Tag Baseline | Architecture Support | Primary Function |
|---|---|---|---|---|
| `postgres` | `postgres` | `17-alpine` | `linux/amd64`, `linux/arm64` | Relational datastore for Zabbix configuration, items, trends, and history. |
| `zabbix-server` | `zabbix/zabbix-server-pgsql` | `alpine-7.4-latest` | `linux/amd64`, `linux/arm64` | Core monitoring daemon: SNMP polling, ICMP pinging, problem generation, LLD discovery, trapper engine. |
| `zabbix-web` | `zabbix/zabbix-web-nginx-pgsql` | `alpine-7.4-latest` | `linux/amd64`, `linux/arm64` | Administrative UI and JSON-RPC 2.0 API gateway (`api_jsonrpc.php`). |
| `zabbix-snmptraps` | `zabbix/zabbix-snmptraps` | `alpine-7.4-latest` | `linux/amd64`, `linux/arm64` | `snmptrapd` listener that receives traps on UDP 162 and spools them into shared log files. |
| `grafana` | `grafana/grafana` | `11.6.0` | `linux/amd64`, `linux/arm64` | Operational visualization and unified executive dashboards. Uses `alexanderzobnin-zabbix-app` v6.x. |
| `nawari-api` | Built from `services/api` | `nawari-api:0.1.0` | `linux/amd64`, `linux/arm64` | Python 3 / FastAPI modular service for desired-state reconciliation, correlation, and health calculation. |
| `asterisk` *(Deferred Profile `voice`)* | Built from `asterisk/docker` | `avtest-asterisk:22.11.0` | `linux/amd64`, `linux/arm64` | Synthetic SIP signaling, mTLS handshake testing, and controlled media loop generation. |

---

## 3. Storage and Volume Strategy

Nawari enforces explicit volume mapping to guarantee that no telemetry, configuration, or state is lost during container redeployments or upgrades:

1. **`postgres-data` (`/var/lib/postgresql/data`)**:
   - Contains all relational schema definitions, user accounts, host definitions, discovery rules, item history, and trend aggregates.
   - Initialized with UTF-8 locale and UTC timezone.
2. **`snmptrap-spool` (`/var/lib/zabbix/snmptraps`)**:
   - **Crucial Shared Volume**: Mounted read-write to `zabbix-snmptraps` and read-only to `zabbix-server`.
   - `zabbix-snmptraps` appends incoming traps to `snmptraps.log`.
   - `zabbix-server` reads `snmptraps.log` using internal `SNMPTrapper` threads enabled via `ZBX_ENABLE_SNMP_TRAPS=true`.
3. **`grafana-data` (`/var/lib/grafana`)**:
   - Persists user preferences, internal session data, and plugin state.
   - Dashboards and datasources are declared as code under `docker/grafana/provisioning/` to maintain reproducibility.
4. **`zabbix-mibs` (`/usr/share/snmp/mibs`)**:
   - Mounted to both `zabbix-server` and `zabbix-snmptraps` to enable parsing of Avaya and network vendor MIB files.

---

## 4. Multi-Stage Compose Architecture

Nawari adopts a 3-tier Compose override pattern:

```text
docker/
  ├── compose.yaml          # Base definitions: containers, volumes, internal network, healthchecks
  ├── compose.dev.yaml      # Development overrides: host port mappings, debug logging, reload mounts
  └── compose.prod.yaml     # Production overrides: strict memory/CPU limits, log rotation, isolated loopback
```

### Execution Commands:

- **Local Development (macOS ARM64):**
  ```bash
  docker compose -f docker/compose.yaml -f docker/compose.dev.yaml up -d
  ```

- **Production Server (`mon-grafana01` Ubuntu 24.04 x86_64):**
  ```bash
  docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d
  ```

- **Optional Profiles (e.g. Synthetic Voice Assurance):**
  ```bash
  docker compose --profile voice up -d
  ```

---

## 5. Security & Runtime Isolation Constraints

1. **No Public Database Binding**: PostgreSQL port `5432` is attached strictly to the internal bridge network. It is never exposed to `0.0.0.0` or external network adapters.
2. **Localhost Binding for Administrative Interfaces**:
   - Grafana is bound to `127.0.0.1:3001` (preventing conflict with any legacy services).
   - Zabbix Web is bound to `127.0.0.1:8080`.
   - Nawari API is bound to `127.0.0.1:8000`.
   - Asterisk AMI is bound strictly to `127.0.0.1:5038` and accessible only via trusted localhost/internal containers.
3. **SNMP Trap Ingress**: UDP port `162` is bound to host interfaces to receive traps from Avaya SBCE, Session Managers, and network switches.
4. **Credential Injection**: All sensitive credentials (DB passwords, SNMPv3 passphrases, API secrets) are injected via `.env` or Docker secret files; no credentials appear in container images or Git history.

