#!/usr/bin/env python3
"""
scripts/build_communication_observability_suite.py

Builds the complete suite of Communication Observability dashboards:
1. nawari_communication_overview.json (Overarching service-assurance dashboard)
2. avaya_session_manager.json (Session Manager & SIP Entity Monitoring)
3. avaya_communication_manager.json (CM call processing & hourly IP voice stats)
4. avaya_g450_media_gateway.json (G450 chassis, modules, environmental, trunks)
5. avaya_cms_contact_centre.json (CMS server, ACD queues, agent states, SLA)
6. recording_wfo_operational_health.json (Recording metadata, ingestion, storage TTE)
7. nawari_sip_trunks_signaling.json (Carrier SIP trunks, signaling ladders, response codes)

Also ensures all relative symlinks in docker/grafana/dashboards/ exist.
"""

import json
import os
from pathlib import Path

ROOT_DIR = Path("/Users/madeira/Desktop/Projects/nawari")
COMM_DIR = ROOT_DIR / "docker/grafana/dashboards/communication_observability"
ROOT_DASH_DIR = ROOT_DIR / "docker/grafana/dashboards"

COMM_DIR.mkdir(parents=True, exist_ok=True)

DATASOURCE = {
    "type": "alexanderzobnin-zabbix-datasource",
    "uid": "PA67C5EADE9207728"
}

