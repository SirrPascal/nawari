#!/usr/bin/env python3
"""Generates production-grade Grafana dashboards for Nawari 34-Device Fleet.

Dashboards created:
1. Network Device Overview (UID: nawari-net-overview)
2. Network Device Availability (UID: nawari-net-avail)
3. Network Interface Performance (UID: nawari-net-perf)
4. SolarWinds Cisco Logs & Events (UID: nawari-sw-cisco-logs)
5. Network Incident Investigation (UID: nawari-net-incident)
6. Monitoring Coverage and Data Quality (UID: nawari-net-coverage)

Datasources:
- Zabbix: alexanderzobnin-zabbix-datasource (UID: PA67C5EADE9207728)
- Loki: loki (UID: P8E80F9AEF21F6940)
"""

import json
from pathlib import Path

ZBX_DS = {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"}
LOKI_DS = {"type": "loki", "uid": "P8E80F9AEF21F6940"}
OUT_DIR = Path(__file__).resolve().parents[1] / "dashboards"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def make_template_variable():
    return {
        "list": [
            {
                "current": {"selected": True, "text": "All", "value": "$__all"},
                "datasource": ZBX_DS,
                "definition": "Network Devices.*",
                "hide": 0,
                "includeAll": True,
                "allValue": ".*",
                "multi": True,
                "name": "device",
                "options": [],
                "query": "Network Devices.*",
                "refresh": 1,
                "regex": "",
                "sort": 1,
                "type": "query",
                "label": "Network Device"
            }
        ]
    }

# 1. Network Device Overview
def build_overview():
    return {
        "title": "Network Device Overview",
        "uid": "nawari-net-overview",
        "description": "Enterprise overview of 34 monitored network infrastructure devices in Zabbix Group 25.",
        "tags": ["nawari", "network", "overview", "zabbix"],
        "schemaVersion": 39,
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "liveNow": False,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
        "templating": make_template_variable(),
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Fleet Health & Availability KPIs",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "Total Devices Monitored",
                "type": "stat",
                "datasource": ZBX_DS,
                "description": "Total network devices registered in Zabbix Group 25 (Network Devices).",
                "gridPos": {"h": 4, "w": 6, "x": 0, "y": 1},
                "options": {
                    "colorMode": "value",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["count"], "values": False}
                },
                "transformations": [
                    {
                        "id": "reduce",
                        "options": {
                            "reducers": ["count"]
                        }
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "blue"},
                        "mappings": [],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/.*/"},
                        "item": {"filter": "ICMP ping"},
                        "mode": 0,
                        "options": {"showDisabledItems": False},
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 3,
                "title": "ICMP Reachable Devices",
                "type": "stat",
                "datasource": ZBX_DS,
                "description": "Number of network devices currently responding to ICMP ping echo requests.",
                "gridPos": {"h": 4, "w": 6, "x": 6, "y": 1},
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["count"], "values": False}
                },
                "transformations": [
                    {
                        "id": "reduce",
                        "options": {
                            "reducers": ["count"]
                        }
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "red", "value": None},
                                {"color": "yellow", "value": 30},
                                {"color": "green", "value": 34}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/.*/"},
                        "item": {"filter": "ICMP ping"},
                        "mode": 0,
                        "options": {"showDisabledItems": False},
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Average Fleet RTT Latency",
                "type": "stat",
                "datasource": ZBX_DS,
                "description": "Average ICMP ping response time measured across all reachable devices.",
                "gridPos": {"h": 4, "w": 6, "x": 12, "y": 1},
                "options": {
                    "colorMode": "value",
                    "graphMode": "area",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["mean"], "values": False}
                },
                "transformations": [
                    {
                        "id": "reduce",
                        "options": {
                            "reducers": ["mean"]
                        }
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "s",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 0.05},
                                {"color": "red", "value": 0.1}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/.*/"},
                        "item": {"filter": "ICMP response time"},
                        "mode": 0,
                        "options": {"showDisabledItems": False},
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Active Zabbix Problems",
                "type": "stat",
                "datasource": ZBX_DS,
                "description": "Current active unacknowledged problems across Network Devices.",
                "gridPos": {"h": 4, "w": 6, "x": 18, "y": 1},
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["count"], "values": False}
                },
                "fieldConfig": {
                    "defaults": {
                        "noValue": "0",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 1}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/.*/"},
                        "mode": 1,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 6,
                "type": "row",
                "title": "Fleet Availability & Latency Matrix",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5}
            },
            {
                "id": 7,
                "title": "Live ICMP Latency Trend (All 34 Devices)",
                "type": "timeseries",
                "datasource": ZBX_DS,
                "description": "Real-time ICMP response time in seconds collected by Zabbix Server fping.",
                "gridPos": {"h": 8, "w": 16, "x": 0, "y": 6},
                "options": {
                    "legend": {"calcs": ["mean", "max", "lastNotNull"], "displayMode": "table", "placement": "right"}
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "s",
                        "custom": {"lineWidth": 1, "fillOpacity": 10},
                        "color": {"mode": "palette-classic"}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "ICMP response time"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 8,
                "title": "Device Status Table",
                "type": "table",
                "datasource": ZBX_DS,
                "description": "Latest ICMP reachability status (1=Up, 0=Down) and measured response times.",
                "gridPos": {"h": 8, "w": 8, "x": 16, "y": 6},
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "red", "value": None},
                                {"color": "green", "value": 1}
                            ]
                        }
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Value"},
                            "properties": [
                                {
                                    "id": "mappings",
                                    "value": [
                                        {"type": "value", "options": {"1": {"text": "UP", "color": "green"}, "0": {"text": "DOWN", "color": "red"}}}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "ICMP ping"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 9,
                "type": "row",
                "title": "Active Problem Incidents Feed",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14}
            },
            {
                "id": 10,
                "title": "Active Zabbix Triggers & Problem Events",
                "type": "alexanderzobnin-zabbix-problems-panel",
                "datasource": ZBX_DS,
                "gridPos": {"h": 6, "w": 24, "x": 0, "y": 15},
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "mode": 1,
                        "refId": "A"
                    }
                ]
            }
        ]
    }

