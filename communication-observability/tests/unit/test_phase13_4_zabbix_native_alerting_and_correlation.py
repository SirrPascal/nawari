"""
Unit test suite for Nawari Phase 13.4:
- Zabbix-Native Communication Alerting & Trigger Conformance
- Native Microsoft 365 Media Type & Action Provisioning
- Zabbix Problem Ingestion & Idempotency
- Composite Aviation Business Service Incident Correlation & Root-Cause Attribution
- Duplicate Notification Prevention & Passive Python Engine Migration
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
import yaml
import pytest

from services.assurance.models import RootCauseDomain
from services.assurance.zabbix_problem_consumer import (
    CompositeServiceIncident,
    IngestedZabbixProblem,
    ZabbixProblemConsumer,
    ZabbixSeverity,
)
from services.alerting.communication_alert_engine import CommunicationAlertEngine
from services.alerting.communication_alert_catalogue import COMMUNICATION_ALERT_RULES
from services.multisite.incident_pipeline import IncidentStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "provisioning/zabbix/templates"
MEDIA_TYPES_DIR = PROJECT_ROOT / "provisioning/zabbix/media_types"
ACTIONS_DIR = PROJECT_ROOT / "provisioning/zabbix/actions"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _extract_triggers_from_template(template_path: Path) -> List[Dict[str, Any]]:
    """Helper to extract all triggers defined within a Zabbix template YAML."""
    with open(template_path) as f:
        data = yaml.safe_load(f)

    triggers: List[Dict[str, Any]] = []
    templates = data.get("zabbix_export", {}).get("templates", [])
    for tmpl in templates:
        # 1. Triggers inside items
        for item in tmpl.get("items", []):
            for trg in item.get("triggers", []):
                triggers.append(trg)
        # 2. Template-level triggers
        for trg in tmpl.get("triggers", []):
            triggers.append(trg)
        # 3. Discovery rule trigger prototypes
        for disc in tmpl.get("discovery_rules", []):
            for trg in disc.get("trigger_prototypes", []):
                triggers.append(trg)

    return triggers


def test_01_zabbix_template_trigger_conformance_across_all_subsystems():
    """Verify all 45 communication alert triggers are declared across native Zabbix templates."""
    template_files = {
        "SBCE": TEMPLATES_DIR / "nawari_avaya_sbce.yaml",
        "SessionManager": TEMPLATES_DIR / "template_nawari_avaya_sm.yaml",
        "CommManager": TEMPLATES_DIR / "template_nawari_avaya_cm.yaml",
        "G450": TEMPLATES_DIR / "template_nawari_avaya_g450.yaml",
        "SIPTrunk": TEMPLATES_DIR / "template_nawari_sip_trunk.yaml",
        "SyntheticVoice": TEMPLATES_DIR / "nawari_voice_synthetic_probe.yaml",
        "CMS_WFO": TEMPLATES_DIR / "template_nawari_avaya_cms_wfo.yaml",
    }

    # Verify all files exist
    for name, path in template_files.items():
        assert path.is_file(), f"Zabbix template '{name}' must exist at {path}"

    all_triggers: List[Dict[str, Any]] = []
    for name, path in template_files.items():
        trgs = _extract_triggers_from_template(path)
        all_triggers.extend(trgs)

    # Validate that we have at least 45 triggers across these templates
    assert len(all_triggers) >= 45, f"Expected >= 45 triggers, found {len(all_triggers)}"

    # Check key operational triggers
    trigger_names = [t.get("name", "") for t in all_triggers]

    # SBCE triggers
    assert any("SBCE: Appliance Unreachable" in n for n in trigger_names)
    assert any("SBCE: Management Interface Unreachable" in n for n in trigger_names)
    assert any("SBCE: Sustained High SIP Failure Rate" in n for n in trigger_names)
    assert any("SBCE: Active Session Capacity Warning" in n for n in trigger_names)
    assert any("SBCE: Active Session Capacity Critical" in n for n in trigger_names)

    # Session Manager triggers
    assert any("SM: Session Manager Host Unavailable" in n for n in trigger_names)
    assert any("SM: SIP Entity Down (Communication Manager)" in n for n in trigger_names)
    assert any("SM: SIP Entity Down (Avaya SBCE)" in n for n in trigger_names)
    assert any("SM: Synthetic SIP OPTIONS Probe Failure" in n for n in trigger_names)
    assert any("SM: SIP OPTIONS Latency Elevated" in n for n in trigger_names)

    # Communication Manager triggers
    assert any("CM: Communication Manager Processor Unreachable" in n for n in trigger_names)
    assert any("CM: Real-Call Packet Loss High" in n for n in trigger_names)
    assert any("CM: Real-Call Peak Jitter High" in n for n in trigger_names)
    assert any("CM: Call Rate Abnormal Drop" in n for n in trigger_names)
    assert any("CM: Performance Telemetry Stale" in n for n in trigger_names)

    # G450 triggers
    assert any("G450: Media Gateway Chassis Unreachable" in n for n in trigger_names)
    assert any("G450: Chassis Ambient Temperature Threshold Exceeded" in n for n in trigger_names)
    assert any("G450: Power Supply Unit Failure" in n for n in trigger_names)
    assert any("G450: Fan Tray Failure" in n for n in trigger_names)
    assert any("G450: E1/ISDN Primary Trunk Port Down" in n for n in trigger_names)

    # SIP Trunk triggers
    assert any("SIP Trunk: Endpoint Unreachable" in n for n in trigger_names)
    assert any("SIP Trunk: Consecutive OPTIONS Probe Failures" in n for n in trigger_names)
    assert any("SIP Trunk: High Error Response Rate" in n for n in trigger_names)
    assert any("SIP Trunk: DNS SRV/A Resolution Failure" in n for n in trigger_names)
    assert any("SIP Trunk: TLS Certificate Expiration" in n for n in trigger_names)

    # Synthetic Voice triggers
    assert any("Synthetic voice test failed" in n or "Synthetic Voice: Call Setup Timeout" in n for n in trigger_names)
    assert any("Synthetic Voice: SIP vs AMI Result Mismatch" in n for n in trigger_names)
    assert any("Synthetic Voice: Connected Duration Below Criterion" in n for n in trigger_names)
    assert any("Synthetic Voice: Consecutive Test Failures" in n for n in trigger_names)

    # CMS / WFO triggers
    assert any("Avaya CMS: Queue Service Level Degradation" in n for n in trigger_names)
    assert any("WFO: Compliance Voice Recording Pipeline Health Failure" in n for n in trigger_names)
    assert any("WFO: Compliance Voice Recording Spool Disk Storage Warning" in n for n in trigger_names)


def test_02_zabbix_media_type_and_action_provisioning_validity():
    """Verify Microsoft 365 Media Types and Action provisioning files exist and conform to Zabbix 7.4 export specs."""
    m365_yaml = MEDIA_TYPES_DIR / "media_type_office365.yaml"
    m365_oauth_yaml = MEDIA_TYPES_DIR / "media_type_office365_oauth.yaml"
    action_yaml = ACTIONS_DIR / "action_communication_alerting.yaml"

    assert m365_yaml.is_file(), "media_type_office365.yaml must exist"
    assert m365_oauth_yaml.is_file(), "media_type_office365_oauth.yaml must exist"
    assert action_yaml.is_file(), "action_communication_alerting.yaml must exist"

    # 1. Native M365 Media Type check
    with open(m365_yaml) as f:
        m365_data = yaml.safe_load(f)
    media_types = m365_data.get("zabbix_export", {}).get("media_types", [])
    assert len(media_types) > 0
    mt = media_types[0]
    assert mt.get("smtp_server") == "smtp.office365.com"
    assert str(mt.get("smtp_port")) == "587"
    assert mt.get("smtp_security") == "STARTTLS"
    assert mt.get("smtp_verify_peer") in (True, "YES")
    assert mt.get("smtp_verify_host") in (True, "YES")
    assert mt.get("status") == "DISABLED"  # Must remain safely disabled until user supplies credentials
    assert mt.get("username") == ""  # Never hardcode secrets
    assert mt.get("password") == ""

    # Check message templates for problem, recovery, update
    msg_tmpls = mt.get("message_templates", [])
    assert len(msg_tmpls) >= 3
    assert any(t.get("recovery") == 0 for t in msg_tmpls)  # Initial Problem
    assert any(t.get("recovery") == 1 for t in msg_tmpls)  # Recovery
    assert any(t.get("recovery") == 2 for t in msg_tmpls)  # Update

    # 2. OAuth AlertScript Media Type check
    with open(m365_oauth_yaml) as f:
        oauth_data = yaml.safe_load(f)
    oauth_mts = oauth_data.get("zabbix_export", {}).get("media_types", [])
    assert len(oauth_mts) > 0
    assert oauth_mts[0].get("script_name") == "zabbix_m365_oauth_sender.py"

    # 3. Action check
    with open(action_yaml) as f:
        action_data = yaml.safe_load(f)
    actions = action_data.get("zabbix_export", {}).get("actions", [])
    assert len(actions) > 0
    act = actions[0]
    assert act.get("events_source") == "TRIGGERS"
    assert act.get("status") == "ENABLED"
    assert act.get("pause_suppressed") in (True, "YES")
    assert len(act.get("operations", [])) >= 2
    assert len(act.get("recovery_operations", [])) >= 1


def test_03_zabbix_m365_oauth_alertscript_safe_unconfigured_behavior():
    """Verify zabbix_m365_oauth_sender.py exits safely (code 0) without credentials."""
    script_path = SCRIPTS_DIR / "zabbix_m365_oauth_sender.py"
    assert script_path.is_file(), "AlertScript must exist"

    cmd = [sys.executable, str(script_path), "noc-duty@kenya-airways.com", "Test Subject", "Test Body"]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 0
    assert "not yet configured" in proc.stderr.lower() or "not yet configured" in proc.stdout.lower()


def test_04_zabbix_problem_consumer_idempotency_and_event_ingestion():
    """Verify ZabbixProblemConsumer ingests problems idempotently and handles recovery."""
    consumer = ZabbixProblemConsumer(zabbix_client=None)

    # 1. Create mock Zabbix problems
    prob1 = IngestedZabbixProblem(
        event_id="1001",
        object_id="2001",
        name="Avaya SM: Session Manager Host Unavailable",
        severity=ZabbixSeverity.DISASTER,
        clock=int(time.time()),
        tags={"component": "sm-core", "scope": "availability"},
        host_name="avaya-sm-01",
    )

    prob2 = IngestedZabbixProblem(
        event_id="1002",
        object_id="2002",
        name="SIP Trunk: Endpoint Unreachable",
        severity=ZabbixSeverity.HIGH,
        clock=int(time.time()),
        tags={"component": "sip-trunk", "scope": "availability"},
        host_name="sip-trunk-safaricom",
    )

    # Ingest active problems
    res1 = consumer.ingest_problems([prob1, prob2])
    assert res1["new_problems"] == 2
    assert len(consumer.active_composite_incidents) >= 1

    # Ingest same problems again -> Idempotency contract (0 new problems)
    res2 = consumer.ingest_problems([prob1, prob2])
    assert res2["new_problems"] == 0

    # Ingest recovery event for prob2
    prob2_rec = IngestedZabbixProblem(
        event_id="1002",
        object_id="2002",
        name="SIP Trunk: Endpoint Unreachable",
        severity=ZabbixSeverity.HIGH,
        clock=prob2.clock,
        r_event_id="1005",
        r_clock=int(time.time()),
    )
    res3 = consumer.ingest_problems([prob2_rec])
    assert res3["recovered_problems"] == 1
    assert consumer.ingested_problems["1002"].is_recovered is True
    assert consumer.ingest_problems([prob2_rec])["recovered_problems"] == 0


def test_05_composite_service_incident_correlation_and_root_cause():
    """Verify multi-device failures correlate into single composite Aviation Business Service incident."""
    dispatched_notifications = []

    def mock_notifier(incident: CompositeServiceIncident, event_type: str):
        dispatched_notifications.append((incident.service_id, incident.root_cause_candidate, event_type))

    consumer = ZabbixProblemConsumer(
        zabbix_client=None,
        notification_handler=mock_notifier,
        emit_composite_notifications=True,
    )

    now = int(time.time())

    # Problem 1: Core Session Manager down
    p_sm = IngestedZabbixProblem(
        event_id="5001",
        object_id="7001",
        name="Avaya SM: Session Manager Host Unavailable",
        severity=ZabbixSeverity.DISASTER,
        clock=now,
        tags={"component": "sm-core", "scope": "availability"},
        host_name="avaya-sm-01",
    )

    # Problem 2: Downstream SIP trunk failure
    p_trunk = IngestedZabbixProblem(
        event_id="5002",
        object_id="7002",
        name="SIP Trunk: Consecutive OPTIONS Probe Failures",
        severity=ZabbixSeverity.HIGH,
        clock=now + 10,
        tags={"component": "sip-trunk", "scope": "availability"},
        host_name="sip-carrier-primary",
    )

    # Problem 3: Downstream Synthetic call failure
    p_synth = IngestedZabbixProblem(
        event_id="5003",
        object_id="7003",
        name="Synthetic voice test failed or congested",
        severity=ZabbixSeverity.HIGH,
        clock=now + 20,
        tags={"component": "voice-probe", "scope": "availability", "telemetry_type": "synthetic"},
        host_name="probe-asterisk-01",
    )

    consumer.ingest_problems([p_sm, p_trunk, p_synth])

    # Must be correlated into ONE composite incident for SRV-VOICE-CORP
    assert len(consumer.active_composite_incidents) == 1
    inc = consumer.active_composite_incidents["SRV-VOICE-CORP"]
    assert inc.service_id == "SRV-VOICE-CORP"
    assert len(inc.underlying_problems) == 3
    assert inc.status == IncidentStatus.CORRELATED

    # Root cause candidate must point to upstream core (Session Manager or Trunk) rather than the synthetic probe symptom!
    assert "Session Manager" in inc.root_cause_candidate or "sm" in inc.root_cause_candidate.lower()
    assert "voice-probe" not in inc.root_cause_candidate.lower()


def test_06_duplicate_notification_prevention():
    """Verify that Nawari only emits composite service notifications, avoiding duplicate device-level alert emails."""
    dispatched_notifications = []

    def mock_notifier(incident: CompositeServiceIncident, event_type: str):
        dispatched_notifications.append(event_type)

    consumer = ZabbixProblemConsumer(
        zabbix_client=None,
        notification_handler=mock_notifier,
        emit_composite_notifications=True,
    )

    p1 = IngestedZabbixProblem(
        event_id="8001",
        object_id="9001",
        name="Avaya SBCE: Appliance Unreachable",
        severity=ZabbixSeverity.DISASTER,
        clock=int(time.time()),
        tags={"component": "sbce-core", "scope": "availability"},
        host_name="sbce-pride-01",
    )

    # Ingest 3 times (e.g. 3 polling cycles)
    consumer.ingest_problems([p1])
    consumer.ingest_problems([p1])
    consumer.ingest_problems([p1])

    # Exactly 1 composite notification should have been emitted
    assert len(dispatched_notifications) == 1
    assert dispatched_notifications[0] == "COMPOSITE_SERVICE_DEGRADED"


def test_07_python_alert_engine_migration_status():
    """Verify CommunicationAlertEngine is formally decoupled and marked as PASSIVE_MIGRATED_TO_ZABBIX."""
    assert CommunicationAlertEngine.OPERATIONAL_MODE == "PASSIVE_MIGRATED_TO_ZABBIX"
    engine = CommunicationAlertEngine()
    assert engine.operational_mode == "PASSIVE_MIGRATED_TO_ZABBIX"
    # Ensure all 45 rules are still preserved for reference and testing
    assert len(COMMUNICATION_ALERT_RULES) == 45


def test_08_declarative_designated_administrator_recipients_and_media():
    """Verify communication_administrators.yaml specifies all 4 named administrators with exact emails."""
    users_yaml = PROJECT_ROOT / "provisioning/zabbix/users/communication_administrators.yaml"
    assert users_yaml.is_file(), f"{users_yaml} must exist"

    with open(users_yaml) as f:
        data = yaml.safe_load(f)

    # 1. User group verification
    user_groups = data.get("user_groups", [])
    assert any(g.get("name") == "Nawari Avaya & Communications Administrators" for g in user_groups)

    # 2. Four exact recipients
    expected = {
        "john.gacomo": "John.Gacomo@kenya-airways.com",
        "robinson.wainaina": "Robinson.Wainaina@kenya-airways.com",
        "pascal.gathungu": "Pascal.Gathungu@kenya-airways.com",
        "mercy.vaati": "Mercy.Vaati@kenya-airways.com",
    }

    users = data.get("users", [])
    assert len(users) == 4, f"Expected 4 administrators, found {len(users)}"

    found_users = {}
    for u in users:
        uname = u.get("username")
        found_users[uname] = u
        assert uname in expected, f"Unexpected administrator username: {uname}"
        assert "Nawari Avaya & Communications Administrators" in u.get("groups", [])
        medias = u.get("medias", [])
        assert len(medias) >= 1
        m = medias[0]
        assert m.get("sendto") == expected[uname]
        assert m.get("active") == 0
        assert m.get("severity") == 63
        assert m.get("period") == "1-7,00:00-24:00"

    assert len(found_users) == 4


def test_09_declarative_action_targets_designated_admin_group():
    """Verify action_communication_alerting.yaml targets Nawari Avaya & Communications Administrators."""
    action_yaml = ACTIONS_DIR / "action_communication_alerting.yaml"
    assert action_yaml.is_file()

    with open(action_yaml) as f:
        data = yaml.safe_load(f)

    actions = data.get("zabbix_export", {}).get("actions", [])
    assert len(actions) > 0
    act = actions[0]

    assert act.get("name") == "Nawari Avaya & Communication Alerting"
    assert act.get("status") in ("ENABLED", 0)
    assert act.get("pause_suppressed") in ("YES", 1, True)

    # Verify operations target group
    ops = act.get("operations", [])
    assert len(ops) >= 2
    op1 = ops[0]
    target_groups_1 = [g.get("name") for g in op1.get("user_groups", [])]
    assert "Nawari Avaya & Communications Administrators" in target_groups_1

    op2 = ops[1]
    target_groups_2 = [g.get("name") for g in op2.get("user_groups", [])]
    assert "Nawari Avaya & Communications Administrators" in target_groups_2
    assert op2.get("esc_period") in ("1800s", "30m", 1800)


def test_10_notification_reconciler_idempotency_and_group_resolution():
    """Verify NotificationReconciler executes idempotently against mock or live client."""
    from services.api.provisioning.notification_reconciler import (
        ADMIN_USER_GROUP,
        ACTION_NAME,
        DESIGNATED_ADMINISTRATORS,
        NotificationReconciler,
    )

    class MockZabbixClient:
        def __init__(self):
            self.calls = []
            self.user_groups = [{"usrgrpid": "14", "name": ADMIN_USER_GROUP}]
            self.users = []
            self.mediatypes = [{"mediatypeid": "1", "name": "Email"}]
            self.roles = [{"roleid": "2", "name": "Admin role"}]
            self.hostgroups = [
                {"groupid": str(i), "name": name}
                for i, name in enumerate(
                    [
                        "Voice Infrastructure",
                        "Avaya Infrastructure",
                        "Edge SBC",
                        "SIP Carrier Trunks",
                        "Communications Applications",
                        "Synthetic Probes",
                    ],
                    20,
                )
            ]
            self.actions = []

        def call(self, method: str, params: Dict[str, Any], requires_auth: bool = True) -> Any:
            self.calls.append((method, params))
            if method == "usergroup.get":
                return self.user_groups
            elif method == "usergroup.create":
                gid = str(len(self.user_groups) + 14)
                self.user_groups.append({"usrgrpid": gid, "name": params["name"]})
                return {"usrgrpids": [gid]}
            elif method == "mediatype.get":
                return self.mediatypes
            elif method == "role.get":
                return self.roles
            elif method == "hostgroup.get":
                return self.hostgroups
            elif method == "user.get":
                filter_uname = params.get("filter", {}).get("username")
                if filter_uname:
                    return [u for u in self.users if u["username"] == filter_uname]
                return self.users
            elif method == "user.create":
                uid = str(len(self.users) + 1)
                new_u = {
                    "userid": uid,
                    "username": params["username"],
                    "name": params.get("name"),
                    "surname": params.get("surname"),
                    "usrgrps": params.get("usrgrps", []),
                    "medias": params.get("medias", []),
                }
                self.users.append(new_u)
                return {"userids": [uid]}
            elif method == "user.update":
                return {"userids": [params["userid"]]}
            elif method == "action.get":
                return self.actions
            elif method == "action.create":
                aid = str(len(self.actions) + 1)
                self.actions.append({"actionid": aid, "name": params["name"]})
                return {"actionids": [aid]}
            elif method == "action.update":
                return {"actionids": [params["actionid"]]}
            return []

    mock_client = MockZabbixClient()
    reconciler = NotificationReconciler(mock_client)

    # 1. First run creates users and action
    res1 = reconciler.reconcile_all()
    assert res1["recipients_count"] == 4
    assert len(mock_client.users) == 4
    assert len(mock_client.actions) == 1

    # 2. Second run is idempotent (0 creates, updates if needed)
    res2 = reconciler.reconcile_all()
    assert res2["recipients_count"] == 4
    assert len(mock_client.users) == 4
    assert len(mock_client.actions) == 1

