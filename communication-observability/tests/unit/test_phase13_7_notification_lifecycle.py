"""
tests/unit/test_phase13_7_notification_lifecycle.py

Automated unit test suite for Nawari Phase 13.7:
Notification Lifecycle Validation and Incident Communication Acceptance.

Verifies:
1. Scenario A: Total Network Outage (mock-core-switch-01 / core-gw-01 -> 5 recipients, correct subject, operational language).
2. Scenario B: Total Communications Outage (avaya-sbce-01 / sm / cm / g450 -> 5 recipients).
3. Scenario C: SIP Trunk Outage (sip-trunk-carrier-01 -> 4 voice admins, Service Desk excluded).
4. Scenario D: Monitoring Failure (SNMP agent down / telemetry stale -> technical team only, Service Desk excluded).
5. Scenario E: Component Failure (PSU failure / fan / interface -> technical team only, Service Desk excluded).
6. Scenario F: Synthetic Voice Failure (Asterisk synthetic test failure / MOS < 3.5 -> 4 voice admins, labeled synthetic).
7. Scenario G: 30-Minute Escalation (repeat step 2..0 every 1800s, {EVENT.AGE} macro, zero duplicates).
8. Scenario H: Recovery Notification ({EVENT.DURATION} monitoring-observed downtime, 5 recipients).
9. Scenario I: Repeated Outage (independent event IDs and durations, no state leakage).
10. Scenario J: Acknowledgment and Maintenance Suppression (acknowledged outage recovers; maintenance suppresses).
11. Zero Platform Branding across all templates and generated messages (no 'Nawari', 'Zabbix', 'Grafana').
12. Action Mutual Exclusivity and Zero Duplicate Notifications (exactly 1 active action matches any event).
13. Monitoring-Observed Downtime vs Physical Outage Timeline quantification.
14. Production Boundary Security (HARD_PRODUCTION_DENY) and Sentra repository isolation (commit 9970404).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
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
)
from services.testing.notification_capture_harness import (
    NotificationCaptureHarness,
    SimulatedZabbixEvent,
    calculate_downtime_delta,
    format_zabbix_duration,
    format_zabbix_timestamp,
    validate_zero_platform_branding,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"

BASE_TIMESTAMP = 1799400000  # Deterministic reference epoch: 2027.01.01 04:00:00 UTC


def test_01_scenario_a_total_network_outage_five_recipients():
    """Verify Scenario A: Total network outage targets exactly 5 recipients with generic operational language."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-1001",
        clock=BASE_TIMESTAMP,
        host_name="mock-core-switch-01",
        host_groups=["Network Infrastructure", "Core Switching"],
        trigger_name="mock-core-switch-01: Device unreachable by ICMP ping",
        severity=5,  # Disaster
        opdata="0% packet reply",
        tags={"notification_class": "total_outage", "target": "network_core"},
    )

    notifications = harness.dispatch_problem("Scenario_A", event, step=1)
    assert len(notifications) == 1, "Exactly one action must match Scenario A"

    n = notifications[0]
    assert n.action_name == ACTION_TOTAL_OUTAGE
    assert len(n.recipients) == 5, f"Expected 5 recipients, got {len(n.recipients)}"

    # Check recipient emails
    expected_emails = {
        "John.Gacomo@kenya-airways.com",
        "Robinson.Wainaina@kenya-airways.com",
        "Pascal.Gathungu@kenya-airways.com",
        "Mercy.Vaati@kenya-airways.com",
        "ITservicedesk@kenya-airways.com",
    }
    assert set(n.recipients) == expected_emails

    # Subject and body checks
    assert n.subject == "[TOTAL OUTAGE] — mock-core-switch-01 — mock-core-switch-01: Device unreachable by ICMP ping"
    assert "Affected Device/Service: mock-core-switch-01" in n.body
    assert "Severity: Disaster" in n.body
    assert "Status: OUTAGE IN PROGRESS" in n.body
    assert "Please investigate and take the necessary action to restore normal operations" in n.body

    # Zero platform branding
    ok, violations = validate_zero_platform_branding(n.subject + "\n" + n.body)
    assert ok, f"Zero branding violation found: {violations}"


