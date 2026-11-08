"""
tests/unit/test_phase13_8a_threshold_rationalisation.py

Automated audit and engineering validation suite for Nawari Phase 13.8A:
Trigger Threshold Rationalisation and Alert Policy Engineering.

Verifies:
1. Complete trigger inventory in the Authoritative Threshold Register.
2. Standard severity model conformance (1-5 mapped to operational responses).
3. Decoupling of metric thresholds from outage notification classification.
4. Rate-based interface metric formulation (preventing raw cumulative counters).
5. Voice metric disambiguation (Synthetic MOS vs Real, Setup Time vs SIP RTT).
6. Anti-flapping hysteresis and persistence definitions.
7. Network RTT zoning (LAN vs WAN vs Remote Outstations).
8. Gated telemetry isolation (Zero fictitious triggers for unverified hardware).
9. Full 16-field metadata schema completeness in the threshold register.
10. Implementation roadmap integration (Phase 13.8A -> 13.8B -> 13.8C -> 13.9).
"""

from pathlib import Path
import re
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"
ROADMAP_FILE = PROJECT_ROOT / "docs/architecture/implementation-roadmap.md"
REGISTER_FILE = PROJECT_ROOT / "docs/phase13/phase13-8a-authoritative-threshold-register.md"
SPEC_FILE = PROJECT_ROOT / "docs/phase13/phase13-8a-trigger-threshold-rationalisation-and-alert-policy.md"

TARGET_TEMPLATES = [
    "Nawari Network Device by SNMP",
    "Network Generic Device by SNMP",
    "Nawari Avaya SBCE by SNMP",
    "Nawari Avaya Session Manager by SNMP",
    "Nawari Avaya Communication Manager by SNMP",
    "Nawari Avaya G450 Media Gateway by SNMP",
    "Nawari SIP Trunk by Trapper",
    "Nawari Avaya CMS and WFO by Trapper",
    "Nawari Voice Synthetic Probe by Zabbix Trapper",
    "Template Nawari Endpoint Probe by Zabbix Trapper",
]


@pytest.fixture(scope="module")
def zabbix_client():
    """Establish authenticated Zabbix API client."""
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()
    return client


def test_01_all_active_triggers_inventoried_in_register(zabbix_client):
    """Verify all key triggers on templates are catalogued in the threshold register."""
    assert REGISTER_FILE.is_file(), f"Threshold register must exist at {REGISTER_FILE}"
    register_content = REGISTER_FILE.read_text()

    # Query templates
    tmpls = zabbix_client.call(
        "template.get",
        {"filter": {"name": TARGET_TEMPLATES}, "output": ["templateid", "name"]}
    )
    tmpl_ids = [t["templateid"] for t in tmpls]

    triggers = zabbix_client.call(
        "trigger.get",
        {
            "templateids": tmpl_ids,
            "output": ["triggerid", "description", "priority"],
        }
    )
    assert len(triggers) > 0

    # Key critical triggers that MUST be explicitly in the register by ID
    key_trigger_ids = [
        "32708",  # Avaya SBCE: Appliance Unreachable
        "32752",  # Avaya SM: Session Manager Host Unavailable
        "32733",  # Avaya CM: Communication Manager Processor Unreachable
        "32742",  # Avaya G450: Media Gateway Chassis Unreachable
        "32753",  # SIP Trunk: Endpoint Unreachable
        "32754",  # SIP Trunk: Consecutive OPTIONS Probe Failures
        "32682",  # Degraded voice quality on synthetic probe (MOS < 3.8)
        "32683",  # Unacceptable voice quality on synthetic probe (MOS < 3.5)
        "32681",  # One-way audio detected on synthetic voice test
        "32736",  # WFO: Compliance Voice Recording Pipeline Health Failure
        "32583",  # High ICMP ping loss
        "32584",  # High ICMP response time
    ]
    for tid in key_trigger_ids:
        assert f"**{tid}**" in register_content, f"Trigger ID {tid} must be documented in register"


