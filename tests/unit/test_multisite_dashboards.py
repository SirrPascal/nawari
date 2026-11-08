"""tests/unit/test_multisite_dashboards.py
=======================================
Unit tests for Multi-Site Grafana Dashboards (Workstream 13F).
"""

import json
from pathlib import Path


def test_global_outstations_dashboard_structure():
    dash_path = Path("docker/grafana/dashboards/nawari_global_outstations.json")
    assert dash_path.exists()

    with open(dash_path, "r") as f:
        data = json.load(f)

    assert data["uid"] == "nawari-global-outstations"
    assert "Nawari — Global Outstation Network" in data["title"]
    assert "multisite" in data["tags"]
    assert "outstations" in data["tags"]

    panel_titles = [p.get("title", "") for p in data["panels"]]
    assert any("Global Outstation Fleet Topology" in t for t in panel_titles)
    assert any("Trans-WAN Voice Quality" in t for t in panel_titles)
    assert any("Edge Telemetry Store-and-Forward" in t for t in panel_titles)


def test_service_catalog_sla_dashboard_structure():
    dash_path = Path("docker/grafana/dashboards/nawari_service_catalog_sla.json")
    assert dash_path.exists()

    with open(dash_path, "r") as f:
        data = json.load(f)

    assert data["uid"] == "nawari-service-catalog-sla"
    assert "Aviation Business Service Catalogue" in data["title"]
    assert "services" in data["tags"]
    assert "sla" in data["tags"]

    panel_titles = [p.get("title", "") for p in data["panels"]]
    assert any("Mission-Critical Aviation Services" in t for t in panel_titles)
    assert any("Error Budget Consumption & Burn Rate" in t for t in panel_titles)
    assert any("Active Correlated Incidents" in t for t in panel_titles)


def test_enterprise_overview_dashboard_structure():
    dash_path = Path("docker/grafana/dashboards/nawari_enterprise_overview.json")
    assert dash_path.exists()

    with open(dash_path, "r") as f:
        data = json.load(f)

    assert data["uid"] == "nawari-enterprise-overview"
    assert "Enterprise Executive Overview" in data["title"]
    assert "enterprise" in data["tags"]

    panel_titles = [p.get("title", "") for p in data["panels"]]
    assert any("Global Station Availability" in t for t in panel_titles)
    assert any("Active P1 / P2 Incidents" in t for t in panel_titles)
    assert any("Regional Health Index" in t for t in panel_titles)


def test_incident_operations_dashboard_structure():
    dash_path = Path("docker/grafana/dashboards/nawari_incident_operations.json")
    assert dash_path.exists()

    with open(dash_path, "r") as f:
        data = json.load(f)

    assert data["uid"] == "nawari-incident-operations"
    assert "Incident Operations" in data["title"]
    assert "incidents" in data["tags"]

    panel_titles = [p.get("title", "") for p in data["panels"]]
    assert any("Incidents by Lifecycle State" in t for t in panel_titles)
    assert any("Max Unacknowledged Incident Age" in t for t in panel_titles)
    assert any("Active Recovery Verification Pipelines" in t for t in panel_titles)


def test_edge_fleet_dashboard_structure():
    dash_path = Path("docker/grafana/dashboards/nawari_edge_fleet.json")
    assert dash_path.exists()

    with open(dash_path, "r") as f:
        data = json.load(f)

    assert data["uid"] == "nawari-edge-fleet"
    assert "Distributed Edge Collector Fleet" in data["title"]
    assert "edge" in data["tags"]

    panel_titles = [p.get("title", "") for p in data["panels"]]
    assert any("Active Edge Collectors" in t for t in panel_titles)
    assert any("Max Outstation Clock Drift" in t for t in panel_titles)
    assert any("Fleet Total Spool Backlog" in t for t in panel_titles)
    assert any("Outstation Spool Storage & Replay Queue Matrix" in t for t in panel_titles)
