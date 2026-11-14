#!/usr/bin/env python3
"""
scripts/enrich_dashboard_telemetry.py

Enriches Grafana dashboards with:
1. Operational panel descriptions (meaning, units, source, limitations) across all panels.
2. Explicit provenance tags ([REAL — ZABBIX], [REAL — AVAYA SNMP], [SYNTHETIC — ASTERISK], [NOT INSTRUMENTED]).
3. Honest uninstrumented indicators for Real-Call MOS (RFC 3611 RTCP-XR required).
4. Avaya CM 8.1.0 IP Voice SNMP telemetry panels (avCmMeasIpVoStatSumDataLstHrTable & avCmMeasIpVoStatHrJitterTable).
5. Ensures null values are never coerced to zero.
"""

import json
from pathlib import Path

BASE_DIR = Path("/Users/madeira/Desktop/Projects/nawari/docker/grafana/dashboards")
COMM_DIR = BASE_DIR / "communication_observability"
NET_DIR = BASE_DIR / "network_observability"

def update_sbce_dashboard():
    p = COMM_DIR / "avaya_sbce_operational_health.json"
    with open(p) as f:
        d = json.load(f)

    desc_map = {
        2: "Operational status of the SNMPv3 monitoring agent on the Avaya Session Border Controller Enterprise (SBCE 8.1). Value 1 indicates SNMP daemon is responding to polling requests; 0 indicates SNMP agent timeout or unreachable. Source: Zabbix SNMPv3 agent ping. Limitations: Verifies management plane reachability only; does not confirm media proxy or SIP signaling functionality.",
        3: "Elapsed time since last reboot of the Avaya SBCE operating system (CentOS-based SBC OS). Units: Seconds (formatted as days, hours, minutes). Source: HOST-RESOURCES-MIB::hrSystemUptime (OID .1.3.6.1.2.1.25.1.1.0). Limitations: A sudden drop to zero indicates an unplanned reboot or power disruption.",
        4: "Total processor utilization across all cores of the Avaya SBCE appliance. Units: Percentage (0–100%). Warning threshold: 75%, Critical: 90%. Source: HOST-RESOURCES-MIB::hrProcessorLoad (OID .1.3.6.1.2.1.25.3.3.1.2). Limitations: High CPU may cause delayed SIP transaction processing and audio transcoding artifacts.",
        5: "Percentage of physical memory currently consumed on the Avaya SBCE. Units: Percentage (0–100%). Source: HOST-RESOURCES-MIB memory allocation metrics. Warning: 80%, Critical: 95%. Limitations: Memory exhaustion can lead to Linux OOM killer terminating SIP signaling processes.",
        6: "Disk space consumption on the root (/) filesystem partition of the Avaya SBCE appliance. Units: Percentage (0–100%). Source: HOST-RESOURCES-MIB::hrStorageUsed (OID .1.3.6.1.2.1.25.2.3.1.6). Limitations: Log file accumulation (e.g., trace_sbc) can fill disk, leading to packet capture failure or service halt.",
        7: "One-minute system load average representing the number of runnable or waiting processes. Units: Scalar load average. Source: UCD-SNMP-MIB::laLoad.1 (OID .1.3.6.1.4.1.2021.10.1.3.1). Limitations: Sustained load higher than CPU core count indicates queue saturation and potential SIP packet drop.",
        9: "Link operational status of physical interface A1 connecting the Avaya SBCE to the external DMZ and telecom service provider SIP trunks (e.g., Safaricom). 1 = Up, 2 = Down. Source: IF-MIB::ifOperStatus.1. Limitations: Down status causes immediate loss of external inbound/outbound telephony.",
        10: "Link operational status of physical interface B1 connecting the Avaya SBCE to the internal core voice network (Avaya Aura Session Manager & Media Gateways). 1 = Up, 2 = Down. Source: IF-MIB::ifOperStatus.2. Limitations: Down status halts internal call routing between SBCE and Aura Core.",
        11: "Link operational status of interface M1 dedicated to out-of-band management and EMS web administration. 1 = Up, 2 = Down. Source: IF-MIB::ifOperStatus.3. Limitations: Interface failure prevents administrative access and EMS configuration synchronization but does not disrupt active call traffic.",
        12: "Link operational status of interface M2 used for High Availability (HA) clustering heartbeat and state synchronization between SBCE primary and standby appliances. 1 = Up, 2 = Down. Source: IF-MIB::ifOperStatus.4. Limitations: Loss of M2 heartbeat can trigger split-brain condition or disable automatic failover.",
        14: "Bidirectional network bandwidth utilization on external interface A1 carrying carrier SIP signaling (UDP/TCP/TLS 5060/5061) and RTP media streams. Units: Bits per second (bps) with delta rate calculation. Source: IF-MIB::ifHCInOctets / ifHCOutOctets. Limitations: Polled at 30s intervals; short microbursts below polling window are smoothed.",
        15: "Bidirectional network throughput on internal interface B1 carrying media streams between SBCE and Avaya Media Servers/Gateways. Units: Bits per second (bps). Source: IF-MIB::ifHCInOctets / ifHCOutOctets. Limitations: Bandwidth spikes correlate with concurrent active RTP call sessions.",
        17: "Rate of inbound and outbound frame/packet errors detected on voice-bearing interfaces (A1 and B1). Units: Errors per second. Source: IF-MIB::ifInErrors / ifOutErrors. Limitations: Any non-zero error rate directly degrades voice audio quality, causing robotic voice, clipping, and clicks.",
        18: "Rate of dropped inbound and outbound packets due to buffer overrun or NIC queue saturation on voice interfaces A1 and B1. Units: Packets per second (pps). Source: IF-MIB::ifInDiscards / ifOutDiscards. Limitations: Non-zero discards indicate interface or switch buffer congestion requiring QoS review.",
        19: "Live real-time alarm stream of active operational problems and threshold violations originating from Avaya SBCE hosts in Zabbix. Source: Zabbix Problems API filtered for Avaya SBCE host group. Limitations: Reflected alarms depend on Zabbix trigger definitions and polling intervals."
    }

    for pan in d.get("panels", []):
        pid = pan.get("id")
        if pid in desc_map:
            pan["description"] = desc_map[pid]
            # Ensure null points are not treated as zero
            if "fieldConfig" in pan and "defaults" in pan["fieldConfig"]:
                custom = pan["fieldConfig"]["defaults"].setdefault("custom", {})
                custom["spanNulls"] = False

    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    print("Updated avaya_sbce_operational_health.json")