def test_02_standard_severity_model_conformance(zabbix_client):
    """Verify triggers conform to the 5 standard operational severities (1 to 5)."""
    tmpls = zabbix_client.call(
        "template.get",
        {"filter": {"name": TARGET_TEMPLATES}, "output": ["templateid"]}
    )
    tmpl_ids = [t["templateid"] for t in tmpls]

    triggers = zabbix_client.call(
        "trigger.get",
        {"templateids": tmpl_ids, "output": ["triggerid", "description", "priority"]}
    )

    valid_severities = {"1", "2", "3", "4", "5"}
    for trg in triggers:
        prio = str(trg["priority"])
        assert prio in valid_severities, f"Trigger {trg['triggerid']} has invalid severity: {prio}"


def test_03_metric_measurement_decoupled_from_outage_classification(zabbix_client):
    """Verify metric measurement is decoupled from notification classification via tags."""
    tmpls = zabbix_client.call(
        "template.get",
        {"filter": {"name": TARGET_TEMPLATES}, "output": ["templateid"]}
    )
    tmpl_ids = [t["templateid"] for t in tmpls]

    triggers = zabbix_client.call(
        "trigger.get",
        {"templateids": tmpl_ids, "output": ["triggerid", "description"], "selectTags": "extend"}
    )

    valid_classes = {
        "total_outage",
        "service_outage",
        "synthetic_failure",
        "degradation",
        "component_failure",
        "monitoring_failure",
        "informational",
    }

    tagged_count = 0
    for trg in triggers:
        tags = {x["tag"]: x["value"] for x in trg.get("tags", [])}
        if "notification_class" in tags:
            tagged_count += 1
            assert tags["notification_class"] in valid_classes, (
                f"Trigger {trg['triggerid']} has unknown notification_class {tags['notification_class']}"
            )

    assert tagged_count >= 45, f"Expected at least 45 tagged triggers, found {tagged_count}"


def test_04_rate_based_interface_metric_formulation():
    """Verify interface utilization, discards, and errors enforce rate-based calculations."""
    register_content = REGISTER_FILE.read_text()
    spec_content = SPEC_FILE.read_text()

    # Must explicitly prohibit raw cumulative counter comparisons
    assert "rate(" in register_content or "rate(" in spec_content
    assert "Cumulative counters vs. Rate Calculations" in spec_content or "cumulative counter" in spec_content.lower()
    assert "errors/s" in register_content
    assert "discards/s" in register_content


def test_05_voice_metric_disambiguation_synthetic_vs_call_setup():
    """Verify synthetic MOS is distinct from live MOS, and Call Setup Time is distinct from SIP RTT."""
    register_content = REGISTER_FILE.read_text()
    spec_content = SPEC_FILE.read_text()

    # Synthetic MOS must be flagged as synthetic
    assert "voice.synthetic.mos" in register_content
    assert "SYNTHETIC_MOS" in spec_content or "Synthetic (E-Model)" in register_content

    # Call setup time vs SIP RTT disambiguation
    assert "voice.synthetic.setup_time" in register_content
    assert "avaya.sm.sip_entity.rtt.cm" in register_content
    assert "Strictly distinct from Call Setup Time" in spec_content
    assert "Strictly distinct from SIP RTT" in spec_content


def test_06_persistence_and_anti_flapping_hysteresis_standard():
    """Verify persistence formulas and recovery hysteresis standards are defined."""
    spec_content = SPEC_FILE.read_text()
    assert "Anti-Flapping Hysteresis" in spec_content
    assert "min(" in spec_content
    assert "max(" in spec_content
    assert "Hysteresis Margin" in spec_content


def test_07_network_rtt_zoning_lan_vs_wan_vs_outstations():
    """Verify network latency thresholds define separate zones for LAN, WAN, and Outstations."""
    spec_content = SPEC_FILE.read_text()
    assert "Network RTT (LAN)" in spec_content
    assert "Network RTT (WAN)" in spec_content
    assert "Network RTT (Outstations)" in spec_content