def test_02_scenario_b_total_communications_outage_avaya_hosts():
    """Verify Scenario B: Total communications outage on Avaya core systems dispatches to 5 recipients."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    avaya_devices = [
        ("avaya-sbce-01", "Avaya SBCE: SBC Appliance Unreachable"),
        ("avaya-sm-01", "Avaya SM: Session Manager Host Unavailable"),
        ("avaya-cm-01", "Avaya CM: Communication Manager Processor Unreachable"),
        ("avaya-g450-01", "Avaya G450: Media Gateway Chassis Unreachable"),
    ]

    for host, trigger in avaya_devices:
        event = SimulatedZabbixEvent(
            event_id=f"EV-{host}",
            clock=BASE_TIMESTAMP,
            host_name=host,
            host_groups=["Avaya Infrastructure", "Voice Infrastructure"],
            trigger_name=trigger,
            severity=5,
            opdata="ICMP check failed (3 consecutive attempts)",
            tags={"notification_class": "total_outage", "vendor": "avaya"},
        )

        notifications = harness.dispatch_problem(f"Scenario_B_{host}", event, step=1)
        assert len(notifications) == 1, f"Expected exactly 1 notification for {host}"

        n = notifications[0]
        assert n.action_name == ACTION_TOTAL_OUTAGE
        assert len(n.recipients) == 5, f"Expected 5 recipients for {host}"
        assert "ITservicedesk@kenya-airways.com" in n.recipients
        assert "John.Gacomo@kenya-airways.com" in n.recipients

        # Mutual exclusivity: Action 7 must NOT match
        assert n.action_name != ACTION_NAME


def test_03_scenario_c_sip_trunk_outage_service_desk_excluded():
    """Verify Scenario C: SIP trunk outage targets 4 voice admins, strictly excluding Service Desk."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-TRUNK-01",
        clock=BASE_TIMESTAMP,
        host_name="sip-trunk-carrier-01",
        host_groups=["SIP Carrier Trunks", "Voice Infrastructure"],
        trigger_name="SIP Trunk Carrier: SIP entity down",
        severity=4,  # High
        opdata="OPTIONS ping timeout (503 Service Unavailable)",
        tags={"notification_class": "service_outage", "scope": "trunk"},
    )

    notifications = harness.dispatch_problem("Scenario_C", event, step=1)
    assert len(notifications) == 1

    n = notifications[0]
    assert n.action_name == ACTION_COMM_SERVICE
    assert len(n.recipients) == 4, f"Expected 4 voice admins, got {len(n.recipients)}"

    # Service Desk MUST NOT be notified for SIP trunk outage
    assert "ITservicedesk@kenya-airways.com" not in n.recipients
    assert "itservicedesk" not in n.recipient_usernames

    assert n.subject == "[SERVICE OUTAGE] — sip-trunk-carrier-01 — SIP Trunk Carrier: SIP entity down"
    assert "Affected Service: sip-trunk-carrier-01" in n.body
    assert "Status: SERVICE OUTAGE IN PROGRESS" in n.body

    # Must NOT declare unrelated network or hardware is down
    assert "total outage" not in n.body.lower()
    assert "device unreachable" not in n.body.lower()


