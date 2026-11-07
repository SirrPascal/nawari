"""Integration test suite for Stage 7E: Grafana Endpoint and Network Experience Dashboards."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import urllib.request
import pytest

DASHBOARDS_DIR = Path(__file__).resolve().parent.parent.parent / "docker" / "grafana" / "dashboards"

EXPECTED_DASHBOARDS = [
    {
        "filename": "endpoint_fleet_overview.json",
        "uid": "nawari-endpoint-fleet",
        "title": "Nawari — Endpoint Fleet Observability Overview",
        "min_panels": 10,
        "required_tags": ["nawari", "endpoint", "fleet"],
    },
    {
        "filename": "endpoint_detail.json",
        "uid": "nawari-endpoint-detail",
        "title": "Nawari — Endpoint Deep-Dive & Edge Experience",
        "min_panels": 12,
        "required_tags": ["nawari", "endpoint", "detail"],
    },
    {
        "filename": "network_path_analysis.json",
        "uid": "nawari-path-analysis",
        "title": "Nawari — Network Path & Directional Hop Analysis",
        "min_panels": 8,
        "required_tags": ["nawari", "network", "path"],
    },
    {
        "filename": "endpoint_voice_correlation.json",
        "uid": "nawari-voice-correlation",
        "title": "Nawari — Cross-Domain Voice & Endpoint Telemetry Correlation",
        "min_panels": 8,
        "required_tags": ["nawari", "voice", "endpoint", "correlation"],
    },
]


@pytest.fixture
def grafana_auth():
    user = "admin"
    password = "nawari_grafana_dev_pass"
    return f"Basic {base64.b64encode(f'{user}:{password}'.encode()).decode()}"


def test_01_dashboard_json_files_exist_and_valid():
    """Verify that all four Stage 7E dashboard files exist and are valid JSON."""
    assert DASHBOARDS_DIR.exists(), f"Dashboards directory does not exist: {DASHBOARDS_DIR}"

    for spec in EXPECTED_DASHBOARDS:
        path = DASHBOARDS_DIR / spec["filename"]
        assert path.exists(), f"Missing dashboard file: {spec['filename']}"

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data.get("uid") == spec["uid"], f"UID mismatch in {spec['filename']}"
        assert data.get("title") == spec["title"], f"Title mismatch in {spec['filename']}"
        assert data.get("schemaVersion", 0) >= 39, f"schemaVersion too low in {spec['filename']}"
        assert len(data.get("panels", [])) >= spec["min_panels"], f"Insufficient panels in {spec['filename']}"

        tags = data.get("tags", [])
        for req_tag in spec["required_tags"]:
            assert req_tag in tags, f"Missing required tag '{req_tag}' in {spec['filename']}"


def test_02_dashboard_reliability_guards():
    """Verify that panels enforce 'STALE / NO DATA' and appropriate noValue guards."""
    for spec in EXPECTED_DASHBOARDS:
        path = DASHBOARDS_DIR / spec["filename"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        panels = data.get("panels", [])
        stat_or_ts_panels = [p for p in panels if p.get("type") in ("stat", "timeseries", "gauge")]
        assert len(stat_or_ts_panels) > 0, f"No stat/timeseries panels found in {spec['filename']}"

        guarded = 0
        for p in stat_or_ts_panels:
            fc = p.get("fieldConfig", {}).get("defaults", {})
            no_val = fc.get("noValue")
            if no_val in ("STALE / NO DATA", "UNKNOWN / NO DATA", "N/A (WIRED/VPN)", "0"):
                guarded += 1

        assert guarded >= len(stat_or_ts_panels) * 0.8, (
            f"Expected at least 80% of metrics panels in {spec['filename']} to have reliability noValue guards, got {guarded}/{len(stat_or_ts_panels)}"
        )


def test_03_copp_and_voice_boundary_notices():
    """Verify that domain boundary and CoPP guard callouts are present in their respective dashboards."""
    # CoPP Guard notice in network path analysis
    path_file = DASHBOARDS_DIR / "network_path_analysis.json"
    with open(path_file, "r", encoding="utf-8") as f:
        path_data = json.load(f)

    path_text_panels = [p for p in path_data.get("panels", []) if p.get("type") == "text"]
    assert any("Control Plane Policing" in p.get("options", {}).get("content", "") for p in path_text_panels), (
        "CoPP guard architectural explanation missing from network path analysis dashboard"
    )

    # Voice boundary notice in voice correlation
    voice_file = DASHBOARDS_DIR / "endpoint_voice_correlation.json"
    with open(voice_file, "r", encoding="utf-8") as f:
        voice_data = json.load(f)

    voice_text_panels = [p for p in voice_data.get("panels", []) if p.get("type") == "text"]
    assert any("Domain Boundary Notice" in p.get("options", {}).get("content", "") for p in voice_text_panels), (
        "Domain boundary notice distinguishing port 5061 reachability from media/SIP health missing from voice correlation dashboard"
    )


def test_04_live_grafana_provisioning(grafana_auth):
    """Verify that all four dashboards are provisioned and accessible via live Grafana HTTP API."""
    for spec in EXPECTED_DASHBOARDS:
        uid = spec["uid"]
        url = f"http://127.0.0.1:3001/api/dashboards/uid/{uid}"
        req = urllib.request.Request(url, headers={"Authorization": grafana_auth})

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                assert resp.status == 200, f"Expected HTTP 200 for dashboard {uid}, got {resp.status}"
                body = json.loads(resp.read().decode("utf-8"))
                dash = body.get("dashboard", {})
                assert dash.get("uid") == uid, f"Reported UID mismatch for {uid}"
                assert dash.get("title") == spec["title"], f"Reported title mismatch for {uid}"
                assert len(dash.get("panels", [])) >= spec["min_panels"]
        except Exception as exc:
            pytest.fail(f"Failed to fetch provisioned dashboard {uid} from Grafana: {exc}")


def test_05_grafana_search_endpoint_folder(grafana_auth):
    """Verify that all four Stage 7E dashboards appear in Grafana search results."""
    url = "http://127.0.0.1:3001/api/search?type=dash-db"
    req = urllib.request.Request(url, headers={"Authorization": grafana_auth})

    with urllib.request.urlopen(req, timeout=5.0) as resp:
        assert resp.status == 200
        dashboards = json.loads(resp.read().decode("utf-8"))
        uids = {d.get("uid") for d in dashboards}

        for spec in EXPECTED_DASHBOARDS:
            assert spec["uid"] in uids, f"Dashboard {spec['uid']} not found in Grafana search index"


def test_06_panel_descriptions_coverage():
    """Verify that 100% of visual panels across all dashboards have technically rigorous descriptions."""
    total_visual = 0
    total_described = 0

    for spec in EXPECTED_DASHBOARDS:
        path = DASHBOARDS_DIR / spec["filename"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        panels = data.get("panels", [])
        visual_panels = [p for p in panels if p.get("type") != "row"]
        assert len(visual_panels) > 0, f"No visual panels found in {spec['filename']}"

        for p in visual_panels:
            total_visual += 1
            desc = p.get("description", "").strip()
            assert desc, f"Panel {p.get('id')} ({p.get('title')}) in {spec['filename']} is missing description"
            assert len(desc) >= 30, (
                f"Panel {p.get('id')} in {spec['filename']} has description that is too brief (<30 chars): '{desc}'"
            )
            # Avoid generic placeholders
            assert not any(ph in desc.lower() for ph in ["shows network performance", "todo", "placeholder", "tbd"]), (
                f"Panel {p.get('id')} in {spec['filename']} contains generic description placeholder: '{desc}'"
            )
            total_described += 1

    assert total_visual == 47, f"Expected 47 visual panels across all 4 dashboards, found {total_visual}"
    assert total_described == total_visual, f"Expected 100% description coverage ({total_visual}/{total_visual})"


def test_07_live_grafana_descriptions_rendered(grafana_auth):
    """Verify that provisioned dashboards in live Grafana retain panel descriptions for the info interface."""
    for spec in EXPECTED_DASHBOARDS:
        uid = spec["uid"]
        url = f"http://127.0.0.1:3001/api/dashboards/uid/{uid}"
        req = urllib.request.Request(url, headers={"Authorization": grafana_auth})

        with urllib.request.urlopen(req, timeout=5.0) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            dash = body.get("dashboard", {})
            panels = dash.get("panels", [])
            visual_panels = [p for p in panels if p.get("type") != "row"]

            for p in visual_panels:
                desc = p.get("description", "").strip()
                assert desc, f"Provisioned panel {p.get('id')} in Grafana dashboard {uid} lost its description"