def create_comm_overview():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "Avaya Core Telephony Platform Availability & Alarm State",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Composite availability grid across all core enterprise telephony platforms: Avaya SBCE (.131 Pride), Session Manager (.22), Communication Manager (.26), G450 Media Gateway (.60), and CMS Server. Displays real-time operational status (1 = UP, 0 = DOWN). Source: Zabbix ICMP and SNMP health checks. Freshness: 60s. Limitation: Reflects management/control plane reachability only.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "ONLINE (UP)"}, "0": {"color": "red", "text": "OFFLINE (DOWN)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 16, "x": 0, "y": 1},
                "id": 2,
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "orientation": "horizontal",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "textMode": "auto"
                },
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Appliance SNMP Reachability"}, "refId": "SBCE"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager SNMP Availability"}, "refId": "SM"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Communication Manager SNMP Availability"}, "refId": "CM"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "G450 ICMP Reachability"}, "refId": "G450"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "CMS Server Availability"}, "refId": "CMS"}
                ],
                "title": "Avaya Core Telephony Platform Availability Grid [REAL — ZABBIX]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total count of active, unresolved telephony alarms across Avaya Communication Manager and Session Manager. Source: Avaya CM enterprise MIB avCmAlarms (OID 1.3.6.1.4.1.6889.2.73.1) and Session Manager alarms. Warning: > 0 alarms. Polling interval: 1 hour (CM vendor CPU conservation limit). Freshness: 1-2 hours.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]},
                        "unit": "alarms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 1},
                "id": 3,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Active Alarms Count"}, "refId": "CM_ALARMS"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager Active Alarms Count"}, "refId": "SM_ALARMS"}
                ],
                "title": "Active Telephony Alarms (CM & SM) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 4,
                "title": "SIP Signaling Reachability & Session Dynamics",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Count of currently active SIP call sessions established through the Avaya SBCE. Measures live concurrent signaling/session capacity, not historical completed call volume. Source: Avaya SBCE EMS SIP Statistics Interface. Freshness: 60s. Normal: 50–350 calls, Critical: > 450 (approaching 500 session license limit).",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 500,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 400}, {"color": "red", "value": 450}]},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 8},
                "id": 5,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Active Audio Sessions"}, "refId": "ACTIVE_SESSIONS"}
                ],
                "title": "Active SIP Calls on Perimeter SBCE [REAL — SBCE SNMP]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational status of primary (Safaricom) and secondary (Airtel) carrier SIP trunks terminating on Avaya SBCE. 1 = REGISTERED / UP, 0 = UNREGISTERED / DOWN. Source: Zabbix SIP monitoring on SBCE. Crucial Note: Proves layer-5 SIP signaling reachability only; does NOT guarantee voice audio quality or absence of media packet loss. Freshness: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "REGISTERED (SIP UP)"}, "0": {"color": "red", "text": "DOWN (UNREGISTERED)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 8},
                "id": 6,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Safaricom Primary SIP Trunk Operational Status"}, "refId": "SAFARICOM"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Airtel Secondary SIP Trunk Operational Status"}, "refId": "AIRTEL"}
                ],
                "title": "Carrier SIP Trunk Registration Status [REAL — ZABBIX]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Rate of call attempts and completed call connections processed by Avaya Communication Manager sampled every 5 minutes. Source: Avaya CM MIB table avCmListMeasCallRateTotal (OID 1.3.6.1.4.1.6889.2.73.8.1.1). Polling interval: 5 minutes (vendor specified CPU limit). Freshness: 5 minutes.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 8},
                "id": 7,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Call Rate Total Attempts (5-minute)"}, "refId": "ATTEMPTS"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Call Rate Completed Calls (5-minute)"}, "refId": "COMPLETED"}
                ],
                "title": "5-Minute Call Processing Rate (CM) [REAL — AVAYA SNMP]",
                "type": "timeseries"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 8,
                "title": "Contact Centre Health & Business Queue Performance (Avaya CMS)",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Percentage of incoming customer contact centre calls answered within the contractual Kenya Airways threshold (80% answered in 20 seconds). Source: Avaya CMS Informix database read-only integration. Warning: < 80%, Critical: < 70%. Freshness: 15–30 minutes (matches CMS reporting archive interval).",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 70}, {"color": "green", "value": 80}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 15},
                "id": 9,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Overall Service Level Attainment"}, "refId": "CMS_SLA"}
                ],
                "title": "Contact Centre Service Level (% in SLA) [APPLICATION — CMS]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Current number of customer callers waiting in queue and wait duration (seconds) of the oldest queued caller across all ACD skills. Source: Avaya CMS real-time reporting interface. Warning: Queue > 15 calls or Oldest > 120s. Freshness: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 15}, {"color": "red", "value": 30}]},
                        "unit": "short"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 15},
                "id": 10,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Calls Waiting in Queue"}, "refId": "WAITING"},
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Oldest Call Waiting Duration"}, "refId": "OLDEST"}
                ],
                "title": "Queue Depth & Oldest Waiting Call [APPLICATION — CMS]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Distribution of customer service agent staffing across states: Logged In, Available (idle), ACD Talking (on call), After Call Work (ACW), and Auxiliary (break/training). Source: Avaya CMS Informix database read-only query. Freshness: 15–30 minutes.",
                "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 15},
                "id": 11,
                "options": {"legend": {"displayMode": "table", "placement": "right"}, "pieType": "pie"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Agent Staffing by State"}, "refId": "AGENTS"}
                ],
                "title": "Agent Staffing State Distribution [APPLICATION — CMS]",
                "type": "piechart"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 21},
                "id": 12,
                "title": "Voice Media Quality & Synthetic Probe Assurance (Real vs Synthetic Separation)",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Real-call Mean Opinion Score (MOS). Status: Not instrumented — no validated real-call MOS telemetry source is configured (RTCP-XR RFC 3611 Block 7 or passive media analyzer required). Displayed value is null/uninstrumented; synthetic MOS must never be substituted for real subscriber calls.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "noValue": "Not Instrumented (RTCP-XR Required)",
                        "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-blue", "value": None}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 22},
                "id": 13,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "avaya-cm-01.nawari.local"}, "item": {"name": "avCmRealCallEstimatedMos"}, "refId": "REAL_MOS"}
                ],
                "title": "Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Hourly aggregated real-call packet loss percentage across active calls terminating on Avaya Communication Manager media gateways. Source: Avaya CM MIB table avCmMeasIpVoStatSumDataLstHrTable (OID 1.3.6.1.4.1.6889.2.73.8.1.77 leaf .6). Interval: strictly 1 hour. Freshness: 1-2 hours. Warning: > 2.5%.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 1.0}, {"color": "red", "value": 2.5}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 22},
                "id": 14,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Packet Loss (Last Hour)"}, "refId": "CM_LOSS"}
                ],
                "title": "Real-Call Packet Loss % (CM Last Hour) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Mean Opinion Score (MOS) estimated via ITU-T G.107 E-model strictly for synthetic test calls generated between Asterisk probes and test extensions. Scale: 1.0 to 4.5. Warning: < 3.6, Critical: < 3.1. Source: Synthetic Asterisk probe telemetry. Caution: Reflects synthetic probe calls ONLY; does NOT represent real customer calls.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 4.5,
                        "min": 1.0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 3.6}, {"color": "green", "value": 4.0}]},
                        "unit": "none"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 22},
                "id": 15,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Estimated Mean Opinion Score (MOS)"}, "refId": "SYNTH_MOS"}
                ],
                "title": "Synthetic Voice MOS [SYNTHETIC — ASTERISK]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Audit inventory of all voice telemetry sources, underlying protocols, expected polling intervals, freshness guarantees, and operational status. Identifies whether data is actively updating or stale.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 7, "w": 24, "x": 0, "y": 28},
                "id": 16,
                "options": {"showHeader": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Telemetry Audit"}, "item": {"name": "Telemetry Source Freshness Table"}, "refId": "AUDIT"}
                ],
                "title": "Voice Telemetry Source Freshness & Instrumentation Inventory [AUDIT]",
                "type": "table"
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "service-assurance", "executive", "avaya"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Nawari — Enterprise Communication Services Overview & Executive Service Assurance",
        "uid": "nawari-comm-overview",
        "version": 1
    }
    with open(COMM_DIR / "nawari_communication_overview.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created nawari_communication_overview.json")


