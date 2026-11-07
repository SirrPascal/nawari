# Nawari Technology Viability & Compatibility Assessment

**Status:** Technical Baseline & Decisions  
**Date:** 2026-11-07  
**Scope:** Evaluation of candidate technologies against official documentation, architecture support, resource boundaries, and operational viability.

---

## 1. Classification Vocabulary

- **Confirmed:** Supported by official vendor documentation or established working code.
- **Validated:** Formally verified and passing automated acceptance tests in Nawari.
- **Unverified:** Requires access to live physical appliances, enterprise network paths, or vendor-specific MIB packages.
- **Deferred:** Intentionally excluded from the core deployment to protect host resources and maintain architectural discipline.
- **Rejected:** Incompatible, redundant, or architecturally unsuitable.

---

## 2. Technology Viability Matrix

### 1. Zabbix 7.4 Server (PostgreSQL)
- **Role:** Primary monitoring engine, discovery, polling, triggers, events, and trapper item datastore.
- **Why Required:** Authoritative enterprise monitoring system with native SNMPv3, ICMP, LLD, and robust JSON-RPC API.
- **Official Documentation Consulted:**
  - [Zabbix 7.4 Container Installation](https://www.zabbix.com/documentation/7.4/en/manual/installation/containers)
  - [Zabbix 7.4 SNMP Traps](https://www.zabbix.com/documentation/7.4/en/manual/config/items/itemtypes/snmptrap)
  - [Zabbix 7.4 API Reference](https://www.zabbix.com/documentation/7.4/en/manual/api)
- **Image & Tag:** `zabbix/zabbix-server-pgsql:alpine-7.4-latest`
- **Architecture Support:** Multi-arch manifest (`linux/amd64` and `linux/arm64` confirmed).
- **Resource Impact:** ~160 MiB RSS baseline; 512 MiB limit. Extremely lightweight compared to Java stacks.
- **Security Considerations:** Dedicated non-root user inside container; DB password injected via environment; listens on port 10051.
- **Decision:** **ADOPT (Confirmed)**.

---

### 2. PostgreSQL 17
- **Role:** Relational database backing Zabbix Server and Web.
- **Why Required:** Standard relational ACID storage for monitoring definitions, users, triggers, and time-series history.
- **Official Documentation Consulted:**
  - [PostgreSQL Official Docker Library](https://hub.docker.com/_/postgres)
  - [Zabbix Database Requirements](https://www.zabbix.com/documentation/7.4/en/manual/installation/requirements#databases)
- **Image & Tag:** `postgres:17-alpine`
- **Architecture Support:** Native multi-arch (`linux/amd64` and `linux/arm64`).
- **Resource Impact:** ~180 MiB RSS; 512 MiB limit.
- **Security Considerations:** No public port exposure; isolated within `nawari-internal` Docker bridge; strong password policy.
- **Decision:** **ADOPT (Confirmed)**.

---

### 3. Zabbix Web Frontend (NGINX / PostgreSQL)
- **Role:** Administrative UI and JSON-RPC API endpoint (`/api_jsonrpc.php`).
- **Why Required:** Facilitates manual operator review and programmatic reconciliation via the Nawari API and Grafana plugin.
- **Official Documentation Consulted:** [Zabbix Web Docker Documentation](https://www.zabbix.com/documentation/7.4/en/manual/installation/containers#zabbix-frontend)
- **Image & Tag:** `zabbix/zabbix-web-nginx-pgsql:alpine-7.4-latest`
- **Architecture Support:** Multi-arch (`linux/amd64` and `linux/arm64`).
- **Resource Impact:** ~90 MiB RSS; 256 MiB limit.
- **Security Considerations:** Bound to localhost `127.0.0.1:8080`; API token authentication supported.
- **Decision:** **ADOPT (Confirmed)**.

---

### 4. Zabbix SNMP Traps Receiver
- **Role:** Asynchronous trap receiver daemon (`snmptrapd`).
- **Why Required:** Catches unsolicited hardware, link, and Avaya alarm traps sent via UDP port 162.
- **Official Documentation Consulted:** [Zabbix SNMP Traps in Docker](https://www.zabbix.com/documentation/7.4/en/manual/config/items/itemtypes/snmptrap)
- **Architecture Requirement:**
  - Must mount shared volume `snmptrap-spool` to `/var/lib/zabbix/snmptraps`.
  - Appends traps to `/var/lib/zabbix/snmptraps/snmptraps.log`.
  - Server reads this file via `SNMPTrapper` threads (`ZBX_ENABLE_SNMP_TRAPS=true`).
- **Image & Tag:** `zabbix/zabbix-snmptraps:alpine-7.4-latest`
- **Architecture Support:** Multi-arch (`linux/amd64` and `linux/arm64`).
- **Resource Impact:** ~25 MiB RSS; 64 MiB limit.
- **Decision:** **ADOPT (Confirmed)**.

---

### 5. Grafana 11.6+
- **Role:** Central visualization platform for operational dashboards.
- **Why Required:** Reusable dashboard templates, dynamic templating variables, and native integration with the Zabbix plugin.
- **Official Documentation Consulted:**
  - [Grafana Docker Installation](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/)
  - [Grafana Plugin Architecture & Deprecations](https://grafana.com/docs/grafana/latest/developers/plugins/)
- **Image & Tag:** `grafana/grafana:11.6.0`
- **Architecture Support:** Multi-arch (`linux/amd64` and `linux/arm64`).
- **Critical Compatibility Finding:** The official Zabbix plugin (`alexanderzobnin-zabbix-app`) requires Grafana **11.6 or later**. The Sentra project's Grafana 11.5.0 cannot be carried forward.
- **Resource Impact:** ~130 MiB RSS; 300 MiB limit.
- **Decision:** **ADOPT (Confirmed)**.

---

### 6. Official Grafana Zabbix Plugin (`alexanderzobnin-zabbix-app`)
- **Role:** Bridges Grafana queries to Zabbix's JSON-RPC API for metrics, item values, and active problem states.
- **Official Documentation Consulted:**
  - [Grafana Zabbix App Plugin](https://grafana.com/grafana/plugins/alexanderzobnin-zabbix-app/)
  - [Plugin Provisioning Guide](https://grafana.com/docs/plugins/alexanderzobnin-zabbix-app/latest/configure/)
- **Installation Method:** Provisioned via `GF_INSTALL_PLUGINS=alexanderzobnin-zabbix-app` and enabled via `/etc/grafana/provisioning/plugins/zabbix.yaml`.
- **Authentication:** Uses Zabbix API token with Bearer authorization.
- **Decision:** **ADOPT (Confirmed)**.

---

### 7. Nawari Application Layer (Python 3 / FastAPI / Pydantic)
- **Role:** Idempotent provisioning engine, monitoring reconciliation, cross-domain event correlation, and service health calculation.
- **Why Required:** Standard monitoring engines do not model higher-order service assurance across disparate network, telephony, and endpoint domains.
- **Design Pattern:** Modular monolith (not microservices). Runs as a single container `nawari-api` with separate internal modules.
- **Resource Impact:** ~85 MiB RSS; 256 MiB limit.
- **Decision:** **ADOPT (Design Confirmed)**.

---

### 8. Asterisk 22.11.0 (Synthetic Voice Assurance Engine)
- **Role:** Executes scheduled, non-invasive synthetic SIP/TLS calls, validates mTLS handshakes, and observes media streams.
- **Official Documentation Consulted:**
  - [Asterisk 22 Documentation](https://docs.asterisk.org/Asterisk_22_Documentation/)
  - [Asterisk Manager Interface (AMI)](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-Manager-Interface-AMI/)
  - [Asterisk PJSIP Configuration](https://docs.asterisk.org/Configuration/Channel-Drivers/SIP/Configuring-res_pjsip/)
- **Portability:** Requires multi-arch build (`linux/arm64` for Mac dev, native `linux/amd64` for target server `mon-grafana01`).
- **Resource Impact:** ~140 MiB RSS; 300 MiB limit.
- **Status & Decision:** **DEFER TO LATER PROFILE (Confirmed Reference, Deferred Runtime)**. Enabled only when production certificates, network firewall rules, and stakeholder approvals are in place.

---

### 9. Zabbix Agent 2 (Endpoint Telemetry)
- **Role:** Collects OS, network adapter, default gateway reachability, and user-experience latency on Linux/Windows desktops.
- **Decision:** **DEFER (Unverified for target fleet)**. Requires an approved endpoint rollout policy and packaging strategy.

---

### 10. OpenTelemetry Collector (Contrib)
- **Role:** Open-standard telemetry proxy for metrics, logs, and traces.
- **Decision:** **DEFER (Deferred Scope)**. Adding an OTel pipeline without a dedicated telemetry source creates unnecessary complexity.

---

### 11. OpenSearch & OpenSearch Dashboards
- **Role:** Distributed log search and indexing engine.
- **Decision:** **DEFER (Deferred Scope)**. OpenSearch consumed >2.5 GiB of RAM in Sentra. Zabbix handles metrics, triggers, and events directly; OpenSearch is deferred until high-volume log analytics (e.g. SIP packet dumps or deep syslog) are formally justified.

---

### 12. TimescaleDB
- **Role:** PostgreSQL time-series extension for chunked hypertables.
- **Decision:** **DEFER (Unverified Benefit)**. Not justified for the initial workload of ~2,500 items and 7-day retention. Adds build complexity and upgrade friction.

---

### 13. Avaya SBCE 10.2 Monitoring
- **Role:** Edge SIP session border controller monitoring.
- **Connectivity:** SNMPv3 `authPriv` (`Admin`, `SHA`, `DES`).
- **Verified Standard OIDs:** System MIB (`1.3.6.1.2.1.1.x`), Interface MIB / IF-MIB (`1.3.6.1.2.1.2.2.1.x`, `1.3.6.1.2.1.31.1.1.1.x`).
- **Vendor Specific OIDs:** Marked as **Unverified**. Must be validated against live appliance MIB exports rather than fabricated.
- **Decision:** **ADOPT STANDARD OIDS; DEFER UNVERIFIED VENDOR OIDS**.

---

### 14. Avaya Session Manager & Communication Manager
- **Role:** Core SIP routing and call processing engines.
- **Status:** **UNVERIFIED INTEGRATION PATH**. Standard SNMP/ICMP reachability is confirmed, but vendor-specific alarms and SAL gateway forwarding require live appliance discovery.
- **Decision:** **ADOPT ICMP/TCP REACHABILITY; DEFER VENDOR-SPECIFIC MIBs UNTIL VALIDATED**.

