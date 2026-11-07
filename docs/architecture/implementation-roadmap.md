# Nawari Implementation Roadmap

**Status:** Proposed sequence  
**Date:** 2026-11-07

The roadmap is dependency-ordered. A later phase may not claim production readiness from a local simulation or bypass an explicit gate.

## Phase 0 — Repository and decision baseline

**Deliverables**

- Git repository and protected default branch.
- `.gitignore`, `.env.example`, README and documentation index.
- Architecture, compatibility and risk documents.
- Sentra reuse inventory with no Sentra file modifications.
- Local host architecture, Docker Engine and Compose versions recorded.

**Exit gate:** decisions are reviewed; no unresolved decision silently becomes an implementation assumption.

## Phase 1 — Core Compose foundation

**Build**

- PostgreSQL.
- Zabbix server with PostgreSQL.
- Zabbix Nginx frontend with PostgreSQL.
- Official SNMP trap receiver and shared spool volume.
- Grafana with the selected Zabbix plugin.
- Nawari API health endpoint and structured logging.

**Engineering requirements**

- Explicit full image tags.
- Named persistent volumes.
- Health checks and dependency conditions.
- Internal Docker network.
- Minimal host bindings.
- Resource limits and log rotation.
- Development and production Compose overrides.

**Exit gate:** clean startup, restart/recovery, frontend/API access, protected credentials, architecture-compatible images and no required production network access.

## Phase 2 — Nawari configuration and provisioning

**Build**

- Typed settings with secret references.
- Zabbix JSON-RPC client with timeout, authentication and error contracts.
- YAML desired-state schema.
- Deterministic diff engine.
- Idempotent reconciliation for host groups, hosts, interfaces, templates, items, triggers, discovery and macros.
- Dry-run and change report.

**Exit gate:** two consecutive runs produce no duplicate objects; simulated API failures are explicit and actionable.

## Phase 3 — Generic network monitoring

**Build**

- Reusable standard SNMP interface template.
- ICMP, packet loss, response time, TCP, DNS and HTTP checks.
- 64-bit interface counters, rates, errors and discards.
- Interface discovery and operational-state triggers.
- Evidence-backed topology inputs (LLDP/CDP/bridge/ARP/routing where available), without guessed edges.

**Exit gate:** simulated SNMP device data and discovery produce expected items, units and trigger behavior.

## Phase 4 — Avaya SBCE and trap integration

**Build**

- SBCE host group and standard OID template from validated MIB evidence.
- SNMPv3 authPriv configuration supplied only at runtime.
- Trap item/fallback strategy and normalized event mapping.
- Syslog integration only if a concrete source and destination are approved.

**Exit gate:** actual appliance release/MIB evidence validates every vendor-specific OID; an authorized trap reaches the matching Zabbix host.

## Phase 5 — Grafana operational views

**Build**

- Network overview.
- Device and interface health.
- SBCE health and alarms.
- Service availability and problem views.
- Variables for site, host group, host and interface.
- Provisioned datasource and dashboards.

**Exit gate:** dashboards query Zabbix using least privilege and show unknown/missing data distinctly from zero.

## Phase 6 — Asterisk/SIP synthetic assurance

**Build only after network approval**

- Isolated Asterisk profile.
- Nawari orchestration over private AMI.
- SIP Call-ID, AMI ActionID, Uniqueid, Linkedid and timestamps correlation.
- Separate signalling and media verdicts.
- Zabbix trapper/Sender metrics with explicit units.
- Circuit breaker, cooldown and live-call safety gates.

**Exit gate:** fixture tests prove correlation and timeout behavior; authorized production tests prove SIP/TLS, answer, media and hangup. A SIP 200 alone is never sufficient.

## Phase 7 — Cross-domain service assurance

**Build**

- Service/dependency model.
- Evidence collection from Zabbix problems, network probes, Avaya integrations and synthetic tests.
- Hypotheses classified as confirmed, suspected, symptom or unknown.
- Deduplication and dependency-aware incident summaries.
- Audit trail for correlation decisions.

**Exit gate:** controlled failure scenarios produce correct evidence and do not claim unsupported root causes.

## Phase 8 — Endpoint and advanced telemetry evaluation

Evaluate, do not automatically deploy:

- Zabbix Agent 2 pilots.
- Endpoint-to-service probes.
- OpenTelemetry for a named telemetry source.
- OpenSearch for a measured high-volume event-analysis requirement.
- TimescaleDB only after Zabbix history/storage measurements.

**Exit gate:** a written capacity/use-case decision exists for every optional component.

## Phase 9 — Production readiness

- Ubuntu 24.04 deployment override.
- Backup/restore and upgrade procedures.
- TLS/reverse proxy and host firewall integration.
- Secret rotation procedure.
- Resource and disk monitoring.
- Failure/recovery drills.
- Operational runbooks and support ownership.

**Exit gate:** restore test, security review, image scan, configuration reconciliation, monitoring self-observation and approved network validation are complete.

## Initial implementation order

1. Review these documents and approve boundaries.
2. Initialize Git metadata and repository hygiene.
3. Implement the core Compose profile.
4. Add automated startup/configuration tests.
5. Implement the Zabbix desired-state engine.
6. Add generic templates before vendor-specific OIDs.
7. Provision Grafana after the datasource contract is proven.
8. Add Avaya and Asterisk only behind explicit validation gates.

## Reusable Sentra components

Reference, test and adapt selectively:

- `asterisk/engine/avtest/ami.py`
- `asterisk/engine/avtest/preflight.py`
- `asterisk/engine/avtest/sip_ami_correlator.py`
- `asterisk/engine/avtest/schema.py`
- `asterisk/engine/avtest/outcomes.py`
- `collectors/devices/network_diagnostics.py`
- Safety, environment and network tests under `sentra/tests/`

Do not copy Sentra's Compose file, production `.env` assumptions, OpenSearch-first data model, secrets archives or hard-coded network identities.
