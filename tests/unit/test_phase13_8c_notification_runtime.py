"""
tests/unit/test_phase13_8c_notification_runtime.py

Automated unit and runtime verification test suite for Nawari Phase 13.8C:
Zabbix Runtime Notification and Incident Lifecycle Verification.

Verifies:
1. Live Zabbix API Action definitions for Actions 10-15 and disabled status of legacy Action 7.
2. User group recipient matrices and media assignments (Group 15: 5 recipients, Group 14: 4 admins, Group 7: tech ops).
3. Action execution evidence manifest completeness across all 10 controlled scenarios.
4. Runtime alert routing exclusivity and recipient isolation (Service Desk excluded from non-total outages).
5. Runtime recovery operations and macro expansion integrity ({EVENT.DURATION} rendered, zero raw macros).
6. Incident acknowledgment (event.acknowledge) audit logging and recovery resilience.
7. Maintenance window problem suppression (suppressed: 1, zero alerts dispatched during active maintenance).
8. Service-outage redundancy semantics (single node fault does not declare total outage).
9. Zero monitoring platform branding in recipient-facing messages.
10. Repository isolation (Sentra untouched at 9970404) and HARD_PRODUCTION_DENY preservation.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
from services.testing.notification_capture_harness import (
    validate_zero_platform_branding,
    differentiate_host_vs_service_recovery,
)
from services.api.provisioning.notification_reconciler import (
    classify_service_outage_semantics,
    classify_trigger_description,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"
SNAPSHOT_DIR = PROJECT_ROOT / "provisioning/zabbix/snapshots"
EVIDENCE_FILE = SNAPSHOT_DIR / "phase13_8c_action_execution_evidence.json"


@pytest.fixture(scope="module")
def zabbix_client():
    """Establish authenticated Zabbix client."""
    client = ZabbixClient(ZabbixSettings())
    client.connect()
    return client


@pytest.fixture(scope="module")
def execution_manifest():
    """Load Phase 13.8C execution evidence manifest."""
    assert EVIDENCE_FILE.is_file(), f"Evidence manifest must exist at {EVIDENCE_FILE}"
    with open(EVIDENCE_FILE) as f:
        return json.load(f)


def test_01_staging_action_definitions_and_conditions(zabbix_client):
    """Verify live Zabbix API action definitions, condition tags, operations, and Action 7 status."""
    actions = zabbix_client.call(
        "action.get",
        {
            "output": ["actionid", "name", "status", "eventsource", "evaltype"],
            "selectFilter": "extend",
            "selectOperations": "extend",
            "selectRecoveryOperations": "extend",
        }
    )
    act_map = {str(a["actionid"]): a for a in actions}

    # 1. Action 7 MUST be disabled
    assert "7" in act_map, "Legacy Action 7 must exist in Zabbix"
    assert str(act_map["7"]["status"]) == "1", "Legacy Action 7 MUST be disabled (status 1)"

    # 2. Structured Actions 10-15 MUST be enabled
    expected_actions = {
        "10": ("Total Outage Alert", "total_outage"),
        "11": ("Communication Service Alert", "service_outage"),
        "12": ("Synthetic Voice Failure Alert", "synthetic_failure"),
        "13": ("Network Degradation Alert", "degradation"),
        "14": ("Component Failure Alert", "component_failure"),
        "15": ("Monitoring Failure Alert", "monitoring_failure"),
    }

    for aid, (expected_name, expected_tag) in expected_actions.items():
        assert aid in act_map, f"Action {aid} must exist"
        act = act_map[aid]
        assert str(act["status"]) == "0", f"Action {aid} ({expected_name}) must be enabled (status 0)"
        assert act["name"] == expected_name

        # Check tag conditions
        conditions = act.get("filter", {}).get("conditions", [])
        assert len(conditions) >= 1
        tag_cond = conditions[0]
        assert str(tag_cond.get("conditiontype")) == "26", "Condition must be tag value (26)"
        assert tag_cond.get("value2") == "notification_class"
        assert tag_cond.get("value") == expected_tag


def test_02_recipient_user_groups_and_medias(zabbix_client):
    """Verify recipient user groups, memberships, and media assignments."""
    groups = zabbix_client.call(
        "usergroup.get",
        {
            "usrgrpids": ["7", "14", "15"],
            "output": ["usrgrpid", "name"],
            "selectUsers": ["userid", "username"],
        }
    )
    grp_map = {str(g["usrgrpid"]): g for g in groups}

    # Group 15: Total Outage Recipients (5 members)
    g15_users = {str(u["userid"]) for u in grp_map["15"].get("users", [])}
    expected_g15 = {"3", "4", "5", "6", "7"}
    assert expected_g15.issubset(g15_users), f"Group 15 must contain all 5 recipients, got {g15_users}"

    # Group 14: Voice Administrators (4 members, User 7 Service Desk excluded)
    g14_users = {str(u["userid"]) for u in grp_map["14"].get("users", [])}
    expected_g14 = {"3", "4", "5", "6"}
    assert expected_g14.issubset(g14_users), f"Group 14 must contain the 4 voice admins, got {g14_users}"
    assert "7" not in g14_users, "IT Service Desk (7) MUST NOT belong to User Group 14"

    # Group 7: Zabbix Administrators (Admin 1)
    g7_users = {str(u["userid"]) for u in grp_map["7"].get("users", [])}
    assert "1" in g7_users, "Admin (1) must belong to User Group 7"

    # Verify all users have active email media
    all_uids = list(expected_g15 | {"1"})
    users = zabbix_client.call("user.get", {"userids": all_uids, "output": ["userid", "username"], "selectMedias": "extend"})
    for u in users:
        medias = u.get("medias", [])
        assert len(medias) >= 1, f"User {u['username']} must have at least one media configured"
        assert any(str(m.get("active")) == "0" for m in medias), f"User {u['username']} must have active media"


def test_03_action_execution_evidence_manifest(execution_manifest):
    """Verify evidence manifest metadata, scenario counts, and zero production mutations."""
    meta = execution_manifest["metadata"]
    assert meta["phase"] == "13.8C"
    assert meta["environment"] == "STAGING_VERIFIED"
    assert meta["hard_production_deny"] is True
    assert meta["email_delivery_status"] == "CONFIGURED_UNVERIFIED"
    assert meta["sms_delivery_status"] == "CONFIGURED_UNVERIFIED"

    summary = execution_manifest["verification_summary"]
    assert summary["scenarios_executed"] == 10
    assert summary["scenarios_passed"] == 10
    assert summary["redundancy_scenarios_verified"] == 6
    assert summary["action_7_alerts_generated"] == 0
    assert summary["zero_platform_branding_verified"] is True
    assert summary["production_mutations_count"] == 0
    assert summary["external_emails_dispatched"] == 0


def test_04_runtime_alert_routing_and_recipient_isolation(execution_manifest):
    """Verify recipient routing exclusivity across the 10 controlled scenarios."""
    scenarios = {s["scenario_id"]: s for s in execution_manifest["controlled_scenarios"]}

    # Event 1: Total Network Outage -> all 5 recipients
    e1 = scenarios["EVENT_01_TOTAL_NETWORK_OUTAGE"]
    assert e1["action_id"] == "10"
    assert e1["service_desk_included"] is True
    assert set(e1["recipients_targeted"]) >= {"3", "4", "5", "6", "7"}

    # Event 3: SIP Carrier Service Outage -> 4 voice admins only
    e3 = scenarios["EVENT_03_SIP_CARRIER_SERVICE_OUTAGE"]
    assert e3["action_id"] == "11"
    assert e3["service_desk_included"] is False
    assert set(e3["recipients_targeted"]) >= {"3", "4", "5", "6"}
    assert "7" not in e3["recipients_targeted"]

    # Event 4: Synthetic Voice Failure -> 4 voice admins only
    e4 = scenarios["EVENT_04_SYNTHETIC_VOICE_FAILURE"]
    assert e4["action_id"] == "12"
    assert e4["service_desk_included"] is False
    assert set(e4["recipients_targeted"]) >= {"3", "4", "5", "6"}
    assert "7" not in e4["recipients_targeted"]

    # Events 5, 6, 7: Technical operations (Group 7 / Admin 1)
    for eid, aid in [
        ("EVENT_05_COMPONENT_FAILURE", "14"),
        ("EVENT_06_MONITORING_FAILURE", "15"),
        ("EVENT_07_NETWORK_DEGRADATION", "13"),
    ]:
        sc = scenarios[eid]
        assert sc["action_id"] == aid
        assert sc["service_desk_included"] is False
        assert "1" in sc["recipients_targeted"]
        assert "7" not in sc["recipients_targeted"]


def test_05_runtime_recovery_and_duration_macro_expansion(zabbix_client, execution_manifest):
    """Verify recovery operations generated recovery alerts with expanded {EVENT.DURATION}."""
    alerts = zabbix_client.call(
        "alert.get",
        {
            "output": ["alertid", "actionid", "subject", "message"],
            "limit": 50,
            "sortfield": "alertid",
            "sortorder": "DESC",
        }
    )

    unexpanded_pattern = re.compile(r"\{(HOST\.|EVENT\.)[A-Z0-9_\.]+\}")
    recovery_alerts = [a for a in alerts if "[RECOVERED]" in a.get("subject", "")]
    assert len(recovery_alerts) >= 5, f"Expected at least 5 recovery alerts, got {len(recovery_alerts)}"

    for a in recovery_alerts:
        subj = a.get("subject", "")
        msg = a.get("message", "")

        # Verify no raw macros in recovery alert subject or body
        assert not unexpanded_pattern.search(subj), f"Unexpanded macro in subject of Alert {a['alertid']}: {subj}"
        assert not unexpanded_pattern.search(msg), f"Unexpanded macro in message of Alert {a['alertid']}: {msg}"

        # Verify duration string is present (e.g. 'Duration: 2s' or 'Total Downtime: 5s')
        assert any(k in subj for k in ["Duration:", "Total Downtime:"]), f"Duration missing in subject: {subj}"


def test_06_incident_acknowledgment_audit_and_resilience(execution_manifest):
    """Verify incident acknowledgment was audited and problem cleared despite acknowledgment."""
    scenarios = {s["scenario_id"]: s for s in execution_manifest["controlled_scenarios"]}
    e8 = scenarios["EVENT_08_ACKNOWLEDGED_INCIDENT"]
    assert e8["acknowledged"] is True
    assert "INC-94810" in e8["ticket_reference"]
    assert e8["recovery_cleared_despite_ack"] is True


def test_07_maintenance_window_suppression(execution_manifest):
    """Verify that maintenance window suppressed alert dispatch during active problem state."""
    scenarios = {s["scenario_id"]: s for s in execution_manifest["controlled_scenarios"]}
    e9 = scenarios["EVENT_09_MAINTENANCE_SUPPRESSION"]
    assert e9["problem_suppressed"] is True
    assert e9["alerts_dispatched_during_maintenance"] == 0


def test_08_service_outage_redundancy_semantics():
    """Verify service-outage redundancy semantics distinguishing single node faults from total outages."""
    # Strict service semantics mode
    assert classify_service_outage_semantics("Core Switch: Total Network Core Transport Failure") == "total_outage"
    assert classify_service_outage_semantics("Network Generic Device: Unavailable by ICMP ping") == "total_outage"

    # Single voice component reachability -> service_outage (NOT total_outage)
    assert classify_service_outage_semantics("Avaya SBCE: Appliance Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya G450: Media Gateway Chassis Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya SM: Session Manager Host Unavailable") == "service_outage"
    assert classify_service_outage_semantics("SIP Trunk: Endpoint Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya CM: Communication Manager Processor Unreachable") == "service_outage"

    # Backward compatibility mode
    assert classify_trigger_description("Avaya SBCE: Appliance Unreachable", strict_service_semantics=False) == "total_outage"

    # Recovery differentiation
    res_host = differentiate_host_vs_service_recovery(
        trigger_name="Network Generic Device: Unavailable by ICMP ping",
        host_name="core-gw-01",
        duration_str="12m 30s",
    )
    assert res_host["recovery_type"] == "HOST_REACHABILITY_RESTORED"
    assert res_host["service_restored_proven"] is False

    res_trunk = differentiate_host_vs_service_recovery(
        trigger_name="SIP Trunk: Consecutive OPTIONS Probe Failures",
        host_name="sip-trunk-carrier-01",
        duration_str="5m 10s",
    )
    assert res_trunk["recovery_type"] == "SIP_TRUNK_SIGNALING_RESTORED"
    assert res_trunk["service_restored_proven"] is True


def test_09_zero_platform_branding_in_all_messages(zabbix_client):
    """Verify that no alerts contain Nawari, Zabbix, or Grafana platform branding."""
    alerts = zabbix_client.call(
        "alert.get",
        {
            "output": ["alertid", "subject", "message"],
            "limit": 100,
            "sortfield": "alertid",
            "sortorder": "DESC",
        }
    )

    for a in alerts:
        content = f"{a.get('subject', '')}\n{a.get('message', '')}"
        ok, violations = validate_zero_platform_branding(content)
        assert ok, f"Prohibited platform branding found in Alert {a['alertid']}: {violations}"


def test_10_sentra_isolation_and_safety():
    """Verify Sentra repository remains pristine on main at 9970404 with HARD_PRODUCTION_DENY."""
    assert SENTRA_ROOT.is_dir(), f"Sentra repository must exist at {SENTRA_ROOT}"
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=SENTRA_ROOT).decode().strip()
    assert status == "", f"Sentra repository must have clean working tree, got:\n{status}"

    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=SENTRA_ROOT).decode().strip()
    assert head == "9970404", f"Sentra HEAD must be 9970404, got {head}"