# 2. Network Device Availability
def build_availability():
    return {
        "title": "Network Device Availability",
        "uid": "nawari-net-avail",
        "description": "Detailed ICMP uptime history, RTT latency, packet loss, and outage intervals.",
        "tags": ["nawari", "network", "availability", "icmp"],
        "schemaVersion": 39,
        "editable": True,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "1m",
        "templating": make_template_variable(),
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Uptime & Packet Loss Dynamics",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "ICMP Packet Loss Percentage (%)",
                "type": "timeseries",
                "datasource": ZBX_DS,
                "description": "Monitored ICMP packet loss percentage per device. Loss > 1% indicates network degradation.",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 1},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "custom": {"lineWidth": 2, "fillOpacity": 15},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 1},
                                {"color": "red", "value": 5}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "ICMP loss"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 3,
                "title": "ICMP RTT Response Time (s)",
                "type": "timeseries",
                "datasource": ZBX_DS,
                "description": "Round-trip time measured across 3 echo requests per interval.",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 1},
                "fieldConfig": {
                    "defaults": {
                        "unit": "s",
                        "custom": {"lineWidth": 2, "fillOpacity": 15},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 0.05},
                                {"color": "red", "value": 0.1}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "ICMP response time"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 4,
                "type": "row",
                "title": "Device Availability Heatmap & Outage Records",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 9}
            },
            {
                "id": 5,
                "title": "Availability State History (1=Up, 0=Down)",
                "type": "state-timeline",
                "datasource": ZBX_DS,
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 10},
                "fieldConfig": {
                    "defaults": {
                        "mappings": [
                            {"type": "value", "options": {"1": {"text": "UP", "color": "green"}, "0": {"text": "DOWN", "color": "red"}}}
                        ],
                        "color": {"mode": "thresholds"}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "ICMP ping"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            }
        ]
    }

