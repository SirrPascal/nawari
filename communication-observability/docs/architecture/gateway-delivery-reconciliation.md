# Endpoint gateway delivery reconciliation

## PLAN · evidence and scope

| Environment | Evidence |
| --- | --- |
| GitHub | Read-only remote query returned `main` at `dd609a7cce074915b774959eee8197d88bfb7b09`. It returned no ref for `feat/github-actions-cicd-pipeline`. |
| Mac | `feat/github-actions-cicd-pipeline` at `782e504`, with uncommitted Release A work, export changes and generated inventory. Preserved the existing worktree, including the gateway auth edits. The existing [A01 artifact](../dashboards/a01-local-trace-evidence.json) records the corrected lab panel rendering **114 µs** and satisfies the local baseline for this iteration. |
| Production | Current revision, effective Compose, runtime versions, bindings, physical observations, and capacity are unverified. No authorized production snapshot accompanied this handoff. Use the owner-run snapshot in the [enterprise plan](enterprise-observability-plan.md) to complete the delta. |

The handoff referenced a starter kit, audit script, and draft `contracts/nawari-event-v1.schema.json`. The two attached text files describe those artifacts but do not include their source files. The checkout has separate endpoint, voice and incident models. Reuse endpoint v1 as the wire payload, keep the voice contract and incident models, and reserve the enterprise envelope and cross-domain outbox for a later reviewed adapter. A receipt is transport metadata and does not define a competing telemetry schema.

### Source-to-consumer traceability

| Source | Collector and authoritative store | Query and alert path | Status |
| --- | --- | --- | --- |
| Network, servers, and Avaya reachability, resources, interfaces | Approved ICMP, SNMPv3, or agent checks → Zabbix PostgreSQL | Zabbix API → Grafana. Zabbix triggers → native action or controlled capture. | Local simulated item-to-browser evidence. Physical target, supported OIDs, and production paths pending. |
| Traps and device alarms | Zabbix trap receiver → Zabbix, or approved vendor event route → proposed investigation store | Zabbix events → Grafana or incident consumer. Alerting depends on approved routing. | Receiver configuration exists. Production ingress and event provenance unverified. |
| Endpoint and site probe measurements | Agent collectors → local JSONL spool → gateway → trapper items in Zabbix PostgreSQL | Zabbix API → endpoint panels, triggers and intended incident routes | Mock sender and isolated receipt evidence below. No physical target receipt. |
| Zabbix problems and recoveries | Native events → problem consumer; Zabbix retains the source event | Native action and selected incident correlation | Local problem replay and notification fixtures in [Release A evidence](../operations/release-a-local-evidence.md). Native production delivery pending. |
| Voice signalling, calls and media | Sentra/Asterisk SIP and AMI → Sentra ledger; selected measurements → Zabbix; selected events → proposed investigation tier | Voice dashboard or incident lookup; safe notification fixture | Isolated SIP/AMI evidence. Real calls, media, and deployed ingestion pending. |
| Wireless, application logs, traces and vendor syslog | Approved agents or OTel → proposed dedicated OpenSearch tier; wireless monitoring can also use vendor-supported Zabbix metrics | Scoped search or Grafana; alert policies tied to approved service signals | Target architecture. Deployed paths, volumes, and retention unverified. |
| Intended inventory and topology | CMDB or NetBox → identity crosswalk and service dependencies | Topology, query enrichment and impact assessment | Authority and runtime contracts pending. |
| Flow, packet capture and AI investigation | Dedicated future collection/storage and read-only investigation interfaces | Scoped evidence queries with policy and audit | Deferred until infrastructure, privacy and ownership gates clear. |

## BUILD · delivery contract

The previous direct-upload path removed one queue entry from the front even when the uploaded report was newer. The previous batch path counted parsed entries as delivered and let clients delete a prefix. Both paths could discard unsent reports. The agent now persists the report through its existing spool and drains that queue by receipt. The SHA-256 identity is derived from the immutable JSON report, including its source timestamp, with stable key ordering. Existing bare JSONL reports can be replayed without rewriting or upgrading their format.

Replay clients send `receipt_version: 1`. The HTTP 200 envelope contains a map of record IDs to `TARGET_ACCEPTED`, `RETRY`, or `REJECTED`. Missing or unrecognized receipts do not authorize deletion. A v1 client ignores count-only responses. For an unversioned request the gateway returns HTTP 503 if any entry lacks target acceptance, so legacy replay cannot delete an arbitrary prefix from a partially accepted batch. Single-report success retains the legacy `ACCEPTED` field and adds an explicit ID and receipt. Legacy agents still have the pre-existing direct-upload prefix bug and must be upgraded before a pilot.