def test_08_gated_telemetry_integrity_no_fictitious_active_triggers(zabbix_client):
    """Verify unsupported/unverified metrics are gated and not assigned fictitious active triggers."""
    register_content = REGISTER_FILE.read_text()
    assert "Gated & Deferred Telemetry Register" in register_content
    assert "G450 DSP Pool Utilization" in register_content
    assert "Real-Time Per-Call RTCP Jitter" in register_content

    # Query all triggers on Avaya G450 template
    g450_tmpls = zabbix_client.call(
        "template.get",
        {"filter": {"name": ["Nawari Avaya G450 Media Gateway by SNMP"]}, "output": ["templateid"]}
    )
    assert len(g450_tmpls) == 1
    g450_triggers = zabbix_client.call(
        "trigger.get",
        {"templateids": [g450_tmpls[0]["templateid"]], "output": ["description"]}
    )

    # Ensure NO active trigger exists claiming DSP utilization
    for trg in g450_triggers:
        assert "DSP resource pool utilization" not in trg["description"], (
            f"Fictitious DSP trigger {trg['description']} found before physical hardware verification!"
        )


def test_09_threshold_register_16_fields_completeness():
    """Verify all 16 standardized metadata fields are documented in the register schema."""
    register_content = REGISTER_FILE.read_text()
    expected_fields = [
        "Trigger ID",
        "Trigger Name",
        "Host / Template",
        "Metric Key",
        "Unit",
        "Warning Threshold",
        "High Threshold",
        "Disaster Threshold",
        "Problem Duration",
        "Recovery Condition",
        "Recovery Duration",
        "Severity",
        "Notification Class",
        "Data Provenance",
        "Threshold Rationale",
        "Validation Status",
    ]
    for field in expected_fields:
        assert field in register_content, f"Field '{field}' must be documented in register schema"


def test_10_roadmap_prerequisite_sequence():
    """Verify implementation-roadmap.md links Phase 13.8A through 13.8C to Phase 13.9."""
    assert ROADMAP_FILE.is_file(), f"Roadmap must exist at {ROADMAP_FILE}"
    roadmap_content = ROADMAP_FILE.read_text()
    assert "Phase 13.8A" in roadmap_content, "Roadmap must document Phase 13.8A"
    assert "Phase 13.8B" in roadmap_content, "Roadmap must document Phase 13.8B"
    assert "Phase 13.8C" in roadmap_content, "Roadmap must document Phase 13.8C"
    assert "Phase 13.9" in roadmap_content, "Roadmap must document Phase 13.9"


def test_11_inventory_reconciliation_exact_counts(zabbix_client):
    """Verify exact ground-truth trigger counts across Nawari templates and hosts."""
    comm_templates = [
        "Nawari Avaya SBCE by SNMP",
        "Nawari Avaya Session Manager by SNMP",
        "Nawari Voice Synthetic Probe by Zabbix Trapper",
        "Nawari Avaya G450 Media Gateway by SNMP",
        "Nawari Avaya Communication Manager by SNMP",
        "Nawari SIP Trunk by Trapper",
        "Nawari Avaya CMS and WFO by Trapper",
    ]
    all_nawari_templates = comm_templates + [
        "Nawari Generic SNMP Base",
        "Nawari Network Device by SNMP",
        "Template Nawari Endpoint Probe by Zabbix Trapper",
    ]

    # Query communication templates
    comm_res = zabbix_client.call("template.get", {"filter": {"name": comm_templates}, "output": ["templateid"]})
    comm_ids = [t["templateid"] for t in comm_res]
    comm_triggers = zabbix_client.call("trigger.get", {"templateids": comm_ids, "output": ["triggerid"]})
    assert len(comm_triggers) == 59, f"Expected 59 communication triggers across 7 templates, got {len(comm_triggers)}"

    # Query all 10 Nawari templates
    all_res = zabbix_client.call("template.get", {"filter": {"name": all_nawari_templates}, "output": ["templateid"]})
    all_ids = [t["templateid"] for t in all_res]
    all_triggers = zabbix_client.call("trigger.get", {"templateids": all_ids, "output": ["triggerid"]})
    assert len(all_triggers) == 70, f"Expected 70 triggers across all 10 Nawari templates, got {len(all_triggers)}"