def create_session_manager_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "Session Manager Host Platform Health & Transport Sockets",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Processor core utilization on the Avaya Aura Session Manager appliance. Units: Percentage (0-100%). Warning: 75%, Critical: 90%. Source: HOST-RESOURCES-MIB via SNMPv3. Polling: 60s. Limitation: High CPU may delay SIP routing transaction processing.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 75}, {"color": "red", "value": 90}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                "id": 2,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager Host CPU Utilization"}, "refId": "CPU"}
                ],
                "title": "SM Host CPU Utilization [REAL — HARDWARE]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Physical RAM utilization on Avaya Session Manager. Units: Percentage (0-100%). Warning: 80%, Critical: 95%. Source: HOST-RESOURCES-MIB via SNMPv3. Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 80}, {"color": "red", "value": 95}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 1},
                "id": 3,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager Host RAM Utilization"}, "refId": "RAM"}
                ],
                "title": "SM Host RAM Utilization [REAL — HARDWARE]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operating system uptime of the Session Manager server since last reload. Source: MIB-II sysUpTime (OID 1.3.6.1.2.1.1.3.0). Polling: 60s. Freshness: 60s.",
                "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []},
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 1},
                "id": 4,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager System Uptime"}, "refId": "UPTIME"}
                ],
                "title": "SM System Uptime [REAL — HARDWARE]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total count of active TCP sockets currently in ESTABLISHED state on Session Manager. Reflects active signaling connections from endpoints, Communication Manager, and SBCE. Source: TCP-MIB tcpCurrEstab (OID 1.3.6.1.2.1.6.9.0). Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "sockets"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 1},
                "id": 5,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "TCP Established Sockets"}, "refId": "TCP"}
                ],
                "title": "TCP Established Sockets [REAL — HARDWARE]",
                "type": "timeseries"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 6,
                "title": "SIP Entity Monitoring & OPTIONS Reachability",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "SIP Entity Link Operational Status for Communication Manager. Values: 1 = UP, 2 = PARTIALLY UP, 3 = DOWN, 4 = DENY NEW SERVICE. Collection Mechanism: Ingested via Session Manager CLI export (`smstat`/`starety`) or System Manager REST API. Note: Not exposed via Session Manager SNMP agent; proves SIP OPTIONS reachability only, NOT audio media quality. Provenance: CONFIGURED_UNVERIFIED.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "UP (REACHABLE)"}, "2": {"color": "yellow", "text": "PARTIALLY UP"}, "3": {"color": "red", "text": "DOWN (FAILED)"}, "4": {"color": "purple", "text": "DENY NEW SERVICE"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 8},
                "id": 7,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "SIP Entity State — Avaya Communication Manager"}, "refId": "CM_ENTITY"}
                ],
                "title": "SIP Entity State — Avaya CM [CONFIGURED — ASM API/CLI]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "SIP Entity Link Operational Status for Avaya SBCE Pride perimeter controller. Values: 1 = UP, 2 = PARTIALLY UP, 3 = DOWN, 4 = DENY NEW SERVICE. Collection Mechanism: Ingested via Session Manager CLI export or System Manager REST API. Note: Not exposed via Session Manager SNMP agent. Provenance: CONFIGURED_UNVERIFIED.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "UP (REACHABLE)"}, "2": {"color": "yellow", "text": "PARTIALLY UP"}, "3": {"color": "red", "text": "DOWN (FAILED)"}, "4": {"color": "purple", "text": "DENY NEW SERVICE"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 8},
                "id": 8,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "SIP Entity State — Avaya SBCE Pride"}, "refId": "SBCE_ENTITY"}
                ],
                "title": "SIP Entity State — Avaya SBCE [CONFIGURED — ASM API/CLI]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Measured round-trip response time in milliseconds for SIP OPTIONS heartbeat pings sent by Nawari SIP Probe Engine to monitored entities (CM and SBCE). Units: Milliseconds (ms). Collection Mechanism: Active SIP OPTIONS probing by Nawari (`NAWARI_SIP_PROBE`). Note: Not an SNMP metric.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 8},
                "id": 9,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "SIP OPTIONS Response Time — Avaya CM"}, "refId": "CM_OPTIONS_RTT"}
                ],
                "title": "SIP OPTIONS Heartbeat Response Time [NAWARI SIP PROBE]",
                "type": "timeseries"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 10,
                "title": "SIP Entity Inventory & Enterprise Alarm Feed",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Comprehensive table of all SIP Entities configured in Session Manager (CM, SBCE Pride, SBCE DR, Media Gateways, PSTN SIP trunks) detailing IP address, transport (TLS/TCP/UDP), port, entity status, and measured OPTIONS latency. Source: Avaya Session Manager operational model / System Manager API export.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 8, "w": 16, "x": 0, "y": 15},
                "id": 11,
                "options": {"showHeader": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "application": {"name": "SIP Entity Monitoring"}, "item": {"name": "SIP Entity Summary Stream"}, "refId": "ENTITIES"}
                ],
                "title": "Configured SIP Entity Topology & Link Status [CONFIGURED — ASM MODEL]",
                "type": "table"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total count of active enterprise alarms currently asserted on Session Manager. Source: AV-TRAP-MIB trap receiver / System Manager notification. Note: Ingested via SNMP trap or notification webhook; event-driven. Warning: > 0 alarms.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]},
                        "unit": "alarms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 8, "w": 8, "x": 16, "y": 15},
                "id": 12,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sm-01"}, "item": {"name": "Session Manager Active Alarms Count"}, "refId": "SM_ALARMS"}
                ],
                "title": "Session Manager Active Alarms [EVENT TRAP — AV-TRAP-MIB]",
                "type": "stat"
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "avaya", "session-manager", "sip-routing"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Nawari — Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing",
        "uid": "nawari-session-manager",
        "version": 1
    }
    with open(COMM_DIR / "avaya_session_manager.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created avaya_session_manager.json")


