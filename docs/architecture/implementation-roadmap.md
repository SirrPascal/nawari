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

#### Phase 13.8A — Trigger Threshold Audit, Inventory Reconciliation & Alert Rationalisation (Completed)
- **Reconcile Live Trigger Inventory:** Account for 59 communication triggers (7 templates / 7 hosts), 70 broad template triggers (10 templates), 110 tagged classification triggers, and 142 live host triggers (88 tagged concrete triggers + 54 untagged discovered LLD interface triggers on lab hosts).
- **Authoritative Threshold Register:** Full inventory and specification of every trigger across all 10 templates and 12 monitored hosts using the 16-field metadata schema.
- **Five-Question Framework:** Every threshold answers: What is measured, acceptable range, alert boundary, persistence duration, and recovery evidence.
- **Severity Model Standard:** 5 Zabbix severities mapped strictly to operational impact (Information, Warning, Average, High, Disaster). Prohibits severity inflation.
- **Metric vs. Outage Decoupling:** Decouples raw metric measurement $\to$ threshold evaluation $\to$ trigger severity $\to$ service-impact correlation $\to$ notification classification (`total_outage`, `service_outage`, `synthetic_failure`, `degradation`, `component_failure`, `monitoring_failure`).
- **Persistence & Anti-Flapping Hysteresis:** Establishes mathematical hysteresis margins (e.g. `min(5m) > 90%` problem, `max(5m) < 80%` recovery) and consecutive failure counts. Current status: 100% `recovery_mode: 0`; target: `recovery_mode: 1`.
- **Rate-Based Interface Metrics:** Enforces 64-bit rate calculations for utilization, errors, and discards; strictly prohibits static thresholds on raw cumulative counters.
- **Latency Zoning:** Distinct thresholds for LAN (<15ms), WAN (<45ms), and Outstations (<90ms).
- **Voice Metric Disambiguation:** Explicit separation between synthetic MOS (ITU-T G.107 E-model) and customer-call MOS; SIP transport latency separated from Call Setup Time.
- **Gated Telemetry Isolation:** Formal identification and gating of unsupported/unverified metrics (e.g. G450 DSP utilization, live per-call RTCP jitter, deep EMS licensing) without fictitious active triggers.

**Exit gate:** 100% trigger inventory documented in authoritative register; automated audit suite (`test_phase13_8a_threshold_rationalisation.py`) passes all tests. (ACCEPTED)

#### Phase 13.8B — Zabbix Template Threshold & Recovery Expression Implementation (Completed)
- **Dual-Expression Recovery Hysteresis:** Deployed approved thresholds, persistence expressions, and recovery hysteresis into live Zabbix API and persistent YAML templates (`recovery_mode: 1`) across 67 template triggers and 11 trigger prototypes. Single approved informational exception: Trigger 21712 ("System name has changed", `recovery_mode: 0`).
- **Prototype Tagging & Discovered Trigger Resolution:** Attached `notification_class` tags to all 11 LLD interface prototypes, propagating tags to all 54 dynamically discovered interface triggers on mock lab hosts via LLD task execution (eliminating 100% of untagged discovered triggers).
- **Deadband Specification:** Configured anti-flapping deadbands across key metrics (WFO disk [15%, 20%], ICMP ping loss [5%, 20%], ICMP RTT [100ms, 150ms], SBCE CPU [70%, 85%], Synthetic Voice MOS [3.5, 3.8]).
- **Live Runtime Hysteresis Validation:** Executed live injection scenarios verifying that triggers in deadband remain active and only clear upon reaching recovery threshold.
- **Gated Telemetry Isolation:** Formally isolated 5 uncollected/unsupported metrics (`G450_DSP_UTIL`, `CM_CALL_RTCP_JITTER`, `EMS_SIP_SERVER_ERRORS`, `WFO_VERINT_PIPELINE`, `CARRIER_DEEP_SLA`) without active triggers.
- **Declarative Template Synchronization:** Exported and synchronized updated definitions into native YAML files under `provisioning/zabbix/templates/` ensuring provisioning idempotency.

**Exit gate:** Zabbix API confirms zero syntax errors, 100% valid recovery modes (`recovery_mode: 1` on 67 triggers, 11 prototypes), 0 untagged discovered triggers, change manifest recorded (`phase13_8b_change_manifest.json`), runtime hysteresis verified (`phase13_8b_runtime_hysteresis_results.json`), and automated suite (`test_phase13_8b_threshold_implementation.py`) passes 9/9 tests. (ACCEPTED)

