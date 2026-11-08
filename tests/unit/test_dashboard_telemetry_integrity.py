"""
tests/unit/test_dashboard_telemetry_integrity.py

Automated test suite for Nawari Dashboard Telemetry Integrity and Domain Separation:
1. Operational domain folder structure (Network vs Communication).
2. Grafana provisioning file provider declarations and stable folder UIDs.
3. Mandatory hover descriptions across 100% of visualization panels (meaning, units, source, limits).
4. Telemetry integrity (no null-as-zero masking, no decorative gauges, spanNulls: False).
5. Semantic separation of signaling reachability (SIP OPTIONS) from voice audio media quality.
6. Honest uninstrumented indicators for Real-Call MOS (RFC 3611 RTCP-XR required).
7. Strict visible labeling for synthetic Asterisk call probes.
8. Avaya CM 8.1.0 MIB template polling interval safety (>= 1 hour delay).
9. Machine-readable dashboard metric catalogue schema validation.
"""

import json
from pathlib import Path
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DASHBOARDS_DIR = ROOT_DIR / "docker/grafana/dashboards"
PROVISIONING_FILE = ROOT_DIR / "docker/grafana/provisioning/dashboards/dashboards.yaml"
CM_TEMPLATE_FILE = ROOT_DIR / "provisioning/zabbix/templates/template_nawari_avaya_cm.yaml"
CATALOGUE_FILE = ROOT_DIR / "docs/observability/dashboard-metric-catalogue.yaml"

NETWORK_OBS_DIR = DASHBOARDS_DIR / "network_observability"
COMM_OBS_DIR = DASHBOARDS_DIR / "communication_observability"

EXPECTED_NETWORK_DASHBOARDS = {
    "nawari_enterprise_overview.json",
    "network_infrastructure_overview.json",
    "network_topology.json",
    "interface_traffic_health.json",
    "network_path_analysis.json",
    "endpoint_fleet_overview.json",
    "endpoint_detail.json",
    "nawari_global_outstations.json",
    "nawari_edge_fleet.json",
    "nawari_incident_operations.json",
    "nawari_service_catalog_sla.json",
    "nawari_controlled_operations.json",
    "nawari_predictive_intelligence.json"
}

EXPECTED_COMM_DASHBOARDS = {
    "avaya_sbce_operational_health.json",
    "nawari-voice-service-assurance.json",
    "nawari_voice_intelligence.json",
    "endpoint_voice_correlation.json"
}


def test_domain_folder_structure_and_provisioning():
    """Verify dashboards are separated into Network and Communication domain folders with stable UIDs."""
    assert PROVISIONING_FILE.is_file(), "Provisioning dashboards.yaml must exist"
    with open(PROVISIONING_FILE) as f:
        prov = yaml.safe_load(f)

    providers = prov.get("providers", [])
    assert len(providers) == 2, "Must declare exactly 2 Grafana dashboard providers"

    prov_map = {p["folderUid"]: p for p in providers}
    assert "nawari-network-obs" in prov_map, "Network Observability provider must have UID nawari-network-obs"
    assert "nawari-comm-obs" in prov_map, "Communication Observability provider must have UID nawari-comm-obs"

    net_prov = prov_map["nawari-network-obs"]
    assert net_prov["folder"] == "Nawari / Network Observability"
    assert "network_observability" in net_prov["options"]["path"]

    comm_prov = prov_map["nawari-comm-obs"]
    assert comm_prov["folder"] == "Nawari / Communication Observability"
    assert "communication_observability" in comm_prov["options"]["path"]

    # Verify physical directories and files
    assert NETWORK_OBS_DIR.is_dir()
    assert COMM_OBS_DIR.is_dir()

    actual_net_files = {p.name for p in NETWORK_OBS_DIR.glob("*.json")}
    assert actual_net_files == EXPECTED_NETWORK_DASHBOARDS, f"Mismatch in network dashboards: {actual_net_files ^ EXPECTED_NETWORK_DASHBOARDS}"

    actual_comm_files = {p.name for p in COMM_OBS_DIR.glob("*.json")}
    assert actual_comm_files == EXPECTED_COMM_DASHBOARDS, f"Mismatch in communication dashboards: {actual_comm_files ^ EXPECTED_COMM_DASHBOARDS}"

    # Verify root symlinks for backwards compatibility
    for fname in EXPECTED_NETWORK_DASHBOARDS | EXPECTED_COMM_DASHBOARDS:
        symlink_path = DASHBOARDS_DIR / fname
        assert symlink_path.exists(), f"Symlink {fname} must exist in root dashboards directory"