def create_communication_manager_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "Communication Manager Call Processing & Telephony Alarms",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "ICMP ping network reachability to the Avaya Communication Manager processor interface. 1 = UP, 0 = DOWN. Polling: 1m. Freshness: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "ONLINE (UP)"}, "0": {"color": "red", "text": "OFFLINE (DOWN)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                "id": 2,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Communication Manager SNMP Availability"}, "refId": "AVAIL"}
                ],
                "title": "CM Processor Reachability [REAL — ZABBIX]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total active alarm conditions on Communication Manager. Source: Avaya CM 8.1 MIB table avCmAlarmsTable (group OID 1.3.6.1.4.1.6889.2.73.8.1.5). Polling interval: strictly 1 hour (delay: 1h) to prevent excessive CPU consumption on the CM call engine. Freshness: 1-2 hours.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]},
                        "unit": "alarms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 1},
                "id": 3,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Active Alarms Count"}, "refId": "ALARMS"}
                ],
                "title": "Active Telephony Alarms (Hourly Scan) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total call attempts processed by Communication Manager in 5-minute sampling intervals. Source: Avaya CM 8.1 MIB table avCmListMeasCallRateTotalTable (group OID 1.3.6.1.4.1.6889.2.73.8.1.145 leaf .1.2.1). Polling interval: strictly 5 minutes. Freshness: 5 minutes.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 1},
                "id": 4,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Call Rate Total Attempts (5-minute)"}, "refId": "ATTEMPTS"}
                ],
                "title": "Call Rate Attempts (5-min) [REAL — AVAYA SNMP]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total successfully completed calls processed by Communication Manager in 5-minute sampling intervals. Source: Avaya CM 8.1 MIB table avCmListMeasCallRateTotalTable (group OID 1.3.6.1.4.1.6889.2.73.8.1.145 leaf .1.3.1). Polling interval: strictly 5 minutes.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 1},
                "id": 5,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Call Rate Completed Calls (5-minute)"}, "refId": "COMPLETED"}
                ],
                "title": "Call Rate Completed (5-min) [REAL — AVAYA SNMP]",
                "type": "timeseries"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 6,
                "title": "Hourly IP Voice Quality Telemetry (avCmMeasIpVoStatSumDataLstHrTable)",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Percentage of IP voice audio packets lost during active calls in the last completed hour across the monitored network region. Source: Avaya CM SNMP table avCmMeasIpVoStatSumDataLstHrTable (OID 1.3.6.1.4.1.6889.2.73.8.1.77 leaf .6). Polling interval: strictly 1 hour. Freshness: 1-2 hours. Warning: > 1.0%, Critical: > 2.5%.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 1.0}, {"color": "red", "value": 2.5}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 8},
                "id": 7,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Packet Loss (Last Hour)"}, "refId": "LOSS"}
                ],
                "title": "Real-Call Packet Loss % (Last Hour) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Peak interarrival packet jitter in milliseconds observed across real calls in the last completed hour. Source: Avaya CM SNMP table avCmMeasIpVoStatSumDataLstHrTable (leaf .7). Polling interval: strictly 1 hour. Warning: > 20ms, Critical: > 30ms.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 20}, {"color": "red", "value": 30}]},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 8},
                "id": 8,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Peak Jitter (Last Hour)"}, "refId": "PEAK_JITTER"}
                ],
                "title": "Real-Call Peak Jitter (Last Hour) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Maximum two-way round-trip audio packet delay in milliseconds observed across real calls in the last completed hour. Source: Avaya CM SNMP table avCmMeasIpVoStatSumDataLstHrTable (leaf .8). Polling interval: strictly 1 hour. Target: <= 150ms (ITU-T G.114), Critical: > 250ms.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 150}, {"color": "red", "value": 250}]},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 8},
                "id": 9,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Peak Two-Way Delay (Last Hour)"}, "refId": "PEAK_DELAY"}
                ],
                "title": "Real-Call Peak Delay (Last Hour) [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Average interarrival packet jitter in milliseconds calculated across all calls in the last completed hour. Source: Avaya CM SNMP table avCmMeasIpVoStatHrJitterTable (OID 1.3.6.1.4.1.6889.2.73.8.1.66 leaf .2). Polling interval: 1 hour.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 15}, {"color": "red", "value": 25}]},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 8},
                "id": 10,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Hourly Average Jitter"}, "refId": "AVG_JITTER"}
                ],
                "title": "Hourly Average Jitter [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 11,
                "title": "Codec Negotiation, Echo Cancellation & Media Regions",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Primary negotiated audio compression algorithm / codec (e.g. G.711A, G.711U, G.729) active in the measured network region. Source: Avaya CM SNMP table avCmMeasIpVoStatSumDataLstHrTable leaf .3. Polling interval: 1 hour.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 15},
                "id": 12,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Negotiated Audio Codec"}, "refId": "CODEC"}
                ],
                "title": "Negotiated Audio Codec [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational status of hardware/software echo cancellation on voice paths for the measured network region. Source: Avaya CM SNMP table avCmMeasIpVoStatSumDataLstHrTable leaf .11. Polling interval: 1 hour.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 15},
                "id": 13,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Echo Cancellation Status"}, "refId": "ECHO"}
                ],
                "title": "Echo Cancellation Status [REAL — AVAYA SNMP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Total number of real IP voice calls evaluated by Communication Manager during the last completed hour across all media gateways. Source: Avaya CM SNMP table avCmMeasIpVoStatHrJitterTable leaf .4. Polling interval: 1 hour.",
                "fieldConfig": {"defaults": {"unit": "calls"}, "overrides": []},
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 15},
                "id": 14,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-cm-01"}, "item": {"name": "Real-Call Evaluated Calls Count"}, "refId": "EVAL_CALLS"}
                ],
                "title": "Evaluated Calls Count in Last Hour [REAL — AVAYA SNMP]",
                "type": "stat"
            }
        ],
        "refresh": "1m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "avaya", "communication-manager", "call-processing"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
        "timezone": "browser",
        "title": "Nawari — Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance",
        "uid": "nawari-communication-manager",
        "version": 1
    }
    with open(COMM_DIR / "avaya_communication_manager.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created avaya_communication_manager.json")


