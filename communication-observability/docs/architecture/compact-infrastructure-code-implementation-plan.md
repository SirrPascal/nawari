# Nawari code implementation plan: compact infrastructure and seven-day logs

Date: 10 November 2026. Status: implementation plan grounded in a read-only checkout audit; no live deployment or capacity verification performed.

## 1. Planning and design

### Problem, inputs and outputs

Keep the complete agreed system while consolidating its infrastructure: Zabbix, Grafana, PostgreSQL, Grafana-Mimir, Kafka, Grafana-Loki, Grafana-Alloy, rsyslog and Nawari application services. Use hosted AI inference. Regional observation points remain on existing site infrastructure. Akvorado remains optional and needs a separate capacity allowance.

The initial central reservation is 16 dedicated vCPU, 64 GB RAM and 1 TB usable SSD/NVMe. This is a load-test candidate, not a demonstrated estate requirement. It does not replace the older deployment profiles until the new profile passes its gates. A single host provides no host-failure availability; service replicas on it share that failure domain.

| Input | Required output |
| --- | --- |
| Endpoint/site DNS, TCP, TLS, HTTPS and permitted ICMP tests | Timestamped experience timeline with observation point, configuration version and freshness |
| Interface, route, VPN and controller association observations | Time-correct endpoint-to-network relationships; measured paths distinguished from inferred links |
| Selected device/FortiAnalyzer syslog and controller events | Redacted, normalized, searchable logs with provenance |
| Selected SolarWinds/controller API readings | Measurements preserving the original source timestamp and quality |
| Zabbix history/problems and inventory mappings | Linked infrastructure evidence and explicit measurement ownership |
| Incident evidence and runbooks | Authorized investigation with cited evidence, contradictions and qualified hypotheses |

Raw logs and all their copies must be removed within the agreed seven-day maximum under tested operating assumptions. Rotation, collection, parsing, forwarding, storage and deletion each need observable failure handling. Missing telemetry must remain unknown. Existing dashboard UIDs, endpoint ingestion routes and incident lifecycle behavior must remain compatible through migration.

### Checkout reuse register

These observations describe files, not production readiness. The worktree already contains edits, including endpoint delivery/retention work and draft architecture documents; preserve them and review their integration before implementation.

| Capability | Existing surface | Decision and required extension |
| --- | --- | --- |
| Hub process and intake | `services/hub_daemon.py`, `services/gateway/{server,config,receipts}.py` | Extend. Current gateway uses `ThreadingHTTPServer`; endpoint reports map to Zabbix. Preserve `/api/v1/telemetry`, replay receipts and health contracts. Add scoped query APIs separately before considering a framework migration. |
| Endpoint collection | `services/endpoint/{runner,models,config}.py`, `probes/`, `os_platform/`, `path/` | Reuse. Validate OS/network-context behavior and add an explicit owner for each metric family. |
| Offline delivery | `services/endpoint/core/{spooler,uploader}.py`, `services/endpoint/delivery.py` | Extend in-progress receipt-based delivery. Test idle expiry, restart, malformed/future timestamps, byte caps and bounded reconnect replay. |
| Identity/topology | `services/topology/{identity,graph,api}.py`, `docker/postgresql/initdb/05-topology-schema.sql` | Extend. IP fallback identifiers and globally unique subnet CIDRs need tenant/routing-domain context and a compatibility crosswalk. Preserve existing IDs. |
| Inventory integration | `services/integrations/{base_adapter,cmdb_adapter}.py` | Reuse adapter conventions. The CMDB adapter contains a static directory and generic fallback; it is not proof of an authoritative inventory integration. Unknown identity must remain unresolved. |
| Assurance/incidents | `services/assurance/`, `services/incidents/{models,lifecycle,fingerprint}.py` | Reuse rules and nine-stage lifecycle. Add durable transactional state, scoped evidence references, expiry and incident revision control. |
| Investigation | `services/analytics/intelligent_diagnosis.py` | Extend deterministic analysis with explicit coverage/freshness. Some branches manufacture healthy counter-evidence from absent anomalies; replace those assumptions before exposing them to AI. Hosted-model integration is additional work. |
| Dashboards | `docker/grafana/`, `provisioning/dashboards/`, existing dashboard generators | Reuse datasource and UID ownership; add contextual links and freshness/expiry views through the existing generation workflow. |
| Packaging | `docker/compose.yaml`, `docker/compose.app.yaml`, `docker/compose.prod.yaml`, `deploy/` | Extend the core stack through a new compact overlay. `deploy/docker-compose.hub-full.yml` is a separate bundle with differing service names/versions; do not combine it blindly with the core files. |
| Retention | `deploy/docker-compose.retention.yml`, endpoint spool and retention architecture note | Partial. Docker `max-size: 10m` and `max-file: 7` bound bytes/file count, not seven days. Spool cleanup currently runs on append/read, so idle files can survive. |
| Backups/recovery | `scripts/backup/{backup_nawari,restore_nawari}.sh`, `tests/recovery/` | Extend. Backups include a database dump and provisioning tree. Archive age pruning and restore do not enforce original log expiry; review evidence snapshots and database payloads too. |
| New collection/storage tier | No runtime references found for Loki/Mimir/Kafka/Alloy/rsyslog in searched service/deployment files beyond a retention comment | Implement and validate pinned configurations; preserve these components in the target design rather than substituting a smaller stack. |