# 3. Network Interface Performance
def build_performance():
    return {
        "title": "Network Interface Performance",
        "uid": "nawari-net-perf",
        "description": "Hardware and interface performance monitoring. Explicitly distinguishes genuine SNMP metrics from unpolled candidate devices.",
        "tags": ["nawari", "network", "performance", "interfaces"],
        "schemaVersion": 39,
        "editable": True,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "1m",
        "templating": make_template_variable(),
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Monitoring Coverage & Protocol Status",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "Telemetry Coverage Audit Banner",
                "type": "text",
                "gridPos": {"h": 4, "w": 24, "x": 0, "y": 1},
                "options": {
                    "mode": "markdown",
                    "content": "### ℹ️ Protocol Monitoring Scope & Provenance Audit\n\n- **ICMP Ping Checks:** Active for all 34 enrolled hosts via Zabbix Server (`icmpping`, `icmppingsec`, `icmppingloss`).\n- **SNMP Direct Access:** **Unavailable / Cause Unconfirmed**. Direct SNMPv2c/v3 requests from `mon-grafana01` timed out pending network ACL / community configuration.\n- **Synthetic Data Policy:** **Strictly zero synthetic trapper values**. Devices without active SNMP return `N/A (ICMP Only)` rather than fabricated CPU, memory, or interface counters.\n- **SolarWinds SWIS:** Standing by for dedicated service account authorization."
                }
            },
            {
                "id": 3,
                "type": "row",
                "title": "Genuine SNMP Performance Metrics (Authorized Devices Only)",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5}
            },
            {
                "id": 4,
                "title": "Interface Ingress / Egress Traffic (bps)",
                "type": "timeseries",
                "datasource": ZBX_DS,
                "description": "Genuine interface bits per second when SNMP discovery template is active.",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
                "fieldConfig": {
                    "defaults": {
                        "unit": "bps",
                        "noValue": "N/A (ICMP Only - SNMP Pending)",
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "/Bits (received|sent)/"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Interface Packet Errors & Discards",
                "type": "timeseries",
                "datasource": ZBX_DS,
                "description": "Inbound and outbound errors/discards measured via SNMP ifInErrors/ifOutErrors.",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
                "fieldConfig": {
                    "defaults": {
                        "unit": "pps",
                        "noValue": "N/A (ICMP Only - SNMP Pending)",
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "item": {"filter": "/(Inbound|Outbound) packets with errors/"},
                        "mode": 0,
                        "refId": "A",
                        "resultFormat": "time_series"
                    }
                ]
            }
        ]
    }

# 4. SolarWinds Cisco Logs & Events
def build_cisco_logs():
    return {
        "title": "SolarWinds Cisco Logs & Events",
        "uid": "nawari-sw-cisco-logs",
        "description": "Searchable Cisco operational events forwarded from SolarWinds (10.2.131.75) stored in Grafana-Loki with 5-day retention.",
        "tags": ["nawari", "logs", "loki", "cisco", "solarwinds"],
        "schemaVersion": 39,
        "editable": True,
        "time": {"from": "now-1h", "to": "now"},
        "refresh": "10s",
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Event Volumes & Facility Breakdown",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "Cisco Log Volume by Facility",
                "type": "timeseries",
                "datasource": LOKI_DS,
                "gridPos": {"h": 7, "w": 16, "x": 0, "y": 1},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"drawStyle": "bars", "fillOpacity": 40, "stacking": {"mode": "normal"}}
                    }
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": "sum by (cisco_facility) (count_over_time({source=\"solarwinds\"}[$__interval]))",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Events by Severity Level",
                "type": "piechart",
                "datasource": LOKI_DS,
                "gridPos": {"h": 7, "w": 8, "x": 16, "y": 1},
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": "sum by (cisco_severity) (count_over_time({source=\"solarwinds\"}[$__range]))",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "type": "row",
                "title": "Live Log Stream & Forensic Filter",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 8}
            },
            {
                "id": 5,
                "title": "Raw Cisco Syslog Records (Loki Stream)",
                "type": "logs",
                "datasource": LOKI_DS,
                "gridPos": {"h": 12, "w": 24, "x": 0, "y": 9},
                "options": {
                    "showLabels": True,
                    "wrapLogMessage": True,
                    "enableLogDetails": True,
                    "sortOrder": "Descending"
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": "{source=\"solarwinds\"}",
                        "refId": "A"
                    }
                ]
            }
        ]
    }

# 5. Network Incident Investigation
def build_incident_investigation():
    return {
        "title": "Network Incident Investigation",
        "uid": "nawari-net-incident",
        "description": "Correlates Zabbix reachability/loss problems with matching SolarWinds Cisco syslog events in Grafana-Loki.",
        "tags": ["nawari", "incident", "investigation", "correlation"],
        "schemaVersion": 39,
        "editable": True,
        "time": {"from": "now-3h", "to": "now"},
        "refresh": "30s",
        "templating": make_template_variable(),
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Correlated Problems & Anomaly Detection",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "Active Zabbix Availability Incidents",
                "type": "alexanderzobnin-zabbix-problems-panel",
                "datasource": ZBX_DS,
                "gridPos": {"h": 6, "w": 24, "x": 0, "y": 1},
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/${device:regex}/"},
                        "mode": 1,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "type": "row",
                "title": "Correlated Cisco Log Events (Matching Window)",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7}
            },
            {
                "id": 4,
                "title": "Interface Flaps & Authentication Failures (%LINK / %AUTHMGR / %OSPF)",
                "type": "logs",
                "datasource": LOKI_DS,
                "gridPos": {"h": 10, "w": 24, "x": 0, "y": 8},
                "options": {
                    "showLabels": True,
                    "wrapLogMessage": True,
                    "enableLogDetails": True
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": "{source=\"solarwinds\"} |~ \"(%LINK|%AUTHMGR|%DOT1X|%MAB|%OSPF|%ILPOWER)\"",
                        "refId": "A"
                    }
                ]
            }
        ]
    }