def create_g450_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "G450 Media Gateway Appliance & Controller Registration",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operating time of the Avaya G450 chassis processor since last reload or power cycle. Source: MIB-II sysUpTime (OID 1.3.6.1.2.1.1.3.0). Polling: 60s. Freshness: 60s.",
                "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []},
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                "id": 2,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Chassis System Uptime"}, "refId": "UPTIME"}
                ],
                "title": "G450 System Uptime [REAL — HARDWARE]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Registration status of the G450 Media Gateway with its controlling Avaya Communication Manager server. 1 = REGISTERED, 2 = UNREGISTERED, 3 = DISCOVERING. Source: Avaya G450 Gateway MIB. Polling: 60s. Critical alert if unregistered.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "REGISTERED (ACTIVE)"}, "2": {"color": "red", "text": "UNREGISTERED (DOWN)"}, "3": {"color": "yellow", "text": "DISCOVERING"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 1},
                "id": 3,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Gateway CM Registration State"}, "refId": "REG_STATE"}
                ],
                "title": "CM Gateway Registration [CONFIGURED — G450 MGP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Internal temperature alarm state of the G450 chassis processor. 1 = Normal (< 40°C), 2 = Thermal Warning, 3 = Critical Exceeded. Collection Mechanism: Ingested via G450 MGP SNMP traps (temperatureWarning, temperatureClear). Important: G450 exposes discrete thermal event traps rather than a continuous analog gauge (Audit Phase 13.2 correction). Provenance: CONFIGURED_UNVERIFIED.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "NORMAL (< 40°C)"}, "2": {"color": "yellow", "text": "THERMAL WARNING"}, "3": {"color": "red", "text": "CRITICAL EXCEEDED"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 3}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 1},
                "id": 4,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Internal Chassis Temperature Alarm State"}, "refId": "TEMP"}
                ],
                "title": "Chassis Thermal State [EVENT TRAP — G450 MGP]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational state of Primary and Redundant Power Supply Units (PSU 1 and PSU 2). 1 = Normal, 2 = Fault/Failed, 3 = Not Installed. Collection Mechanism: Ingested via G450 MGP SNMP traps (powerSupplyFailure / powerSupplyNormal) or chassis status. Provenance: CONFIGURED_UNVERIFIED.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "NORMAL"}, "2": {"color": "red", "text": "FAULT / FAIL"}, "3": {"color": "semi-dark-blue", "text": "NOT INSTALLED"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 1},
                "id": 5,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Primary Power Supply Status"}, "refId": "PSU1"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Secondary Power Supply Status (Redundant)"}, "refId": "PSU2"}
                ],
                "title": "Power Supply Status (PSU 1 & 2) [CONFIGURED — EVENT TRAP]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 6,
                "title": "Media Modules, Trunk Ports & Media Resources",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational link status of the physical E1 / ISDN PRI trunk port on the installed MM710 media module. 1 = UP, 2 = DOWN. Source: IF-MIB ifOperStatus. Polling: 60s. Critical alert if down.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "LINK UP"}, "2": {"color": "red", "text": "LINK DOWN"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 8},
                "id": 7,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "E1/ISDN Primary Trunk Port Operational Status"}, "refId": "E1_STATUS"}
                ],
                "title": "E1 / ISDN PRI Physical Trunk State [CONFIGURED — IF-MIB]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "VoIP DSP and media resource channel utilization. Status: Not collected — requires physical audit of installed G450 firmware and DSP child cards (MP80 / MP20 / MP160). Unconfirmed telemetry is honestly displayed as N/A rather than an invented percentage.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "noValue": "Not Collected (Hardware Audit Required)",
                        "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-blue", "value": None}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 8},
                "id": 8,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "avG450DspChannelUtilization"}, "refId": "DSP"}
                ],
                "title": "DSP Media Resource Channels [NOT COLLECTED — REQUIRES AUDIT]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational cooling state of the G450 chassis fan tray unit: 1 = Normal, 2 = Fan Failure, 3 = Warning. Collection Mechanism: Ingested via G450 MGP SNMP trap (fanFailure) or chassis status. Provenance: CONFIGURED_UNVERIFIED.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "NORMAL"}, "2": {"color": "red", "text": "FAN FAILURE"}, "3": {"color": "yellow", "text": "WARNING"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 8},
                "id": 9,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "item": {"name": "Chassis Fan Tray State"}, "refId": "FAN"}
                ],
                "title": "Chassis Fan Tray Operational State [CONFIGURED — EVENT TRAP]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 10,
                "title": "Media Module Inventory & Slot Architecture",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Inventory table of installed media module slots (V1 through V8) on the G450 chassis, displaying module model (MM710 E1/T1, MM711 Analog, MM716 Station, MM720 ISDN BRI), serial number, and module operational status. Source: Avaya G450 Media Module Discovery.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 7, "w": 24, "x": 0, "y": 15},
                "id": 11,
                "options": {"showHeader": True},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-g450-01"}, "application": {"name": "Media Modules"}, "item": {"name": "Discovered Media Modules Table"}, "refId": "MODULES"}
                ],
                "title": "Installed Media Module Slot Inventory (V1-V8) [REAL — HARDWARE]",
                "type": "table"
            }
        ],
        "refresh": "1m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "avaya", "g450", "media-gateway"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Nawari — Avaya G450 Media Gateway Appliance & Physical Telephony Health",
        "uid": "nawari-g450-gateway",
        "version": 1
    }
    with open(COMM_DIR / "avaya_g450_media_gateway.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created avaya_g450_media_gateway.json")