Runtime dependencies currently list PyYAML and typing-extensions. FastAPI, Pydantic, SQLAlchemy, Alembic and a C# helper are proposals, not installed implementation. Keep Python modules and existing probes where they suffice. Add a Windows helper only for demonstrated OS API gaps; avoid introducing a second probe owner.

### Sources of truth and collection paths

| Fact | Authority | Nawari behavior |
| --- | --- | --- |
| Asset identity/lifecycle and network ownership | Designated enterprise inventory, to be selected | PostgreSQL stores stable mappings, validity intervals and provenance; collectors cannot establish inventory authority |
| Existing infrastructure signals and alerts | Zabbix for its assigned measurement families | Query supported APIs; retain current history and native alert ownership |
| SolarWinds-owned signals | SolarWinds for explicitly assigned families | Import selected fields with original observation time; do not run competing alert owners |
| New synthetic metric families | Identified probe; Mimir stores selected series | Introduce through ownership configuration; current Zabbix endpoint families stay in place until a reviewed cutover |
| Received operational logs | Loki within retention | Preserve source device identity separately from relay/collector identity |
| Client/AP/port/VPN association | Controller/session observation valid at incident time | Store time-bound associations and confidence |
| Incident state and evidence references | Nawari application PostgreSQL schema | Versioned transitions, evidence expiry and access audit |
| Confirmed cause | Operator-confirmed resolution | AI output remains a hypothesis until confirmed |

Forwarding paths:

1. Approved device/FortiAnalyzer event copy → regional rsyslog → Alloy parsing/redaction → authenticated central Loki intake.
2. Existing endpoint Python probes → existing gateway → Zabbix for current metric ownership. New Mimir families use validated Alloy scrape/remote-write profiles; do not duplicate a family silently.
3. Regional Alloy/site probes → authenticated Mimir remote write → selected Kafka ingest-storage path → Mimir/object storage.
4. Read-only vendor APIs → scoped Python adapters → normalized measurements/associations, with checkpoint and source freshness.
5. Inventory plus Zabbix/Loki/Mimir evidence → Nawari correlation/query API → Grafana navigation and bounded hosted-AI investigation.

Forwarders transport and buffer; parsers extract fields and redact; Prometheus-style exporters expose samples; remote-write writers send samples. None becomes the inventory authority. An Alloy deployment must explicitly connect an input or exporter, processing/scraping and output; installing it alone establishes no pipeline.

### Code and data contracts

Create the following proposed additions after reviewing adjacent existing APIs:

