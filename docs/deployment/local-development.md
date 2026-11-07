# Nawari Local Development Guide

**Target Environment:** macOS (Apple Silicon ARM64 / M3 Pro, Docker Desktop)  
**Date:** 2026-11-07

---

## 1. Prerequisites

- **Host Hardware:** Apple Silicon Mac (M1/M2/M3).
- **Docker:** Docker Desktop 29.x+ with Docker Compose v5.x+.
- **Python:** Python 3.12 or 3.13 (`pytest` installed for unit tests).
- **Terminal Shell:** `zsh` or `bash`.

---

## 2. Quickstart Configuration

1. **Navigate to the Project Root:**
   ```bash
   cd ~/Desktop/Projects/nawari
   ```

2. **Initialize Environment Configuration:**
   ```bash
   cp .env.example .env
   ```
   *Review `.env` and verify port assignments (e.g. Grafana on port 3001 to prevent conflicts with legacy Sentra containers).*

3. **Validate Docker Engine Status:**
   ```bash
   docker info > /dev/null 2>&1 && echo "Docker daemon is ready" || echo "Docker is not running"
   ```

---

## 3. Starting the Core Development Stack

The development stack starts the Phase 1 core services: PostgreSQL 17, Zabbix Server 7.4, Zabbix Web 7.4, Zabbix SNMP Traps, and Grafana 11.6+.

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml up -d
```

### Checking Container Health:
```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml ps
```

All core containers should transition to `healthy` status within 20–40 seconds.

---

## 4. Local Service Access Endpoints

| Service | Local URL / Binding | Default Credentials | Description |
|---|---|---|---|
| **Grafana** | [http://localhost:3001](http://localhost:3001) | Set via `.env` (`GRAFANA_ADMIN_*`) | Central visualization dashboard |
| **Zabbix Web** | [http://localhost:8088](http://localhost:8088) | Set via `.env` (`ZBX_API_*`) | Monitoring administration & API |
| **Zabbix Server Trap Receiver** | `udp://localhost:162` | N/A | Local trap receiver port |
| **Zabbix Server Trapper** | `tcp://127.0.0.1:10051` | N/A | Zabbix agent & trapper port |
| **PostgreSQL 17** | `127.0.0.1:5433` | Set via `.env` (`POSTGRES_*`) | Relational state & telemetry store |

---

## 5. Running Automated Acceptance Tests

Run the full automated integration test suite against the running stack:

```bash
# Using pytest (12 automated checks covering compose, containers, DB, API, Grafana, Traps, RAM)
python3 -m pytest tests/integration/test_core_infrastructure.py -v

# OR using the standalone verification script (14 automated checks)
./scripts/verify_phase1.sh
```

---

## 6. Simulating Telemetry Locally

Because macOS cannot directly poll the production Avaya subnets without corporate VPN and route attachments, local development uses simulation fixtures:

- **Mock SNMP Polling:** `tests/mocks/mock_snmp_agent.py` simulates SBCE IF-MIB and System MIB responses.
- **Trap Generation Test:**
  ```bash
  snmptrap -v 2c -c public 127.0.0.1:162 "" 1.3.6.1.4.1.6889.1.1 1.3.6.1.4.1.6889.1.1.1 s "TEST_TRAP"
  ```
  Verify trap reception in `/var/lib/zabbix/snmptraps/snmptraps.log` inside the `zabbix-snmptraps` container.

---

## 7. Graceful Teardown

To stop all services and preserve data in persistent named volumes:
```bash
docker compose -f docker/compose.yaml -f docker/compose.dev.yaml stop
```

To completely remove containers and the local bridge network (volumes preserved):
```bash
docker compose -f docker/compose.yaml -f docker/compose.dev.yaml down
```

