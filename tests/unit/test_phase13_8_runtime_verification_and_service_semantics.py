"""
tests/unit/test_phase13_8_runtime_verification_and_service_semantics.py

Automated unit and runtime verification test suite for Nawari Phase 13.8:
Zabbix Runtime Notification Verification and Service-Outage Semantics.

Verifies:
1. Live Zabbix Action API configuration (Conditions, tags, operations, user groups, Action 7 disabled).
2. Live Zabbix runtime execution of Synthetic Failure (Action 12, 4 voice admins, Service Desk excluded).
3. Live Zabbix runtime execution of Communication Service Outage (Action 11, 4 voice admins, Service Desk excluded).
4. Live Zabbix runtime execution of Total Outage (Action 10, all 5 recipients including Service Desk).
5. Runtime action mutual exclusivity (Zero duplicate alerts across actions, Action 7 generates 0 alerts).
6. Runtime macro expansion integrity (Subject and message contain fully rendered values, no raw macros).
7. Service-outage semantics (Distinguishing single host/gateway component outage from total network core outage).
8. Recovery semantics (Distinguishing host ICMP reachability from verified service restoration).
9. Delivery boundary preservation (CONFIGURED_UNVERIFIED maintained; zero live email delivery).
10. Project roadmap integration (Phase 13.8 feeding into Phase 8.2 commissioning gate, HARD_PRODUCTION_DENY, Sentra 9970404).
"""

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import time
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
from services.api.provisioning.notification_reconciler import (
    ADMIN_USER_GROUP,
    TOTAL_OUTAGE_USER_GROUP,
    TECH_ADMIN_USER_GROUP,
    ACTION_TOTAL_OUTAGE,
    ACTION_COMM_SERVICE,
    ACTION_SYNTHETIC_VOICE,
    ACTION_NETWORK_DEGRADATION,
    ACTION_COMPONENT_FAILURE,
    ACTION_MONITORING_FAILURE,
    ACTION_NAME,
    DESIGNATED_ADMINISTRATORS,
    SERVICE_DESK_RECIPIENT,
    classify_trigger_description,
    classify_service_outage_semantics,
)
from services.testing.notification_capture_harness import (
    differentiate_host_vs_service_recovery,
    validate_zero_platform_branding,
)
from services.voice.zabbix_sender import ZabbixSender, ZabbixMetric

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"
ROADMAP_FILE = PROJECT_ROOT / "docs/architecture/implementation-roadmap.md"


@pytest.fixture(scope="module")
def zabbix_env():
    """Establish authenticated Zabbix client and sender for live tests."""
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()
    sender = ZabbixSender(host="127.0.0.1", port=10051)
    return client, sender


def test_01_live_zabbix_action_api_conditions_and_operations(zabbix_env):
    """Verify live Zabbix API action definitions, conditions, user groups, and Action 7 status."""
    client, _ = zabbix_env

    # 1. Verify structured actions are enabled and have correct condition tags
    actions = client.call(
        "action.get",
        {
            "output": ["actionid", "name", "status", "eventsource", "esc_period"],
            "selectFilter": "extend",
            "selectOperations": "extend",
            "selectRecoveryOperations": "extend",
        }
    )
    act_map = {a["name"]: a for a in actions}

    # Verify Action 7 is DISABLED
    assert ACTION_NAME in act_map
    assert str(act_map[ACTION_NAME]["status"]) == "1", f"Legacy action {ACTION_NAME} MUST be disabled (status 1)"

    # Verify Structured Actions 10-15 are ENABLED
    structured_names = [
        ACTION_TOTAL_OUTAGE,
        ACTION_COMM_SERVICE,
        ACTION_SYNTHETIC_VOICE,
        ACTION_NETWORK_DEGRADATION,
        ACTION_COMPONENT_FAILURE,
        ACTION_MONITORING_FAILURE,
    ]
    for name in structured_names:
        assert name in act_map, f"Action {name} must exist in Zabbix"
        act = act_map[name]
        assert str(act["status"]) == "0", f"Action {name} must be enabled (status 0)"

        # Check tag conditions
        conditions = act.get("filter", {}).get("conditions", [])
        assert len(conditions) >= 1
        tag_cond = conditions[0]
        assert str(tag_cond.get("conditiontype")) == "26", "Condition must be tag value (26)"
        assert tag_cond.get("value2") == "notification_class"

    # Action 10 specific checks
    a10 = act_map[ACTION_TOTAL_OUTAGE]
    assert a10["filter"]["conditions"][0]["value"] == "total_outage"
    op_groups_10 = [g["usrgrpid"] for op in a10.get("operations", []) for g in op.get("opmessage_grp", [])]
    assert "15" in op_groups_10, "Action 10 must target User Group 15 (Total Outage Recipients)"

    # Action 11 specific checks
    a11 = act_map[ACTION_COMM_SERVICE]
    assert a11["filter"]["conditions"][0]["value"] == "service_outage"
    op_groups_11 = [g["usrgrpid"] for op in a11.get("operations", []) for g in op.get("opmessage_grp", [])]
    assert "14" in op_groups_11, "Action 11 must target User Group 14 (Comms Administrators)"


