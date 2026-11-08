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

## Phase 10 — Multi-Host Provisioning Automation & Pipeline Hardening

- Containerized service topology orchestration across dedicated monitoring nodes.
- Automated health gating and idempotency validation.
- Zero-drift Zabbix desired-state provisioning engine (`provisioning_orchestrator.py`).
- Deterministic verification suite (`scripts/verify_phase10.sh`).

**Exit gate:** all provisioning runs converge with zero duplicate objects and zero unhandled exceptions.

## Phase 11 — Security Controls, Auditing & Access Boundaries

- Least-privilege API tokens and role-based access control (RBAC).
- Read-only datasource isolation for Grafana.
- Air-gapped secret handling and environmental isolation.
- Strict repository boundary enforcement: `sentra` working tree preserved clean at baseline commit `9970404`.

**Exit gate:** security audit script passes 100%; zero leaked credentials or unauthorized write scopes.

## Phase 12 — Production-Scale Performance & Resiliency Testing

- High-throughput Zabbix Trapper ingestion stress-testing (1,000+ metrics/sec).
- Time-series metric retention and database partitioning verification.
- Simulated network failure recovery drills (core switch, carrier trunk, probe node).
- Zero-loss message queue buffering under container restart.

**Exit gate:** synthetic load generates zero packet drops; metric backlog resolves within 30 seconds of service restoration.

## Phase 13 — Avaya Multi-Device Observability, Native Alerting & Communication

- Separation of Avaya infrastructure dashboards into dedicated, scoped views:
  - Communication Manager Duplex Pair (`avaya-cm-01`, `avaya-cm-02`)
  - Session Manager Cluster (`avaya-sm-01`, `avaya-sm-02`)
  - Session Border Controller Enterprise (`avaya-sbce-01`, `avaya-sbce-02`)
  - G450 Media Gateway Fleet (`avaya-g450-01`)
  - Carrier SIP Interconnects (`sip-trunk-carrier-01`)
- Zabbix native trigger and action architecture replacing dual-engine evaluation.
- Staging simulated telemetry vs. production telemetry evidence categorization (`CONFIGURED_UNVERIFIED`).
- Phase 13.7: Deterministic notification lifecycle validation, tag-based routing, retirement of legacy Action 7, and zero platform branding enforcement.

### Phase 13.8 — Native Alerting Architecture & Controlled Operational Transition

The Phase 13.8 milestone is partitioned into three rigorous engineering phases to ensure technically defensible thresholds and actionable notifications before production telemetry commissioning:

#### Phase 13.8A — Trigger Threshold Rationalisation & Alert Policy Engineering (Current)
- **Authoritative Threshold Register:** Full inventory and specification of every trigger across all 10 templates and 12 monitored hosts using the 16-field metadata schema.
- **Five-Question Framework:** Every threshold answers: What is measured, acceptable range, alert boundary, persistence duration, and recovery evidence.
- **Severity Model Standard:** 5 Zabbix severities mapped strictly to operational impact (Information, Warning, Average, High, Disaster). Prohibits severity inflation.
- **Metric vs. Outage Decoupling:** Decouples raw metric measurement $\to$ threshold evaluation $\to$ trigger severity $\to$ service-impact correlation $\to$ notification classification (`total_outage`, `service_outage`, `synthetic_failure`, `degradation`, `component_failure`, `monitoring_failure`).
- **Persistence & Anti-Flapping Hysteresis:** Establishes mathematical hysteresis margins (e.g. `min(5m) > 90%` problem, `max(5m) < 80%` recovery) and consecutive failure counts.
- **Rate-Based Interface Metrics:** Enforces 64-bit rate calculations for utilization, errors, and discards; strictly prohibits static thresholds on raw cumulative counters.
- **Gated Telemetry Isolation:** Formal identification and gating of unsupported/unverified metrics (e.g. G450 DSP utilization, live per-call RTCP jitter, deep EMS licensing) without fictitious active triggers.

**Exit gate:** 100% trigger inventory documented in authoritative register; automated audit suite (`test_phase13_8a_threshold_rationalisation.py`) passes 10/10 tests.

#### Phase 13.8B — Zabbix Template Threshold & Recovery Expression Implementation
- Deploy approved thresholds, persistence expressions, and recovery hysteresis into Zabbix template YAMLs and live Zabbix API.
- Update trigger prototypes for LLD network interfaces.
- Reconcile trigger priorities and expression syntax.

**Exit gate:** Zabbix API confirms zero syntax errors, valid recovery modes (`recovery_mode: 1`), and reconciled trigger definitions.

#### Phase 13.8C — Alert Behaviour, Event Classification & Runtime Notification Verification
- Validate live event engine dispatches via `ZabbixSender` across Actions 10–15.
- Verify native macro expansion (`{EVENT.DURATION}`, `{HOST.NAME}`, `{EVENT.SEVERITY}`) and zero platform branding.
- Confirm recipient targeting (Action 10 to all 5 recipients; Actions 11–12 to 4 Voice Admins; Service Desk excluded from component alerts).
- Maintain Email media type in `CONFIGURED_UNVERIFIED` state (zero external email transmissions).

**Exit gate:** Live Zabbix API confirms 100% action mutual exclusivity, valid macro expansion, correct recipient group targeting, and passing `verify_phase13.sh`.

---

## Phase 13.9 — Controlled Read-Only Production Telemetry Commissioning Gate (Phase 8.2 Gate)

The transition from staging validation to live production monitoring is strictly gated. Staging runtime proof does not permit automatic production mutation.

```
+-------------------------------------------------------------------------+
| Phase 13.8C Staging Runtime Verification & Alert Policy (ACCEPTED)      |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| PHASE 13.9 / PHASE 8.2: CONTROLLED PRODUCTION TELEMETRY COMMISSIONING   |
|                                                                         |
| 1. Read-Only Production Telemetry Ingestion:                            |
|    - Connect to production Avaya SNMP interfaces (CM, SM, SBCE, G450)   |
|    - Validate official Avaya OIDs against live appliances               |
|    - Receive production SNMP traps and Syslog feeds                     |
|                                                                         |
| 2. Microsoft 365 OAuth 2.0 Email Media Commissioning:                   |
|    - Configure Azure AD / Entra ID Client ID, Tenant ID & Secret        |
|    - Transition Email Media Type from CONFIGURED_UNVERIFIED to VERIFIED |
|    - Perform single-recipient test before enabling all-group broadcast |
|                                                                         |
| 3. Mandatory Safety Enforcement:                                        |
|    - mon-grafana01 mutation lock remains locked                         |
|    - HARD_PRODUCTION_DENY remains enforced: ZERO automated carrier     |
|      failovers, gateway reboots, or production configuration mutations  |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Executive Operational Sign-off (KQ IT Service Desk & Voice Engineering) |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Live Production Delivery & Active Service Assurance                     |
+-------------------------------------------------------------------------+
```

### Safety & Mutation Policy: HARD_PRODUCTION_DENY

At all stages of deployment, Nawari operates under strict read-only assurance principles:
- **`HARD_PRODUCTION_DENY`**: The `AutomationPolicyEngine` unconditionally denies and blocks any automated operational action targeting production infrastructure (`ActionState.BLOCKED`). Automated failovers, trunk rerouting, and appliance reboots must never occur without manual engineer execution.
- **Repository Isolation**: The upstream `sentra` repository remains completely isolated at baseline commit `9970404`. No code, configuration, or operational dependencies may alter the Sentra working tree.

---

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
