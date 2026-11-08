#!/usr/bin/env python3
"""
scripts/build_consolidated_dashboards.py

Builds the 9 consolidated operational dashboards by merging panel sets from the 25
audited dashboards into clean, structured, collapsible rows with progressive drill-down
navigation, variables, and cross-dashboard header links.
"""

import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS_DIR = ROOT / "docker/grafana/dashboards"
NET_DIR = DASHBOARDS_DIR / "network_observability"
COMM_DIR = DASHBOARDS_DIR / "communication_observability"
ENDPOINT_DIR = ROOT / "provisioning/endpoint/dashboards"
OUTPUT_DIR = ROOT / "provisioning/dashboards/consolidated"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Standard Navigation Header Links
NAV_LINKS = [
    {
        "asDropdown": False,
        "icon": "home",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Home (Exec)",
        "tooltip": "Enterprise Executive Overview",
        "type": "link",
        "url": "/d/nawari-enterprise-overview/0bff031"
    },
    {
        "asDropdown": False,
        "icon": "network",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Network Ops",
        "tooltip": "Network Operations Overview",
        "type": "link",
        "url": "/d/nawari-network-operations/network-operations"
    },
    {
        "asDropdown": False,
        "icon": "globe",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "WAN & Outstations",
        "tooltip": "WAN, Path & Outstation Observability",
        "type": "link",
        "url": "/d/nawari-wan-path-outstation/wan-path-outstation"
    },
    {
        "asDropdown": False,
        "icon": "laptop",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Endpoints & Users",
        "tooltip": "Endpoint & User Experience",
        "type": "link",
        "url": "/d/nawari-endpoint-experience/endpoint-experience"
    },
    {
        "asDropdown": False,
        "icon": "heartbeat",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Services & SLA",
        "tooltip": "Network Services & Incident Assurance",
        "type": "link",
        "url": "/d/nawari-network-services-assurance/network-services-assurance"
    },
    {
        "asDropdown": False,
        "icon": "phone",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Voice Overview",
        "tooltip": "Communication Services Overview",
        "type": "link",
        "url": "/d/nawari-comm-overview/e353360"
    },
    {
        "asDropdown": False,
        "icon": "server",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Avaya Infra",
        "tooltip": "Avaya Infrastructure & Signaling",
        "type": "link",
        "url": "/d/nawari-avaya-infrastructure/avaya-infrastructure"
    },
    {
        "asDropdown": False,
        "icon": "volume-up",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Voice Quality & CC",
        "tooltip": "Voice Quality & Contact Centre",
        "type": "link",
        "url": "/d/nawari-voice-contact-centre/voice-contact-centre"
    },
    {
        "asDropdown": False,
        "icon": "share-alt",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Cross-Domain",
        "tooltip": "Cross-Domain Correlation & Operations",
        "type": "link",
        "url": "/d/nawari-voice-correlation/2983cfd"
    },
    {
        "asDropdown": False,
        "icon": "folder",
        "includeVars": False,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": "Browse All",
        "tooltip": "Browse All Dashboards",
        "type": "link",
        "url": "/dashboards"
    }
]

def load_dashboard(path):
    with open(path) as f:
        return json.load(f)

def merge_dashboards(target_uid, target_title, sections_spec, target_tags=None, folder_uid="nawari-network-obs"):
    """
    sections_spec is a list of tuples: (source_path, section_title, collapse_row)
    """
    combined_panels = []
    combined_variables = {}
    current_panel_id = 1
    current_y = 0

    for src_path, section_title, collapse in sections_spec:
        src_data = load_dashboard(src_path)
        
        # Merge variables
        for v in src_data.get("templating", {}).get("list", []):
            if v["name"] not in combined_variables:
                combined_variables[v["name"]] = deepcopy(v)

        # Create row header for this section
        row_id = current_panel_id
        current_panel_id += 1
        row_panel = {
            "collapsed": collapse,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": current_y},
            "id": row_id,
            "panels": [],
            "title": section_title,
            "type": "row"
        }
        current_y += 1

        # Extract visualization panels from source
        src_panels = src_data.get("panels", [])
        viz_panels = []
        for p in src_panels:
            if p.get("type") == "row":
                # if row contains nested panels in 'panels' key
                for sub_p in p.get("panels", []):
                    viz_panels.append(sub_p)
            else:
                viz_panels.append(p)

        # Position panels under this row
        row_children = []
        row_y = 0
        for p in viz_panels:
            p_copy = deepcopy(p)
            p_copy["id"] = current_panel_id
            current_panel_id += 1
            
            # Recalculate gridPos
            orig_h = p_copy.get("gridPos", {}).get("h", 8)
            orig_w = p_copy.get("gridPos", {}).get("w", 12)
            orig_x = p_copy.get("gridPos", {}).get("x", 0)
            
            if collapse:
                # In Grafana, collapsed row panels are stored in row.panels with relative y
                p_copy["gridPos"] = {"h": orig_h, "w": orig_w, "x": orig_x, "y": row_y}
                row_y += orig_h
                row_children.append(p_copy)
            else:
                p_copy["gridPos"] = {"h": orig_h, "w": orig_w, "x": orig_x, "y": current_y}
                current_y += orig_h
                combined_panels.append(p_copy)

        if collapse:
            row_panel["panels"] = row_children
            combined_panels.append(row_panel)
        else:
            combined_panels.insert(len(combined_panels) - len(viz_panels), row_panel)

    base_dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": NAV_LINKS,
        "liveNow": False,
        "panels": combined_panels,
        "refresh": "10s",
        "schemaVersion": 38,
        "style": "dark",
        "tags": target_tags or ["nawari", "consolidated"],
        "templating": {"list": list(combined_variables.values())},
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]},
        "timezone": "browser",
        "title": target_title,
        "uid": target_uid,
        "version": 1
    }
    return base_dashboard