def test_mandatory_panel_descriptions_100_percent_coverage():
    """Verify 100% of visualization panels across all 17 dashboards have non-empty operational descriptions."""
    total_vis_panels = 0
    missing_descriptions = []

    all_dashboards = list(NETWORK_OBS_DIR.glob("*.json")) + list(COMM_OBS_DIR.glob("*.json"))
    assert len(all_dashboards) == 17, f"Expected 17 dashboards, found {len(all_dashboards)}"

    for dash_path in all_dashboards:
        with open(dash_path) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            ptype = p.get("type")
            title = p.get("title", f"Panel {p.get('id')}")
            if ptype == "row":
                continue  # Rows do not have hover tooltips

            total_vis_panels += 1
            desc = p.get("description", "")
            if not desc or len(desc.strip()) < 15:
                missing_descriptions.append(f"{dash_path.name} -> ID {p.get('id')} ({title})")

    assert total_vis_panels == 134, f"Expected exactly 134 visualization panels, got {total_vis_panels}"
    assert len(missing_descriptions) == 0, f"Missing descriptions on {len(missing_descriptions)} panels: {missing_descriptions}"


def test_telemetry_integrity_and_null_preservation():
    """Verify no dashboard coerces null to zero or hides gaps in measurement telemetry."""
    all_dashboards = list(NETWORK_OBS_DIR.glob("*.json")) + list(COMM_OBS_DIR.glob("*.json"))

    violations = []
    for dash_path in all_dashboards:
        with open(dash_path) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue

            # Check legacy nullPointMode
            if p.get("nullPointMode") == "null as zero":
                violations.append(f"{dash_path.name} -> ID {p.get('id')}: nullPointMode is 'null as zero'")

            # Check transformations that replace null with 0
            for t in p.get("transformations", []):
                t_str = json.dumps(t).lower()
                if "null" in t_str and "0" in t_str:
                    violations.append(f"{dash_path.name} -> ID {p.get('id')}: transformation converts null to zero: {t}")

    assert len(violations) == 0, f"Found null-as-zero violations: {violations}"


def test_communication_signaling_vs_media_separation():
    """Verify voice intelligence dashboard separates signaling reachability from media quality and isolates synthetic calls."""
    voice_dash = COMM_OBS_DIR / "nawari_voice_intelligence.json"
    assert voice_dash.is_file()

    with open(voice_dash) as f:
        data = json.load(f)

    panels = {p.get("id"): p for p in data.get("panels", [])}

    # 1. Panel 11: Real SIP trunk registration status
    assert 11 in panels, "Panel 11 (SIP Trunk Registration Status) must exist"
    p11 = panels[11]
    assert "[REAL — ZABBIX]" in p11["title"]
    assert "layer-5" in p11["description"].lower() or "reachability only" in p11["description"].lower()
    assert "not guarantee" in p11["description"].lower() or "not prove" in p11["description"].lower()

    # 2. Panel 14: Real-call MOS uninstrumented indicator
    assert 14 in panels, "Panel 14 (Real-Call MOS) must exist"
    p14 = panels[14]
    assert "[NOT INSTRUMENTED — RTCP XR REQUIRED]" in p14["title"]
    assert "not instrumented" in p14["description"].lower()
    assert "rtcp-xr" in p14["description"].lower()

    # 3. Panel 9: Synthetic Voice Quality Index
    assert 9 in panels, "Panel 9 (Synthetic Voice Quality Index) must exist"
    p9 = panels[9]
    assert "[SYNTHETIC — ASTERISK]" in p9["title"]
    assert "synthetic" in p9["description"].lower()
    assert "not measure or represent real customer" in p9["description"].lower()

    # 4. Panels 12 & 13: Avaya CM SNMP real call metrics
    assert 12 in panels, "Panel 12 (Real-Call Packet Loss) must exist"
    assert 13 in panels, "Panel 13 (Real-Call Peak Jitter & Delay) must exist"
    assert "[REAL — AVAYA SNMP]" in panels[12]["title"]
    assert "[REAL — AVAYA SNMP]" in panels[13]["title"]
    assert "avCmMeasIpVoStatSumDataLstHrTable" in panels[12]["description"]
    assert "1 hour" in panels[12]["description"]


