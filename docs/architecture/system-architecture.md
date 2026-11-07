# Nawari System Architecture Specification

**Status:** Proposed architecture for review  
**Date:** 2026-11-07  
**Scope:** Local macOS foundation and eventual Ubuntu 24.04 deployment

## 1. Goals and boundaries

Nawari provides service assurance across network infrastructure and Avaya communications. It combines authoritative monitoring data with correlation and operational workflows; it does not replace the monitoring engine or dashboard platform.

### In scope

- Reproducible Zabbix monitoring configuration.
- SNMPv2c/SNMPv3, ICMP, TCP, DNS, HTTP(S), discovery and traps.
- PostgreSQL-backed Zabbix persistence.
- Grafana dashboards backed by the official Zabbix plugin.
- A modular Python API for provisioning, integrations, correlation and service health.
- Evidence-based service and incident summaries.
- A later, controlled Asterisk synthetic voice integration.

### Explicitly out of the first runtime boundary

- OpenSearch and Data Prepper.
- A separate message broker, workflow engine or alert manager.
- A fleet of Nawari microservices.
- Endpoint agents and user-experience monitoring.
- Production SIP/RTP testing.
- Unverified vendor-specific Avaya OIDs.
- TimescaleDB unless a measured Zabbix history workload justifies it.

## 2. Architectural principles

1. **One owner per responsibility:** Zabbix owns collection, history, triggers, problems and primary alerting; Grafana owns visualization; Nawari owns desired-state provisioning, normalization, correlation and service assurance.
2. **Evidence before inference:** missing data is `unknown`, never zero or healthy. Root cause requires supporting observations.
3. **Read-only by default:** monitoring integrations do not change Avaya configuration or network state.
4. **Idempotent operations:** provisioning and reconciliation can be run repeatedly without duplicates.
5. **Modular monolith first:** keep one deployable Nawari API until execution isolation or scale requires a worker/service split.
6. **Production network behavior is a separate proof:** local container success does not prove SNMP, traps, SIP, RTP, routing or source-IP behavior across the enterprise network.
7. **No secrets in Git:** credentials enter through deployment-time secrets or protected environment files.

## 3. Logical architecture

```mermaid
flowchart LR
  Devices["Network devices / Avaya appliances"] -->|SNMP polling| ZServer["Zabbix server"]
  Devices -->|SNMP traps UDP 162| Trap["snmptrapd / Zabbix SNMP traps"]
  Probes["ICMP / TCP / DNS / HTTP checks"] --> ZServer
  DB[(PostgreSQL)] <--> ZServer
  ZServer --> ZWeb["Zabbix frontend"]
  ZServer -->|JSON-RPC API| Nawari["Nawari API"]
  ZServer -->|metrics, problems, events| Grafana["Grafana + Zabbix plugin"]
  Nawari -->|desired-state reconciliation| ZServer
  Nawari -->|service summaries / integrations| Ops["Operators / integrations"]
  Asterisk["Asterisk synthetic engine (later)"] -->|Sender / trapper results| ZServer
  Nawari -->|AMI orchestration (later)| Asterisk
```

## 4. Runtime components

| Component | Initial status | Authority | Persistence |
|---|---|---|---|
| PostgreSQL | Core | Zabbix database | Named volume; backup/restore required |
| Zabbix server (PostgreSQL image) | Core | Monitoring, triggers, problems, history | Configuration and history in PostgreSQL |
| Zabbix web (Nginx/PostgreSQL image) | Core | Administrative UI and API endpoint | Stateless |
| Zabbix SNMP traps | Core | Trap reception and handoff | Shared trap spool volume |
| Grafana | Core | Dashboards and exploration | Named volume plus provisioned files |
| Nawari API | Core | Reconciliation, integration, correlation, service assurance | Initially stateless; PostgreSQL schema only when justified |
| Asterisk | Later | SIP/RTP synthetic execution | Configuration/certificates and test evidence |
| Zabbix Agent 2 | Later | Endpoint telemetry | Endpoint-local |
| OpenTelemetry Collector | Deferred | Application/log telemetry if a real source requires it | Stateless pipeline |
| OpenSearch | Deferred | High-volume event/log analytics if Zabbix is insufficient | Separate capacity decision |