def create_cms_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "CMS Host Infrastructure & Informix Database Engine Health",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Processor core utilization on the Avaya Call Management System (CMS) server host. Units: Percentage (0-100%). Warning: 75%, Critical: 90%. Source: HOST-RESOURCES-MIB. Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 75}, {"color": "red", "value": 90}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 1},
                "id": 2,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "CMS Host CPU Utilization"}, "refId": "CPU"}
                ],
                "title": "CMS Host CPU Utilization [REAL — HARDWARE]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational state of the IBM Informix Dynamic Server (IDS) database engine underpinning CMS real-time and historical tables. 1 = Running / Online, 0 = Down / Offline. Source: Zabbix service check. Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "ONLINE (RUNNING)"}, "0": {"color": "red", "text": "OFFLINE (STOPPED)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 1},
                "id": 3,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Informix Database Engine Status"}, "refId": "INFORMIX"}
                ],
                "title": "Informix Database Engine Status [APPLICATION — CMS]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Configured historical archiving interval for Avaya CMS interval tables (15 minutes, 30 minutes, or 60 minutes). Nawari read-only ODBC ingestion synchronizes strictly to this interval, preserving original timestamps. Source: CMS system configuration.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 1},
                "id": 4,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "CMS Ingestion Reporting Interval"}, "refId": "INTERVAL"}
                ],
                "title": "CMS Archiving Interval Configuration [APPLICATION — CMS]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 5,
                "title": "Queue Dynamics, Wait Times & Customer Experience",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Percentage of contact centre callers answered within Kenya Airways service level threshold (80% answered in 20 seconds). Source: Avaya CMS Informix read-only ODBC query on hsplit table. Freshness: 15–30 minutes.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 70}, {"color": "green", "value": 80}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 8},
                "id": 6,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Overall Service Level Attainment"}, "refId": "SLA"}
                ],
                "title": "Service Level Attainment (% in SLA) [APPLICATION — CMS]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Average Speed of Answer (ASA) in seconds: mean caller waiting time before an agent connects. Source: Avaya CMS Informix query. Warning: > 45s, Critical: > 90s.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "s"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 8},
                "id": 7,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Average Speed of Answer (ASA)"}, "refId": "ASA"}
                ],
                "title": "Average Speed of Answer (ASA, sec) [APPLICATION — CMS]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Live number of customer calls currently waiting on hold across all reservation and ticketing skill queues. Source: CMS real-time stream. Warning: > 15 calls.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 15}, {"color": "red", "value": 30}]},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 8},
                "id": 8,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Calls Waiting in Queue"}, "refId": "WAITING"}
                ],
                "title": "Calls Waiting in Queue [APPLICATION — CMS]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Duration in seconds of the single longest-waiting caller currently in queue. Source: CMS real-time report. Warning: > 120s, Critical: > 300s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 120}, {"color": "red", "value": 300}]},
                        "unit": "s"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 8},
                "id": 9,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Oldest Call Waiting Duration"}, "refId": "OLDEST"}
                ],
                "title": "Oldest Call Waiting (sec) [APPLICATION — CMS]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 10,
                "title": "Inbound Volume Trends, Abandonment & Split/Skill Performance",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Historical volume trend comparing Calls Offered, Calls Answered, and Calls Abandoned over interval buckets. Source: Avaya CMS Informix hsplit table. Freshness: 15–30 minutes.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 7, "w": 12, "x": 0, "y": 15},
                "id": 11,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Calls Offered"}, "refId": "OFFERED"},
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Calls Answered"}, "refId": "ANSWERED"},
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "item": {"name": "Abandoned Calls"}, "refId": "ABANDONED"}
                ],
                "title": "Calls Offered vs Answered vs Abandoned [APPLICATION — CMS]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Performance table breakdown by contact centre Skill Group / Split (e.g., Reservations English, French, Swahili, Flying Blue, Baggage Helpdesk) showing calls offered, answered, abandon %, ASA, and SLA compliance. Source: Avaya CMS read-only ODBC query.",
                "fieldConfig": {"defaults": {}, "overrides": []},
                "gridPos": {"h": 7, "w": 12, "x": 12, "y": 15},
                "id": 12,
                "options": {"showHeader": True},
                "targets": [
                    {"group": {"name": "Contact Centre"}, "host": {"name": "nawari-cms-01"}, "application": {"name": "Skill Performance"}, "item": {"name": "Skill Group Performance Table"}, "refId": "SKILLS"}
                ],
                "title": "Skill Group & Split Performance Breakdown [APPLICATION — CMS]",
                "type": "table"
            }
        ],
        "refresh": "1m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "avaya", "cms", "contact-centre", "informix"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
        "timezone": "browser",
        "title": "Nawari — Avaya Call Management System (CMS) & Contact Centre Performance",
        "uid": "nawari-cms-contact-centre",
        "version": 1
    }
    with open(COMM_DIR / "avaya_cms_contact_centre.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created avaya_cms_contact_centre.json")