def test_04_scenario_d_monitoring_failure_technical_team_only():
    """Verify Scenario D: SNMP telemetry failure targets technical team only; voice admins & Service Desk excluded."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-MON-01",
        clock=BASE_TIMESTAMP,
        host_name="avaya-cm-01",
        host_groups=["Avaya Infrastructure"],
        trigger_name="SNMP agent is not responding on avaya-cm-01",
        severity=2,  # Warning
        opdata="No response to get-request for 300s",
        tags={"notification_class": "monitoring_failure", "scope": "telemetry"},
    )

    notifications = harness.dispatch_problem("Scenario_D", event, step=1)
    assert len(notifications) == 1

    n = notifications[0]
    assert n.action_name == ACTION_MONITORING_FAILURE
    assert "noc-infrastructure@kenya-airways.com" in n.recipients

    # Voice admins and Service Desk must NOT receive monitoring failures
    for admin in DESIGNATED_ADMINISTRATORS:
        assert admin["email"] not in n.recipients
    assert "ITservicedesk@kenya-airways.com" not in n.recipients

    assert n.subject == "[MONITORING FAILURE] — avaya-cm-01 — SNMP agent is not responding on avaya-cm-01"
    assert "Status: TELEMETRY COLLECTION FAILURE" in n.body
    assert "Underlying device may remain operational; telemetry retrieval has stalled" in n.body


def test_05_scenario_e_component_failure_technical_team_only():
    """Verify Scenario E: Component failure targets technical team; Service Desk excluded."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-COMP-01",
        clock=BASE_TIMESTAMP,
        host_name="core-gw-01",
        host_groups=["Network Infrastructure"],
        trigger_name="Power supply unit 2 failure on core-gw-01",
        severity=2,  # Warning
        opdata="PSU 2 voltage 0V (PSU 1 nominal)",
        tags={"notification_class": "component_failure", "hardware": "psu"},
    )

    notifications = harness.dispatch_problem("Scenario_E", event, step=1)
    assert len(notifications) == 1

    n = notifications[0]
    assert n.action_name == ACTION_COMPONENT_FAILURE
    assert "noc-infrastructure@kenya-airways.com" in n.recipients
    assert "ITservicedesk@kenya-airways.com" not in n.recipients

    assert n.subject == "[COMPONENT FAILURE] — core-gw-01 — Power supply unit 2 failure on core-gw-01"
    assert "Status: COMPONENT FAILURE" in n.body


def test_06_scenario_f_synthetic_voice_failure_probe_labeled():
    """Verify Scenario F: Synthetic probe failure is explicitly labeled and sent to 4 voice admins."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-SYN-01",
        clock=BASE_TIMESTAMP,
        host_name="nawari-voice-probe-01",
        host_groups=["Synthetic Probes", "Voice Infrastructure"],
        trigger_name="Synthetic Voice Probe: MOS below threshold 3.5",
        severity=3,  # Average
        opdata="Calculated MOS: 2.84, Jitter: 42ms, Packet Loss: 8.5%",
        tags={"notification_class": "synthetic_failure", "scope": "synthetic"},
    )

    notifications = harness.dispatch_problem("Scenario_F", event, step=1)
    assert len(notifications) == 1

    n = notifications[0]
    assert n.action_name == ACTION_SYNTHETIC_VOICE
    assert len(n.recipients) == 4
    assert "ITservicedesk@kenya-airways.com" not in n.recipients

    assert n.subject == "[SYNTHETIC ALERT] — nawari-voice-probe-01 — Synthetic Voice Probe: MOS below threshold 3.5"
    assert "Probe Target: nawari-voice-probe-01" in n.body
    assert "Status: SYNTHETIC TEST FAILURE" in n.body
    assert "Please inspect synthetic probe metrics and verify voice path integrity" in n.body


def test_07_scenario_g_prolonged_outage_30m_escalation_age_macro():
    """Verify Scenario G: 30-minute escalation evaluates {EVENT.AGE} macro and dispatches escalation."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    event = SimulatedZabbixEvent(
        event_id="EV-ESC-01",
        clock=BASE_TIMESTAMP,
        host_name="core-gw-01",
        host_groups=["Network Infrastructure"],
        trigger_name="core-gw-01: Device unreachable by ICMP ping",
        severity=5,
        opdata="100% packet loss",
        tags={"notification_class": "total_outage"},
    )

    # Step 1: Initial alert at T0
    p1 = harness.dispatch_problem("Scenario_G", event, step=1, current_clock=BASE_TIMESTAMP)
    assert len(p1) == 1
    assert p1[0].operation_type == "PROBLEM"

    # Step 2: Escalation alert at T0 + 1800s (30 minutes)
    escalation_clock = BASE_TIMESTAMP + 1800
    p2 = harness.dispatch_problem("Scenario_G", event, step=2, current_clock=escalation_clock)
    assert len(p2) == 1
    esc = p2[0]

    assert esc.operation_type == "ESCALATION"
    assert esc.action_name == ACTION_TOTAL_OUTAGE
    assert len(esc.recipients) == 5

    # Check macro evaluation
    assert esc.subject == "[TOTAL OUTAGE ESCALATION] — core-gw-01 — core-gw-01: Device unreachable by ICMP ping — Duration: 30m"
    assert "Current Duration: 30m" in esc.body
    assert "Status: OUTAGE UNRESOLVED (ESCALATION)" in esc.body
    assert "Please escalate immediately to the designated duty manager" in esc.body


