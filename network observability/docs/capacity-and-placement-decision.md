# Capacity and placement decision gate

Status: authorized bounded pilot; full profile remains deferred pending compute expansion.

The prepared full profile reserves approximately 11.75 CPU and 20.75 GiB before operating-system, Docker, filesystem cache, backups, existing monitoring and failure headroom. The historical 2-vCPU/8-GB/low-disk report is not sufficient for this placement.

| Option | Placement | Decision | Conditions |
| --- | --- | --- | --- |
| Consolidated host | PostgreSQL, API/worker, Loki/Alloy, Mimir/Kafka/object storage and Alertmanager beside existing services | No-go pending audit and substantially larger measured capacity | Preserve existing services; include compaction, backup and disk-pressure headroom; validate I/O and operator concurrency |
| Split hosts | Intake/PostgreSQL; logs/Loki; metrics/Mimir/Kafka/object storage; existing Netdata Parent retained or isolated | Preferred production direction if the existing host remains small | Requires approved infrastructure, internal TLS/firewall design, independent backup capacity and failure-domain review |
| Bounded pilot | Existing Parent remains untouched; deploy PostgreSQL plus Nawari API/worker after audit | Authorized | Defers Loki physical-deletion proof and Mimir/Kafka history; UI uses authorized Parent history and must label those gaps |

The bounded pilot is authorized after the approved retirement and storage verification. It must preserve existing services, use the measured filesystem, and stop if the host becomes unhealthy. Required measurements are current CPU/memory pressure, swap, filesystem free space and growth, disk I/O, Parent series/sample rate and retention, log volume, existing service limits, backup size, and restore headroom.

The default platform Compose invocation starts only the bounded core. The `logs`, `metrics`, and `shadow` profiles are deferred stages and must not be enabled solely because storage was expanded.