def update_interface_traffic_dashboard():
    p = NET_DIR / "interface_traffic_health.json"
    with open(p) as f:
        d = json.load(f)

    desc_map = {
        2: "Current operational state of the selected network interface. Values: Up (1) or Down (2). Source: IF-MIB::ifOperStatus (OID .1.3.6.1.2.1.2.2.1.8). Limitations: Reflects physical layer link status and data-link state; does not verify IP routing or application-layer reachability.",
        3: "Negotiated or statically configured transmission speed of the network interface. Units: Bits per second (bps, formatted as Mbps/Gbps). Source: IF-MIB::ifHighSpeed (OID .1.3.6.1.2.1.31.1.1.1.15). Limitations: Speed duplex mismatch can lead to massive packet loss and throughput collapse.",
        4: "Desired administrative configuration state of the interface set by network administrators. Values: Up (1), Down (2), Testing (3). Source: IF-MIB::ifAdminStatus (OID .1.3.6.1.2.1.2.2.1.7). Limitations: If Admin State is Down, the port was intentionally shut down by policy.",
        6: "Real-time inbound (RX) and outbound (TX) traffic throughput on the selected network interface. Units: Bits per second (bps) calculated from 64-bit high-capacity octet counters. Source: IF-MIB::ifHCInOctets / ifHCOutOctets. Limitations: Polling interval is 30 seconds; sub-second bursts are averaged across the polling window.",
        8: "Rate of corrupt, malformed, or CRC-failing packets received or transmitted on the interface. Units: Errors per second. Source: IF-MIB::ifInErrors / ifOutErrors. Limitations: Non-zero error rates indicate physical cable degradation, transceiver fault, or electromagnetic interference.",
        9: "Rate of valid inbound and outbound packets dropped due to internal queue or buffer exhaustion. Units: Packets per second (pps). Source: IF-MIB::ifInDiscards / ifOutDiscards. Limitations: Indicates egress queue congestion or policing drops; warrants investigation into QoS queue configuration."
    }

    for pan in d.get("panels", []):
        pid = pan.get("id")
        if pid in desc_map:
            pan["description"] = desc_map[pid]
            if "fieldConfig" in pan and "defaults" in pan["fieldConfig"]:
                custom = pan["fieldConfig"]["defaults"].setdefault("custom", {})
                custom["spanNulls"] = False

    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    print("Updated interface_traffic_health.json")


