# Telemetry source of truth and retention

## Source of truth

Forwarders transport data and preserve source metadata. Parsers normalize fields,
redact protected values, validate timestamps, and emit parser-failure and queue
health metrics. They do not become authoritative for the measurement itself.

| Measurement | Authoritative store |
| --- | --- |
| Infrastructure polling, discovery, and device history | Zabbix |
| Avaya/CMS contact-centre measurements | Read-only CMS/Avaya adapter and its normalized records |
| Endpoint and synthetic experience measurements | Endpoint/synthetic probe observation |
| Identity, relationships, incidents, evidence references, and audit state | Nawari PostgreSQL |
| Searchable operational logs | Grafana Loki, when deployed, with its Compactor |

Nawari correlation may derive incidents and health states, but every derived
result must retain the source record ID, observation time, quality, freshness,
configuration version, and evidence references. A missing observation is not a
zero and must not be interpreted as a healthy measurement.

## Seven-day policy

The policy applies to Nawari copies of raw logs, collector queues, quarantine
records, incident excerpts, AI payloads, and recoverable backup/object versions.
Source systems such as FortiAnalyzer, SolarWinds, Avaya CMS, and Zabbix retain
their own data under their separately approved policies.

The endpoint spool now expires records using `timestamp_ns` and a receipt-time
fallback for records without a trustworthy observation timestamp. The retention
overlay bounds Docker's JSON log copies with daily-sized rotation. Apply it with:

```sh
docker compose -f docker/compose.yaml -f deploy/docker-compose.retention.yml up -d
```

Rotation bounds storage but does not prove age-based deletion. If Loki is
enabled, configure its TSDB index period, delete-request store, retention, and
Compactor, then verify deletion with aged canary records. A seven-day maximum
requires cleanup headroom, monitoring for stalled cleanup, and a restore test
that confirms expired payloads are not reintroduced. Do not delete Loki chunks
or queue files with a generic filesystem cleanup job.

## Operational checks

Monitor parser failures, oldest queued payload, queue saturation, collector
freshness, Compactor health, expired-copy count, and cleanup failures. Preserve
immutable incident transitions and expire sensitive evidence excerpts together
with their inherited raw-payload deadline.