| Proposed path | Responsibility |
| --- | --- |
| `services/telemetry/contracts.py` | Versioned normalized event, quality, identity and expiry contracts |
| `services/telemetry/ownership.py` | Primary measurement/source selection and freshness rules |
| `services/integrations/solarwinds_adapter.py`, `controller_adapter.py` | Version-specific read-only APIs and cursor handling |
| `services/storage/`, `services/storage/migrations/` | Application repositories, transactional migrations and outbox |
| `services/api/query/` | Scoped asset, experience, incident, evidence and path queries |
| `services/investigations/` | Provider adapter, evidence authorization and response validation |
| `services/retention/{policy,worker,verifier}.py` | Deadline calculation, application-copy cleanup and store verification |
| `provisioning/telemetry/` | Ownership register, event schema, parser fixtures and test profiles |
| `docker/{alloy,rsyslog,loki,mimir,kafka}/` | Validated component configuration with no embedded credentials |
| `deploy/docker-compose.compact.yml` | Additional target services, networks, volumes and measured limits |

The normalized event contract includes `schema_version`, stable `event_id`, `event_time`, `ingested_at`, `expires_at`, authenticated tenant/collector identity, `site_id`, `routing_domain_id`, nullable resolved `asset_id`, source system/record ID, event type, normalized/original severity, parser/configuration version, timestamp quality and bounded attributes. Distinguish parse failure from unresolved enrichment. Use stable source IDs when available; retries reuse ingestion IDs. Text-only hashes cannot universally deduplicate legitimate repeated events.

Use bounded metric dimensions such as site, stable asset, test and address family. Put arbitrary URLs, route sequences, usernames and exception text in protected context records. Preserve counters and their reset semantics; never convert a stale API snapshot into a new measurement.

Use a separate application database/schema and role from vendor-owned Zabbix tables. Add migrations for scoped assets/aliases, associations with validity intervals, measurement owners, adapter checkpoints, incidents/revisions, immutable transitions, evidence references, AI jobs and payload-free audit events. Use unique constraints for source mappings and stable incident scope keys. Store raw logs in Loki, not PostgreSQL. Restrict JSON evidence payloads and inherit their original expiry. Existing init SQL alone does not upgrade an initialized database.

## 2. Algorithm design before source changes

### Receive, parse and forward an event

```text
authenticate collector; bind allowed tenant/site/source scope
stamp receipt time; preserve original source separately from relay
select versioned parser; enforce byte/field limits
if parse fails: count failure; optionally retain redacted bounded quarantine
otherwise normalize, redact, classify timestamp quality
resolve identity using source + routing domain + observation time
compute original expiry; reject payload already past its deadline
forward through supported bounded buffering; preserve event ID/deadline
emit queue age, dropped/expired counts and delivery failures
```

For valid timestamps use source event time. For missing, malformed or untrustworthy future time use first trusted receipt time and flag quality. Clamp the retention anchor so future timestamps cannot extend it past receipt-based expiry. Replays retain the first deadline, including at downstream intake. Enforce expiry before spooling as well as before backend submission. Do not retain rejected payloads in error messages.

### Poll a vendor API

```text
acquire scoped lease; load last completed checkpoint
fetch bounded page/window with documented overlap
validate supported fields; preserve actual source observation timestamp
transactionally stage normalized results + replay IDs and checkpoint
publish staged records with bounded retry; expire stale payloads
record source freshness separately from polling success
```

Use a transactional outbox for application-owned delivery where required. Acceptance followed by a publisher crash can replay a record; receiving behavior must tolerate it. If staging fails, do not advance the cursor. Define version-specific pagination, rate-limit, token-expiry and partial-response behavior.

### Measure endpoint experience

```text
load signed/enrolled allowlisted profile; jitter schedule
record configuration and current network context
run fixed diagnostics with bounded timeout and concurrency
emit actual observation time, outcome and missing-data reasons
deliver; remove spool entries only for explicit successful receipts
on reconnect: cap replay rate; discard expired records first
```

Reuse the current uploader receipt contract. Test service versus user proxy/VPN context, IPv6, sleep/resume and network changes. Give collectors per-device or scoped credentials with revocation; a fleet-wide bearer secret does not establish individual collector identity.

### Correlate and investigate

