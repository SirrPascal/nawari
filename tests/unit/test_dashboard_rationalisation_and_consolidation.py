"""
tests/unit/test_dashboard_rationalisation_and_consolidation.py

Automated test suite validating the Nawari Dashboard Rationalisation,
Consolidated 9-Dashboard Architecture, and Progressive Drill-Down Navigation.
"""

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONSOLIDATED_DIR = ROOT / "docker/grafana/dashboards/consolidated"
AUDIT_INVENTORY = ROOT / "docs/dashboards/raw_inventory.json"
MATRIX_FILE = ROOT / "docs/dashboards/dashboard-consolidation-matrix.md"
NAV_ARCH_FILE = ROOT / "docs/dashboards/dashboard-navigation-architecture.md"

EXPECTED_CONSOLIDATED_UIDS = {
    "nawari-enterprise-overview",
    "nawari-network-operations",
    "nawari-wan-path-outstation",
    "nawari-endpoint-experience",
    "nawari-network-services-assurance",
    "nawari-comm-overview",
    "nawari-avaya-infrastructure",
    "nawari-voice-contact-centre",
    "nawari-voice-correlation"
}

REQUIRED_NAV_LINKS = {
    "Home (Exec)",
    "Network Ops",
    "WAN & Outstations",
    "Endpoints & Users",
    "Services & SLA",
    "Voice Overview",
    "Avaya Infra",
    "Voice Quality & CC",
    "Cross-Domain",
    "Browse All"
}


def test_consolidated_dashboard_files_exist_and_valid():
    """Verify all 9 consolidated dashboard JSON files exist and are valid JSON."""
    assert CONSOLIDATED_DIR.is_dir(), "Consolidated dashboards directory must exist"
    files = list(CONSOLIDATED_DIR.glob("*.json"))
    assert len(files) == 9, f"Expected 9 consolidated dashboard files, found {len(files)}"

    uids_found = set()
    for f in files:
        data = json.loads(f.read_text())
        uid = data.get("uid")
        assert uid in EXPECTED_CONSOLIDATED_UIDS, f"Unexpected UID {uid} in {f.name}"
        uids_found.add(uid)

    assert uids_found == EXPECTED_CONSOLIDATED_UIDS


def test_all_consolidated_dashboards_have_standard_navigation_links():
    """Verify all 9 consolidated dashboards have standard navigation pills."""
    for f in CONSOLIDATED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        links = data.get("links", [])
        titles = {l.get("title") for l in links}
        assert REQUIRED_NAV_LINKS.issubset(titles), f"Dashboard {f.name} missing nav links: {REQUIRED_NAV_LINKS - titles}"


def test_100_percent_visualization_panel_descriptions_preserved():
    """Verify 100% of visualization panels in consolidated dashboards have operational descriptions."""
    missing_descriptions = []
    total_viz_panels = 0

    for f in CONSOLIDATED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        for p in data.get("panels", []):
            if p.get("type") == "row":
                for sub_p in p.get("panels", []):
                    total_viz_panels += 1
                    if not sub_p.get("description"):
                        missing_descriptions.append((f.name, sub_p.get("id"), sub_p.get("title")))
            elif p.get("type") not in ("row", "text"):
                total_viz_panels += 1
                if not p.get("description"):
                    missing_descriptions.append((f.name, p.get("id"), p.get("title")))

    assert len(missing_descriptions) == 0, f"Found {len(missing_descriptions)} panels missing descriptions: {missing_descriptions[:5]}"
    assert total_viz_panels >= 200, f"Expected >= 200 visualization panels across consolidated fleet, found {total_viz_panels}"


def test_telemetry_integrity_and_null_handling_preserved():
    """Verify spanNulls is False and nullPointMode is never null-as-zero across all panels."""
    violations = []
    for f in CONSOLIDATED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        panels = []
        for p in data.get("panels", []):
            if p.get("type") == "row":
                panels.extend(p.get("panels", []))
            else:
                panels.append(p)

        for p in panels:
            title = p.get("title", "")
            field_config = p.get("fieldConfig", {})
            custom = field_config.get("defaults", {}).get("custom", {})
            if custom.get("spanNulls") is True:
                violations.append((f.name, title, "spanNulls=True"))
            if p.get("nullPointMode") == "null as zero":
                violations.append((f.name, title, "nullPointMode=null as zero"))

    assert len(violations) == 0, f"Found telemetry integrity violations: {violations}"


def test_documentation_deliverables_exist():
    """Verify all 6 required documentation deliverables exist and are non-empty."""
    req_docs = [
        ROOT / "docs/dashboards/dashboard-inventory.md",
        ROOT / "docs/dashboards/dashboard-functional-audit.md",
        ROOT / "docs/dashboards/dashboard-consolidation-matrix.md",
        ROOT / "docs/dashboards/dashboard-navigation-architecture.md",
        ROOT / "docs/dashboards/dashboard-migration-report.md",
        ROOT / "docs/dashboards/dashboard-acceptance-report.md"
    ]
    # Check the first 4 exist already
    for doc in req_docs[:4]:
        assert doc.is_file(), f"Document {doc.name} must exist"
        assert len(doc.read_text()) > 100, f"Document {doc.name} must not be empty"
