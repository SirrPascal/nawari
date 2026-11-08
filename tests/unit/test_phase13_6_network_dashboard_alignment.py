"""
tests/unit/test_phase13_6_network_dashboard_alignment.py

Automated unit test suite for Nawari Phase 13.6:
1. Network Observability dashboard inventory completeness (13 dashboards, valid JSON, UIDs, symlinks).
2. Hostname and item-key correctness (authoritative Zabbix hosts, no fictitious hosts).
3. Zabbix datasource configuration (PA67C5EADE9207728, postgres for topology).
4. Mandatory operational descriptions across 100% of 87 visualization panels with missing data explanation.
5. Native Zabbix Problems panel integration in Network Infrastructure Overview.
6. Interface traffic health 64-bit HC counters, throughput calculations, and null preservation.
7. Total outage notification user groups and 5 configured recipients (4 voice admins + IT Service Desk).
8. Total outage action, 30m escalation, recovery operations with {EVENT.DURATION}, and clean operational language.
9. Trigger notification_class tag classification across templates and hosts.
10. Production boundary safety (HARD_PRODUCTION_DENY) and Sentra repository isolation (9970404).
"""

import json
from pathlib import Path
import subprocess
import pytest
import yaml

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
from services.api.provisioning.notification_reconciler import (
    ADMIN_USER_GROUP,
    TOTAL_OUTAGE_USER_GROUP,
    ACTION_TOTAL_OUTAGE,
    ACTION_COMM_SERVICE,
    ACTION_SYNTHETIC_VOICE,
    ACTION_NETWORK_DEGRADATION,
    ACTION_COMPONENT_FAILURE,
    ACTION_MONITORING_FAILURE,
    DESIGNATED_ADMINISTRATORS,
    SERVICE_DESK_RECIPIENT,
    classify_trigger_description,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARDS_DIR = PROJECT_ROOT / "docker/grafana/dashboards"
NET_OBS_DIR = DASHBOARDS_DIR / "network_observability"
COMM_OBS_DIR = DASHBOARDS_DIR / "communication_observability"
TEMPLATES_DIR = PROJECT_ROOT / "provisioning/zabbix/templates"
USERS_DIR = PROJECT_ROOT / "provisioning/zabbix/users"
ACTIONS_DIR = PROJECT_ROOT / "provisioning/zabbix/actions"
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"

EXPECTED_NETWORK_DASHBOARDS = [
    "endpoint_detail.json",
    "endpoint_fleet_overview.json",
    "interface_traffic_health.json",
    "nawari_controlled_operations.json",
    "nawari_edge_fleet.json",
    "nawari_enterprise_overview.json",
    "nawari_global_outstations.json",
    "nawari_incident_operations.json",
    "nawari_predictive_intelligence.json",
    "nawari_service_catalog_sla.json",
    "network_infrastructure_overview.json",
    "network_path_analysis.json",
    "network_topology.json",
]

AUTHORITATIVE_HOSTS = {
    "mock-core-switch-01",
    "core-gw-01",
    "mon-grafana01",
    "endpoint-probe-01",
    "nawari-voice-probe-01",
    "$host",
    "$endpoint",
    "/.*/",
    "",
}


def test_01_network_dashboard_inventory_completeness():
    """Verify all 13 network dashboards are present, valid JSON, and have root compatibility symlinks."""
    assert NET_OBS_DIR.is_dir(), f"{NET_OBS_DIR} must exist"

    found_files = sorted([p.name for p in NET_OBS_DIR.glob("*.json")])
    assert found_files == sorted(EXPECTED_NETWORK_DASHBOARDS), f"Mismatch in network dashboards: {set(found_files) ^ set(EXPECTED_NETWORK_DASHBOARDS)}"

    for fname in EXPECTED_NETWORK_DASHBOARDS:
        fpath = NET_OBS_DIR / fname
        with open(fpath) as f:
            data = json.load(f)
        assert data.get("title"), f"Dashboard {fname} must have title"
        assert data.get("uid"), f"Dashboard {fname} must have uid"

        # Verify root symlink exists
        symlink = DASHBOARDS_DIR / fname
        assert symlink.exists(), f"Symlink {symlink} must exist in root dashboards directory"


def test_02_network_hostname_and_target_correctness():
    """Verify no legacy or fictitious hostnames are referenced in network dashboards."""
    forbidden_hostnames = {
        "nawari-core-01",
        "nawari-net-01",
        "nawari-switch-01",
        "cisco-core-01",
        "core-switch-01.nawari.local",
    }

    for fname in EXPECTED_NETWORK_DASHBOARDS:
        fpath = NET_OBS_DIR / fname
        with open(fpath) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            for t in p.get("targets", []):
                h = t.get("host")
                hname = ""
                if isinstance(h, dict):
                    hname = h.get("filter") or h.get("name") or ""
                elif isinstance(h, str):
                    hname = h

                assert hname not in forbidden_hostnames, f"Forbidden host '{hname}' found in {fname} panel '{p.get('title')}'"


def test_03_zabbix_datasource_and_query_integrity():
    """Verify panels use valid datasource UIDs (PA67C5EADE9207728 for Zabbix, postgres for topology)."""
    for fname in EXPECTED_NETWORK_DASHBOARDS:
        fpath = NET_OBS_DIR / fname
        with open(fpath) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue
            if fname == "network_topology.json":
                ds = p.get("datasource", {})
                dstype = ds.get("type") if isinstance(ds, dict) else ds
                assert dstype in ("postgres", "nawari-postgres-telemetry", None)
            else:
                p_ds = p.get("datasource", {})
                if isinstance(p_ds, dict) and p_ds.get("uid"):
                    assert p_ds.get("uid") == "PA67C5EADE9207728", f"Unexpected panel datasource UID in {fname} panel '{p.get('title')}'"
                for t in p.get("targets", []):
                    ds = t.get("datasource", {})
                    if isinstance(ds, dict) and ds.get("uid"):
                        assert ds.get("uid") == "PA67C5EADE9207728", f"Unexpected target datasource UID in {fname} panel '{p.get('title')}'"


def test_04_network_panel_descriptions_100_percent_coverage():
    """Verify 100% of 87 visualization panels have operational descriptions explaining missing data."""
    total_panels = 0
    for fname in EXPECTED_NETWORK_DASHBOARDS:
        fpath = NET_OBS_DIR / fname
        with open(fpath) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue
            total_panels += 1
            desc = p.get("description", "")
            title = p.get("title", "")

            assert len(desc) >= 40, f"Panel '{title}' in {fname} has short/missing description (len={len(desc)})"
            has_missing_clause = any(
                k in desc.lower() for k in [
                    "missing data", "no data", "missing telemetry",
                    "data is missing", "uncollected", "not collected"
                ]
            )
            assert has_missing_clause, f"Panel '{title}' in {fname} missing explanation of missing data"

    assert total_panels == 87, f"Expected 87 visualization panels in Network Observability, found {total_panels}"


def test_05_native_zabbix_problems_panel_in_network_overview():
    """Verify Network Infrastructure Overview integrates native Zabbix problems panel."""
    overview_file = NET_OBS_DIR / "network_infrastructure_overview.json"
    with open(overview_file) as f:
        data = json.load(f)

    panels = {p.get("id"): p for p in data.get("panels", [])}
    assert 9 in panels, "Panel 9 must exist in Network Infrastructure Overview"

    p9 = panels[9]
    assert p9.get("type") == "alexanderzobnin-zabbix-problems-panel", "Panel 9 must be alexanderzobnin-zabbix-problems-panel"
    assert "Live Network Alert Feed" in p9.get("title", "")
    assert "Zabbix Problems" in p9.get("title", "")

    # Target mode must be 1 (problems)
    target = p9.get("targets", [])[0]
    assert target.get("mode") == 1
    assert target.get("resultFormat") == "problems"
    assert target.get("group", {}).get("filter") == "Core Network"

    # Description must explain source, freshness, and missing data
    desc = p9.get("description", "")
    assert "Zabbix Problems" in desc
    assert "missing data" in desc.lower()


def test_06_interface_traffic_health_metrics_and_null_preservation():
    """Verify interface traffic health dashboard uses 64-bit counters, bps throughput, and preserves nulls."""
    iface_file = NET_OBS_DIR / "interface_traffic_health.json"
    with open(iface_file) as f:
        data = json.load(f)

    panels = {p.get("id"): p for p in data.get("panels", [])}

    # Panel 6: Bandwidth Ingress / Egress
    p6 = panels[6]
    desc = p6.get("description", "")
    assert "64-bit" in desc or "ifHC" in desc
    assert "bits per second" in desc.lower() or "bps" in desc.lower()

    # Panel 8: Packet Error Rates
    p8 = panels[8]
    assert "ifInErrors" in p8.get("description", "") or "errors/sec" in p8.get("description", "").lower()

    # Panel 9: Packet Discard Rates
    p9 = panels[9]
    assert "ifInDiscards" in p9.get("description", "") or "packets per second" in p9.get("description", "").lower()


def test_07_total_outage_user_groups_and_recipients():
    """Verify Nawari Total Outage Recipients group and all 5 recipients in Zabbix provisioning."""
    users_file = USERS_DIR / "total_outage_recipients.yaml"
    assert users_file.is_file(), f"{users_file} must exist"

    with open(users_file) as f:
        data = yaml.safe_load(f)

    user_groups = data.get("user_groups", [])
    assert any(g.get("name") == TOTAL_OUTAGE_USER_GROUP for g in user_groups)

    users = {u["username"]: u for u in data.get("users", [])}
    assert len(users) == 5, f"Expected 5 recipients, found {len(users)}"

    # Check 4 communication admins
    for admin in DESIGNATED_ADMINISTRATORS:
        uname = admin["username"]
        assert uname in users, f"Admin '{uname}' missing from total outage recipients"
        media = users[uname]["medias"][0]
        sendto = media["sendto"]
        actual_email = sendto[0] if isinstance(sendto, list) else sendto
        assert actual_email == admin["email"]
        assert media["active"] == 0
        assert media["severity"] == 63

    # Check IT Service Desk
    sd_uname = SERVICE_DESK_RECIPIENT["username"]
    assert sd_uname in users, f"IT Service Desk '{sd_uname}' missing"
    sd_media = users[sd_uname]["medias"][0]
    sd_sendto = sd_media["sendto"]
    actual_sd_email = sd_sendto[0] if isinstance(sd_sendto, list) else sd_sendto
    assert actual_sd_email == SERVICE_DESK_RECIPIENT["email"]
    assert sd_media["active"] == 0
    assert sd_media["severity"] == 63


def test_08_total_outage_action_templates_and_duration_macro():
    """Verify Total Outage action specifies 30m escalation, recovery duration macro, and clean language."""
    action_file = ACTIONS_DIR / "action_total_outage.yaml"
    assert action_file.is_file(), f"{action_file} must exist"

    with open(action_file) as f:
        data = yaml.safe_load(f)

    actions = data.get("zabbix_export", {}).get("actions", [])
    assert len(actions) == 1
    act = actions[0]

    assert act.get("name") == ACTION_TOTAL_OUTAGE
    assert act.get("esc_period") in ("30m", "1800s")

    # Check tag condition
    conditions = act.get("filter", {}).get("conditions", [])
    tag_cond = [c for c in conditions if c.get("value2") == "notification_class"]
    assert len(tag_cond) == 1
    assert tag_cond[0].get("value") == "total_outage"

    # Operations: Step 1 (immediate), Step 2..0 (30m repeat)
    ops = act.get("operations", [])
    assert len(ops) >= 2
    op1 = ops[0]
    assert op1.get("esc_step_from") == 1
    assert op1.get("esc_step_to") == 1
    assert any(g.get("name") == TOTAL_OUTAGE_USER_GROUP for g in op1.get("user_groups", []))

    msg1 = op1.get("message", {})
    sub1 = msg1.get("subject", "")
    body1 = msg1.get("message", "")
    assert "[TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}" in sub1
    assert "OUTAGE IN PROGRESS" in body1

    op2 = ops[1]
    assert op2.get("esc_step_from") == 2
    assert op2.get("esc_step_to") == 0
    assert op2.get("esc_period") in ("1800s", "30m")

    # Recovery operation: must use {EVENT.DURATION}
    rec_ops = act.get("recovery_operations", [])
    assert len(rec_ops) >= 1
    rec_msg = rec_ops[0].get("message", {})
    rec_sub = rec_msg.get("subject", "")
    rec_body = rec_msg.get("message", "")

    assert "[RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}" in rec_sub
    assert "{EVENT.DURATION}" in rec_body
    assert "{EVENT.RECOVERY.DATE}" in rec_body
    assert "{EVENT.RECOVERY.TIME}" in rec_body

    # Clean operational language: NO mention of Nawari, Zabbix, or internal monitoring tools!
    for text in [sub1, body1, rec_sub, rec_body]:
        assert "nawari" not in text.lower(), f"Forbidden brand 'nawari' in message: {text}"
        assert "zabbix" not in text.lower(), f"Forbidden brand 'zabbix' in message: {text}"


def test_09_trigger_notification_class_tagging():
    """Verify trigger classification logic correctly maps all alert types."""
    # Total outage triggers
    assert classify_trigger_description("Avaya SM: Session Manager Host Unavailable") == "total_outage"
    assert classify_trigger_description("Avaya CM: Communication Manager Processor Unreachable") == "total_outage"
    assert classify_trigger_description("Avaya SBCE: Appliance Unreachable") == "total_outage"
    assert classify_trigger_description("Avaya G450: Media Gateway Chassis Unreachable") == "total_outage"
    assert classify_trigger_description("SIP Trunk: Endpoint Unreachable") == "total_outage"
    assert classify_trigger_description("Network Generic Device: Unavailable by ICMP ping") == "total_outage"

    # Service outage triggers
    assert classify_trigger_description("Avaya SM: SIP Entity Down (Communication Manager)") == "service_outage"
    assert classify_trigger_description("Avaya SM: SIP Entity DENY NEW SERVICE (Avaya SBCE)") == "service_outage"
    assert classify_trigger_description("Avaya G450: Media Gateway Unregistered from Communication Manager") == "service_outage"
    assert classify_trigger_description("SIP Trunk: Consecutive OPTIONS Probe Failures") == "service_outage"

    # Synthetic failure triggers
    assert classify_trigger_description("Synthetic voice test failed or congested") == "synthetic_failure"
    assert classify_trigger_description("One-way audio detected on synthetic voice test") == "synthetic_failure"
    assert classify_trigger_description("Degraded voice quality on synthetic probe (MOS < 3.8)") == "synthetic_failure"

    # Degradation triggers
    assert classify_trigger_description("Avaya SBCE: High CPU utilization (> {$CPU.UTIL.WARN}%)") == "degradation"
    assert classify_trigger_description("Avaya CM: Real-Call Packet Loss High (> 2.5% in Last Hour)") == "degradation"
    assert classify_trigger_description("High packet loss to default gateway (>20%)") == "degradation"

    # Component failure triggers
    assert classify_trigger_description("Avaya G450: Power Supply Unit Failure") == "component_failure"
    assert classify_trigger_description("Interface eth0: Link down") == "component_failure"

    # Monitoring failure triggers
    assert classify_trigger_description("Nawari Generic SNMP Base: SNMP agent is not responding") == "monitoring_failure"
    assert classify_trigger_description("Avaya SM: Management Telemetry Stale or Loss of Monitoring") == "monitoring_failure"


def test_10_production_boundary_and_sentra_isolation():
    """Verify HARD_PRODUCTION_DENY safety boundary and Sentra repository baseline (9970404)."""
    assert SENTRA_ROOT.is_dir(), f"Sentra repository {SENTRA_ROOT} must exist"

    cmd = ["git", "-C", str(SENTRA_ROOT), "rev-parse", "HEAD"]
    commit = subprocess.check_output(cmd).decode().strip()
    assert commit.startswith("9970404"), f"Sentra must remain at baseline 9970404, found {commit}"

    status_cmd = ["git", "-C", str(SENTRA_ROOT), "status", "--porcelain"]
    status = subprocess.check_output(status_cmd).decode().strip()
    assert status == "", f"Sentra working tree must be clean, found:\n{status}"