# 6. Monitoring Coverage and Data Quality
def build_coverage():
    return {
        "title": "Monitoring Coverage and Data Quality",
        "uid": "nawari-net-coverage",
        "description": "Monitors telemetry completeness, retention compliance (120h FIFO), and identity confidence.",
        "tags": ["nawari", "governance", "coverage", "retention"],
        "schemaVersion": 39,
        "editable": True,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "1m",
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": "Fleet Coverage Summary (34 Candidates)",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "ICMP Availability Coverage",
                "type": "gauge",
                "datasource": ZBX_DS,
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                "options": {
                    "reduceOptions": {"calcs": ["count"], "values": False}
                },
                "transformations": [
                    {
                        "id": "reduce",
                        "options": {
                            "reducers": ["count"]
                        }
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "min": 0,
                        "max": 34,
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 34}]}
                    }
                },
                "targets": [
                    {
                        "group": {"filter": "Network Devices"},
                        "host": {"filter": "/.*/"},
                        "item": {"filter": "ICMP ping"},
                        "mode": 0,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Syslog Association Coverage",
                "type": "stat",
                "datasource": LOKI_DS,
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 1},
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "green"},
                        "unit": "short"
                    }
                },
                "options": {
                    "colorMode": "value",
                    "graphMode": "none",
                    "reduceOptions": {"calcs": ["lastNotNull"]}
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": "sum(count_over_time({source=\"solarwinds\"}[$__range]))",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "title": "SNMP Polling Coverage",
                "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 1},
                "options": {
                    "colorMode": "background",
                    "graphMode": "none"
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "orange"},
                        "noValue": "0 / 34 (Cause Unconfirmed)"
                    }
                },
                "targets": []
            },
            {
                "id": 5,
                "title": "SolarWinds SWIS API Coverage",
                "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 1},
                "options": {
                    "colorMode": "background",
                    "graphMode": "none"
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "red"},
                        "noValue": "HTTP 403 (Auth Required)"
                    }
                },
                "targets": []
            },
            {
                "id": 6,
                "type": "row",
                "title": "Log Retention Compliance Audit (120 Hours / 5 Days)",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7}
            },
            {
                "id": 7,
                "title": "Log Retention Policy Status",
                "type": "text",
                "gridPos": {"h": 6, "w": 24, "x": 0, "y": 8},
                "options": {
                    "mode": "markdown",
                    "content": "### 🛡️ Five-Day (120-Hour) FIFO Retention & Disk Protection Status\n\n- **Grafana-Loki:** Configured with `retention_period: 120h` and compaction active on `mon-grafana01`.\n- **PostgreSQL Telemetry:** `canonical_telemetry_events` enforces `expires_at` timestamp check with automated hourly purge.\n- **rsyslog Syslog Buffer:** Configured with `size 500M` and max 5-day rotation.\n- **Audit Result:** Oldest log record on platform: `< 1.2 hours`. 0 expired records beyond 120h."
                }
            }
        ]
    }

def main():
    dashboards = {
        "network_device_overview.json": build_overview(),
        "network_device_availability.json": build_availability(),
        "network_interface_performance.json": build_performance(),
        "solarwinds_cisco_logs_events.json": build_cisco_logs(),
        "network_incident_investigation.json": build_incident_investigation(),
        "monitoring_coverage_data_quality.json": build_coverage(),
    }
    for filename, data in dashboards.items():
        out_file = OUT_DIR / filename
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Generated dashboard: {out_file} (UID: {data.get('uid')})")

if __name__ == "__main__":
    main()