def test_12_untagged_triggers_root_cause_analysis(zabbix_client):
    """Verify that all untagged triggers are discovered interface triggers on mock lab hosts."""
    hosts = zabbix_client.call("host.get", {"output": ["hostid", "host", "name"]})
    nawari_hosts = [h for h in hosts if h["host"] != "Zabbix server"]
    assert len(nawari_hosts) == 11, f"Expected 11 Nawari hosts, found {len(nawari_hosts)}"

    all_untagged = []
    concrete_untagged = []
    for h in nawari_hosts:
        trigs = zabbix_client.call(
            "trigger.get",
            {"hostids": [h["hostid"]], "output": ["triggerid", "description", "flags"], "selectTags": "extend"}
        )
        for t in trigs:
            has_nc = any(tag.get("tag") == "notification_class" for tag in t.get("tags", []))
            if not has_nc:
                all_untagged.append(t)
                if h["host"] not in ["mock-core-switch-01", "mock-avaya-sbce-01"]:
                    concrete_untagged.append(t)

    assert len(all_untagged) == 54, f"Expected exactly 54 untagged triggers across mock hosts, got {len(all_untagged)}"
    assert len(concrete_untagged) == 0, f"Concrete hosts must have 0 untagged triggers, found {len(concrete_untagged)}"
    for t in all_untagged:
        assert str(t["flags"]) == "4", f"Untagged trigger {t['triggerid']} must be discovered (flags=4)"


def test_13_recovery_mode_status_and_target_hysteresis(zabbix_client):
    """Verify that live template triggers currently have recovery_mode: 0, confirming hysteresis necessity."""
    all_nawari_templates = [
        "Nawari Generic SNMP Base",
        "Nawari Network Device by SNMP",
        "Nawari Avaya SBCE by SNMP",
        "Nawari Voice Synthetic Probe by Zabbix Trapper",
        "Template Nawari Endpoint Probe by Zabbix Trapper",
        "Nawari Avaya CMS and WFO by Trapper",
        "Nawari SIP Trunk by Trapper",
        "Nawari Avaya Session Manager by SNMP",
        "Nawari Avaya Communication Manager by SNMP",
        "Nawari Avaya G450 Media Gateway by SNMP",
    ]
    res = zabbix_client.call("template.get", {"filter": {"name": all_nawari_templates}, "output": ["templateid"]})
    t_ids = [t["templateid"] for t in res]
    triggers = zabbix_client.call("trigger.get", {"templateids": t_ids, "output": ["triggerid", "recovery_mode"]})

    # All 70 template triggers are currently recovery_mode: 0 (Expression only)
    for t in triggers:
        assert str(t.get("recovery_mode", "0")) == "0", f"Trigger {t['triggerid']} has unexpected recovery_mode"

    # Confirm documentation specifies target recovery_mode: 1 for Phase 13.8B
    assessment_doc = PROJECT_ROOT / "docs/phase13/phase13-8a-inventory-reconciliation-and-threshold-assessment.md"
    assert assessment_doc.is_file()
    assert "recovery_mode: 1" in assessment_doc.read_text()


def test_14_full_eleven_milestone_roadmap_structure():
    """Verify that implementation-roadmap.md formalises all 11 milestones from 13.8A to 13.16."""
    roadmap_content = ROADMAP_FILE.read_text()
    expected_milestones = [
        "Phase 13.8A",
        "Phase 13.8B",
        "Phase 13.8C",
        "Phase 13.9",
        "Phase 13.10",
        "Phase 13.11",
        "Phase 13.12",
        "Phase 13.13",
        "Phase 13.14",
        "Phase 13.15",
        "Phase 13.16",
    ]
    for milestone in expected_milestones:
        assert milestone in roadmap_content, f"Milestone {milestone} must be defined in roadmap"


