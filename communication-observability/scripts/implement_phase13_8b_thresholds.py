#!/usr/bin/env python3
"""scripts/implement_phase13_8b_thresholds.py

Phase 13.8B: Controlled Zabbix Threshold Implementation, Hysteresis & Alert Policy Enforcement.
Translates the engineering policy and authoritative threshold register established in Phase 13.8A
into technically valid, operationally consistent Zabbix 7.4 trigger configurations.

Batch Implementation Architecture:
- Batch 1: Base ICMP & SNMP Availability (Nawari Generic SNMP Base - 10784)
- Batch 2: Network Device LLD Discovery Prototypes & Tags (Nawari Network Device by SNMP - 10786)
- Batch 3: Endpoint Trapper Infrastructure (Template Nawari Endpoint Probe - 10792)
- Batch 4: Avaya SBCE Host Resources, Sessions & Interfaces (Nawari Avaya SBCE by SNMP - 10788)
- Batch 5: Synthetic Voice & Audio Media Telemetry (Nawari Voice Synthetic Probe - 10790)
- Batch 6: Communication Manager Core QoS & Processors (Nawari Avaya CM by SNMP - 10793)
- Batch 7: G450 Media Gateway Fleet (Nawari Avaya G450 Media Gateway by SNMP - 10794)
- Batch 8: Session Manager Routing & SIP Entities (Nawari Avaya SM by SNMP - 10795)
- Batch 9: Carrier SIP Trunks & Signaling (Nawari SIP Trunk by Trapper - 10797)
- Batch 10: CMS Contact Center & WFO Recording (Nawari Avaya CMS and WFO - 10796)
- Batch 11: Network Generic Device by SNMP & Prototypes (10226)
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase13_8b_implementation")

SNAPSHOT_DIR = PROJECT_ROOT / "provisioning/zabbix/snapshots"
CHANGE_MANIFEST_PATH = SNAPSHOT_DIR / "phase13_8b_change_manifest.json"

BATCH_DEFINITIONS = [
    {
        "batch_id": "BATCH_01",
        "template_name": "Nawari Generic SNMP Base",
        "template_id": "10784",
        "description": "Base ICMP reachability, packet loss, and SNMP daemon availability",
        "triggers": [
            {
                "triggerid": "32573",
                "description": "Nawari Generic SNMP Base: Device has just been restarted",
                "recovery_mode": 1,
                "recovery_expression": "last(/Nawari Generic SNMP Base/system.uptime[sysUpTime.0])>=10m",
                "tags": [{"tag": "notification_class", "value": "informational"}],
            },
            {
                "triggerid": "32574",
                "description": "Nawari Generic SNMP Base: SNMP agent is not responding",
                "priority": 4,
                "recovery_mode": 1,
                "recovery_expression": "min(/Nawari Generic SNMP Base/zabbix[host,snmp,available],#3)=1",
                "tags": [{"tag": "notification_class", "value": "monitoring_failure"}],
            },
            {
                "triggerid": "32575",
                "description": "Nawari Generic SNMP Base: High ICMP ping loss",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Generic SNMP Base/icmppingloss,5m)>20",
                "recovery_expression": "max(/Nawari Generic SNMP Base/icmppingloss,5m)<5",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32576",
                "description": "Nawari Generic SNMP Base: High ICMP response time",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "avg(/Nawari Generic SNMP Base/icmppingsec,5m)>0.15",
                "recovery_expression": "avg(/Nawari Generic SNMP Base/icmppingsec,5m)<0.10",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_02",
        "template_name": "Nawari Network Device by SNMP",
        "template_id": "10786",
        "description": "Network device interface LLD discovery prototypes and tags",
        "triggers": [],
        "prototypes": [
            {
                "triggerid": "32585",
                "description": "Interface {#IFNAME}: Link down",
                "priority": 3,
                "recovery_mode": 1,
                "recovery_expression": "last(/Nawari Network Device by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=1",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32586",
                "description": "Interface {#IFNAME}: High bandwidth utilization (> {$IF_UTIL_MAX}%)",
                "priority": 2,
                "recovery_mode": 1,
                "recovery_expression": "(last(/Nawari Network Device by SNMP/net.if.in[ifInOctets.{#SNMPINDEX}]) < (last(/Nawari Network Device by SNMP/net.if.speed[ifSpeed.{#SNMPINDEX}]) * 60 / 100) and last(/Nawari Network Device by SNMP/net.if.out[ifOutOctets.{#SNMPINDEX}]) < (last(/Nawari Network Device by SNMP/net.if.speed[ifSpeed.{#SNMPINDEX}]) * 60 / 100))",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32587",
                "description": "Interface {#IFNAME}: High error rate (> {$IF_ERRORS_WARN} err/s)",
                "priority": 2,
                "recovery_mode": 1,
                "recovery_expression": "max(/Nawari Network Device by SNMP/net.if.in.errors[ifInErrors.{#SNMPINDEX}],5m)<1 and max(/Nawari Network Device by SNMP/net.if.out.errors[ifOutErrors.{#SNMPINDEX}],5m)<1",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
        ],
    },
    {
        "batch_id": "BATCH_03",
        "template_name": "Template Nawari Endpoint Probe by Zabbix Trapper",
        "template_id": "10792",
        "description": "Endpoint latency, gateway packet loss, and probe staleness",
        "triggers": [
            {
                "triggerid": "32691",
                "description": "Endpoint probe telemetry is stale (>15m)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.info,15m)=1",
                "recovery_expression": "nodata(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.info,15m)=0",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32692",
                "description": "High packet loss to default gateway (>20%)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "min(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.loss,5m)>20",
                "recovery_expression": "max(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.loss,5m)<5",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32693",
                "description": "High default gateway latency (>50ms)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.rtt,5m)>0.05",
                "recovery_expression": "max(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.rtt,5m)<0.03",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_04",
        "template_name": "Nawari Avaya SBCE by SNMP",
        "template_id": "10788",
        "description": "Avaya SBCE host resources, session capacity, and interface prototypes",
        "triggers": [
            {
                "triggerid": "32626",
                "description": "Avaya SBCE: High CPU utilization (> {$CPU.UTIL.WARN}%)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/system.cpu.util,5m)>85",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/system.cpu.util,5m)<70",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32627",
                "description": "Avaya SBCE: High memory utilization (> {$MEMORY.UTIL.WARN}%)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/vm.memory.util,5m)>90",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/vm.memory.util,5m)<80",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32628",
                "description": "Avaya SBCE: High root filesystem disk usage (> {$DISK.UTIL.WARN}%)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/vfs.fs.used.percent[/],5m)>85",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/vfs.fs.used.percent[/],5m)<75",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32701",
                "description": "Avaya SBCE: Telemetry Stale or Loss of Monitoring",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.active_calls,15m)=1",
                "recovery_expression": "nodata(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.active_calls,15m)=0",
                "tags": [
                    {"tag": "component", "value": "sip-sessions"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32702",
                "description": "Avaya SBCE: Active Session Capacity Warning (>= 80%)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,5m)>=80",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,5m)<75",
                "tags": [
                    {"tag": "component", "value": "capacity"},
                    {"tag": "scope", "value": "capacity"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32703",
                "description": "Avaya SBCE: Active Session Capacity Critical (>= 95%)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,3m)>=95",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,5m)<85",
                "tags": [
                    {"tag": "component", "value": "capacity"},
                    {"tag": "scope", "value": "capacity"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32704",
                "description": "Avaya SBCE: Management Interface Unreachable",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "count(/Nawari Avaya SBCE by SNMP/net.tcp.service[https,10.2.156.131,443],#2,\"eq\",0)>=2",
                "recovery_expression": "min(/Nawari Avaya SBCE by SNMP/net.tcp.service[https,10.2.156.131,443],#1)=1",
                "tags": [
                    {"tag": "component", "value": "management"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32705",
                "description": "Avaya SBCE: Sustained High SIP Failure Rate (> 5%)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/avaya.sbce.sip_failure_rate_pct,5m)>5",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/avaya.sbce.sip_failure_rate_pct,5m)<2",
                "tags": [
                    {"tag": "component", "value": "sip-signaling"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32706",
                "description": "Avaya SBCE: License Utilization Limit Approached (>= 90%)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/avaya.sbce.allocated_licenses_pct,5m)>=90",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/avaya.sbce.allocated_licenses_pct,5m)<80",
                "tags": [
                    {"tag": "component", "value": "capacity"},
                    {"tag": "scope", "value": "capacity"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32707",
                "description": "Avaya SBCE: Interface Packet Discards / Errors Elevated (> 1%)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya SBCE by SNMP/avaya.sbce.if_error_rate_pct,5m)>1",
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/avaya.sbce.if_error_rate_pct,5m)<0.5",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32708",
                "description": "Avaya SBCE: Appliance Unreachable",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "max(/Nawari Avaya SBCE by SNMP/icmpping[10.2.156.131],#3)=0",
                "recovery_expression": "min(/Nawari Avaya SBCE by SNMP/icmpping[10.2.156.131],#2)=1",
                "tags": [
                    {"tag": "component", "value": "sbce-core"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
        ],
        "prototypes": [
            {
                "triggerid": "32629",
                "description": "Interface {#IFNAME}: Link down",
                "priority": 4,
                "recovery_mode": 1,
                "recovery_expression": "last(/Nawari Avaya SBCE by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=1",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32630",
                "description": "Interface {#IFNAME}: High bandwidth utilization (> {$IF_UTIL_MAX}%)",
                "priority": 2,
                "recovery_mode": 1,
                "recovery_expression": "(last(/Nawari Avaya SBCE by SNMP/net.if.in[ifHCInOctets.{#SNMPINDEX}]) < (last(/Nawari Avaya SBCE by SNMP/net.if.speed[ifHighSpeed.{#SNMPINDEX}]) * 60 / 100) and last(/Nawari Avaya SBCE by SNMP/net.if.out[ifHCOutOctets.{#SNMPINDEX}]) < (last(/Nawari Avaya SBCE by SNMP/net.if.speed[ifHighSpeed.{#SNMPINDEX}]) * 60 / 100))",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32631",
                "description": "Interface {#IFNAME}: High error rate (> {$IF_ERRORS_WARN} err/s)",
                "priority": 2,
                "recovery_mode": 1,
                "recovery_expression": "max(/Nawari Avaya SBCE by SNMP/net.if.in.errors[ifInErrors.{#SNMPINDEX}],5m)<1 and max(/Nawari Avaya SBCE by SNMP/net.if.out.errors[ifOutErrors.{#SNMPINDEX}],5m)<1",
                "tags": [
                    {"tag": "component", "value": "interface"},
                    {"tag": "interface", "value": "{#IFNAME}"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
        ],
    },
    {
        "batch_id": "BATCH_05",
        "template_name": "Nawari Voice Synthetic Probe by Zabbix Trapper",
        "template_id": "10790",
        "description": "Synthetic voice call outcomes, MOS quality scores, setup time, and RTP media",
        "triggers": [
            {
                "triggerid": "32679",
                "description": "Synthetic voice test failed or congested",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome)=\"FAILED\" or last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome)=\"CONGESTION\"",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome)=\"SUCCESS\" or last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome)=\"ANSWERED\"",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32680",
                "description": "Synthetic Voice: Call Setup Timeout (> 4000 ms)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "min(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.setup_time,#2)>4000",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.setup_time)<2500",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "source", "value": "asterisk"},
                    {"tag": "telemetry_type", "value": "synthetic"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32681",
                "description": "One-way audio detected on synthetic voice test",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.media_status)=\"TRANSMIT_ONLY\" or last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.media_status)=\"RECEIVE_ONLY\"",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.media_status)=\"BIDIRECTIONAL\"",
                "tags": [
                    {"tag": "scope", "value": "media-path"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32682",
                "description": "Degraded voice quality on synthetic probe (MOS < 3.8)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "max(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos,#2)<3.8 and last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos)>0",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos)>=4.0",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32683",
                "description": "Unacceptable voice quality on synthetic probe (MOS < 3.5)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "max(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos,#2)<3.5 and last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos)>0",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.mos)>=3.8",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32689",
                "description": "Synthetic voice probe telemetry is stale (>15m)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome,15m)=1",
                "recovery_expression": "nodata(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome,15m)=0",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "synthetic_failure"},
                ],
            },
            {
                "triggerid": "32725",
                "description": "Synthetic Voice: Connected Duration Below Criterion (< 5s)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.duration)<5 and last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.duration)>=0",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.duration)>=10",
                "tags": [{"tag": "notification_class", "value": "synthetic_failure"}],
            },
            {
                "triggerid": "32726",
                "description": "Synthetic Voice: SIP vs AMI Result Mismatch",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.sip_ami_mismatch)=1",
                "recovery_expression": "last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.sip_ami_mismatch)=0",
                "tags": [{"tag": "notification_class", "value": "monitoring_failure"}],
            },
            {
                "triggerid": "32727",
                "description": "Synthetic Voice: Consecutive Test Failures (3 Consecutive)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "count(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.call_success,#3,\"eq\",0)=3",
                "recovery_expression": "count(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.call_success,#2,\"eq\",1)=2",
                "tags": [{"tag": "notification_class", "value": "synthetic_failure"}],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_06",
        "template_name": "Nawari Avaya Communication Manager by SNMP",
        "template_id": "10793",
        "description": "Avaya Communication Manager QoS, alarm counts, call rates, and core reachability",
        "triggers": [
            {
                "triggerid": "32694",
                "description": "Avaya CM: Real-Call Packet Loss High (> 2.5% in Last Hour)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.loss_pct,1h)>2.5",
                "recovery_expression": "max(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.loss_pct,1h)<0.8",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32695",
                "description": "Avaya CM: Real-Call Peak Jitter High (> 30 ms)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.peak_jitter,1h)>30",
                "recovery_expression": "max(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.peak_jitter,1h)<15",
                "tags": [{"tag": "notification_class", "value": "degradation"}],
            },
            {
                "triggerid": "32696",
                "description": "Avaya CM: Active Telephony Alarms Present",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.alarms.active_count)>0",
                "recovery_expression": "last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.alarms.active_count)=0",
                "tags": [{"tag": "notification_class", "value": "component_failure"}],
            },
            {
                "triggerid": "32731",
                "description": "Avaya CM: Call Rate Abnormal Drop (< 10 calls/hr)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed)<10 and last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed)>=0",
                "recovery_expression": "last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed)>=30",
                "tags": [
                    {"tag": "component", "value": "call-rate"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32732",
                "description": "Avaya CM: Performance Telemetry Stale (> 2h)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed,2h)=1",
                "recovery_expression": "nodata(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed,2h)=0",
                "tags": [
                    {"tag": "component", "value": "call-rate"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32733",
                "description": "Avaya CM: Communication Manager Processor Unreachable",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "max(/Nawari Avaya Communication Manager by SNMP/icmpping[10.102.10.25],#3)=0",
                "recovery_expression": "min(/Nawari Avaya Communication Manager by SNMP/icmpping[10.102.10.25],#2)=1",
                "tags": [
                    {"tag": "component", "value": "cm-core"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_07",
        "template_name": "Nawari Avaya G450 Media Gateway by SNMP",
        "template_id": "10794",
        "description": "Avaya G450 Media Gateway environmental metrics, PSU, fans, E1 links, and registration",
        "triggers": [
            {
                "triggerid": "32697",
                "description": "Avaya G450: Media Gateway Unregistered from Communication Manager",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.cm_registration_state)<>1",
                "recovery_expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.cm_registration_state)=1",
                "tags": [{"tag": "notification_class", "value": "service_outage"}],
            },
            {
                "triggerid": "32700",
                "description": "Avaya G450: Chassis Ambient Temperature Threshold Exceeded (Warning)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.temperature,5m)>=2",
                "recovery_expression": "max(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.temperature,5m)=1",
                "tags": [
                    {"tag": "component", "value": "environment"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32738",
                "description": "Avaya G450: Media Gateway Telemetry Missing (> 10m)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Avaya G450 Media Gateway by SNMP/system.uptime,10m)=1",
                "recovery_expression": "nodata(/Nawari Avaya G450 Media Gateway by SNMP/system.uptime,10m)=0",
                "tags": [
                    {"tag": "component", "value": "system"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32739",
                "description": "Avaya G450: Power Supply Unit Failure",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.psu.status.1)=2 or last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.psu.status.2)=2",
                "recovery_expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.psu.status.1)=1 and last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.psu.status.2)=1",
                "tags": [
                    {"tag": "component", "value": "environment"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32740",
                "description": "Avaya G450: Fan Tray Failure",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.fan_tray.status)=2",
                "recovery_expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.fan_tray.status)=1",
                "tags": [
                    {"tag": "component", "value": "environment"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32741",
                "description": "Avaya G450: E1/ISDN Primary Trunk Port Down",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/ifOperStatus.e1.1)=2",
                "recovery_expression": "last(/Nawari Avaya G450 Media Gateway by SNMP/ifOperStatus.e1.1)=1",
                "tags": [
                    {"tag": "component", "value": "pstn-trunk"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32742",
                "description": "Avaya G450: Media Gateway Chassis Unreachable",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "max(/Nawari Avaya G450 Media Gateway by SNMP/icmpping[10.2.156.60],#3)=0",
                "recovery_expression": "min(/Nawari Avaya G450 Media Gateway by SNMP/icmpping[10.2.156.60],#2)=1",
                "tags": [
                    {"tag": "component", "value": "infrastructure"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_08",
        "template_name": "Nawari Avaya Session Manager by SNMP",
        "template_id": "10795",
        "description": "Avaya Session Manager SIP entities, signalling failure rate, alarms, and reachability",
        "triggers": [
            {
                "triggerid": "32698",
                "description": "Avaya SM: SIP Entity Down (Communication Manager)",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=3",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32699",
                "description": "Avaya SM: SIP Entity Down (Avaya SBCE)",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=3",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32743",
                "description": "Avaya SM: Management Telemetry Stale or Loss of Monitoring",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Avaya Session Manager by SNMP/system.uptime,10m)=1",
                "recovery_expression": "nodata(/Nawari Avaya Session Manager by SNMP/system.uptime,10m)=0",
                "tags": [
                    {"tag": "component", "value": "system"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32744",
                "description": "Avaya SM: SIP Entity PARTIALLY UP (Communication Manager)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=2",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32745",
                "description": "Avaya SM: SIP Entity DENY NEW SERVICE (Communication Manager)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=4",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32746",
                "description": "Avaya SM: SIP Entity PARTIALLY UP (Avaya SBCE)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=2",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32747",
                "description": "Avaya SM: SIP Entity DENY NEW SERVICE (Avaya SBCE)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=4",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1",
                "tags": [
                    {"tag": "component", "value": "sip-entity"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32748",
                "description": "Avaya SM: SIP OPTIONS Latency Elevated (> 250ms)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.rtt.cm,5m)>250",
                "recovery_expression": "max(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.rtt.cm,5m)<100",
                "tags": [
                    {"tag": "component", "value": "sip-signaling"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32749",
                "description": "Avaya SM: Synthetic SIP OPTIONS Probe Failure",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "count(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_options_status,#2,\"eq\",0)>=2",
                "recovery_expression": "count(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_options_status,#2,\"eq\",1)=2",
                "tags": [
                    {"tag": "component", "value": "sip-signaling"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
            {
                "triggerid": "32750",
                "description": "Avaya SM: Session Manager Signalling Failure Rate High (> 5%)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya Session Manager by SNMP/avaya.sm.signalling_failure_pct,5m)>5",
                "recovery_expression": "max(/Nawari Avaya Session Manager by SNMP/avaya.sm.signalling_failure_pct,5m)<1",
                "tags": [
                    {"tag": "component", "value": "sip-routing"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32751",
                "description": "Avaya SM: Critical Enterprise Alarm Reported",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.alarms.active_count)>0",
                "recovery_expression": "last(/Nawari Avaya Session Manager by SNMP/avaya.sm.alarms.active_count)=0",
                "tags": [
                    {"tag": "component", "value": "alarms"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "32752",
                "description": "Avaya SM: Session Manager Host Unavailable",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "max(/Nawari Avaya Session Manager by SNMP/icmpping[10.2.156.22],#3)=0",
                "recovery_expression": "min(/Nawari Avaya Session Manager by SNMP/icmpping[10.2.156.22],#2)=1",
                "tags": [
                    {"tag": "component", "value": "infrastructure"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_09",
        "template_name": "Nawari SIP Trunk by Trapper",
        "template_id": "10797",
        "description": "Carrier SIP trunk reachability, SIP OPTIONS failures, 5xx/4xx error rates, DNS and TLS",
        "triggers": [
            {
                "triggerid": "32753",
                "description": "SIP Trunk: Endpoint Unreachable",
                "priority": 5,
                "recovery_mode": 1,
                "expression": "max(/Nawari SIP Trunk by Trapper/icmpping[10.2.156.100],#3)=0",
                "recovery_expression": "min(/Nawari SIP Trunk by Trapper/icmpping[10.2.156.100],#2)=1",
                "tags": [
                    {"tag": "component", "value": "sip-trunk"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
            {
                "triggerid": "32754",
                "description": "SIP Trunk: Consecutive OPTIONS Probe Failures",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "count(/Nawari SIP Trunk by Trapper/sip.trunk.options_status,#4,\"eq\",0)>=3",
                "recovery_expression": "count(/Nawari SIP Trunk by Trapper/sip.trunk.options_status,#3,\"eq\",1)=3",
                "tags": [
                    {"tag": "component", "value": "sip-signaling"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32755",
                "description": "SIP Trunk: High Error Response Rate (5xx/4xx > 10%)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "min(/Nawari SIP Trunk by Trapper/sip.trunk.error_rate_pct,5m)>10",
                "recovery_expression": "max(/Nawari SIP Trunk by Trapper/sip.trunk.error_rate_pct,5m)<2",
                "tags": [
                    {"tag": "component", "value": "sip-signaling"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32756",
                "description": "SIP Trunk: DNS SRV/A Resolution Failure",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "count(/Nawari SIP Trunk by Trapper/sip.trunk.dns_resolved,#2,\"eq\",0)>=2",
                "recovery_expression": "min(/Nawari SIP Trunk by Trapper/sip.trunk.dns_resolved,#1)=1",
                "tags": [
                    {"tag": "component", "value": "dns"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32757",
                "description": "SIP Trunk: TLS Certificate Expiration Warning (<= 30 days)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)<=30 and last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)>7",
                "recovery_expression": "last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)>30",
                "tags": [
                    {"tag": "component", "value": "tls-security"},
                    {"tag": "scope", "value": "security"},
                    {"tag": "notification_class", "value": "informational"},
                ],
            },
            {
                "triggerid": "32758",
                "description": "SIP Trunk: TLS Certificate Expiration Critical (<= 7 days)",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)<=7",
                "recovery_expression": "last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)>7",
                "tags": [
                    {"tag": "component", "value": "tls-security"},
                    {"tag": "scope", "value": "security"},
                    {"tag": "notification_class", "value": "informational"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_10",
        "template_name": "Nawari Avaya CMS and WFO by Trapper",
        "template_id": "10796",
        "description": "Avaya CMS contact center SLA and WFO call recording compliance",
        "triggers": [
            {
                "triggerid": "32734",
                "description": "Avaya CMS: Queue Service Level Degradation (< 80%)",
                "priority": 3,
                "recovery_mode": 1,
                "expression": "min(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct,15m)<80 and last(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct)>=0",
                "recovery_expression": "max(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct,15m)>=85",
                "tags": [
                    {"tag": "component", "value": "contact-centre"},
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32735",
                "description": "Avaya CMS: Telemetry Data Stale (> 45m)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "nodata(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct,45m)=1",
                "recovery_expression": "nodata(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct,45m)=0",
                "tags": [
                    {"tag": "component", "value": "contact-centre"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "32736",
                "description": "WFO: Compliance Voice Recording Pipeline Health Failure",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.pipeline_status)=0",
                "recovery_expression": "last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.pipeline_status)=1",
                "tags": [
                    {"tag": "component", "value": "call-recording"},
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "service_outage"},
                ],
            },
            {
                "triggerid": "32737",
                "description": "WFO: Compliance Voice Recording Spool Disk Storage Warning (< 15%)",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.disk_free_pct)<15",
                "recovery_expression": "last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.disk_free_pct)>20",
                "tags": [
                    {"tag": "component", "value": "call-recording"},
                    {"tag": "scope", "value": "capacity"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
        ],
        "prototypes": [],
    },
    {
        "batch_id": "BATCH_11",
        "template_name": "Network Generic Device by SNMP",
        "template_id": "10226",
        "description": "Generic network switch base triggers and interface prototypes",
        "triggers": [
            {
                "triggerid": "21709",
                "description": "Network Generic Device: Unavailable by ICMP ping",
                "priority": 4,
                "recovery_mode": 1,
                "expression": "max(/Network Generic Device by SNMP/icmpping,#3)=0",
                "recovery_expression": "min(/Network Generic Device by SNMP/icmpping,#2)=1",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "total_outage"},
                ],
            },
            {
                "triggerid": "21710",
                "description": "Network Generic Device: High ICMP ping loss",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "min(/Network Generic Device by SNMP/icmppingloss,5m)>20",
                "recovery_expression": "max(/Network Generic Device by SNMP/icmppingloss,5m)<5",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "21711",
                "description": "Network Generic Device: High ICMP ping response time",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "avg(/Network Generic Device by SNMP/icmppingsec,5m)>0.15",
                "recovery_expression": "avg(/Network Generic Device by SNMP/icmppingsec,5m)<0.10",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "21712",
                "description": "Network Generic Device: System name has changed",
                "priority": 1,
                "recovery_mode": 0,
                "tags": [
                    {"tag": "scope", "value": "security"},
                    {"tag": "notification_class", "value": "informational"},
                ],
            },
            {
                "triggerid": "21713",
                "description": "Network Generic Device: Host has been restarted",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "(last(/Network Generic Device by SNMP/system.net.uptime[sysUpTime.0])>0 and last(/Network Generic Device by SNMP/system.net.uptime[sysUpTime.0])<10m) or (last(/Network Generic Device by SNMP/system.net.uptime[sysUpTime.0])=0 and last(/Network Generic Device by SNMP/system.hw.uptime[hrSystemUptime.0])<10m)",
                "recovery_expression": "last(/Network Generic Device by SNMP/system.net.uptime[sysUpTime.0])>=10m or last(/Network Generic Device by SNMP/system.hw.uptime[hrSystemUptime.0])>=10m",
                "tags": [
                    {"tag": "scope", "value": "notice"},
                    {"tag": "notification_class", "value": "informational"},
                ],
            },
            {
                "triggerid": "21714",
                "description": "Network Generic Device: No SNMP data collection",
                "priority": 2,
                "recovery_mode": 1,
                "expression": "max(/Network Generic Device by SNMP/zabbix[host,snmp,available],#3)=0",
                "recovery_expression": "min(/Network Generic Device by SNMP/zabbix[host,snmp,available],#2)=1",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "monitoring_failure"},
                ],
            },
        ],
        "prototypes": [
            {
                "triggerid": "29741",
                "description": "Network Generic Device: Interface {#IFNAME}({#IFALIAS}): Ethernet has changed to lower speed than it was before",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "informational"},
                ],
            },
            {
                "triggerid": "29742",
                "description": "Network Generic Device: Interface {#IFNAME}({#IFALIAS}): High bandwidth usage",
                "recovery_mode": 1,
                "recovery_expression": "(last(/Network Generic Device by SNMP/net.if.in[ifInOctets.{#SNMPINDEX}]) < (last(/Network Generic Device by SNMP/net.if.speed[ifSpeed.{#SNMPINDEX}]) * 60 / 100) and last(/Network Generic Device by SNMP/net.if.out[ifOutOctets.{#SNMPINDEX}]) < (last(/Network Generic Device by SNMP/net.if.speed[ifSpeed.{#SNMPINDEX}]) * 60 / 100))",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "29743",
                "description": "Network Generic Device: Interface {#IFNAME}({#IFALIAS}): High error rate",
                "recovery_mode": 1,
                "recovery_expression": "max(/Network Generic Device by SNMP/net.if.in.errors[ifInErrors.{#SNMPINDEX}],5m)<1 and max(/Network Generic Device by SNMP/net.if.out.errors[ifOutErrors.{#SNMPINDEX}],5m)<1",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
            {
                "triggerid": "29744",
                "description": "Network Generic Device: Interface {#IFNAME}({#IFALIAS}): Link down",
                "recovery_mode": 1,
                "recovery_expression": "last(/Network Generic Device by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=1",
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "notification_class", "value": "component_failure"},
                ],
            },
            {
                "triggerid": "29745",
                "description": "Network Generic Device: Interface {#IFNAME}({#IFALIAS}): In half-duplex mode",
                "recovery_mode": 1,
                "recovery_expression": "last(/Network Generic Device by SNMP/net.if.duplex[dot3StatsDuplexStatus.{#SNMPINDEX}])=3",
                "tags": [
                    {"tag": "scope", "value": "performance"},
                    {"tag": "notification_class", "value": "degradation"},
                ],
            },
        ],
    },
]


def execute_phase13_8b_implementation() -> Dict[str, Any]:
    client = ZabbixClient(ZabbixSettings())
    client.connect()
    logger.info("Connected to staging Zabbix API: %s", client.url)

    manifest_records = []
    total_triggers_updated = 0
    total_prototypes_updated = 0

    for batch in BATCH_DEFINITIONS:
        bid = batch["batch_id"]
        tname = batch["template_name"]
        tid = batch["template_id"]
        logger.info(">>> Processing %s: %s (Template ID: %s)", bid, tname, tid)

        # 1. Update Triggers
        for trig in batch.get("triggers", []):
            trigger_id = trig["triggerid"]
            update_payload: Dict[str, Any] = {"triggerid": trigger_id}
            if "expression" in trig:
                update_payload["expression"] = trig["expression"]
            if "expression" in trig:
                update_payload["expression"] = trig["expression"]
            if "recovery_mode" in trig:
                update_payload["recovery_mode"] = trig["recovery_mode"]
            if "recovery_expression" in trig:
                update_payload["recovery_expression"] = trig["recovery_expression"]
            if "priority" in trig:
                update_payload["priority"] = trig["priority"]
            if "tags" in trig:
                update_payload["tags"] = trig["tags"]

            try:
                res = client.call("trigger.update", update_payload)
                logger.info("   [OK] Trigger %s: %s", trigger_id, trig["description"])
                total_triggers_updated += 1
                manifest_records.append({
                    "batch_id": bid,
                    "template": tname,
                    "template_id": tid,
                    "target_type": "trigger",
                    "id": trigger_id,
                    "description": trig["description"],
                    "status": "SUCCESS",
                    "recovery_mode": trig.get("recovery_mode", 0),
                    "tags": trig.get("tags", []),
                })
            except Exception as e:
                logger.error("   [FAIL] Trigger %s: %s -> %s", trigger_id, trig["description"], e)
                manifest_records.append({
                    "batch_id": bid,
                    "template": tname,
                    "template_id": tid,
                    "target_type": "trigger",
                    "id": trigger_id,
                    "description": trig["description"],
                    "status": "ERROR",
                    "error": str(e),
                })

        # 2. Update Prototypes
        for proto in batch.get("prototypes", []):
            proto_id = proto["triggerid"]
            proto_payload: Dict[str, Any] = {"triggerid": proto_id}
            if "expression" in proto:
                proto_payload["expression"] = proto["expression"]
            if "recovery_mode" in proto:
                proto_payload["recovery_mode"] = proto["recovery_mode"]
            if "recovery_expression" in proto:
                proto_payload["recovery_expression"] = proto["recovery_expression"]
            if "priority" in proto:
                proto_payload["priority"] = proto["priority"]
            if "tags" in proto:
                proto_payload["tags"] = proto["tags"]

            try:
                res = client.call("triggerprototype.update", proto_payload)
                logger.info("   [OK] Prototype %s: %s", proto_id, proto["description"])
                total_prototypes_updated += 1
                manifest_records.append({
                    "batch_id": bid,
                    "template": tname,
                    "template_id": tid,
                    "target_type": "prototype",
                    "id": proto_id,
                    "description": proto["description"],
                    "status": "SUCCESS",
                    "recovery_mode": proto.get("recovery_mode", 0),
                    "tags": proto.get("tags", []),
                })
            except Exception as e:
                logger.error("   [FAIL] Prototype %s: %s -> %s", proto_id, proto["description"], e)
                manifest_records.append({
                    "batch_id": bid,
                    "template": tname,
                    "template_id": tid,
                    "target_type": "prototype",
                    "id": proto_id,
                    "description": proto["description"],
                    "status": "ERROR",
                    "error": str(e),
                })

    # Trigger LLD task discovery on mock hosts to synchronize discovered triggers
    logger.info("Triggering LLD rediscovery on mock lab hosts...")
    hosts = client.call("host.get", {"filter": {"host": ["mock-avaya-sbce-01", "mock-core-switch-01"]}})
    hostids = [h["hostid"] for h in hosts]
    drules = client.call("discoveryrule.get", {"hostids": hostids, "output": ["itemid", "name"]})
    if drules:
        client.call("task.create", [{"type": 6, "request": {"itemid": dr["itemid"]}} for dr in drules])
        logger.info("Created LLD rediscovery tasks for %d discovery rules; waiting 5s for propagation...", len(drules))
        time.sleep(5)

    # Readback Verification
    NAWARI_TEMPLATE_IDS = [b["template_id"] for b in BATCH_DEFINITIONS]
    current_triggers = client.call("trigger.get", {
        "output": ["triggerid", "description", "expression", "recovery_mode", "recovery_expression", "priority"],
        "selectHosts": ["hostid", "name"],
        "selectTags": "extend",
        "templateids": NAWARI_TEMPLATE_IDS,
        "inherited": False,
    })
    current_prototypes = client.call("triggerprototype.get", {
        "output": ["triggerid", "description", "expression", "recovery_mode", "recovery_expression", "priority"],
        "selectHosts": ["hostid", "name"],
        "selectTags": "extend",
        "templateids": NAWARI_TEMPLATE_IDS,
        "inherited": False,
    })

    # Discovered triggers readback
    discovered_triggers = client.call("trigger.get", {
        "output": ["triggerid", "description", "flags", "recovery_mode"],
        "selectTags": "extend",
        "filter": {"flags": ["4"]},
    })
    tagged_discovered = [t for t in discovered_triggers if any(tag["tag"] == "notification_class" for tag in t.get("tags", []))]

    rec_mode_1_triggers = [t for t in current_triggers if t["recovery_mode"] == "1"]
    tagged_triggers = [t for t in current_triggers if any(tag["tag"] == "notification_class" for tag in t.get("tags", []))]
    rec_mode_1_prototypes = [p for p in current_prototypes if p["recovery_mode"] == "1"]
    tagged_prototypes = [p for p in current_prototypes if any(tag["tag"] == "notification_class" for tag in p.get("tags", []))]

    manifest = {
        "phase": "13.8B",
        "title": "Controlled Zabbix Threshold Implementation, Hysteresis & Alert Policy Enforcement",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "staging",
        "summary": {
            "total_batches": len(BATCH_DEFINITIONS),
            "records_count": len(manifest_records),
            "triggers_updated": total_triggers_updated,
            "prototypes_updated": total_prototypes_updated,
            "template_triggers_count": len(current_triggers),
            "template_triggers_recovery_mode_1": len(rec_mode_1_triggers),
            "template_triggers_tagged": len(tagged_triggers),
            "template_prototypes_count": len(current_prototypes),
            "template_prototypes_recovery_mode_1": len(rec_mode_1_prototypes),
            "template_prototypes_tagged": len(tagged_prototypes),
            "discovered_triggers_count": len(discovered_triggers),
            "discovered_triggers_tagged": len(tagged_discovered),
            "untagged_discovered_resolved": len(tagged_discovered) == len(discovered_triggers),
        },
        "records": manifest_records,
        "verification_readback": {
            "template_triggers": current_triggers,
            "template_prototypes": current_prototypes,
            "discovered_triggers_summary": {
                "total": len(discovered_triggers),
                "tagged": len(tagged_discovered),
            },
        },
    }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHANGE_MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Saved change manifest to %s", CHANGE_MANIFEST_PATH)

    return manifest


if __name__ == "__main__":
    execute_phase13_8b_implementation()
