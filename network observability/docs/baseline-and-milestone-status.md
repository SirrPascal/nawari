# Nawari network-experience baseline and milestone status

Status: locally implemented and verified where identified below. Production targets and server deployment remain pending.

Latest local extension (12 November 2026): dynamic discovery now records every dimension exposed by the pinned agent, retains disappeared dimensions as historical, and serves bounded v3 history through the Nawari backend. The device view adds System, Applications, Network, Business services, All metrics and Evidence sections. Operation-specific fixtures distinguish collaboration front-door, authentication, media-coverage and independent-reference evidence. PostgreSQL 17.6 fresh and legacy-upgrade validation passed in disposable local containers. Server SSH reaches the verified host but non-interactive authentication remains blocked; no server facts or mutations are claimed.

## Source baseline

| Item | Observed baseline |
| --- | --- |
| Nawari checkout | `feat/github-actions-cicd-pipeline` at `782e50431276b9b4e5530703c30e33106b8d2be5`; `main` and merge base at `dd609a7cce074915b774959eee8197d88bfb7b09` |
| Relocation | 543 tracked deletions have byte-identical files under `communication-observability/`; 42 corresponding files are modified; three workflow files have no relocated counterpart |
| Netdata endpoint | Homebrew Netdata `2.12.3`, macOS ARM64 bottle; build info and local API observed |
| Netdata source | Release tag `v2.12.3` resolves to annotated tag object `c0aa57e...` and source commit `0549a74d8493c32dcea87506ff8de6555ddf6905` |
| Existing Parent | Source and historical evidence describe Netdata `2.12.3`, TLS streaming, 0.5 CPU and 768 MiB; live server access timed out during this milestone |
| Server runtime | Docker CLI is present. The laptop Docker engine is unavailable. Server SSH to `10.2.1.58` timed out. |

## Findings and reuse register

| Requirement | Current evidence | Gap | Action and status |
| --- | --- | --- | --- |
| One managed endpoint installation | Netdata supports managed external plugins. The pinned `httpcheck` measures total duration and outcome. | DNS/connect/TLS/TTFB phases and typed structured evidence were absent. | Added `nawari.plugin` and installed it in Homebrew Netdata `2.12.3`. Netdata launched and supervised the process; phase and result charts contained live fixture samples, structured service/context evidence reached intake, and the queue drained to zero. This proves local fixture lifecycle integration, not Parent streaming or production packaging. |
| Service contract | The pilot catalogue only defined three loopback URLs and statuses. | Owner, contexts, request budgets, objective and retention were absent. | Added a validated operation contract and a controlled fixture operation. The first production operation remains owner-supplied. |
| Enrollment and authoritative identity | Legacy communications enrollment uses process-memory dictionaries. Legacy IP/subnet fallback lacks site/routing-domain scope. | State and revocation do not survive restart. IP identity can collide. | New platform storage persists enrollment, revocation and time-versioned asset mappings scoped by tenant, site and routing domain. Legacy communications enrollment is retained for compatibility and is not used by this slice. |
| Durable intake | Legacy receipt code records a downstream success after forwarding and lacks the agreed inbox/outbox envelope. | No atomic record, expiry, deduplication and pending-work transaction. | Added transactional inbox/outbox, stable deduplication keys, conflict handling, partial batch results, expiry and worker lease recovery. SQLite validates local behavior; PostgreSQL is the server target. |
| Missing evidence | Legacy SLI code returned 100% when no valid intervals existed. | No data could appear healthy. | Changed no-interval SLI and coverage results to 0% with an SLO breach. Focused communications tests pass. |
| Investigation UI | No dedicated frontend was found. | No synchronized device/service/time investigation. | Added React/TypeScript UI with an ECharts sample timeline, Cytoscape focused path, metric definition, context, events, shadow incident and explicit unknown/stale/partial states. Browser validation uses controlled fixtures. |
| Metric export | Netdata supports Prometheus and remote-write export in the installed build. | Parent-to-Mimir identity, timestamps, loss and replay remain untested. | Mimir/Kafka configuration is prepared for later server validation. Status remains pending. |
| Seven-day logs | Existing Compose files use byte/count rotation. | No maximum-age proof across queues, Loki, excerpts or backups. | Structured staging now carries immutable expiry and purges payloads. Loki is configured for a 144-hour operational cutoff plus a 2-hour asynchronous delete delay. Physical deletion, backup and outage verification remain pending. |
| Server platform | The current pilot host was previously reported as 2 CPU, 8 GB and low free storage. | It cannot establish full-stack capacity. | Prepared a profile-gated, resource-bounded Compose stack. No server changes were made. |
| Endpoint context | The UI and intake contract accepted fixture context only. | No endpoint-produced interface, destination route, resolver, Wi-Fi, VPN or proxy state. | The macOS collector now gathers a bounded system-context record. A loopback run observed `lo0`, resolver inventory, VPN state and system-proxy state. An opt-in read-only default-route test observed the real tunnel route and resolver inventory; it correctly accepted the absence of a next-hop gateway on that scoped tunnel. Wi-Fi remained explicitly unavailable. SSIDs are represented only by a truncated SHA-256 digest. Roaming and transition tests remain pending. |
| Endpoint packaging | No versioned collector artifact existed. | Install, upgrade and rollback were not reproducible. | Added a checksum-producing package builder, a macOS ARM64 artifact with guarded install/uninstall scripts, and a Windows AMD64 build-only artifact. The macOS artifact requires the pinned Netdata version and preserves existing configuration. Signing, upgrade tests, Windows service integration and fleet tooling remain pending. |
| Source preservation | The root worktree contains a large relocation represented as tracked deletions plus untracked directories. | A normal Git archive would omit the untracked implementation. | Added a deterministic snapshot tool that includes current relocated/untracked source, records tracked deletions and per-file SHA-256 values, and excludes runtime data, credentials, keys and build artifacts. |

## First slice behavior

The controlled slice follows endpoint and regional fixture observations through durable intake into a single operator view. It distinguishes service delay, DNS failure, connectivity failure, TLS failure, HTTP status failure, permission denial, missing collection and stale data. Correlated conditions remain in `shadow` state. All fixture identities and relationships are labeled in the interface.

The metric stream remains separate from structured evidence. The compiled plugin emits Netdata protocol metrics and sends bounded structured records through the authenticated evidence intake. The Mimir and Loki destinations remain server acceptance gates.

## Remaining gates

1. Select and approve a real business service operation.
2. Run the Windows collector/build/permission matrix on supported Windows hardware.
3. Sign and exercise install, upgrade, uninstall and rollback for the prepared macOS package; complete Windows Netdata service integration on Windows hardware.
4. Inspect the server and reconcile `/opt/nawari`, existing monitoring, listeners, storage and backups.
5. Build and pin the application image by digest, then validate PostgreSQL migration rollback compatibility.
6. Validate Parent export through Mimir/Kafka, including gaps, resets, rejections and restart boundaries.
7. Validate Loki physical deletion, queues and restore behavior against the seven-day policy.
8. Connect an approved regional observation point and one infrastructure source.
9. Set accepted endpoint overhead, reporting, capacity, RPO and RTO limits.

The system is a locally validated implementation slice. It is not production-ready.