def test_08_scenario_h_recovery_notification_duration_and_recipients():
    """Verify Scenario H: Recovery notification computes {EVENT.DURATION} and delivers to 5 recipients."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    start_clock = BASE_TIMESTAMP
    recovery_clock = BASE_TIMESTAMP + 1470  # 24 minutes 30 seconds

    event = SimulatedZabbixEvent(
        event_id="EV-REC-01",
        clock=start_clock,
        recovery_clock=recovery_clock,
        recovery_event_id="REC-EV-REC-01",
        host_name="avaya-sbce-01",
        host_groups=["Avaya Infrastructure", "Edge SBC"],
        trigger_name="Avaya SBCE: SBC Appliance Unreachable",
        severity=5,
        opdata="0% reply",
        tags={"notification_class": "total_outage"},
    )

    recoveries = harness.dispatch_recovery("Scenario_H", event)
    assert len(recoveries) == 1

    rec = recoveries[0]
    assert rec.action_name == ACTION_TOTAL_OUTAGE
    assert len(rec.recipients) == 5
    assert set(rec.recipients) == {
        "John.Gacomo@kenya-airways.com",
        "Robinson.Wainaina@kenya-airways.com",
        "Pascal.Gathungu@kenya-airways.com",
        "Mercy.Vaati@kenya-airways.com",
        "ITservicedesk@kenya-airways.com",
    }

    # Macro {EVENT.DURATION} check
    assert rec.subject == "[RECOVERED] — avaya-sbce-01 — Total Downtime: 24m 30s"
    assert "Total Downtime: 24m 30s" in rec.body
    assert "Status: RECOVERED" in rec.body
    assert "Original Issue: Avaya SBCE: SBC Appliance Unreachable" in rec.body
    assert "The affected device or service is responding again and has returned to an operational state" in rec.body
    assert "Please review the incident and establish the underlying cause where necessary" in rec.body


def test_09_scenario_i_repeated_outage_distinct_events_and_durations():
    """Verify Scenario I: Consecutive outages generate distinct event IDs and independent durations."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    # First Outage: 15 minutes
    t1_start = BASE_TIMESTAMP
    t1_end = BASE_TIMESTAMP + 900
    ev1 = SimulatedZabbixEvent(
        event_id="EV-CYCLE-01",
        clock=t1_start,
        recovery_clock=t1_end,
        recovery_event_id="REC-01",
        host_name="core-gw-01",
        host_groups=["Network Infrastructure"],
        trigger_name="core-gw-01: Device unreachable by ICMP ping",
        severity=5,
        opdata="100% loss",
        tags={"notification_class": "total_outage"},
    )
    r1 = harness.dispatch_recovery("Scenario_I_1", ev1)[0]
    assert r1.event_id == "EV-CYCLE-01"
    assert r1.monitoring_duration_str == "15m"
    assert "Total Downtime: 15m" in r1.body

    # Second Outage: 42 minutes (occurs 3 hours later)
    t2_start = BASE_TIMESTAMP + 10800
    t2_end = t2_start + 2520
    ev2 = SimulatedZabbixEvent(
        event_id="EV-CYCLE-02",
        clock=t2_start,
        recovery_clock=t2_end,
        recovery_event_id="REC-02",
        host_name="core-gw-01",
        host_groups=["Network Infrastructure"],
        trigger_name="core-gw-01: Device unreachable by ICMP ping",
        severity=5,
        opdata="100% loss",
        tags={"notification_class": "total_outage"},
    )
    r2 = harness.dispatch_recovery("Scenario_I_2", ev2)[0]
    assert r2.event_id == "EV-CYCLE-02"
    assert r2.event_id != r1.event_id
    assert r2.monitoring_duration_str == "42m"
    assert "Total Downtime: 42m" in r2.body


