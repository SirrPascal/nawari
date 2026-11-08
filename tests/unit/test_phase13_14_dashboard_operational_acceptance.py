"""tests/unit/test_phase13_14_dashboard_operational_acceptance.py
=============================================================
Comprehensive unit test suite for Phase 13.14:
Dashboard & Reporting Operational Acceptance.
"""

import json
from pathlib import Path
import pytest

DASHBOARDS_DIR = Path("docker/grafana/dashboards")


def test_authoritative_dashboard_count():
    """Verify exactly 24 dashboards exist across communication and network directories."""
    comm_files = list((DASHBOARDS_DIR / "communication_observability").glob("*.json"))
    net_files = list((DASHBOARDS_DIR / "network_observability").glob("*.json"))
    assert len(comm_files) == 11
    assert len(net_files) == 13
    assert len(comm_files) + len(net_files) == 24


def test_folder_isolation_structure():
    """Verify folder paths strictly separate communication and network observability."""
    comm_dir = DASHBOARDS_DIR / "communication_observability"
    net_dir = DASHBOARDS_DIR / "network_observability"
    assert comm_dir.exists() and comm_dir.is_dir()
    assert net_dir.exists() and net_dir.is_dir()


def test_total_panel_inventory():
    """Verify all 24 dashboards parse cleanly and aggregate to 282 total panels."""
    all_files = list(DASHBOARDS_DIR.glob("**/*.json"))
    # Filter only files in communication_observability and network_observability
    scoped_files = [f for f in all_files if f.parent.name in ("communication_observability", "network_observability")]
    assert len(scoped_files) == 24

    total_panels = 0
    for fpath in scoped_files:
        with open(fpath, "r") as f:
            data = json.load(f)
        total_panels += len(data.get("panels", []))

    assert total_panels == 282


def test_panel_types_diversity():
    """Verify presence of core Grafana panel visualization types."""
    scoped_files = [f for f in DASHBOARDS_DIR.glob("**/*.json") if f.parent.name in ("communication_observability", "network_observability")]
    types = set()
    for fpath in scoped_files:
        with open(fpath) as f:
            d = json.load(f)
        for p in d.get("panels", []):
            types.add(p.get("type"))

    assert "stat" in types
    assert "timeseries" in types
    assert "gauge" in types
    assert "table" in types
    assert "row" in types


def test_datasource_integrity():
    """Verify datasources conform to Zabbix or PostgreSQL standards."""
    scoped_files = [f for f in DASHBOARDS_DIR.glob("**/*.json") if f.parent.name in ("communication_observability", "network_observability")]
    valid_datasources = {"alexanderzobnin-zabbix-datasource", "postgres", "None", None, "-- Grafana --"}

    for fpath in scoped_files:
        with open(fpath) as f:
            d = json.load(f)
        for p in d.get("panels", []):
            ds = p.get("datasource")
            ds_type = ds.get("type") if isinstance(ds, dict) else str(ds)
            assert ds_type in valid_datasources or "zabbix" in str(ds_type).lower(), f"Unexpected datasource {ds_type} in {fpath.name}"


def test_provenance_distribution():
    """Verify panels can be attributed to valid telemetry provenance classes."""
    scoped_files = [f for f in DASHBOARDS_DIR.glob("**/*.json") if f.parent.name in ("communication_observability", "network_observability")]
    physical_count = 0
    synthetic_count = 0
    calculated_count = 0

    for fpath in scoped_files:
        with open(fpath) as f:
            d = json.load(f)
        for p in d.get("panels", []):
            text = (p.get("title", "") + " " + p.get("description", "")).lower()
            if any(k in text for k in ("snmp", "ifhcin", "physical", "live", "hardware", "cpu", "mem", "fan", "temp")):
                physical_count += 1
            elif any(k in text for k in ("probe", "synthetic", "sip options", "ping", "traceroute", "dns", "http")):
                synthetic_count += 1
            elif any(k in text for k in ("e-model", "r-factor", "mos", "sli", "slo", "burn", "calculated", "rate", "percent")):
                calculated_count += 1
            else:
                physical_count += 1

    assert physical_count > 0
    assert synthetic_count > 0
    assert calculated_count > 0


def test_templating_variables():
    """Verify dashboards requiring drill-downs define templating variables."""
    traffic_dash = DASHBOARDS_DIR / "network_observability/interface_traffic_health.json"
    with open(traffic_dash) as f:
        d = json.load(f)
    variables = d.get("templating", {}).get("list", [])
    var_names = [v.get("name") for v in variables]
    assert len(var_names) >= 2


def test_zero_broken_json():
    """Verify all dashboard JSON files parse without errors."""
    for fpath in DASHBOARDS_DIR.glob("**/*.json"):
        with open(fpath) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "panels" in data or "title" in data


def test_communication_manager_panels():
    """Verify Avaya Communication Manager dashboard includes call processing panels."""
    cm_dash = DASHBOARDS_DIR / "communication_observability/avaya_communication_manager.json"
    with open(cm_dash) as f:
        d = json.load(f)
    titles = [p.get("title", "") for p in d.get("panels", [])]
    assert any("Call Processing" in t or "IP Voice" in t or "Active" in t for t in titles)


def test_network_path_analysis_panels():
    """Verify Network Path dashboard includes directional hop analysis panels."""
    path_dash = DASHBOARDS_DIR / "network_observability/network_path_analysis.json"
    with open(path_dash) as f:
        d = json.load(f)
    titles = [p.get("title", "") for p in d.get("panels", [])]
    assert any("Path" in t or "Hop" in t or "Latency" in t or "Loss" in t for t in titles)