def update_network_infrastructure_dashboard():
    p = NET_DIR / "network_infrastructure_overview.json"
    with open(p) as f:
        d = json.load(f)

    desc_map = {
        2: "SNMP reachability status of Kenya Airways core distribution and datacenter switches. Values: 1 = Available/Responding, 0 = Timeout/Unreachable. Source: Zabbix zabbix[host,snmp,available] internal metric. Limitations: Verifies UDP/161 polling response; does not measure packet forwarding throughput.",
        3: "Continuous operating time since the switch was last reloaded or rebooted. Units: Seconds (formatted as Days, Hours, Minutes). Source: SNMPv2-MIB::sysUpTime (OID .1.3.6.1.2.1.1.3.0). Limitations: Uptime resets during firmware upgrades, power cycles, or kernel crash reboots.",
        4: "Round-trip ping response time between the Nawari monitoring collector and the core switch management interface. Units: Milliseconds (ms). Source: Zabbix icmppingsec metric. Warning: > 10ms, Critical: > 50ms. Limitations: Control plane ICMP response is low priority and may spike during high control plane CPU without impacting forwarding plane traffic.",
        5: "Total count of unresolved active alerts and threshold breaches currently open against core network infrastructure in Zabbix. Source: Zabbix Problems API filtered for Network Infrastructure host group. Limitations: Count reflects unacknowledged and acknowledged active problem events.",
        7: "Inventory table of all discovered physical Ethernet, port-channel, and VLAN interfaces on the core switch, detailing operational status, speed, and traffic statistics. Source: Zabbix Low-Level Discovery (LLD) on IF-MIB. Limitations: Updated every 1 hour by discovery rule.",
        9: "Live streaming feed of unresolved network problem events ordered by severity (Information, Warning, Average, High, Disaster). Source: Zabbix Problems integration. Limitations: Real-time event feed depends on active WebSocket/polling connection to Zabbix API."
    }

    for pan in d.get("panels", []):
        pid = pan.get("id")
        if pid in desc_map:
            pan["description"] = desc_map[pid]
            if "fieldConfig" in pan and "defaults" in pan["fieldConfig"]:
                custom = pan["fieldConfig"]["defaults"].setdefault("custom", {})
                custom["spanNulls"] = False

    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    print("Updated network_infrastructure_overview.json")