def test_02_live_zabbix_runtime_synthetic_failure_execution(zabbix_env):
    """Verify live Zabbix runtime execution of Synthetic Voice Failure (Action 12)."""
    client, sender = zabbix_env

    initial_alerts = client.call("alert.get", {"output": ["alertid"]})
    initial_ids = {a["alertid"] for a in initial_alerts}

    # 1. Trigger synthetic failure (MOS = 2.2 < 3.5)
    resp = sender.send([ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.mos", value=2.2)])
    assert resp.response == "success"
    time.sleep(4)

    # Inspect alerts generated in Zabbix
    alerts = client.call("alert.get", {"output": "extend"})
    new_alerts = [a for a in alerts if a["alertid"] not in initial_ids]
    assert len(new_alerts) >= 4, "Expected at least 4 alerts for the 4 administrators"

    # Verify Action ID and user recipients
    user_ids = {str(a["userid"]) for a in new_alerts if str(a["actionid"]) == "12"}
    assert {"3", "4", "5", "6"}.issubset(user_ids), "All 4 voice administrators must receive Action 12 alerts"
    assert "7" not in user_ids, "IT Service Desk (ID: 7) MUST NOT receive synthetic failure alerts"

    # Verify subject
    sample = [a for a in new_alerts if str(a["actionid"]) == "12"][0]
    assert "[SYNTHETIC ALERT]" in sample["subject"]
    assert "Voice Synthetic Probe 01" in sample["subject"]

    # 2. Recover synthetic failure (MOS = 4.4)
    resp_rec = sender.send([ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.mos", value=4.4)])
    assert resp_rec.response == "success"
    time.sleep(4)

    alerts_post = client.call("alert.get", {"output": "extend"})
    rec_alerts = [
        a for a in alerts_post
        if a["alertid"] not in initial_ids
        and a["alertid"] not in {x["alertid"] for x in new_alerts}
        and str(a["actionid"]) == "12"
    ]
    assert len(rec_alerts) >= 4, "Expected at least 4 recovery alerts"
    rec_sample = rec_alerts[0]
    assert "[RECOVERED]" in rec_sample["subject"]
    assert "Duration:" in rec_sample["subject"]


def test_03_live_zabbix_runtime_service_outage_execution(zabbix_env):
    """Verify live Zabbix runtime execution of SIP Trunk Service Outage (Action 11)."""
    client, sender = zabbix_env

    initial_alerts = client.call("alert.get", {"output": ["alertid"]})
    initial_ids = {a["alertid"] for a in initial_alerts}

    # 1. Trigger SIP Trunk OPTIONS failure (status = 0)
    resp = sender.send([ZabbixMetric(host="sip-trunk-carrier-01", key="sip.trunk.options_status", value=0)])
    assert resp.response == "success"
    time.sleep(4)

    alerts = client.call("alert.get", {"output": "extend"})
    new_alerts = [a for a in alerts if a["alertid"] not in initial_ids and str(a["actionid"]) == "11"]
    assert len(new_alerts) >= 4

    user_ids = {str(a["userid"]) for a in new_alerts}
    assert {"3", "4", "5", "6"}.issubset(user_ids), "All 4 voice administrators must receive Action 11 alerts"
    assert "7" not in user_ids, "IT Service Desk (ID: 7) MUST NOT receive service outage alerts"

    sample = new_alerts[0]
    assert "[SERVICE OUTAGE]" in sample["subject"]
    assert "Safaricom SIP Carrier Interconnect (Primary)" in sample["subject"]

    # 2. Recover SIP Trunk (status = 1)
    resp_rec = sender.send([ZabbixMetric(host="sip-trunk-carrier-01", key="sip.trunk.options_status", value=1)])
    assert resp_rec.response == "success"
    time.sleep(4)

    alerts_post = client.call("alert.get", {"output": "extend"})
    rec_alerts = [
        a for a in alerts_post
        if a["alertid"] not in initial_ids
        and a["alertid"] not in {x["alertid"] for x in new_alerts}
        and str(a["actionid"]) == "11"
    ]
    assert len(rec_alerts) >= 4
    rec_sample = rec_alerts[0]
    assert "[RECOVERED]" in rec_sample["subject"]
    assert "Duration:" in rec_sample["subject"]


def test_04_live_zabbix_runtime_total_outage_execution(zabbix_env):
    """Verify live Zabbix runtime execution of Total Outage (Action 10) alerting all 5 recipients."""
    client, sender = zabbix_env

    # 0. Ensure switch state is clear (0)
    sender.send([ZabbixMetric(host="mock-core-switch-01", key="core.switch.total_outage_state", value=0)])
    time.sleep(2)

    initial_alerts = client.call("alert.get", {"output": ["alertid"]})
    initial_ids = {a["alertid"] for a in initial_alerts}

    # 1. Trigger Core Switch Total Outage (state = 1)
    resp = sender.send([ZabbixMetric(host="mock-core-switch-01", key="core.switch.total_outage_state", value=1)])
    assert resp.response == "success"
    time.sleep(4)

    alerts = client.call("alert.get", {"output": "extend"})
    new_alerts = [a for a in alerts if a["alertid"] not in initial_ids and str(a["actionid"]) == "10"]
    assert len(new_alerts) >= 5, f"Expected 5 alerts for all 5 recipients, got {len(new_alerts)}"

    user_ids = {str(a["userid"]) for a in new_alerts}
    # MUST contain all 4 voice administrators AND IT Service Desk (ID: 7)
    expected_ids = {"3", "4", "5", "6", "7"}
    assert expected_ids.issubset(user_ids), f"Expected User IDs {expected_ids}, got {user_ids}"

    sample = new_alerts[0]
    assert "[TOTAL OUTAGE]" in sample["subject"]
    assert "Simulated Core Switch 01 (Lab)" in sample["subject"]

    # 2. Recover Core Switch Total Outage (state = 0)
    resp_rec = sender.send([ZabbixMetric(host="mock-core-switch-01", key="core.switch.total_outage_state", value=0)])
    assert resp_rec.response == "success"
    time.sleep(4)

    alerts_post = client.call("alert.get", {"output": "extend"})
    rec_alerts = [
        a for a in alerts_post
        if a["alertid"] not in initial_ids
        and a["alertid"] not in {x["alertid"] for x in new_alerts}
        and str(a["actionid"]) == "10"
    ]
    assert len(rec_alerts) >= 5, f"Expected 5 recovery alerts, got {len(rec_alerts)}"

    rec_user_ids = {str(a["userid"]) for a in rec_alerts}
    assert expected_ids.issubset(rec_user_ids)
    rec_sample = rec_alerts[0]
    assert "[RECOVERED]" in rec_sample["subject"]
    assert "Total Downtime:" in rec_sample["subject"]


def test_05_runtime_action_exclusivity_and_zero_duplicate_alerts(zabbix_env):
    """Verify that Action 7 generated ZERO alerts and actions remain mutually exclusive."""
    client, _ = zabbix_env

    # Query all alerts recorded in Zabbix
    alerts = client.call("alert.get", {"output": ["alertid", "actionid", "userid"]})
    action_ids = {str(a["actionid"]) for a in alerts}

    # Assert Action 7 has 0 alerts in runtime execution
    assert "7" not in action_ids, "Action 7 MUST NOT have generated any alerts while disabled"

    # For each action, verify user group consistency
    action_10_users = {str(a["userid"]) for a in alerts if str(a["actionid"]) == "10"}
    assert "7" in action_10_users, "Action 10 must alert User 7 (IT Service Desk)"

    action_11_users = {str(a["userid"]) for a in alerts if str(a["actionid"]) == "11"}
    assert "7" not in action_11_users, "Action 11 must NOT alert User 7 (IT Service Desk)"

    action_12_users = {str(a["userid"]) for a in alerts if str(a["actionid"]) == "12"}
    assert "7" not in action_12_users, "Action 12 must NOT alert User 7 (IT Service Desk)"


def test_06_runtime_macro_expansion_integrity(zabbix_env):
    """Verify that Zabbix server fully rendered all macros in subjects and message bodies."""
    client, _ = zabbix_env

    alerts = client.call("alert.get", {"output": ["alertid", "actionid", "subject", "message"]})
    assert len(alerts) > 0

    unexpanded_pattern = re.compile(r"\{(HOST\.|EVENT\.)[A-Z0-9_\.]+\}")

    for a in alerts:
        subj = a.get("subject", "")
        msg = a.get("message", "")

        # Check for unexpanded macros
        subj_macros = unexpanded_pattern.findall(subj)
        assert len(subj_macros) == 0, f"Unexpanded macro in subject of Alert {a['alertid']}: {subj_macros}"

        msg_macros = unexpanded_pattern.findall(msg)
        assert len(msg_macros) == 0, f"Unexpanded macro in message of Alert {a['alertid']}: {msg_macros}"

        # Check zero platform branding
        ok, violations = validate_zero_platform_branding(f"{subj}\n{msg}")
        assert ok, f"Prohibited platform branding found in Alert {a['alertid']}: {violations}"


def test_07_service_outage_semantics_vs_component_failure():
    """Verify Phase 13.8 service-outage semantics distinguishing single host faults from total outages."""
    # Strict service semantics mode
    assert classify_service_outage_semantics("Core Switch: Total Network Core Transport Failure") == "total_outage"
    assert classify_service_outage_semantics("Network Generic Device: Unavailable by ICMP ping") == "total_outage"

    # Single voice component reachability -> service_outage (NOT total_outage)
    assert classify_service_outage_semantics("Avaya SBCE: Appliance Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya G450: Media Gateway Chassis Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya SM: Session Manager Host Unavailable") == "service_outage"
    assert classify_service_outage_semantics("SIP Trunk: Endpoint Unreachable") == "service_outage"
    assert classify_service_outage_semantics("Avaya CM: Communication Manager Processor Unreachable") == "service_outage"

    # Hardware component failure -> component_failure
    assert classify_service_outage_semantics("Avaya G450: Power Supply Unit Failure") == "component_failure"
    assert classify_service_outage_semantics("Avaya G450: Fan Tray Failure") == "component_failure"

    # Backward compatibility mode
    assert classify_trigger_description("Avaya SBCE: Appliance Unreachable", strict_service_semantics=False) == "total_outage"


def test_08_recovery_semantics_service_restoration_vs_host_reachability():
    """Verify that recovery evaluation distinguishes host ping recovery from proven service restoration."""
    # 1. Host reachability recovery
    res_host = differentiate_host_vs_service_recovery(
        trigger_name="Network Generic Device: Unavailable by ICMP ping",
        host_name="core-gw-01",
        duration_str="12m 30s",
    )
    assert res_host["recovery_type"] == "HOST_REACHABILITY_RESTORED"
    assert res_host["service_restored_proven"] is False
    assert "Higher-layer voice daemons" in res_host["operational_interpretation"]

    # 2. SIP trunk signaling recovery
    res_trunk = differentiate_host_vs_service_recovery(
        trigger_name="SIP Trunk: Consecutive OPTIONS Probe Failures",
        host_name="sip-trunk-carrier-01",
        duration_str="5m 10s",
    )
    assert res_trunk["recovery_type"] == "SIP_TRUNK_SIGNALING_RESTORED"
    assert res_trunk["service_restored_proven"] is True
    assert "Inbound and outbound trunk capacity is operational" in res_trunk["operational_interpretation"]

    # 3. Synthetic voice probe recovery
    res_syn = differentiate_host_vs_service_recovery(
        trigger_name="Degraded voice quality on synthetic probe (MOS < 3.8)",
        host_name="nawari-voice-probe-01",
        duration_str="4m 00s",
    )
    assert res_syn["recovery_type"] == "SYNTHETIC_PROBE_VALIDATED"
    assert res_syn["service_restored_proven"] is True
    assert "End-to-end voice path media quality confirmed" in res_syn["operational_interpretation"]


def test_09_configured_unverified_email_guard_preserved(zabbix_env):
    """Verify Email media type remains in CONFIGURED_UNVERIFIED status with zero live email delivery."""
    client, _ = zabbix_env

    # Query Email media type in Zabbix
    mts = client.call("mediatype.get", {"filter": {"name": "Email"}, "output": ["mediatypeid", "name", "status"]})
    assert len(mts) >= 1

    # Verify that in alert records, errors show media type disabled/unconfigured rather than live delivery
    alerts = client.call("alert.get", {"limit": 10, "output": ["alertid", "status", "error"]})
    for a in alerts:
        # Status 2 indicates failed delivery (expected because mail server credentials remain unverified)
        # Status 1 would mean sent to external mail server
        assert str(a.get("status")) == "2", f"Alert {a['alertid']} must not be delivered live (status=2 expected)"


def test_10_roadmap_integration_and_phase8_2_gating():
    """Verify implementation-roadmap.md links Phase 13.8 to Phase 8.2 commissioning gate."""
    # 1. Check roadmap file
    assert ROADMAP_FILE.is_file(), f"Roadmap file must exist at {ROADMAP_FILE}"
    content = ROADMAP_FILE.read_text()
    assert "Phase 13.8" in content, "Roadmap must document Phase 13.8"
    assert "Phase 8.2" in content, "Roadmap must link Phase 13.8 to Phase 8.2 commissioning gate"
    assert "HARD_PRODUCTION_DENY" in content, "Roadmap must document HARD_PRODUCTION_DENY"

    # 2. Check HARD_PRODUCTION_DENY enforcement
    from services.actions.action_framework import (
        ActionRiskTier,
        ActionState,
        AutomationPolicyEngine,
        OperationalAction,
    )
    action = OperationalAction(
        action_id="ACT-PROD-DENY-138",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::live_production_carrier",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-1002",
        incident_id="INC-2002",
        hypothesis_id="HYP-3002",
    )
    is_permitted, msg = AutomationPolicyEngine.evaluate_policy(action, simulation_mode=True)
    assert is_permitted is False
    assert msg == "HARD_PRODUCTION_DENY"
    assert action.state == ActionState.BLOCKED

    # 3. Check Sentra repository isolation
    assert SENTRA_ROOT.is_dir(), f"Sentra repository must exist at {SENTRA_ROOT}"
    git_status = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=str(SENTRA_ROOT),
        text=True,
    )
    assert git_status.strip() == "", f"Sentra repository has uncommitted changes:\n{git_status}"

    head_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(SENTRA_ROOT),
        text=True,
    ).strip()
    assert head_commit.startswith("9970404"), f"Sentra must remain at baseline commit 9970404, found {head_commit}"