def test_10_scenario_j_acknowledgment_and_maintenance_suppression():
    """Verify Scenario J: Acknowledged problems still dispatch recovery; maintenance suppresses alerts."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    # Case J1: Acknowledgment
    ev_ack = SimulatedZabbixEvent(
        event_id="EV-ACK-01",
        clock=BASE_TIMESTAMP,
        recovery_clock=BASE_TIMESTAMP + 600,
        host_name="mock-core-switch-01",
        host_groups=["Network Infrastructure"],
        trigger_name="mock-core-switch-01: Device unreachable by ICMP ping",
        severity=5,
        opdata="100% loss",
        tags={"notification_class": "total_outage"},
        acknowledged=True,
    )
    rec_ack = harness.dispatch_recovery("Scenario_J_Ack", ev_ack)
    assert len(rec_ack) == 1, "Recovery notification MUST be dispatched even if acknowledged"
    assert len(rec_ack[0].recipients) == 5

    # Case J2: Maintenance Suppression
    ev_maint = SimulatedZabbixEvent(
        event_id="EV-MAINT-01",
        clock=BASE_TIMESTAMP,
        host_name="mock-core-switch-01",
        host_groups=["Network Infrastructure"],
        trigger_name="mock-core-switch-01: Device unreachable by ICMP ping",
        severity=5,
        opdata="100% loss",
        tags={"notification_class": "total_outage"},
        maintenance=True,
    )
    prob_maint = harness.dispatch_problem("Scenario_J_Maint", ev_maint, step=1)
    assert len(prob_maint) == 0, "Alerts MUST be suppressed when host is in maintenance"


def test_11_zero_platform_branding_across_all_templates_and_scenarios():
    """Verify ZERO monitoring engine branding appears in any rendered subject or message body."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    # Run full scenario battery
    test_events = [
        SimulatedZabbixEvent("1", BASE_TIMESTAMP, "host-a", ["Network Infrastructure"], "Trigger A", 5, "op", {"notification_class": "total_outage"}),
        SimulatedZabbixEvent("2", BASE_TIMESTAMP, "host-b", ["Voice Infrastructure"], "Trigger B", 4, "op", {"notification_class": "service_outage"}),
        SimulatedZabbixEvent("3", BASE_TIMESTAMP, "host-c", ["Synthetic Probes"], "Trigger C", 3, "op", {"notification_class": "synthetic_failure"}),
        SimulatedZabbixEvent("4", BASE_TIMESTAMP, "host-d", ["Network Infrastructure"], "Trigger D", 2, "op", {"notification_class": "degradation"}),
        SimulatedZabbixEvent("5", BASE_TIMESTAMP, "host-e", ["Network Infrastructure"], "Trigger E", 2, "op", {"notification_class": "component_failure"}),
        SimulatedZabbixEvent("6", BASE_TIMESTAMP, "host-f", ["Avaya Infrastructure"], "Trigger F", 2, "op", {"notification_class": "monitoring_failure"}),
    ]

    for ev in test_events:
        harness.dispatch_problem("Test", ev, step=1)
        harness.dispatch_problem("Test", ev, step=2, current_clock=BASE_TIMESTAMP + 1800)
        ev.recovery_clock = BASE_TIMESTAMP + 1200
        harness.dispatch_recovery("Test", ev)

    assert len(harness.captured_notifications) > 0

    for notif in harness.captured_notifications:
        combined_text = f"{notif.subject}\n{notif.body}"
        ok, violations = validate_zero_platform_branding(combined_text)
        assert ok, f"Prohibited platform branding found in {notif.action_name} ({notif.operation_type}): {violations}"


