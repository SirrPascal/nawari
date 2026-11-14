# Nawari local observability lab

This Compose project is an isolated Apple Silicon development environment. It
adds a Netdata Parent, Grafana Mimir, Grafana Loki, Grafana Alloy, and Blackbox
Exporter without recreating the existing Nawari Zabbix, Grafana, or PostgreSQL
containers.

It is a development lab, not a production topology. Mimir and Loki use local
filesystem storage, authentication is disabled on loopback-only HTTP ports,
and the generated local CA is not an enterprise trust anchor.

## Start

Generate local-only TLS and streaming material if `runtime/` is absent:

```sh
python3 ../prepare_server.py \
  --output-dir ./runtime \
  --address 127.0.0.1 \
  --api-key-file ./runtime/api-key
```

Then start the lab:

```sh
docker compose up -d
./validate.sh
./configure-grafana.sh
```

The generated runtime files and test log are ignored by Git. Do not commit
private keys or API keys.

## Loopback endpoints

| Component | Endpoint |
| --- | --- |
| Netdata Parent streaming | `127.0.0.1:19997` |
| Netdata Parent dashboard | `https://127.0.0.1:19998` |
| Mimir | `http://127.0.0.1:19009` |
| Loki | `http://127.0.0.1:13100` |
| Alloy | `http://127.0.0.1:12345` |
| Blackbox Exporter | `http://127.0.0.1:19115` |

Alloy scrapes the native macOS Netdata agent at `127.0.0.1:19999`, remote
writes selected metrics to Mimir, probes the Netdata API through Blackbox
Exporter, and forwards JSON lines from `spool/*.log` to Loki. Mimir metrics and
Loki logs have a seven-day local retention policy.

The native Mac child is deliberately not reconfigured by this lab. Connecting
it to this Parent requires a separately reviewed multi-destination streaming
change so the working server Parent configuration is preserved.

## Stop

```sh
docker compose down
```

Do not add `-v` unless the explicit goal is to delete all local lab history.