def update_voice_service_assurance_dashboard():
    p = COMM_DIR / "nawari-voice-service-assurance.json"
    with open(p) as f:
        d = json.load(f)

    title_map = {
        3: "Estimated MOS (ITU-T G.107) [SYNTHETIC — ASTERISK]",
        6: "R-Factor (Transmission Quality) [SYNTHETIC — ASTERISK]",
        11: "Estimated MOS Trend & SLA Thresholds [SYNTHETIC — ASTERISK]",
        12: "RTP Jitter & Packet Loss Impairments [SYNTHETIC — ASTERISK]",
        14: "SBCE Signaling (A1) & Media (B1) Traffic Throughput [REAL — SBCE SNMP]",
        15: "SBCE CPU Utilization [REAL — SBCE SNMP]"
    }

    desc_map = {
        2: "Signaling outcome of the most recent synthetic voice test call (e.g., Completed 200 OK, Busy 486, Timeout 408, Service Unavailable 503). Source: Synthetic Asterisk probe AMI event logs. Limitations: Reflects synthetic probe calls between test extensions; does not evaluate live customer or agent calls.",
        3: "Estimated Mean Opinion Score (MOS) calculated strictly for synthetic test calls via ITU-T G.107 E-model based on measured packet loss, jitter, and delay. Scale: 1.0 (unusable) to 4.5 (toll quality). Warning: < 3.6, Critical: < 3.1. Source: Synthetic Asterisk voice probe. Limitations: Synthetic probe only; real subscriber calls are NOT included.",
        4: "Designates the media routing path of the tested voice session (e.g., Inbound Carrier DMZ, Outbound PSTN, Internal Inter-Station). Source: Synthetic probe call profile configuration. Limitations: Validates designated routing profile under test.",
        5: "Elapsed duration from initial SIP INVITE transmission to receiving the first 18x progress response (Post-Dial Delay / PDD). Units: Milliseconds (ms). Warning: > 1500ms, Critical: > 3000ms. Source: Synthetic Asterisk probe SIP signaling timer. Limitations: Measures synthetic signaling latency across SBCE.",
        6: "Transmission rating factor (R) calculated via ITU-T G.107 E-model for synthetic test calls. Scale: 0 to 100 (R >= 80 indicates toll quality, R < 60 is unacceptable). Source: Synthetic Asterisk probe RTCP calculation. Limitations: Strictly synthetic test call calculation.",
        16: "Explicit operational indicator distinguishing between SIMULATED/MOCK synthetic test environments and physical production infrastructure. Values: MOCK_SIMULATED (Blue) or PHYSICAL_PRODUCTION (Purple). Source: Voice probe environment provenance metric. Purpose: Guarantees full operator awareness of telemetry origin.",
        8: "Historical time-series trend of Post-Dial Delay (PDD) and session setup duration across consecutive synthetic voice probe runs. Units: Milliseconds (ms). Source: Synthetic Asterisk probe logs. Limitations: Useful for identifying carrier signaling latency drift over diurnal cycles.",
        9: "Distribution of SIP response codes (1xx progress, 2xx success, 4xx client errors, 5xx server failures) returned during synthetic probe campaigns. Source: Synthetic Asterisk SIP transaction logs. Limitations: Differentiates client busy/offline states from carrier 503 outages.",
        11: "Continuous time-series trend of estimated Mean Opinion Score (MOS) from synthetic voice probes plotted against SLA contractual limits (Toll Quality = 4.0, Minimum Acceptable = 3.6). Source: Synthetic Asterisk probe ITU-T G.107 calculation. Limitations: Measures synthetic probe stream quality only.",
        12: "Measured RTP packet loss percentage and jitter (ms) recorded during synthetic probe voice calls. Source: Asterisk RTCP reports. Target: Packet loss < 1%, Jitter < 20ms. Limitations: Reflects acoustic path between synthetic probe endpoints.",
        14: "Real-time physical interface throughput on Avaya SBCE interface A1 (External DMZ carrier signaling) and B1 (Internal Core media). Units: Bits per second (bps). Source: Avaya SBCE IF-MIB via Zabbix SNMPv3. Note: This panel displays REAL infrastructure traffic, distinct from synthetic probe metrics.",
        15: "Processor core utilization on the Avaya SBCE appliance. Units: Percentage (0–100%). Source: HOST-RESOURCES-MIB via Zabbix. Note: Real appliance hardware telemetry."
    }

    for pan in d.get("panels", []):
        pid = pan.get("id")
        if pid in title_map:
            pan["title"] = title_map[pid]
        if pid in desc_map:
            pan["description"] = desc_map[pid]
            if "fieldConfig" in pan and "defaults" in pan["fieldConfig"]:
                custom = pan["fieldConfig"]["defaults"].setdefault("custom", {})
                custom["spanNulls"] = False

    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    print("Updated nawari-voice-service-assurance.json")