```text
select authorized fresh observations from primary measurement owners
join associations valid during the evaluation window
if coverage insufficient: publish visibility condition, not healthy/fault
else evaluate sustained symptoms and contradictory measured evidence
transactionally upsert incident + revision + allowed lifecycle transition
append immutable transition and durable notification intent
late evidence updates history; it does not automatically page as new
```

Retain existing incident stages. Assign one alert owner per condition; run new rules in shadow mode before enabling transitions that notify. Concurrent evaluators must produce one transition per revision, enforced by database constraints/locking.

```text
authorize AI request; freeze incident revision
retrieve bounded scoped evidence, rechecking expiry before each use
redact; call provider using approved retention/region controls
validate proposed read-only tool name, arguments, scope and budget locally
validate returned evidence IDs against supplied evidence
save permitted result with inherited sensitive-payload expiry
```

Provider failure leaves deterministic processing available. Treat logs and runbooks as untrusted tool input. An AI summary containing copied or revealing log content inherits the original payload deadline; merely renaming it a summary does not exempt it.

## 3. Seven-day deletion and rotation implementation

Define seven days as 168 hours from the trusted retention anchor, across all recoverable Nawari copies. Native scheduled deletion is not an exact physical-deletion guarantee. Set earlier operational expiry targets only after measuring deletion delay and reserving headroom. A cleanup outage can breach the deadline; surface that as failed acceptance and an operational incident.

| Location | Required implementation and proof |
| --- | --- |
| Loki | Configure supported TSDB retention, 24-hour index period, singleton Compactor, persisted marker state and delete-request storage. Measure query disappearance and actual supported storage deletion separately. Set retention target plus deletion allowance below the requested maximum. |
| rsyslog/Alloy buffers and WALs | Bound bytes and oldest payload age. Test expiry while downstream is unavailable and buffers idle. A replay-time drop does not remove an expired on-disk copy. If native durable queues lack safe age eviction, select a supported age-aware buffering design before accepting the policy. |
| Endpoint spool | Extend current code with periodic/idle cleanup, strict timestamp classification, byte bounds, metrics and restart tests. Verify nested report timestamps against actual wire structure. Lock append/cleanup consistently. |
| Ordinary application text files | Rotate daily or more frequently, compress closed files, cap total bytes and remove closed payload files by an age-aware schedule. `rotate 7` alone is insufficient. Include oldest content in active files; force rotation when quiet. Reopen via supported application mechanism. |
| Container/host diagnostics | Current JSON-file overlay provides size rotation only. Select and validate an age-capable logging path, including host persistence and local copies. Do not edit Docker-owned JSON files. Validate active-file and idle-host behavior. |
| Quarantine/outbox/incident excerpts/AI records | Inherit `expires_at`; background cleanup works without incoming traffic, removes sensitive derivatives and reports oldest pending payload. References remain with `expired` status and no payload. |
| Backups/snapshots/object versions | Exclude raw telemetry and excerpts from durable-state backups where possible. Otherwise expire each recoverable copy by the original payload deadline, not backup creation time. Include encrypted bundles, snapshots, previous object versions and provisioning evidence exports in the inventory. |
| Hosted AI | Permit raw excerpts only with verified provider storage/retention behavior compatible with their remaining lifetime. Otherwise use permitted payload-free context. |

Do not apply a generic filesystem deletion job to Loki chunks, Docker logs, database files or active queue segments. Compression and encryption do not count as deletion. Metric history, Kafka metric buffering and payload-free incident metadata need separate explicit retention policies. If Kafka ever carries raw logs, those records fall under the raw-log policy too.

Build `RetentionVerifier` around per-store adapters and payload-free reports: store ID, check time, oldest payload age, expired-copy count, deletion lag and inspection error. Inspection failure means unknown/failed verification, not zero expired copies. Seed uniquely identified canaries, check API visibility and supported storage inspection, and retain only canary identifiers/digests in results. Use clock-controlled unit tests plus real elapsed-time storage integration tests. A restore test must keep expired data inaccessible and remove it before application/query access resumes; backups themselves must already meet the copy policy.