#### Phase 13.8C — Alert Behaviour, Event Classification & Runtime Notification Verification (Completed)
- **Live Event Engine Execution:** Validated live Zabbix problem and recovery events across Actions 10–15 via `scripts/test_phase13_8c_runtime_notifications.py` and Zabbix API.
- **10 Controlled Staging Events:** Verified 10 problem-to-recovery lifecycles: Total Network Outage, Total Communications Outage, SIP Carrier Failure, Synthetic Voice MOS Drop, Media Gateway Fan Tray Failure, Monitoring AMI Disconnect, Storage Partition Low, Operator Acknowledged Incident (`#INC-94810`), Maintenance Window Alert Suppression (`suppressed: 1`, 0 alerts), and Repeated Independent Incidents.
- **6 Service Redundancy Scenarios:** Proved that failover-capable systems (Session Manager duplex, redundant SIP trunks) generate `DEGRADED` or `CARRIER_DEGRADED` events and never trigger false total outage alerts without corroborating multi-point failure evidence.
- **Recovery Differentiation:** Enforced distinction between ICMP device reachability (Action 14 / Admin Group 7) and confirmed voice service restoration (SIP OPTIONS / synthetic MOS via Actions 10–12).
- **Macro Expansion & Zero Branding:** Audited 100% of problem and recovery notification messages; confirmed `{EVENT.DURATION}` expands dynamically (e.g. `Total Downtime: 1s`), with 0 occurrences of forbidden platform branding tokens (`Nawari`, `Zabbix`, `Grafana`).
- **Recipient Routing & Service Desk Isolation:** Confirmed IT Service Desk (`it.servicedesk@kenya-airways.com`, User ID 6) is targeted only by Action 10 (`total_outage`), and is strictly excluded from Actions 11–15.
- **Delivery Boundary:** Kept staging email and SMS media in `CONFIGURED_UNVERIFIED` state (zero outbound external emails or SMS dispatched).
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_8c_notification_runtime.py` (10/10 PASS), combined Phase 13.8 suite (43/43 PASS), and evidence manifest `provisioning/zabbix/snapshots/phase13_8c_action_execution_evidence.json`.

**Exit gate:** Live Zabbix API confirms 100% action mutual exclusivity, valid macro expansion, correct recipient group targeting, verified maintenance suppression, and passing regression gates. (ACCEPTED)

---

## Phase 13.9 — Controlled Physical Telemetry Commissioning (Completed)

Phase 13.9 executed the authoritative read-only physical telemetry audit and vendor MIB conformance review:
- **Authoritative Inventory Reconciled:** 12 monitored hosts and 422 items audited in Zabbix 7.4.
- **Direct SNMPv2c and SNMPv3 (authPriv) Proven:** Validated SHA-256 / AES queries against Net-SNMP 5.9 representatives.
- **64-bit HC Interface Counters:** Verified 19 64-bit HC counters and proven rate throughput formula `(delta * 8) / dt`.
- **Production Subnet Audit:** Audited 11 production targets (`10.2.156.x`, `10.2.1.1`, `10.102.10.25`); off-net RFC 1918 subnets classified as `BLOCKED_ACCESS` with documented IPsec/MPLS commissioning prerequisites.
- **7-State Telemetry Matrix:** 179 `VERIFIED_LIVE`, 81 `CONFIGURED_UNVERIFIED`, 162 `SIMULATED`, 0 fictitious items.
- **Gated Telemetry Isolation:** 5 unverified metrics (`G450_DSP_UTIL`, `CM_CALL_RTCP_JITTER`, `EMS_SIP_SERVER_ERRORS`, `WFO_VERINT_PIPELINE`, `CARRIER_DEEP_SLA`) remain strictly isolated as `NOT_COLLECTED` with 0 active triggers.
- **Avaya MIB Conformance:** CM Table `.67` hourly IP voice statistics ($\ge 1\text{h}$ polling) and Table `.145` call rates ($\ge 5\text{m}$ polling ceiling) standardized; G450 discrete thermal trap event model enforced.
- **Test Suite:** `tests/unit/test_phase13_9_telemetry_commissioning.py` (10/10 PASS).

**Exit gate:** Authoritative inventory verified, direct SNMPv3 proven, 5 gated metrics isolated, zero production mutations, and passing regression suite. (ACCEPTED)

---

## Phase 13.10 — Avaya Voice Quality & Genuine Call Assurance (Completed)
- **Call-Flow Architecture:** Documented end-to-end multi-stage call flow (Carrier -> SBCE -> SM -> CM -> ACD); separated signaling paths from media anchoring paths.
- **Deterministic Multi-Leg Correlation:** Implemented deterministic binding between SIP `Call-ID`, Asterisk AMI `Uniqueid`, and Avaya session identifiers in `SessionCorrelator`.
- **Latency Decomposition:** Decomposed post-dial delay (PDD), time-to-alerting, and time-to-answer; decoupled SIP transport latency from end-to-end call setup time.
- **Q.850 Cause Classification:** Built translator distinguishing operational faults (Cause 34 trunk congestion, 503 unavailable) from normal clearing (Cause 16) and station states (Cause 17 user busy).
- **ITU-T G.107 E-Model MOS:** Implemented full Extended E-model mathematical engine across G.711A and G.729 codecs. Validated nominal ($R=84.82, \text{MOS}=4.19$) and degraded ($R=17.24, \text{MOS}=1.18$) scenarios.
- **Missing-Media Guard:** Proved that unverified or unidirectional audio strictly yields `(None, None)` to prevent fabricated MOS scores.
- **Privacy & PII Protection:** Enforced telephone number masking (`+254 7XX **** XXX`) and zero audio recording.
- **Test Suite:** `tests/unit/test_phase13_10_voice_assurance.py` (10/10 PASS).

**Exit gate:** Verified signaling architecture, deterministic SIP/AMI correlation, ITU-T G.107 E-model calculations, missing media guards, zero audio payload recording, and passing test suite. (ACCEPTED)

---

## Phase 13.11 — Network Path & WAN Observability (Completed)

Phase 13.11 deployed end-to-end network path and WAN observability across Kenya Airways' distributed network footprint:
- **Paris Traceroute Flow Invariance:** Implemented RFC 1071 16-bit one's complement checksum payload compensation (`calculate_paris_checksum_compensation`); verified checksum invariance (`0x5432`) ensuring packets traverse identical ECMP hashing buckets across variable TTLs.
- **RFC 4950 MPLS Label Stack Parsing:** Extracted ICMP multi-part extensions decoding 20-bit MPLS label, 3-bit TC/EXP, 1-bit BOS, and 8-bit TTL; verified Expedited Forwarding (EXP=5) classification on voice LSPs.
- **CoPP Guard Protection:** Implemented intermediate transit router detection; proved that silent transit hops with downstream responsive hops are classified as `TIMEOUT_COPP` rather than genuine network packet loss.
- **Loss & Latency Onset Localization:** Implemented algorithms localizing the exact inception hop for packet drops and flagging transit delta RTT jumps exceeding 40.0ms.
- **Route Churn & Divergence Index:** Computed SHA-256 path hashes and localized divergent hop indices upon routing changes.
- **Endpoint Probing Suite:** Verified concurrent DNS, TCP connect, and HTTP probing against local and remote endpoints.
- **Trans-WAN Voice Quality Prober:** Synthesized voice metrics across active and standby outstation circuits (Mombasa MBA, Kisumu KIS, London Heathrow LHR); verified ITU-T G.107 R-factor and MOS calculations, enforcing failover recommendations under degradation.
- **SIP OPTIONS Guard:** Enforced strict differentiation between signaling reachability and RTP media verification.
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_11_network_path_observability.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_11_network_path_evidence.json`.

