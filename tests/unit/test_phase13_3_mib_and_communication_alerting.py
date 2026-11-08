"""
tests/unit/test_phase13_3_mib_and_communication_alerting.py

Automated unit test suite for Nawari Phase 13.3:
1. Avaya Communication Manager MIB Conformance & Hourly Telemetry Semantics (.67 vs .77/.66, .145 call rates, .5 alarms).
2. G450 Hardware & Discrete Thermal Trap Model (0=UNKNOWN, 1=CLEARED, 2=WARNING, MP20/MP80/MP120/MP160 modules).
3. Communication Alert Catalogue & Evaluation Engine (43 rules, deduplication, cooldown, 3-cycle recovery).
4. Microsoft 365 Email Notification Provider (STARTTLS, Modern Auth abstraction, secret masking, templates).
5. Dashboard Description Assurance (100% of 200 panels have complete descriptions including missing data).
"""

import json
from pathlib import Path
import pytest
import yaml

from services.alerting.models import (
    AlertEvidence,
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertState,
)
from services.alerting.communication_alert_catalogue import (
    COMMUNICATION_ALERT_RULES,
)
from services.alerting.communication_alert_engine import (
    CommunicationAlertEngine,
)
from services.integrations.m365_email_provider import (
    M365AuthMode,
    M365Config,
    M365EmailProvider,
    ProviderStatus,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = ROOT_DIR / "provisioning/zabbix/templates"
GRAFANA_DASHBOARDS_DIR = ROOT_DIR / "docker/grafana/dashboards"
DOCS_MONITORING_DIR = ROOT_DIR / "docs/monitoring"


def test_01_communication_manager_official_mib67_conformance():
    """Verify CM template uses official MIB .67 for hourly IP voice statistics."""
    cm_file = TEMPLATES_DIR / "template_nawari_avaya_cm.yaml"
    assert cm_file.is_file()
    with open(cm_file) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    # Hourly voice statistics must reside under .67 (avCmMeasIpVoStatHrData)
    loss_item = items["avaya.cm.ip_voice.loss_pct"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.67" in loss_item["snmp_oid"]
    assert loss_item["delay"] in ("1h", "3600s", "3600")

    peak_jitter = items["avaya.cm.ip_voice.peak_jitter"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.67" in peak_jitter["snmp_oid"]
    assert peak_jitter["delay"] in ("1h", "3600s", "3600")

    peak_delay = items["avaya.cm.ip_voice.peak_delay"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.67" in peak_delay["snmp_oid"]
    assert peak_delay["delay"] in ("1h", "3600s", "3600")

    codec = items["avaya.cm.ip_voice.codec"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.67" in codec["snmp_oid"]
    assert codec["delay"] in ("1h", "3600s", "3600")

    # Alarms must reside under .5 (avCmAlarmsTable) with delay >= 1h
    alarms = items["avaya.cm.alarms.active_count"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.5" in alarms["snmp_oid"]
    assert alarms["delay"] in ("1h", "3600s", "3600")

    # Call rate must reside under .145 with delay 5m and hourly measurement interval semantics
    completed = items["avaya.cm.call_rate.completed"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.145" in completed["snmp_oid"]
    assert completed["delay"] in ("5m", "300s", "300")
    assert "hourly measurement block" in completed["description"].lower()


def test_02_g450_discrete_thermal_events_and_hardware_modules():
    """Verify G450 thermal item has explicit UNKNOWN, CLEARED, WARNING states with no critical state."""
    g450_file = TEMPLATES_DIR / "template_nawari_avaya_g450.yaml"
    assert g450_file.is_file()
    with open(g450_file) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    temp_item = items["avaya.g450.temperature"]
    assert temp_item["type"] == "TRAP"
    assert temp_item["value_type"] == "UNSIGNED"
    desc = temp_item["description"]
    assert "0 = UNKNOWN" in desc
    assert "1 = CLEARED" in desc
    assert "2 = WARNING" in desc
    assert "continuous analog" in desc.lower()

    # Verify triggers for thermal warning
    triggers = temp_item.get("triggers", [])
    assert len(triggers) >= 1
    assert any("=2" in t["expression"] for t in triggers)


def test_03_communication_alert_catalogue_coverage():
    """Verify Communication Alert Catalogue defines required alert rules across all subsystems."""
    rules = {r.alert_id: r for r in COMMUNICATION_ALERT_RULES}
    assert len(rules) >= 40

    # A. SBCE
    sbce_ids = [k for k in rules if "ALERT-SBCE" in k]
    assert len(sbce_ids) >= 7
    assert "ALERT-SBCE-001" in rules  # reachability
    assert "ALERT-SBCE-003" in rules  # failure rate
    assert "ALERT-SBCE-005" in rules  # license capacity

    # B. Session Manager
    sm_ids = [k for k in rules if "ALERT-ASM" in k]
    assert len(sm_ids) >= 8
    assert "ALERT-ASM-002" in rules   # entity down
    assert "ALERT-ASM-005" in rules   # synthetic options probe

    # C. Communication Manager
    cm_ids = [k for k in rules if "ALERT-CM" in k]
    assert len(cm_ids) >= 6
    assert "ALERT-CM-003" in rules    # packet loss

    # D. G450 Media Gateway
    g450_ids = [k for k in rules if "ALERT-G450" in k]
    assert len(g450_ids) >= 6
    assert "ALERT-G450-002" in rules  # thermal trap warning

    # E. SIP Trunks
    sip_ids = [k for k in rules if "ALERT-SIP" in k]
    assert len(sip_ids) >= 6

    # F. Synthetic Voice
    synth_ids = [k for k in rules if "ALERT-SYNTH" in k]
    assert len(synth_ids) >= 6
    for sid in synth_ids:
        assert rules[sid].is_synthetic is True
        assert rules[sid].evidence_class == AlertEvidence.SYNTHETIC

    # G. CMS & WFO
    assert "ALERT-CMS-001" in rules
    assert "ALERT-WFO-001" in rules
    assert rules["ALERT-CMS-001"].evidence_class == AlertEvidence.CONFIGURED_UNVERIFIED
    assert rules["ALERT-WFO-001"].evidence_class == AlertEvidence.CONFIGURED_UNVERIFIED


def test_04_alert_engine_lifecycle_deduplication_and_recovery():
    """Verify alert engine deduplication, cooldown, 3-cycle nominal recovery, and missing telemetry hold."""
    dispatched_events = []

    def handler(inst: AlertInstance, event: str):
        dispatched_events.append((inst.alert_id, inst.entity_id, event, inst.observed_value))

    engine = CommunicationAlertEngine(notification_handler=handler, cooldown_seconds=300.0)

    # 1. Trigger SBCE reachability failure
    # Alert pending for 60s
    t0 = 1000.0
    insts = engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 0}, current_time=t0)
    assert len(insts) == 1
    assert insts[0].current_state == AlertState.PENDING
    assert len(dispatched_events) == 0  # Still pending, no notification yet

    # Advance time to t0 + 65s (pending duration exceeded -> FIRING)
    t1 = t0 + 65.0
    insts = engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 0}, current_time=t1)
    assert insts[0].current_state == AlertState.FIRING
    assert len(dispatched_events) == 1
    assert dispatched_events[0] == ("ALERT-SBCE-001", "sbce-pride-01", "NEW_ALERT", 0)

    # 2. Duplicate symptom during cooldown (< 300s): deduplicated without sending repeat email
    t2 = t1 + 30.0
    insts = engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 0}, current_time=t2)
    assert insts[0].current_state == AlertState.FIRING
    assert len(dispatched_events) == 1  # No duplicate notification sent

    # 3. Missing / None telemetry: MUST NOT count toward recovery!
    t3 = t2 + 60.0
    insts = engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": None}, current_time=t3)
    assert insts[0].current_state == AlertState.FIRING
    assert insts[0].nominal_recovery_cycles == 0

    # 4. Recovery: requires 3 consecutive nominal cycles
    # Cycle 1:
    t4 = t3 + 30.0
    engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 1}, current_time=t4)
    assert insts[0].current_state == AlertState.RECOVERING
    assert insts[0].nominal_recovery_cycles == 1
    assert len(dispatched_events) == 1

    # Cycle 2:
    t5 = t4 + 30.0
    engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 1}, current_time=t5)
    assert insts[0].current_state == AlertState.RECOVERING
    assert insts[0].nominal_recovery_cycles == 2

    # Cycle 3: Reaches 3 nominal cycles -> transitions to RESOLVED and dispatches RECOVERY notification
    t6 = t5 + 30.0
    engine.evaluate_telemetry("sbce-pride-01", "NBO-JKIA", {"avaya.sbce.reachability": 1}, current_time=t6)
    assert len(dispatched_events) == 2
    assert dispatched_events[1] == ("ALERT-SBCE-001", "sbce-pride-01", "RECOVERY", 1)