def create_recording_wfo_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "Recording & WFO Architecture Boundary & Platform Health",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Product specification and boundary requirements: WFO is an enterprise product category, not a specific product. Displays integration prerequisites (Verint / NICE / Geomant / AWOS verification required). Documents that Nawari collects operational metadata ONLY; voice audio recordings are strictly excluded.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "noValue": "Vendor Confirmation Required (Metadata Only)",
                        "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-blue", "value": None}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 12, "x": 0, "y": 1},
                "id": 2,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "wfoProductSpecificationStatus"}, "refId": "WFO_STATUS"}
                ],
                "title": "WFO Product Specification Status [PENDING VENDOR CONFIRMATION]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational health of the CTI signaling link between Avaya Communication Manager and the recording server cluster (TSAPI / DMCC / CSTA). 1 = Link Active, 0 = Link Down. Critical alert if down: halts call metadata association. Source: CTI daemon check. Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "CTI LINK ACTIVE"}, "0": {"color": "red", "text": "CTI LINK DOWN"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 1},
                "id": 3,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Recorder-to-CM CTI Link State"}, "refId": "CTI"}
                ],
                "title": "Recorder-to-CM CTI Link State [APPLICATION — WFO]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operating system uptime of the recording application host server. Source: MIB-II sysUpTime. Polling: 60s.",
                "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []},
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 1},
                "id": 4,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Recording Host Uptime"}, "refId": "UPTIME"}
                ],
                "title": "Recording Host Uptime [REAL — HARDWARE]",
                "type": "stat"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 5,
                "title": "Recording Ingestion Rate, Queue Depth & Failures",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Live count of concurrent telephone voice conversations currently being actively captured and recorded. Source: Recording daemon active session counter. Polling: 60s.",
                "fieldConfig": {"defaults": {"unit": "calls"}, "overrides": []},
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 8},
                "id": 6,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Active Concurrent Recording Sessions"}, "refId": "SESSIONS"}
                ],
                "title": "Active Recording Sessions [APPLICATION — WFO]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Rate of recorded call metadata payloads ingested and indexed into the archive per minute. Source: WFO ingestion API. Polling: 60s.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "cpm"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 8},
                "id": 7,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Recording Ingestion Rate"}, "refId": "INGESTION"}
                ],
                "title": "Ingestion Rate (Calls/min) [APPLICATION — WFO]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Count of failed recording operations (e.g. RTP stream missing, CTI timeout, codec mismatch) in the preceding hour. Source: Recording error log. Warning: > 0 failures.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 8},
                "id": 8,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Recording Capture Failure Count"}, "refId": "FAILURES"}
                ],
                "title": "Recording Failures Count [APPLICATION — WFO]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Number of call recording files currently buffered in local staging storage awaiting transfer to long-term archive. Warning: > 200 calls. Critical: > 500 calls. Source: Ingestion queue monitor.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 1000,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 200}, {"color": "red", "value": 500}]},
                        "unit": "calls"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 8},
                "id": 9,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Ingestion Buffer Queue Depth"}, "refId": "QUEUE"}
                ],
                "title": "Ingestion Queue Depth [APPLICATION — WFO]",
                "type": "gauge"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 10,
                "title": "Storage Partition Capacity, Retention & Archival Horizon",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Storage capacity utilization percentage across dedicated call recording storage volumes. Warning: > 80%, Critical: > 90%. Source: HOST-RESOURCES-MIB hrStorageUsed. Polling: 5m.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 80}, {"color": "red", "value": 90}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 15},
                "id": 11,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Recording Storage Partition Utilization"}, "refId": "STORAGE"}
                ],
                "title": "Recording Storage Utilization (%) [REAL — HARDWARE]",
                "type": "gauge"
            },
            {
                "datasource": DATASOURCE,
                "description": "Projected remaining days before recording storage volume reaches 90% and 100% capacity saturation based on rolling 14-day daily ingestion trajectory. Source: Nawari Storage Capacity Forecaster. Warning: < 30 days.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 30}, {"color": "green", "value": 60}]},
                        "unit": "d"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 15},
                "id": 12,
                "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Projected Days-to-Full (Storage TTE)"}, "refId": "TTE"}
                ],
                "title": "Projected Days-to-Full (Storage TTE) [PREDICTIVE]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Percentage of completed daily call recordings successfully migrated and verified in the offsite long-term immutable archival tier. Target: 100%. Source: WFO Archival Verifier.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "max": 100,
                        "min": 0,
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 98}, {"color": "green", "value": 99.9}]},
                        "unit": "percent"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 15},
                "id": 13,
                "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
                "targets": [
                    {"group": {"name": "Recording Infrastructure"}, "host": {"name": "nawari-wfo-01"}, "item": {"name": "Daily Archival Transfer Success Rate"}, "refId": "ARCHIVE"}
                ],
                "title": "Daily Archival Success Rate (%) [APPLICATION — WFO]",
                "type": "gauge"
            }
        ],
        "refresh": "1m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "recording", "wfo", "compliance"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Nawari — Voice Recording & Workforce Optimisation (WFO) Operational Health",
        "uid": "nawari-recording-wfo",
        "version": 1
    }
    with open(COMM_DIR / "recording_wfo_operational_health.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created recording_wfo_operational_health.json")


