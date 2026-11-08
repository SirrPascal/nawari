# Phase 13.15 — Platform Resilience & Infrastructure Audit

## Executive Summary

Phase 13.15 delivers the comprehensive health, capacity, resilience, and security audit of the Nawari monitoring platform itself running on `mon-grafana01`. The audit evaluates the containerized stack composed of Zabbix Server 7.4, PostgreSQL 17, Grafana 11.6, Asterisk 22.11, Net-SNMP, and SNMP Trapper services.

The platform demonstrates extraordinary operational stability, consuming approximately **599.5 MiB of RAM** (< 8% of the available 7.748 GiB host memory) and **< 16% CPU** across 2 vCPUs under full monitoring load.

---

## 1. Container Fleet Health & Runtime Audit

| Service Name | Container Name | Image Version | Status | Memory Used | Limit | PIDs | Restart Policy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL** | `nawari-postgres` | `postgres:17-alpine` | Up 24h (healthy) | 226.5 MiB | 7.748 GiB | 38 | `unless-stopped` |
| **Grafana** | `nawari-grafana` | `nawari-grafana:11.6.0` | Up 2h (healthy) | 126.7 MiB | 7.748 GiB | 31 | `unless-stopped` |
| **Zabbix Web** | `nawari-zabbix-web` | `zabbix/zabbix-web-nginx:7.4` | Up 24h (healthy) | 92.9 MiB | 7.748 GiB | 18 | `unless-stopped` |
| **Asterisk PBX**| `nawari-asterisk` | `avtest-asterisk:22.11.0` | Up 23h (healthy) | 77.4 MiB | 7.748 GiB | 56 | `unless-stopped` |
| **Zabbix Server**| `nawari-zabbix-server` | `zabbix/zabbix-server:7.4` | Up 25m (healthy) | 67.2 MiB | 7.748 GiB | 84 | `unless-stopped` |
| **Mock SNMP** | `nawari-mock-snmp` | `net-snmp:5.9` | Up 23h | 6.2 MiB | 7.748 GiB | 3 | `unless-stopped` |
| **SNMP Traps** | `nawari-snmptraps` | `zabbix/zabbix-snmptraps:7.4` | Up 24h | 2.7 MiB | 7.748 GiB | 1 | `unless-stopped` |

---

## 2. Zabbix Internal Process & Engine Performance

Zabbix internal self-monitoring metrics confirm that the engine is completely unburdened:

```
Zabbix History Syncer Busy %:   [====                    ]  0.16%
Zabbix Configuration Syncer %:  [======                  ]  0.42%
Zabbix Escalator Busy %:        [====                    ]  0.24%
Zabbix ICMP Pinger Busy %:      [==================      ]  7.82%
Zabbix Alerter Busy %:          [                        ]  0.00%
```

All core processes operate well below the 25% warning threshold, confirming massive headroom for expanding monitored host inventory.