def test_05_alert_engine_maintenance_suppression():
    """Verify maintenance window suppression suppresses notification dispatch."""
    dispatched_events = []
    engine = CommunicationAlertEngine(
        notification_handler=lambda inst, ev: dispatched_events.append(inst.alert_id),
    )

    # Suppress host
    engine.add_suppression("nawari-sm-01")
    assert engine.is_suppressed("nawari-sm-01") is True

    # Trigger failure
    t0 = 2000.0
    engine.evaluate_telemetry("nawari-sm-01", "NBO-JKIA", {"avaya.sm.reachability": 0}, current_time=t0)
    engine.evaluate_telemetry("nawari-sm-01", "NBO-JKIA", {"avaya.sm.reachability": 0}, current_time=t0 + 100.0)

    # Instance should be suppressed and zero notifications dispatched
    inst = engine.active_instances.get("ALERT-ASM-001|nawari-sm-01|NBO-JKIA")
    assert inst is not None
    assert inst.suppressed is True
    assert len(dispatched_events) == 0


def test_06_m365_email_provider_safe_startup_and_templates():
    """Verify Microsoft 365 provider defaults to safe disabled state and renders rich templates."""
    # 1. Unconfigured credentials defaults to DISABLED without crashing
    cfg = M365Config(
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_secure=False,
        smtp_user="",
        smtp_pass="",
        delivery_enabled=False,
    )
    provider = M365EmailProvider(cfg)
    assert provider.status == ProviderStatus.DISABLED

    # 2. Secret masking in logs
    masked = provider.sanitize_logs("Authentication with token=SecretBearerToken123 and password='SuperSecretPassword' failed")
    assert "SecretBearerToken123" not in masked
    assert "SuperSecretPassword" not in masked
    assert "token=********" in masked

    # 3. Modern Auth XOAUTH2 string formatting
    xoauth2 = provider.generate_xoauth2_string("noc@kenya-airways.com", "eySAMPLE_TOKEN")
    assert len(xoauth2) > 20

    # 4. Notification rendering for all 5 event types
    alert_info = {
        "alert_id": "ALERT-G450-002",
        "name": "G450 Ambient Temperature Threshold Exceeded",
        "severity": "HIGH",
        "component": "G450",
        "entity_id": "nawari-g450-01",
        "site_id": "MBA-STATION",
        "observed_value": 2,
        "description": "G450 MGP firmware issued temperatureWarning trap.",
        "runbook": "Inspect branch office HVAC and air intake filters.",
        "evidence_class": "CONFIGURED_UNVERIFIED",
        "fingerprint": "fprint-g450-002",
    }

    events = ["NEW_ALERT", "SEVERITY_ESCALATION", "REPEAT_REMINDER", "RECOVERY", "DELIVERY_FAILURE"]
    for ev in events:
        subject, plain, html_content = provider.render_notification(ev, alert_info)
        assert "ALERT-G450-002" in plain
        assert "nawari-g450-01" in plain
        assert "MBA-STATION" in plain
        assert "NAWARI" in subject
        assert "html" in html_content.lower()

    # 5. Mock send records message in memory safely
    sent_ok = provider.send_notification("NEW_ALERT", alert_info, ["operator@kenya-airways.com"], mock_transport=True)
    assert sent_ok is True
    assert len(provider._sent_messages) == 1
    assert provider._sent_messages[0]["to"] == ["operator@kenya-airways.com"]


def test_07_dashboard_descriptions_100_percent_coverage_and_missing_data():
    """Verify all 200 panels across 24 dashboards have operational descriptions including missing data explanation."""
    dashboards = list(GRAFANA_DASHBOARDS_DIR.glob("*/*.json"))
    assert len(dashboards) == 24, f"Expected 24 unique dashboards in subdirectories, found {len(dashboards)}"

    total_panels = 0
    for dp in dashboards:
        with open(dp) as f:
            d = json.load(f)

        for pnl in d.get("panels", []):
            if pnl.get("type") == "row":
                continue
            total_panels += 1
            desc = pnl.get("description", "")
            title = pnl.get("title", "")

            # 1. Description must exist and be comprehensive (> 40 chars)
            assert len(desc) >= 40, f"Panel '{title}' in {dp.name} has short/missing description"

            # 2. Must explain missing data behavior
            has_missing_data_info = any(
                k in desc.lower() for k in ["missing data", "no data", "missing telemetry", "data is missing", "uncollected", "not collected"]
            )
            assert has_missing_data_info, f"Panel '{title}' in {dp.name} missing explanation of missing data"

    assert total_panels == 200, f"Expected exactly 200 panels, found {total_panels}"