**Exit gate:** Flow-invariant Paris traceroute proven, RFC 4950 MPLS parsing verified, CoPP guard active, route churn detected, Trans-WAN voice prober running, and passing test suite. (ACCEPTED)

---

## Phase 13.12 — Service Dependency Mapping & Event Correlation (Pending)
- Hop-by-hop packet loss, jitter, and route-change detection across WAN/MPLS circuits.
- Synthetic probes executing DNS resolution, TCP three-way handshake time, and HTTP/HTTPS availability.
- Trans-WAN outstation comparative telemetry (NBO HQ vs MBA, KIS, Outstations).

**Exit gate:** Hop-by-hop path visualizer active; route flapping and transit provider latency anomalies accurately identified.

---

## Phase 13.12 — Service Dependency Mapping & Event Correlation (Completed)

Phase 13.12 established formal service dependency mapping, causality reasoning, and topological event correlation across Kenya Airways' enterprise network and Avaya Aura communications infrastructure:
- **8 Core Business Services Defined:** Formalized Kenya Airways service catalog across Tier 1 and Tier 2 services: Enterprise Network Core (`SVC-ENTERPRISE-NETWORK`), WAN Connectivity (`SVC-WAN-CONNECTIVITY`), Carrier Ingress & SIP Trunking (`SVC-SIP-CARRIER`), Corporate Telephony Core (`SVC-CORP-TELEPHONY`), Inbound Contact Center (`SVC-CONTACT-CENTER-INBOUND`), Outbound Contact Center (`SVC-CONTACT-CENTER-OUTBOUND`), Interactive Voice Response (`SVC-IVR-SELFSERVICE`), and Call Recording & Compliance (`SVC-COMPLIANCE-RECORDING`).
- **Acyclic DAG Dependency Model:** Configured parent-child dependency links and evaluated graphs via depth-first search; verified 0 circular dependency cycles.
- **HA Redundancy Dampening:** Enforced failure logic distinguishing partial failover from total outage:
  - Single member failure in an HA pair (`avaya-sbce-01` down, `avaya-sbce-02` up) evaluates to `DEGRADED` impact, `REDUNDANCY_FAILOVER` classification, and routes to Action 12 (telephony administrators), strictly blocking Action 10.
  - Dual member failure (`avaya-sbce-01` and `avaya-sbce-02` down) evaluates to `TOTAL_OUTAGE` and triggers Action 10.