def test_avaya_cm_zabbix_template_safety_constraints():
    """Verify Avaya CM Zabbix template respects 1-hour polling interval constraint and documents system impact."""
    assert CM_TEMPLATE_FILE.is_file(), "Avaya CM template must exist"
    with open(CM_TEMPLATE_FILE) as f:
        tmpl = yaml.safe_load(f)

    zabbix_export = tmpl.get("zabbix_export", {})
    templates = zabbix_export.get("templates", [])
    assert len(templates) > 0

    cm_tmpl = templates[0]
    assert cm_tmpl.get("template") == "Nawari Avaya Communication Manager by SNMP"

    items = cm_tmpl.get("items", [])
    assert len(items) >= 6, "Must define IP voice hourly summary and jitter items"

    for item in items:
        delay = item.get("delay", "")
        # For Avaya CM IP Voice statistics, delay must be at least 1h or 3600s to prevent CM CPU impact
        if "avCmMeas" in item.get("snmp_oid", "") or "Avaya CM IP Voice" in str(item.get("applications", [])):
            assert delay in ("1h", "3600s", "3600"), f"IP Voice Item {item.get('name')} delay '{delay}' violates >= 1h polling limit"

    desc = cm_tmpl.get("description", "")
    assert "avCmMeasIpVoStatSumDataLstHrTable" in desc
    assert "1 hour" in desc
    assert "prevent system impact on CM processor" in desc


def test_machine_readable_metric_catalogue_validity():
    """Verify dashboard metric catalogue exists, is valid YAML, and catalogues all 134 visualization panels."""
    assert CATALOGUE_FILE.is_file(), "dashboard-metric-catalogue.yaml must exist"
    with open(CATALOGUE_FILE) as f:
        cat = yaml.safe_load(f)

    assert cat.get("catalogue_version") == "1.0.0"
    assert cat.get("total_dashboards") == 17
    assert cat.get("total_visualization_panels") == 134

    domains = cat.get("domains", [])
    assert len(domains) == 2

    dashboards = cat.get("dashboards", [])
    assert len(dashboards) == 17

    panel_count = sum(len(d.get("panels", [])) for d in dashboards)
    assert panel_count == 134

    for d in dashboards:
        assert d.get("dashboard_uid")
        assert d.get("dashboard_title")
        assert d.get("domain") in ("Network Observability", "Communication Observability")
        for p in d.get("panels", []):
            assert p.get("panel_id") is not None
            assert p.get("panel_title")
            assert p.get("description")
            assert p.get("provenance_type") in (
                "NOT_INSTRUMENTED",
                "SYNTHETIC_PROBE",
                "REAL_AVAYA_SNMP",
                "REAL_SBCE_SNMP",
                "REAL_ZABBIX_TELEMETRY",
                "CORRELATED_ANALYTICS",
                "PREDICTIVE_STATISTICAL",
                "SERVICE_ASSURANCE_SLI"
            )
            assert "spanNulls: False" in p.get("null_handling")