The gateway issues `TARGET_ACCEPTED` only when the sender reports success and explicit counts show every submitted metric processed with zero failures. This is a Zabbix protocol receipt. It does not prove a PostgreSQL durability checkpoint or successful item-history queries. [Zabbix sender protocol](https://www.zabbix.com/documentation/7.4/en/manual/appendix/protocols/zabbix_sender)

The gateway suppresses simultaneous same-ID requests and keeps the latest 10,000 accepted IDs by default. A configured `--receipt-db-path` or `NAWARI_RECEIPT_DB_PATH` persists receipts in a SQLite file before the gateway acknowledges. Use a private directory and one gateway process per file, scoped to its sink and environment. The unconfigured cache is process-local. SQLite stores IDs only. There is no change to Zabbix or production schemas. Retain the existing source timestamp when mapping replayed reports. Reject invalid schemas, unsupported agent versions and simulated-environment production claims. With the existing clock-skew guard enabled, live requests enforce age and future skew while replay allows historical samples and rejects excessive future skew.

Affected paths include the [agent uploader](../../services/endpoint/core/uploader.py), [spool](../../services/endpoint/core/spooler.py), [runner](../../services/endpoint/runner.py), [shared delivery vocabulary](../../services/endpoint/delivery.py), [gateway handler](../../services/gateway/server.py), [receipt store](../../services/gateway/receipts.py), [gateway config](../../services/gateway/config.py), [hub wiring](../../services/hub_daemon.py), and [sender response parser](../../services/voice/zabbix_sender.py). The [gateway](../../tests/unit/test_stage7d_gateway.py), [hub](../../tests/unit/test_hub_daemon.py), and [backpressure](../../tests/performance/test_capacity_and_backpressure.py) tests exercise the contract and update existing sender doubles to return explicit counts.

## EXECUTE → ANALYZE → TEST

Used loopback HTTP, an in-process mock Zabbix sender, disposable JSONL/SQLite files, and no live container changes. The focused run passed **77 tests** in **11.07 seconds** with **55,705,600 bytes** of peak resident set size for the Python process. These are test-process measurements, not pilot sizing.

```sh
python3.13 -m pytest tests/unit/test_stage7d_gateway.py \
  tests/unit/test_endpoint_agent.py tests/unit/test_hub_daemon.py \
  tests/unit/test_rbac_permissions.py tests/unit/test_trace_zabbix_panel.py \
  tests/unit/test_zabbix_sender.py tests/unit/test_telemetry_schema.py \
  tests/performance/test_capacity_and_backpressure.py::test_01_gateway_queue_backpressure_http_429
```

- Successful reports before and after a partial Zabbix rejection were removed by ID. The rejected report, invalid-schema record, and corrupt spool line remained. Out-of-order source clocks were preserved.
- After a response was discarded and the gateway was restarted against the same SQLite file, replay received the saved receipt and removed the report with one sender call in total. Simultaneous same-ID requests also caused one send.
- Backpressure, unavailable or partial downstream responses, malformed counts, unsupported versions, invalid schema, future skew and missing/wrong auth had no successful receipt. A count-only response left the new agent's spool intact. The gateway tests used simulated provenance.
- The initial run found an existing client/test expectation for the replay-guard diagnostic prefix. The final implementation preserved the prefix and passed the focused suite. Live Zabbix integration tests were excluded because they submit to the running stack.

## Promotion and rollback

Delivery is at least once. A crash after Zabbix acceptance and before SQLite commit, loss of the sender response, partial downstream processing, or eviction of a bounded receipt can cause a repeat send. The existing bounded spool capacity policy can evict old entries, and enough permanently rejected records can occupy the replay batch until an operator handles them. The spool has one writer per agent. Test retention and failure behavior against realistic rates before commissioning.

Endpoint exposure remains blocked by TLS enforcement and certificate management, per-agent identity and source authorization, protected receipt/spool storage, pilot sizing, and real trapper readback. The hub's current auth and TLS defaults were reviewed and do not establish those controls. The version allowlist is distinct from a device identity allowlist.

Coordinate the gateway and agent promotion. Upgrade the clients before any supported replay pilot and preserve existing spool and receipt data during rollback. Reverting the code has no Zabbix migration to undo, but reintroduces unsafe count-based deletion, so pause endpoint uploads before running a legacy agent. Keep the existing production approval gates. The smallest next package is isolated staging with authenticated TLS and an enrolled lab identity, followed by readback of one approved endpoint item in Zabbix history.