## 5. Nawari application modules

The initial API is one Python package with clear internal boundaries:

```text
nawari/
  api/                 # HTTP routes and request/response models
  config/              # typed settings and secret references
  zabbix/              # API client, desired state, diff and reconciliation
  integrations/        # Avaya, Asterisk, network and endpoint adapters
  correlation/         # evidence collection and hypothesis evaluation
  services/            # service/dependency model and health summaries
  jobs/                # bounded background tasks; no broker initially
  observability/       # structured logs, metrics and audit events
```

Routes should remain thin. Zabbix API access, provisioning and correlation logic must be testable without an HTTP server or live appliances.

## 6. Data and contract model

### Zabbix-owned data

- Hosts, host groups, interfaces and templates.
- Items, discovery rules, prototypes and macros.
- Triggers, actions, services and problem state.
- Raw history and trends.
- Trapper values submitted by Nawari/Asterisk.

### Nawari-owned concepts

- Desired monitoring configuration and reconciliation result.
- Normalized observation reference.
- Service and dependency definition.
- Correlation case with evidence, hypotheses and confidence basis.
- Integration execution and audit record.

Nawari should reference Zabbix identifiers and timestamps rather than duplicating all Zabbix history. A dedicated Nawari database schema is introduced only when a durable workflow or domain entity cannot be represented safely in Zabbix.

### Evidence states

Every correlation result must distinguish:

- `confirmed`: direct supporting observations satisfy the rule.
- `suspected`: evidence supports a hypothesis but is incomplete.
- `symptom`: observed failure with no causal claim.
- `unknown`: required observation is unavailable.
- `not_applicable`: the check does not apply.

## 7. Network and security boundaries

| Flow | Port/protocol | Boundary |
|---|---|---|
| Zabbix server to agents | 10050/TCP | Internal monitoring network only |
| Active Zabbix server ingress | 10051/TCP | Internal/trusted senders only |
| SNMP polling | 161/UDP | Egress to approved device addresses |
| SNMP traps | 162/UDP | Ingress from approved devices to trap receiver |
| Grafana | 3000/TCP | Local/reverse-proxy protected |
| Zabbix web | 8080/HTTP initially | Local/reverse-proxy protected |
| PostgreSQL | 5432/TCP | Docker internal network; never public |
| Nawari API | 8000/TCP initially | Local/internal; authentication required before exposure |
| Asterisk SIP/SIP TLS | 5060/UDP, 5061/TCP later | Explicit production firewall and source-IP validation |
| Asterisk AMI | 5038/TCP later | Private network only; never public |
| RTP | Configured UDP range later | Explicit firewall/NAT/source-IP validation |

SNMPv3 auth/privacy values are supplied at runtime and must not appear in logs, templates or committed `.env` files. Grafana uses a least-privilege Zabbix API token where supported.

## 8. Deployment topology

### Local development

- Docker Desktop on macOS, with ARM64 or amd64 image validation.
- One Compose project with named volumes.
- Core profile starts PostgreSQL, Zabbix server/web/traps, Grafana and Nawari.
- Optional profiles start test tools only.
- Synthetic devices and trap generators are local test fixtures, not claims about production reachability.

### Production target

- Ubuntu 24.04 host.
- Same service definitions with a production override.
- Pinned image tags, resource limits, log rotation, backups and restricted bind addresses.
- Host firewall and network ACLs managed outside the application repository.
- Asterisk is not enabled until source-IP, SIP/TLS, AMI and RTP requirements are approved and tested.

## 9. Architecture decisions requiring review

1. Adopt Zabbix 7.4 PostgreSQL images and the official SNMP trap pattern.
2. Use Grafana at or above the plugin-supported baseline; pin the exact tested version after a plugin smoke test.
3. Use a modular FastAPI application, not microservices.
4. Use YAML desired state, with schema validation and deterministic reconciliation.
5. Defer OpenSearch, OTel, endpoint agents and Asterisk from the core startup profile.
6. Treat all Avaya vendor OIDs as unverified until tested against the deployed release and MIB package.