def main():
    print("Building 9 Consolidated Dashboards...")

    # 1. Enterprise Executive Overview (Retained & Enhanced with Links)
    exec_data = load_dashboard(NET_DIR / "nawari_enterprise_overview.json")
    exec_data["links"] = NAV_LINKS
    exec_data["refresh"] = "10s"
    (OUTPUT_DIR / "01_enterprise_executive_overview.json").write_text(json.dumps(exec_data, indent=2))
    print("Built 01_enterprise_executive_overview.json")

    # 2. Network Operations Overview (Core Infra + Interface Health + Topology)
    net_ops = merge_dashboards(
        target_uid="nawari-network-operations",
        target_title="Nawari — Network Operations Overview",
        sections_spec=[
            (NET_DIR / "network_infrastructure_overview.json", "Core Infrastructure Devices & Appliance Resources", False),
            (NET_DIR / "interface_traffic_health.json", "Interface Bandwidth, Throughput, Discards & Errors", True),
            (NET_DIR / "network_topology.json", "Network Topology & Structural Dependency Layers", True)
        ],
        target_tags=["nawari", "network", "operations", "tier2"]
    )
    (OUTPUT_DIR / "02_network_operations_overview.json").write_text(json.dumps(net_ops, indent=2))
    print("Built 02_network_operations_overview.json")

    # 3. WAN, Path & Outstation Observability (Global Outstations + Path Analysis + Edge Fleet)
    wan_ops = merge_dashboards(
        target_uid="nawari-wan-path-outstation",
        target_title="Nawari — WAN, Path & Outstation Observability",
        sections_spec=[
            (NET_DIR / "nawari_global_outstations.json", "Global Outstation Connectivity & Regional Hub Telemetry", False),
            (NET_DIR / "network_path_analysis.json", "Hop-by-Hop Path Tracing & Directional Latency Analysis", True),
            (NET_DIR / "nawari_edge_fleet.json", "Distributed Edge Collector Fleet & SQLite Spool Storage", True)
        ],
        target_tags=["nawari", "network", "wan", "outstation", "tier3"]
    )
    (OUTPUT_DIR / "03_wan_path_outstation_observability.json").write_text(json.dumps(wan_ops, indent=2))
    print("Built 03_wan_path_outstation_observability.json")

    # 4. Endpoint & User Experience (Fleet Overview + Forensic Detail + Real-Time Active Probe Diagnostics)
    endp_ops = merge_dashboards(
        target_uid="nawari-endpoint-experience",
        target_title="Nawari — Endpoint & User Experience",
        sections_spec=[
            (NET_DIR / "endpoint_fleet_overview.json", "Endpoint Fleet Observability & Presence Distribution", False),
            (ENDPOINT_DIR / "end_user_network_experience.json", "Real-Time Active Probe Diagnostics (Pilot Fleet)", False),
            (NET_DIR / "endpoint_detail.json", "Forensic Single-Endpoint Investigation ($endpoint)", True)
        ],
        target_tags=["nawari", "network", "endpoint", "experience", "tier3"]
    )
    (OUTPUT_DIR / "04_endpoint_user_experience.json").write_text(json.dumps(endp_ops, indent=2))
    print("Built 04_endpoint_user_experience.json")

    # 5. Network Services & Incident Assurance (Service Catalog SLA + Incident Operations + Predictive + Controlled Ops)
    svc_ops = merge_dashboards(
        target_uid="nawari-network-services-assurance",
        target_title="Nawari — Network Services & Incident Assurance",
        sections_spec=[
            (NET_DIR / "nawari_service_catalog_sla.json", "Aviation Business Service Catalogue & Multi-Dimensional SLIs", False),
            (NET_DIR / "nawari_incident_operations.json", "Active Incidents, MTTR & Verified Recovery Lifecycle", False),
            (NET_DIR / "nawari_predictive_intelligence.json", "Predictive Intelligence, Dynamic Baselines & Degradation Assurance", True),
            (NET_DIR / "nawari_controlled_operations.json", "Controlled Operational Actions & Remediation Circuit Breakers", True)
        ],
        target_tags=["nawari", "network", "service-assurance", "incidents", "tier3"]
    )
    (OUTPUT_DIR / "05_network_services_incident_assurance.json").write_text(json.dumps(svc_ops, indent=2))
    print("Built 05_network_services_incident_assurance.json")

    # 6. Communication Services Overview (Retained & Enhanced with Links)
    comm_exec = load_dashboard(COMM_DIR / "nawari_communication_overview.json")
    comm_exec["links"] = NAV_LINKS
    comm_exec["refresh"] = "10s"
    (OUTPUT_DIR / "06_communication_services_overview.json").write_text(json.dumps(comm_exec, indent=2))
    print("Built 06_communication_services_overview.json")

    # 7. Avaya Infrastructure & Signaling (SBCE + Session Manager + Communication Manager + G450 + Carrier SIP Trunks)
    avaya_ops = merge_dashboards(
        target_uid="nawari-avaya-infrastructure",
        target_title="Nawari — Avaya Infrastructure & Signaling",
        sections_spec=[
            (COMM_DIR / "avaya_sbce_operational_health.json", "Session Border Controller (SBCE) Diagnostics & Perimeter Security", False),
            (COMM_DIR / "avaya_session_manager.json", "Avaya Aura Session Manager (ASM) & SIP Entity Routing", True),
            (COMM_DIR / "avaya_communication_manager.json", "Avaya Aura Communication Manager (CM) Call Processing & IP Telephony", True),
            (COMM_DIR / "avaya_g450_media_gateway.json", "Avaya G450 Media Gateway Appliance & Physical DSP Voice Channels", True),
            (COMM_DIR / "nawari_sip_trunks_signaling.json", "Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing", True)
        ],
        target_tags=["nawari", "communication", "avaya", "signaling", "tier3"]
    )
    (OUTPUT_DIR / "07_avaya_infrastructure_signaling.json").write_text(json.dumps(avaya_ops, indent=2))
    print("Built 07_avaya_infrastructure_signaling.json")

    # 8. Voice Quality & Contact Centre (Voice Intelligence + Voice Service Assurance + CMS + WFO Recording)
    voice_ops = merge_dashboards(
        target_uid="nawari-voice-contact-centre",
        target_title="Nawari — Voice Quality & Contact Centre",
        sections_spec=[
            (COMM_DIR / "nawari_voice_intelligence.json", "Voice Intelligence & Synthetic Probes (Asterisk PESQ / Real-Call Indicators)", False),
            (COMM_DIR / "nawari-voice-service-assurance.json", "Voice Media Quality, RTP Loss & Codec Distribution", True),
            (COMM_DIR / "avaya_cms_contact_centre.json", "Avaya Call Management System (CMS) & Contact Centre Performance", True),
            (COMM_DIR / "recording_wfo_operational_health.json", "Voice Recording & Workforce Optimisation (WFO) Compliance", True)
        ],
        target_tags=["nawari", "communication", "voice-quality", "contact-centre", "tier3"]
    )
    (OUTPUT_DIR / "08_voice_quality_contact_centre.json").write_text(json.dumps(voice_ops, indent=2))
    print("Built 08_voice_quality_contact_centre.json")

    # 9. Cross-Domain Correlation & Operations (Retained & Enhanced with Links)
    corr_data = load_dashboard(COMM_DIR / "endpoint_voice_correlation.json")
    corr_data["links"] = NAV_LINKS
    corr_data["refresh"] = "10s"
    (OUTPUT_DIR / "09_cross_domain_correlation_operations.json").write_text(json.dumps(corr_data, indent=2))
    print("Built 09_cross_domain_correlation_operations.json")

    print("\nAll 9 consolidated dashboards built successfully in docker/grafana/dashboards/consolidated/!")

if __name__ == "__main__":
    main()

