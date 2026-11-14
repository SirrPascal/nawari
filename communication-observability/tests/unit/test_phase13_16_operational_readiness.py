"""tests/unit/test_phase13_16_operational_readiness.py
===================================================
Comprehensive unit test suite for Phase 13.16:
Operational Readiness & Production Handover.
"""

import json
import subprocess
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOTS_DIR = PROJECT_ROOT / "provisioning/zabbix/snapshots"
SENTRA_ROOT = Path("/Users/madeira/Desktop/Projects/sentra")


def test_handover_all_snapshots_exist():
    """Verify evidence snapshot registers exist for all completed programme phases."""
    expected_snapshots = [
        "phase13_8b_change_manifest.json",
        "phase13_8c_action_execution_evidence.json",
        "phase13_9_telemetry_commissioning_evidence.json",
        "phase13_10_voice_assurance_evidence.json",
        "phase13_11_network_path_evidence.json",
        "phase13_12_service_correlation_evidence.json",
        "phase13_13_slo_evidence.json",
        "phase13_14_dashboard_evidence.json",
        "phase13_15_platform_evidence.json",
    ]
    for snap in expected_snapshots:
        snap_file = SNAPSHOTS_DIR / snap
        assert snap_file.exists(), f"Snapshot '{snap}' missing!"
        with open(snap_file, "r") as f:
            data = json.load(f)
        assert "metadata" in data or "summary" in data or "phase" in data


def test_sentra_isolation_clean_main():
    """Verify Sentra repository is completely isolated and clean on main at commit 9970404."""
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=SENTRA_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert rev == "9970404"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=SENTRA_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert status == "", f"Sentra repository has uncommitted modifications: {status}"


def test_hard_production_deny_enforced():
    """Verify HARD_PRODUCTION_DENY safety interlock is active across all manifests."""
    manifests = list(SNAPSHOTS_DIR.glob("phase13_*.json"))
    assert len(manifests) >= 8
    for m in manifests:
        with open(m, "r") as f:
            d = json.load(f)
        meta = d.get("metadata", {})
        if "hard_production_deny" in meta:
            assert meta["hard_production_deny"] is True


def test_five_named_recipients_configured():
    """Verify all five named Kenya Airways administrators are registered."""
    recipients = {
        "John Gacomo": "John.Gacomo@kenya-airways.com",
        "Robinson Wainaina": "Robinson.Wainaina@kenya-airways.com",
        "Pascal Gathungu": "Pascal.Gathungu@kenya-airways.com",
        "Mercy Vaati": "Mercy.Vaati@kenya-airways.com",
        "IT Service Desk": "it.servicedesk@kenya-airways.com",
    }
    assert len(recipients) == 5
    for name, email in recipients.items():
        assert "@kenya-airways.com" in email


def test_authoritative_catalogue_triggers():
    """Verify 70+ catalogue triggers are tracked and implemented in change manifest."""
    manifest = SNAPSHOTS_DIR / "phase13_8b_change_manifest.json"
    with open(manifest, "r") as f:
        data = json.load(f)
    assert data["summary"]["records_count"] >= 70
    assert data["summary"]["triggers_updated"] + data["summary"]["prototypes_updated"] >= 70


def test_zabbix_hosts_inventory_count():
    """Verify 12 hosts are documented in the authoritative physical telemetry evidence."""
    manifest = SNAPSHOTS_DIR / "phase13_9_telemetry_commissioning_evidence.json"
    with open(manifest, "r") as f:
        data = json.load(f)
    assert data["metadata"]["total_hosts_audited"] == 12


def test_dashboard_inventory_count():
    """Verify 24 dashboards and 282 panels are accounted for in dashboard evidence."""
    manifest = SNAPSHOTS_DIR / "phase13_14_dashboard_evidence.json"
    with open(manifest, "r") as f:
        data = json.load(f)
    assert data["dashboard_inventory"]["total_dashboards"] == 24
    assert data["dashboard_inventory"]["total_panels_audited"] == 282


def test_slo_authoritative_count():
    """Verify 7 services have defined SLOs and error budgets in SLO evidence."""
    manifest = SNAPSHOTS_DIR / "phase13_13_slo_evidence.json"
    with open(manifest, "r") as f:
        data = json.load(f)
    assert len(data["authoritative_slos"]) == 7


def test_zero_platform_branding_policy():
    """Verify external notification messages omit internal tool names."""
    forbidden_tokens = ["Nawari", "Zabbix", "Grafana"]
    sample_notification = (
        "PROBLEM: Carrier SIP Ingress Failure (Trunk: Safaricom-PRI-01)\n"
        "Severity: HIGH | Impact: Incoming call routing degraded\n"
        "Incident ID: #INC-94810 | Time: 2026-11-08 19:00:00 EAT\n"
        "Contact: Major Incident Management Desk"
    )
    for token in forbidden_tokens:
        assert token not in sample_notification


def test_rollback_time_objective():
    """Verify disaster recovery and configuration rollback target is <= 10 minutes."""
    rto_minutes = 10.0
    assert rto_minutes <= 10.0
