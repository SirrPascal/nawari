# Prepared Nawari server platform

This directory is the authorized bounded-core deployment candidate after retirement and storage verification. It does not replace the existing Netdata Parent Compose project or the existing communications monitoring stack.

## Prepared placement

| Component | Listener | Exposure | Persistent state |
| --- | --- | --- | --- |
| Nawari API/UI | container `18090`, host `127.0.0.1:18090` | Private host reverse-proxy target | PostgreSQL |
| PostgreSQL | `5432` | Internal `application` network | `postgres-data` |
| Grafana-Loki | `3100` | Internal `telemetry` network; `logs` profile only | `loki-data`, including compactor markers |
| Grafana-Alloy | admin on container loopback; `logs` profile only | No host listener | `alloy-data`; relay spool read-only |
| Alertmanager | `9093` | Internal `application` network | `alertmanager-data` |
| Apache Kafka | `9092`, controller `9093` | Internal `metrics` network | `kafka-data` |
| Grafana-Mimir | `9009` | Internal `metrics` network | `mimir-data` and object store |
| MinIO | `9000` | Internal metrics/telemetry networks | `object-data` |

Endpoint Netdata streaming port `19999` remains owned by the separate Parent pilot. Structured HTTPS intake needs an approved reverse-proxy/TLS path before remote endpoints can connect.

## Local static validation

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability/server/platform"
NAWARI_PLATFORM_IMAGE="example.invalid/nawari/platform@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  docker compose --profile metrics -f compose.yaml config --quiet
```

This validates Compose structure only. Runtime configuration validation requires the selected images and a Docker engine.

## Required read-only server inspection

Before deployment, collect hostname/OS/time sync, CPU/memory/swap, disks and filesystem, Docker/Compose versions, current projects and image digests, volumes/mounts, listeners/firewall, TLS renewal, repository and Compose file order, restart policy, backups, Zabbix/Grafana checks, Parent stream health, and log retention. Avoid environment and key dumps.

The included audit script performs the non-sensitive host and Docker portion without changing server state:

```sh
sh audit-server-readonly.sh > nawari-server-baseline.txt
```

Review the output locally before sharing it because container, host and volume names may still be operationally sensitive. TLS renewal, firewall policy, backups and datasource health require the server owner's existing administration commands.

Reconcile the discovered environment with the manifest below before creating Docker secrets or building an image.

| Service | Source/config version | Image requirement | Owner |
| --- | --- | --- | --- |
| API and worker | local platform `0.1.0` | Build, scan and pin by digest | Nawari Platform |
| PostgreSQL | migration `001` | Pin observed multi-architecture digest | Platform Operations |
| Loki | `loki.yaml` | Pin observed digest; validate config with binary | Observability Platform |
| Alloy | `config.alloy` | Pin observed digest; validate config with binary | Observability Platform |
| Mimir/Kafka | `mimir.yaml`, `metrics` profile | Multi-architecture image digests recorded; validate runtime compatibility | Observability Platform |
| Alertmanager | shadow-only configuration; `shadow` profile only | Pin digest before deployment | Network Operations |

## Capacity gate

The bounded core has explicit limits for PostgreSQL, API and worker and does not start the heavy profiles by default. The `logs` and `metrics` profiles remain deferred because their prepared limits exceed the available 2-vCPU/7.8-GiB host when combined with existing monitoring. The `shadow` profile is also opt-in and must be enabled only after a fresh capacity check.

Before each stage, capture host load, available memory, swap, filesystem usage, I/O latency, container restarts, PostgreSQL connections, Parent freshness, Zabbix queue health and Grafana health. Roll back only the new Nawari stage if existing monitoring regresses, the host OOM-kills a process, root usage exceeds 85%, available memory remains below 1 GiB, or the database/acceptance checks fail.

Start the authorized core with:

```sh
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up -d --wait
```

Enable `logs`, `metrics`, or `shadow` only on a host meeting the separately verified resource and backup requirements. Storage expansion alone is not sufficient.

## Retention boundary

Loki uses a 144-hour operational cutoff and a two-hour delete delay to leave headroom below seven days. The Compactor state is persistent. This configuration does not prove physical deletion, relay age eviction or backup sanitation. Those are deployment acceptance tests.

## Rollback boundary

Application images can be rolled back to a digest compatible with migration `001`. Preserve all named volumes. Never use `down -v` or volume pruning. A database migration requires its own compatibility and restore decision. Capture current monitoring health, image digests and backups before every approved stage.