def test_12_mutual_exclusivity_zero_duplicate_action_matches():
    """Verify that every event class matches EXACTLY ONE action, and Action 7 is retired."""
    harness = NotificationCaptureHarness(retire_legacy_action=True)

    classes = [
        "total_outage",
        "service_outage",
        "synthetic_failure",
        "degradation",
        "component_failure",
        "monitoring_failure",
    ]

    for c in classes:
        ev = SimulatedZabbixEvent(
            event_id=f"EV-{c}",
            clock=BASE_TIMESTAMP,
            host_name="test-host",
            host_groups=["Avaya Infrastructure", "Voice Infrastructure", "Network Infrastructure"],
            trigger_name=f"Sample trigger for {c}",
            severity=5,
            opdata="nominal",
            tags={"notification_class": c},
        )
        matched = harness.match_actions_for_event(ev)
        assert len(matched) == 1, f"Class {c} matched {len(matched)} actions, expected exactly 1!"

    # Verify in live Zabbix API that Action 7 has status 1 (disabled)
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()
    actions = client.call("action.get", {"filter": {"name": ACTION_NAME}})
    assert len(actions) == 1
    assert str(actions[0]["status"]) == "1", "Legacy Action 7 MUST be disabled in live Zabbix API"

    # Verify structured actions are enabled
    structured = client.call(
        "action.get",
        {"filter": {"name": [
            ACTION_TOTAL_OUTAGE,
            ACTION_COMM_SERVICE,
            ACTION_SYNTHETIC_VOICE,
            ACTION_NETWORK_DEGRADATION,
            ACTION_COMPONENT_FAILURE,
            ACTION_MONITORING_FAILURE,
        ]}}
    )
    assert len(structured) == 6
    for a in structured:
        assert str(a["status"]) == "0", f"Action {a['name']} must be enabled (status 0)"


def test_13_monitoring_observed_downtime_vs_real_outage_timeline():
    """Verify monitoring-observed downtime calculations and explain detection/recovery delta."""
    # Physical outage: 10:00:00 to 10:10:00 (600s)
    # ICMP ping interval: 10s, 3 failures needed = 30s detection delay
    # Recovery poll interval: 10s = 10s recovery delay
    delta_data = calculate_downtime_delta(
        real_outage_start=BASE_TIMESTAMP,
        real_outage_end=BASE_TIMESTAMP + 600,
        poll_interval_seconds=10,
        consecutive_failures_required=3,
        recovery_poll_interval_seconds=10,
    )

    assert delta_data["real_duration_seconds"] == 600
    assert delta_data["real_duration_str"] == "10m"
    assert delta_data["detection_delay_seconds"] == 30
    assert delta_data["recovery_delay_seconds"] == 10
    assert delta_data["observed_duration_seconds"] == 580
    assert delta_data["observed_duration_str"] == "9m 40s"
    assert delta_data["delta_seconds"] == -20  # Under-reported by 20s due to 30s confirmation window


def test_14_production_boundary_and_sentra_isolation():
    """Verify HARD_PRODUCTION_DENY remains strictly locked and Sentra repository is untouched at 9970404."""
    # 1. HARD_PRODUCTION_DENY check via AutomationPolicyEngine
    from services.actions.action_framework import (
        ActionRiskTier,
        ActionState,
        AutomationPolicyEngine,
        OperationalAction,
    )
    action = OperationalAction(
        action_id="ACT-PROD-DENY",
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

    # 2. HARD_PRODUCTION_DENY check via Packaging
    from services.multisite.packaging import DeploymentProfileManager
    mgr = DeploymentProfileManager()
    res_prod = mgr.validate_deployment_eligibility("single-site-production", is_phase_8_2_certified=False)
    assert res_prod["status"] == "HARD_PRODUCTION_DENY"
    assert res_prod["allowed"] is False

    # 3. Sentra Isolation check
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