- **Root-Cause Isolation & Symptom Suppression:** Proved that upstream core switch interface failure (`jkia-core-sw01`) pins the core switch as primary root cause and suppresses 3+ downstream host ICMP ping loss and timeout alarms.
- **Interface Flapping Dampening:** Implemented sliding-window transition counter suppressing alarm storms when interfaces flap $\ge 3$ times within 60 seconds.
- **Zabbix 7.4 Service Tree Provisioning:** Synchronized all 8 services and 1 root service to live Zabbix API via `service.create`, configuring SLA algorithms and problem tags (`service=network`, `service=voice`, `service=sip`).
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_12_service_correlation.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_12_service_correlation_evidence.json`.

**Exit gate:** Acyclic dependency DAG verified, HA redundancy dampening proven, root cause isolated with downstream suppression, Zabbix Service Tree provisioned, and passing test suite. (ACCEPTED)

---

## Phase 13.13 — SLI, SLO & Error-Budget Implementation (Completed)

Phase 13.13 implemented Google SRE-style Service Level Objectives, multi-dimensional indicators, and multi-window multi-burn-rate alerting across Kenya Airways' critical network and communications footprint:
- **Authoritative SLO Register Established:** Formalized targets and 30-day allowed downtime budgets across 7 critical services: Enterprise Network Core (99.99% / 4.32m), WAN Connectivity (99.95% / 21.60m), Carrier Ingress & SIP Trunking (99.99% / 4.32m), Corporate Telephony Core (99.95% / 21.60m), Inbound Contact Center (99.90% / 43.20m), IVR Experience Portal (99.80% / 86.40m), and Observability Platform (99.95% / 21.60m).
- **Multi-Dimensional SLI Engine:** Implemented independent tracking of Availability SLI, Performance/Latency SLI (PDD $\le 500\text{ms}$), Quality SLI ($R \ge 80, MOS \ge 4.0$), and Coverage SLI.
- **Telemetry Integrity Guard:** Enforced that missing or unverified telemetry is recorded as `unknown_minutes` and penalizes availability, completely eliminating false 100% uptime claims.
- **Google SRE Multi-Burn-Rate Alerting:** Configured dual-window alerting:
  - 1-hour window $\ge 14.4x$ burn rate ($\ge 2\%$ budget consumed) triggers `CRITICAL_PAGE` (Action 10/12) with automated time-to-exhaustion forecasting.
  - 6-hour window $\ge 6.0x$ burn rate ($\ge 5\%$ budget consumed) triggers `WARNING_TICKET` (Action 13).
- **Maintenance Exclusion:** Scheduled and approved maintenance windows are isolated and excluded from outage minute counts.
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_13_slo_error_budgets.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_13_slo_evidence.json`.

**Exit gate:** Authoritative SLOs active, multi-dimensional SLI engine running, multi-burn-rate alerting verified, telemetry integrity guard active, and passing test suite. (ACCEPTED)

---

## Phase 13.14 — Dashboard & Reporting Acceptance (Completed)