The Loki requirements and asynchronous deletion behavior follow [Grafana retention documentation](https://grafana.com/docs/loki/latest/operations/storage/retention/). Docker documents size/file-count rotation and daemon ownership of its files in the [JSON-file driver reference](https://docs.docker.com/engine/logging/drivers/json-file/). Validate queue capabilities against the chosen version of the [rsyslog queue reference](https://docs.rsyslog.com/doc/rainerscript/queue_parameters.html); capacity settings cannot establish age expiry.

## 4. Translate the design into code

Implement in reviewable increments; each row is a proposed change set, not work already completed.

| Order | Source/configuration delta | Acceptance evidence |
| --- | --- | --- |
| 1 — Contracts | Add event/expiry contracts, ownership register, sanitized fixtures and inventory mapping rules | Missing identity stays unresolved; overlapping addresses, late arrivals and future clocks behave deterministically |
| 2 — Durable state | Add migration runner, application repositories, revision constraints and bounded outbox; integrate existing incident models | Upgrade existing state without replacing IDs; concurrent workers/retry produce one logical transition |
| 3 — Compact foundation | Add pinned service images/digests, storage backend, collector configs and compact Compose overlay; resource budget includes object storage and Kafka | Configuration validators pass; isolated services ingest/query correctly; health probes distinguish dependency failure |
| 4 — First complete slice | One inventory asset, one existing endpoint test, one representative redacted device event, evidence API and Grafana link | Operator follows normal navigation to both measurements and related log; source/time/scope are traceable; expiry works |
| 5 — Collection coverage | Add version-specific SolarWinds/controller adapters and parser families; extend endpoint profiles | Pagination/replay, source staleness, realistic vendor messages and OS context tests pass |
| 6 — Correlation/query UI | Integrate durable incident rules, scoped query routes, contextual dashboard links and explicit stale/expired states | Shadow replay matches labeled cases; no duplicate paging; UI retains asset/site/time context |
| 7 — Retention completion | Implement every store adapter, idle cleanup, backup exclusion and restore sanitation | All declared copies meet measured policy under restart/outage tests; unresolved copy paths block release |
| 8 — Hosted AI | Add provider boundary, read-only tool allowlist, budgets and validated evidence citations | Unknown citations rejected; expired evidence withheld; cross-scope requests denied; provider timeout isolated |
| 9 — Commissioning | Package endpoint artifacts; run fleet load/recovery tests and staged rollout | Capacity, deletion, recovery and operational acceptance signed for the measured scope |

Use the selected Mimir version's supported ingest-storage topology; Kafka remains in scope. Pin topic settings, partitioning, replication assumptions and recovery behavior together with Mimir. The current [Mimir Kafka backend guide](https://grafana.com/docs/mimir/latest/configure/configure-kafka-backend/) describes ingest storage; validate the chosen single-host configuration rather than assuming an older monolithic example is compatible.

Keep existing `/api/v1` ingestion behavior. Proposed query routes under that prefix are `GET /assets`, `/sites/{id}/health`, `/endpoints/{id}/experience`, `/incidents/{id}`, `/incidents/{id}/evidence` and `/paths`; `POST /incidents/{id}/investigations` uses an idempotency key scoped to actor, tenant and incident revision. Query responses expose observation time, freshness, provenance and evidence expiry. Enforce authorization, pagination, bounded time windows and query cost in the API, workers and AI tools.

## 5. Testing and debugging

Start with sanitized fixtures and dry runs of each algorithm branch. Existing tests are regression anchors, not evidence that the new target stack is commissioned.

| Test level | Existing anchors / proposed additions | Failure that must be caught |
| --- | --- | --- |
| Endpoint/intake | `tests/unit/test_endpoint_agent.py`, `test_stage7d_gateway.py`, `test_hub_daemon.py`; add expiry tests | Partial receipts, replay, future/malformed timestamps, idle expiry, restart and bounded replay |
| Identity/integration | `test_topology_identity.py`, `test_integrations_adapters.py`; add real API fixture contracts | Overlapping IP/VRF, roaming validity, stale vendor values, partial pages and cursor advancement after crash |
| Incident/analytics | `test_incident_lifecycle.py`, `test_assurance_correlator.py`, `test_analytics_intelligent_diagnosis.py` | Absence mistaken for health, stale recovery, concurrent duplicate transitions, fabricated contradictions |
| Retention | New unit and pinned-container integration tests plus `tests/recovery/` | Quiet active files, disconnected queues, surviving object versions/backups, restored expired excerpts |
| Scope/AI | Existing multisite RBAC tests plus new query/job/provider tests | Cross-tenant/site access, forged collector scope, expired payload access, unknown citations and unapproved tools |
| Operator journey | Existing dashboard acceptance tests plus browser verification of the first slice | Wrong datasource/UID, lost time context, missing/expired data shown as healthy |

Run relevant Python tests with `python3 -m pytest <affected test files>`, then required CI checks. Run pinned binary configuration validators, migration upgrade/compatibility checks and isolated integration tests. Test a Windows helper with .NET tooling only if one is introduced. Use browser checks for the real Grafana journey. Store aggregate results with versions, test scope and fixture/physical classification; avoid retaining test raw payloads in CI artifacts past their deadlines.

Load-test the complete stack, including object storage, Kafka, compaction and dashboard/AI evidence queries. At six test runs per minute across 2,500 active laptops, the starting synthetic workload is 250 runs/second; calculate scalar samples per run from actual profiles. Add measured device/API rates and log bytes/event, a 3× log burst, WAN disconnection/replay, disk pressure, process/host restart, cleanup failure and provider timeout. Record CPU, RSS, disk latency/free space, active series, ingestion/query lag, queue age, parser failures and deletion lag. Set pass thresholds before running the pilot, including required free capacity and maximum recovery time.

Storage sizing must sum Zabbix history, Mimir blocks, Kafka buffering, Loki chunks/indexes, collector queues, application state, object versions, compaction workspace and free headroom. Seven-day logs reduce only part of this total. Use measured compressed bytes and growth; do not reserve the full 1 TB for log payload.

## 6. Packaging, deployment and system execution

1. Select a compatible bill of materials and pin image digests and application dependencies. Preserve current datasource UIDs and template ownership. Resolve differing existing Compose versions/service names per environment.
2. Build the Python application image and signed endpoint package. Introduce new dependencies explicitly with a reproducible lock. Compile UI/plugin assets only when a demonstrated UI gap requires them.
3. Validate the effective core + application + compact configuration without printing interpolated secrets. Include networks, service identities, authenticated intake, volumes, object storage and all resource budgets. Check that logging settings cover every active service/profile.
4. In isolation, back up permitted durable state, run additive migrations with a least-privilege application role, start dependencies, then API/workers/collectors. Separate liveness from readiness; a listening socket does not prove evidence delivery.
5. Execute the first-slice checks through authenticated intake, backend query and normal Grafana navigation. Verify actual expiry/storage deletion. Enable source integrations in shadow mode before notification cutover.
6. Roll out to 25–50 endpoints, then approximately 250, then country cohorts after capacity, source quality, privacy, retention and recovery gates pass. Confirm representative old switches, both wireless vendors and off-VPN/VPN endpoint contexts.
7. Retain prior images/configuration and a migration compatibility window. Roll back only the introduced change set; use forward repair for irreversible schema changes. Restore procedures must enforce current expiry before exposing data.

## 7. Decisions and completion gates

Independent contract/fixture work can proceed now. Before production acceptance, resolve inventory authority, actual source versions/API fields, endpoint OS/context mix, approved ingress/enrollment, object-storage backend and recoverable-version behavior, hosted-AI provider/region/retention, metric/Kafka retention, deletion headroom, backup scope, acceptable host downtime and RTO/RPO. Record an owner and evidence for each decision.

The immediate coding milestone is **one asset → one endpoint test + one device event → linked operator evidence → verified expiry**. It is complete only when contracts, identity, scope, timestamps, delivery, navigation and every declared payload copy are demonstrated. Full-estate readiness additionally requires measured capacity and host-recovery evidence. This document adds a code implementation plan; it does not supersede historical phase evidence or claim the proposed services are running.