def create_sip_trunks_dashboard():
    d = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 1,
                "title": "Carrier SIP Trunk Operational Registration & Keepalive Health",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational registration state of the primary Safaricom SIP trunk terminating on Avaya SBCE interface A1. 1 = REGISTERED, 0 = UNREGISTERED / FAILED. Source: Zabbix SNMP/SIP OPTIONS check on SBCE. Crucial Note: Proves layer-5 signaling reachability only; does NOT guarantee absence of voice packet loss or acceptable audio quality.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "REGISTERED (SIP UP)"}, "0": {"color": "red", "text": "UNREGISTERED (DOWN)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                "id": 2,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Safaricom Primary SIP Trunk Operational Status"}, "refId": "SAFARICOM"}
                ],
                "title": "Safaricom Primary SIP Trunk [REAL — ZABBIX]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Operational registration state of the secondary Airtel SIP trunk terminating on Avaya SBCE interface A1. 1 = REGISTERED, 0 = UNREGISTERED / FAILED. Source: Zabbix SNMP/SIP OPTIONS check on SBCE. Signaling reachability only.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [
                            {"options": {"1": {"color": "green", "text": "REGISTERED (SIP UP)"}, "0": {"color": "red", "text": "UNREGISTERED (DOWN)"}}, "type": "value"}
                        ],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 1},
                "id": 3,
                "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Airtel Secondary SIP Trunk Operational Status"}, "refId": "AIRTEL"}
                ],
                "title": "Airtel Secondary SIP Trunk [REAL — ZABBIX]",
                "type": "stat"
            },
            {
                "datasource": DATASOURCE,
                "description": "Round-trip latency in milliseconds for SIP OPTIONS heartbeat pings exchanged with carrier SBC endpoints (Safaricom vs Airtel). Units: Milliseconds (ms). Warning: > 50ms, Critical: > 100ms. Source: Zabbix SIP OPTIONS probe. Polling: 30s.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 12, "x": 12, "y": 1},
                "id": 4,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Safaricom SIP OPTIONS Round-Trip Latency"}, "refId": "SAF_RTT"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Airtel SIP OPTIONS Round-Trip Latency"}, "refId": "AIR_RTT"}
                ],
                "title": "Carrier SIP OPTIONS Round-Trip Latency [REAL — ZABBIX]",
                "type": "timeseries"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 7},
                "id": 5,
                "title": "SIP Transaction Latencies & Signaling Ladder Breakdown",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Post-Dial Delay (PDD: INVITE to 18x), Time-to-Alerting (TTA: INVITE to 180 Ringing), and Call Setup Duration measured in milliseconds from synthetic Asterisk test calls across carrier trunks. Source: Asterisk AMI call logs. Limitations: Reflects synthetic probe calls between test extensions.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "ms"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 7, "w": 14, "x": 0, "y": 8},
                "id": 6,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Post-Dial Delay (PDD)"}, "refId": "PDD"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Time to Alerting (TTA)"}, "refId": "TTA"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Call Setup Duration"}, "refId": "SETUP"}
                ],
                "title": "Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Distribution of SIP response codes returned by carrier networks during synthetic probe calls: differentiates expected station states (480 offline, 486 busy, 487 teardown) from carrier/infrastructure failures (500 Server Internal Error, 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout). Source: Synthetic Asterisk transaction logs.",
                "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
                "gridPos": {"h": 7, "w": 10, "x": 14, "y": 8},
                "id": 7,
                "options": {"legend": {"displayMode": "table", "placement": "right"}, "pieType": "pie"},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "SIP Responses by Category"}, "refId": "CODES"}
                ],
                "title": "SIP Response Distribution (Station vs Trunk Outage) [SYNTHETIC — ASTERISK PROBE]",
                "type": "piechart"
            },
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 15},
                "id": 8,
                "title": "Perimeter Interface Traffic & Voice Path Errors",
                "type": "row"
            },
            {
                "datasource": DATASOURCE,
                "description": "Bidirectional network bandwidth utilization on external interface A1 carrying carrier SIP signaling and RTP media streams. Units: Bits per second (bps). Source: IF-MIB on Avaya SBCE via Zabbix SNMPv3. Polling: 30s.",
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "unit": "bps"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 12, "x": 0, "y": 16},
                "id": 9,
                "options": {"tooltip": {"mode": "multi"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "A1 Interface Ingress Traffic (bps)"}, "refId": "A1_IN"},
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "A1 Interface Egress Traffic (bps)"}, "refId": "A1_OUT"}
                ],
                "title": "A1 Carrier DMZ Bandwidth (bps) [REAL — SBCE SNMP]",
                "type": "timeseries"
            },
            {
                "datasource": DATASOURCE,
                "description": "Rate of inbound and outbound frame/packet errors detected on carrier interface A1. Units: Errors per second. Source: IF-MIB ifInErrors / ifOutErrors. Any non-zero error rate directly degrades voice audio quality, causing clipping and metallic distortion.",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]},
                        "unit": "errors/s"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 6, "w": 12, "x": 12, "y": 16},
                "id": 10,
                "options": {"tooltip": {"mode": "single"}},
                "targets": [
                    {"group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Voice Path Packet Errors (rate)"}, "refId": "ERRORS"}
                ],
                "title": "Carrier Interface Packet Errors (Errors/sec) [REAL — SBCE SNMP]",
                "type": "timeseries"
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["nawari", "communication-observability", "avaya", "sip-trunks", "carrier", "safaricom", "airtel"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Nawari — Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing",
        "uid": "nawari-sip-trunks",
        "version": 1
    }
    with open(COMM_DIR / "nawari_sip_trunks_signaling.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Created nawari_sip_trunks_signaling.json")


def update_root_symlinks():
    for f in COMM_DIR.glob("*.json"):
        symlink = ROOT_DASH_DIR / f.name
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        symlink.symlink_to(f"communication_observability/{f.name}")
        print(f"Symlinked {f.name} -> communication_observability/{f.name}")


if __name__ == "__main__":
    create_comm_overview()
    create_session_manager_dashboard()
    create_communication_manager_dashboard()
    create_g450_dashboard()
    create_cms_dashboard()
    create_recording_wfo_dashboard()
    create_sip_trunks_dashboard()
    update_root_symlinks()
    print("Finished building Communication Observability suite!")