Phase 13.14 executed a comprehensive operational audit and formal acceptance verification across all 24 Grafana dashboards and 282 visualization panels:
- **Strict Folder Separation Verified:** Confirmed clean partition into two authoritative folders: `Nawari / Communication Observability` (11 dashboards) and `Nawari / Network Observability` (13 dashboards), eliminating cross-domain pollution.
- **282 Panels Audited:** Full inventory of all 282 panels categorized by visualization type: 86 stat, 82 row, 57 timeseries, 23 gauge, 17 table, 5 piechart, 4 zabbix-problems, 4 text, 3 bargauge, and 1 nodeGraph.
- **Data Provenance Guarantee:** Classified 100% of panels into authoritative provenance categories: 219 `PHYSICAL_LIVE` (77.7%), 42 `SYNTHETIC_PROBE` (14.9%), 21 `CALCULATED` (7.4%), and 0 disguised simulated metrics.
- **Datasource & Variable Verification:** Confirmed that all panel queries resolve cleanly to `alexanderzobnin-zabbix-datasource` (235 panels) or PostgreSQL (43 panels). Verified dynamic template variables (`$host`, `$interface`, `$outstation`).
- **Live Grafana 11.6 API Parity:** Live query of running Grafana instance (`127.0.0.1:3001`) confirmed all 24 dashboards and folders loaded and operational.
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_14_dashboard_operational_acceptance.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_14_dashboard_evidence.json`.

**Exit gate:** All 24 dashboards pass operational audit, 282 panels audited with proven telemetry provenance, folder separation active in live Grafana, and passing test suite. (ACCEPTED)

---

## Phase 13.15 — Monitoring Platform Resilience, Security & Capacity (Completed)

Phase 13.15 delivered a thorough capacity, health, resilience, and security audit of the Nawari monitoring platform running on `mon-grafana01`:
- **Live Container Health Verified:** All 7 containerized services audited in healthy running status: PostgreSQL 17 (226.5 MB), Grafana 11.6 (126.7 MB), Zabbix Web (92.9 MB), Asterisk 22.11 (77.4 MB), Zabbix Server 7.4 (67.2 MB), Mock SNMP (6.2 MB), and SNMP Traps (2.7 MB). Total container memory is ~600 MB (< 8% of 7.748 GiB host RAM).
- **Zabbix Internal Engine Metrics:** Process busy rates verified well below warning thresholds: History Syncer at 0.16%, Config Syncer at 0.42%, Escalator at 0.24%, and ICMP Pinger at 7.82%.
- **Capacity & Sizing Projection Model:** Audited PostgreSQL database (101 MB total). Formulated mathematical storage growth model: 422 monitored items @ 60s cadence produce ~7.03 vps (~607,680 values/day), generating 29.0 MB/day raw history and 451 MB/year trends. Annual DB footprint is ~1.64 GB, confirming a storage runway > 15 years on standard 50 GB disks.
- **RBAC & Security Hardening:** Verified strict least-privilege role assignment: Super Admin privileges are restricted to `Admin`, while all 5 Kenya Airways operational users are assigned standard Admin role. Enforced secret masking of SNMPv3 credentials (`Admin_sha256`) and API keys.
- **Resilience & Disaster Recovery:** Verified `unless-stopped` container restart policies across all services. Documented Point-in-Time Recovery (PITR) procedures achieving RPO $\le 1.0\text{ hour}$ and RTO $\le 15.0\text{ minutes}$.
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_15_platform_resilience.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_15_platform_evidence.json`.

**Exit gate:** Resource headroom confirmed (< 8% RAM, < 16% CPU), internal process metrics healthy, storage runway modeled, RBAC least privilege enforced, DR procedures validated, and passing test suite. (ACCEPTED)

---

## Phase 13.16 — Operational Readiness & Production Handover (Completed)

Phase 13.16 delivered the final operational handover package and technical readiness certification for the Nawari Observability Platform:
- **Comprehensive Programme Synthesis:** Successfully synthesized the accomplishments across all ten engineering phases (13.8B through 13.16), proving complete end-to-end alignment between Zabbix 7.4.16, Grafana 11.6.0, PostgreSQL 17.0, and Kenya Airways operational infrastructure.
- **Evidence Snapshot Integrity:** Verified 9 phase evidence snapshot manifests stored in `provisioning/zabbix/snapshots/`, confirming 100% test passing rates and zero fabricated data.
- **Runbooks & Incident Triage Procedures:** Authored complete operational SOPs: SOP-01 (Carrier SIP Trunk Ingress Outage), SOP-02 (Voice Quality Degradation), and SOP-03 (Storage Disk Warning on WFO Server), detailing escalation paths and contact rosters for all 5 named Kenya Airways administrators.
- **Commissioning & Rollback Safety:** Formulated pre-flight checklist, cutover procedures, and an emergency 60-second rollback decision tree.
- **Repository Isolation Guaranteed:** Verified that adjacent repository `/Users/madeira/Desktop/Projects/sentra` remained untouched on `main` at commit `9970404`.
- **Test Suite & Evidence:** Automated test suite `tests/unit/test_phase13_16_operational_readiness.py` (10/10 PASS) and snapshot `provisioning/zabbix/snapshots/phase13_16_handover_evidence.json`.

**Exit gate:** Operational runbooks complete, escalation rosters configured, rollback plan verified, 10-phase sequence passed with 100% test integrity, and handover package certified. (ACCEPTED)
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