def update_voice_intelligence_dashboard():
    p = COMM_DIR / "nawari_voice_intelligence.json"
    with open(p) as f:
        d = json.load(f)

    # Build updated panel list
    # Original panels:
    # 1: row - SIP Signaling Performance
    # 2: timeseries - Signaling Phase Latencies
    # 3: piechart - SIP Response Distribution
    # 4: row - RTP & RTCP-XR Media Quality
    # 5: timeseries - Network Packet Loss vs Jitter Buffer Discards
    # 6: timeseries - Mouth-to-Ear Voice Latency (RTT)
    # 7: row - Carrier Trunk Health & Route Selection
    # 8: gauge - SBCE Active Concurrent Sessions
    # 9: stat - Voice Quality Index (Estimated MOS)
    # 10: table - Recent Correlated Voice Call Sessions

    # Updated structure:
    # Panel 2: Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE]
    # Panel 3: SIP Response Distribution (Station vs Trunk) [SYNTHETIC — ASTERISK PROBE]
    # Panel 11 (new): SIP Trunk Registration Status [REAL — ZABBIX]
    # Panel 14 (new): Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]
    # Panel 9: Synthetic Voice Quality Index (MOS) [SYNTHETIC — ASTERISK]
    # Panel 12 (new): Real-Call Packet Loss (CM SNMP) [REAL — AVAYA SNMP]
    # Panel 13 (new): Real-Call Peak Jitter & Delay [REAL — AVAYA SNMP]
    # Panel 5: Network Packet Loss vs Jitter Buffer Discards [SYNTHETIC — ASTERISK]
    # Panel 6: Mouth-to-Ear Voice Latency (RTT) [SYNTHETIC — ASTERISK]
    # Panel 8: SBCE Active Concurrent Sessions (Max 500) [REAL — SBCE SNMP]
    # Panel 10: Recent Correlated Voice Call Sessions [CORRELATED PROBES]

    new_panels = []

    # Row 1: SIP Signaling Performance & Carrier Reachability
    row1 = {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
        "id": 1,
        "title": "SIP Signaling Reachability & Transaction Latency Breakdown",
        "type": "row"
    }
    new_panels.append(row1)

    # Panel 2: Signaling Phase Latencies
    p2 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Post-Dial Delay (PDD: INVITE to 18x), Time to Alerting (TTA: INVITE to 180 Ringing), and Time to Answer (TTOA: 180 to 200 OK) measured in milliseconds from synthetic Asterisk test calls. Source: Asterisk AMI synthetic call engine via Zabbix. Limitations: Reflects synthetic probe transactions only; does not represent live customer or agent calls.",
        "fieldConfig": {
            "defaults": {
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                "unit": "ms"
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 10, "x": 0, "y": 1},
        "id": 2,
        "options": {"tooltip": {"mode": "multi"}},
        "targets": [
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Post-Dial Delay (PDD)"}, "refId": "PDD"},
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Time to Alerting (TTA)"}, "refId": "TTA"},
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Call Setup Duration"}, "refId": "SETUP"}
        ],
        "title": "Signaling Phase Latencies (PDD vs TTA vs Setup) [SYNTHETIC — ASTERISK PROBE]",
        "type": "timeseries"
    }
    new_panels.append(p2)

    # Panel 3: SIP Response Distribution
    p3 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Categorization of SIP response events from synthetic test calls: differentiates normal station states (480 offline, 486 busy, 487 probe teardown) from true trunk/infrastructure failures (500, 502, 503, 504). Source: Synthetic Asterisk probe logs. Limitations: Synthetic probe calls only.",
        "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
        "gridPos": {"h": 8, "w": 8, "x": 10, "y": 1},
        "id": 3,
        "options": {"legend": {"displayMode": "table", "placement": "right"}, "pieType": "pie"},
        "targets": [
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "SIP Responses by Category"}, "refId": "SIP_CODES"}
        ],
        "title": "SIP Response Distribution (Station vs Trunk) [SYNTHETIC — ASTERISK PROBE]",
        "type": "piechart"
    }
    new_panels.append(p3)

    # Panel 11: SIP Trunk Registration Status [REAL — ZABBIX]
    p11 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Real-time SIP trunk registration state and signaling reachability for Avaya SBCE / Session Manager carrier interconnects (e.g., Safaricom, Airtel SIP trunks). Source: Zabbix SNMP/SIP OPTIONS monitor on Avaya SBCE. Important: Proves layer-5 SIP signaling reachability only; does NOT guarantee voice audio media quality or absence of RTP packet loss.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [
                    {"type": "value", "options": {"1": {"color": "green", "text": "REGISTERED (SIP UP)"}, "0": {"color": "red", "text": "UNREGISTERED (DOWN)"}}}
                ],
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 1},
        "id": 11,
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
        "targets": [
            {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "/.*sbce.*/"}, "application": {"name": "SIP Trunks"}, "item": {"name": "Safaricom Primary SIP Trunk Operational Status"}, "refId": "TRUNK_STATUS"}
        ],
        "title": "SIP Trunk Registration Status [REAL — ZABBIX]",
        "type": "stat"
    }
    new_panels.append(p11)

    # Row 4: Voice Media Quality & Acoustic Telemetry (Real vs Synthetic Separation)
    row4 = {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 9},
        "id": 4,
        "title": "Voice Media Quality & Acoustic Telemetry (Real vs Synthetic Separation)",
        "type": "row"
    }
    new_panels.append(row4)

    # Panel 14: Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]
    p14 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Real-call Mean Opinion Score (MOS). Status: Not instrumented — no validated real-call MOS telemetry source is configured (RTCP-XR RFC 3611 Block 7 / E-Model calculation on actual media streams is required). Displayed value is null/uninstrumented; synthetic MOS must never be substituted for real customer calls.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "noValue": "Not Instrumented (RTCP-XR Required)",
                "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-blue", "value": None}]}
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 10},
        "id": 14,
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
        "targets": [
            {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "avaya-cm-01.nawari.local"}, "application": {"name": "Real Call Voice Telemetry"}, "item": {"name": "avCmRealCallEstimatedMos"}, "refId": "REAL_MOS"}
        ],
        "title": "Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]",
        "type": "stat"
    }
    new_panels.append(p14)

    # Panel 9: Synthetic Voice Quality Index (MOS) [SYNTHETIC — ASTERISK]
    p9 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Mean Opinion Score (MOS) estimated via ITU-T G.107 E-model strictly for synthetic test calls generated between Asterisk probes and test extensions. Source: Synthetic Asterisk probe RTCP telemetry via Zabbix. Caution: This metric reflects synthetic probe calls ONLY; it does NOT measure or represent real customer or staff calls.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "max": 4.5,
                "min": 1.0,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "yellow", "value": 3.6},
                        {"color": "green", "value": 4.0}
                    ]
                },
                "unit": "none"
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 10},
        "id": 9,
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto"
        },
        "targets": [
            {"application": {"name": "Synthetic Voice Probes"}, "group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "item": {"name": "Estimated Mean Opinion Score (MOS)"}, "refId": "MOS"}
        ],
        "title": "Synthetic Voice Quality Index (MOS) [SYNTHETIC — ASTERISK]",
        "type": "stat"
    }
    new_panels.append(p9)

    # Panel 12: Real-Call Packet Loss (CM SNMP) [REAL — AVAYA SNMP]
    p12 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Aggregated hourly packet loss percentage across real voice calls terminating on Avaya Communication Manager 8.1.0 media gateways. Source: Avaya CM MIB table avCmMeasIpVoStatSumDataLstHrTable (OID 1.3.6.1.4.1.6889.2.73.8.1.77). Interval: 1 hour (CM internal bucket calculation). Freshness: 1–2 hours. Limitations: Hourly aggregated snapshot; does not provide per-call real-time streaming telemetry.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                "unit": "percent",
                "min": 0
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 10},
        "id": 12,
        "options": {"tooltip": {"mode": "multi"}},
        "targets": [
            {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "avaya-cm-01.nawari.local"}, "application": {"name": "Avaya CM IP Voice Hourly Stats"}, "item": {"name": "avCmMeasIpVoStatSumDataLstHrPktLoss"}, "refId": "CM_LOSS"}
        ],
        "title": "Real-Call Packet Loss (CM SNMP) [REAL — AVAYA SNMP]",
        "type": "timeseries"
    }
    new_panels.append(p12)

    # Panel 13: Real-Call Peak Jitter & Delay [REAL — AVAYA SNMP]
    p13 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Peak network jitter (ms) and peak one-way delay (ms) recorded across real voice sessions in Avaya Communication Manager. Source: Avaya CM MIB table avCmMeasIpVoStatSumDataLstHrTable (OID 1.3.6.1.4.1.6889.2.73.8.1.77) and avCmMeasIpVoStatHrJitterTable (OID 1.3.6.1.4.1.6889.2.73.8.1.66). Interval: 1 hour. Limitations: Reflects historical peak values during the preceding hour interval; not instantaneous jitter.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                "unit": "ms",
                "min": 0
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 10},
        "id": 13,
        "options": {"tooltip": {"mode": "multi"}},
        "targets": [
            {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "avaya-cm-01.nawari.local"}, "application": {"name": "Avaya CM IP Voice Hourly Stats"}, "item": {"name": "avCmMeasIpVoStatSumDataLstHrPkJitter"}, "refId": "CM_JITTER"},
            {"group": {"name": "Avaya Infrastructure"}, "host": {"name": "avaya-cm-01.nawari.local"}, "application": {"name": "Avaya CM IP Voice Hourly Stats"}, "item": {"name": "avCmMeasIpVoStatSumDataLstHrPkDelay"}, "refId": "CM_DELAY"}
        ],
        "title": "Real-Call Peak Jitter & Delay [REAL — AVAYA SNMP]",
        "type": "timeseries"
    }
    new_panels.append(p13)

    # Row 15: Synthetic Audio Stream Impairments & Acoustic Analysis
    row15 = {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 18},
        "id": 15,
        "title": "Synthetic Audio Stream Impairments & Acoustic Analysis",
        "type": "row"
    }
    new_panels.append(row15)

    # Panel 5: Network Packet Loss vs Jitter Buffer Discards [SYNTHETIC — ASTERISK]
    p5 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Synthetic voice call media impairment breakdown: network packet drop rate vs jitter buffer discard rate. Source: Synthetic Asterisk RTCP reports via Zabbix. Limitations: Reflects synthetic probe calls between test extensions.",
        "fieldConfig": {
            "defaults": {
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                "unit": "percent"
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 19},
        "id": 5,
        "options": {"tooltip": {"mode": "multi"}},
        "targets": [
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Network Packet Loss (%)"}, "refId": "NET_LOSS"},
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Jitter Buffer Discard Rate (%)"}, "refId": "JB_DISCARDS"}
        ],
        "title": "Network Packet Loss vs Jitter Buffer Discards [SYNTHETIC — ASTERISK]",
        "type": "timeseries"
    }
    new_panels.append(p5)

    # Panel 6: Mouth-to-Ear Voice Latency (RTT) [SYNTHETIC — ASTERISK]
    p6 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Synthetic round-trip mouth-to-ear voice latency (ITU-T G.114 target: <= 150ms). Source: Synthetic Asterisk probe RTP timestamps via Zabbix. Limitations: Synthetic probe path latency.",
        "fieldConfig": {
            "defaults": {
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "spanNulls": False},
                "unit": "ms"
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 19},
        "id": 6,
        "options": {"tooltip": {"mode": "multi"}},
        "targets": [
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Synthetic Voice Probes"}, "item": {"name": "Mouth-to-Ear Latency (RTT)"}, "refId": "RTT"}
        ],
        "title": "Mouth-to-Ear Voice Latency (RTT) [SYNTHETIC — ASTERISK]",
        "type": "timeseries"
    }
    new_panels.append(p6)

    # Row 7: Carrier Trunk Health & Route Selection
    row7 = {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 27},
        "id": 7,
        "title": "Carrier Trunk Capacity & Cross-Domain Correlated Probes",
        "type": "row"
    }
    new_panels.append(row7)

    # Panel 8: SBCE Active Concurrent Sessions (Max 500) [REAL — SBCE SNMP]
    p8 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Active concurrent call sessions and licensed capacity utilization on Avaya SBCE 8.1. Source: Avaya SBCE SNMP agent via Zabbix. Warning: > 400 sessions (80%), Critical: > 450 sessions (90%). Real hardware telemetry.",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "max": 500,
                "min": 0,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "yellow", "value": 400},
                        {"color": "red", "value": 450}
                    ]
                },
                "unit": "short"
            },
            "overrides": []
        },
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 28},
        "id": 8,
        "options": {"orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "showThresholdLabels": False, "showThresholdMarkers": True},
        "targets": [
            {"application": {"name": "Avaya SBCE Status"}, "group": {"name": "Voice Infrastructure"}, "host": {"name": "nawari-sbce-01"}, "item": {"name": "Active Audio Sessions"}, "refId": "SESSIONS"}
        ],
        "title": "SBCE Active Concurrent Sessions (Max 500) [REAL — SBCE SNMP]",
        "type": "gauge"
    }
    new_panels.append(p8)

    # Panel 10: Recent Correlated Voice Call Sessions [CORRELATED PROBES]
    p10 = {
        "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
        "description": "Recent correlated voice calls with signaling outcome, Q.850 cause code, and topology verification status. Source: Nawari Voice Intelligence Engine.",
        "fieldConfig": {"defaults": {}, "overrides": []},
        "gridPos": {"h": 8, "w": 16, "x": 8, "y": 28},
        "id": 10,
        "options": {"showHeader": True},
        "targets": [
            {"group": {"name": "Voice Infrastructure"}, "host": {"name": "/.*/"}, "application": {"name": "Correlated Calls"}, "item": {"name": "Recent Correlated Calls Stream"}, "refId": "CALLS"}
        ],
        "title": "Recent Correlated Voice Call Sessions [CORRELATED PROBES]",
        "type": "table"
    }
    new_panels.append(p10)

    d["panels"] = new_panels

    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    print("Updated nawari_voice_intelligence.json with real vs synthetic separation and CM SNMP panels.")

if __name__ == "__main__":
    update_sbce_dashboard()
    update_interface_traffic_dashboard()
    update_network_infrastructure_dashboard()
    update_voice_service_assurance_dashboard()
    update_voice_intelligence_dashboard()
