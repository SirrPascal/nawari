"""
tests/unit/test_avaya_device_observability.py

Automated test suite verifying device-specific Avaya monitoring templates,
observability architecture, polling safety constraints, and communications
quality evidence hierarchy for Kenya Airways.
"""

from pathlib import Path
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = ROOT_DIR / "provisioning/zabbix/templates"
DOCS_MONITORING_DIR = ROOT_DIR / "docs/monitoring"

SBCE_TEMPLATE = TEMPLATES_DIR / "nawari_avaya_sbce.yaml"
SM_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_sm.yaml"
CM_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_cm.yaml"
G450_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_g450.yaml"

COMPATIBILITY_MATRIX = DOCS_MONITORING_DIR / "avaya-device-compatibility-matrix.md"
CMS_INTEGRATION = DOCS_MONITORING_DIR / "avaya-cms-integration.md"
WFO_OBSERVABILITY = DOCS_MONITORING_DIR / "recording-wfo-observability.md"
VOICE_QUALITY_SPEC = DOCS_MONITORING_DIR / "voice-quality-measurement-and-validity.md"


def test_avaya_sbce_template_ems_statistics():
    """Verify Avaya SBCE template includes both appliance metrics and EMS SIP statistics."""
    assert SBCE_TEMPLATE.is_file(), "SBCE template must exist"
    with open(SBCE_TEMPLATE) as f:
        data = yaml.safe_load(f)

    templates = data.get("zabbix_export", {}).get("templates", [])
    assert len(templates) > 0
    tmpl = templates[0]
    assert tmpl.get("template") == "Nawari Avaya SBCE by SNMP"

    items = {item.get("key"): item for item in tmpl.get("items", [])}

    # Verify appliance items
    assert "system.cpu.util" in items
    assert "system.cpu.load.avg1" in items
    assert "vfs.fs.used.percent[/]" in items

    # Verify EMS SIP statistics items
    assert "avaya.sbce.ems.active_calls" in items
    assert "avaya.sbce.ems.active_registrations" in items
    assert "avaya.sbce.ems.active_srtp_calls" in items
    assert "avaya.sbce.ems.direct_media_calls" in items
    assert "avaya.sbce.ems.license_utilization_pct" in items

    # License utilization must document hourly collection
    license_item = items["avaya.sbce.ems.license_utilization_pct"]
    assert "hourly" in license_item.get("description", "").lower()


def test_avaya_session_manager_sip_entity_monitoring():
    """Verify Avaya Session Manager template monitors SIP Entity states and OPTIONS response times."""
    assert SM_TEMPLATE.is_file(), "Session Manager template must exist"
    with open(SM_TEMPLATE) as f:
        data = yaml.safe_load(f)

    templates = data.get("zabbix_export", {}).get("templates", [])
    assert len(templates) > 0
    tmpl = templates[0]
    assert tmpl.get("template") == "Nawari Avaya Session Manager by SNMP"

    items = {item.get("key"): item for item in tmpl.get("items", [])}

    # Verify host resources
    assert "system.cpu.util" in items
    assert "vm.memory.util" in items
    assert "system.uptime" in items
    assert "tcp.established" in items

    # Verify SIP entity monitoring items
    assert "avaya.sm.sip_entity.status.cm" in items
    assert "avaya.sm.sip_entity.status.sbce" in items
    assert "avaya.sm.sip_entity.rtt.cm" in items

    # Description must clarify signaling vs media quality
    cm_entity = items["avaya.sm.sip_entity.status.cm"]
    desc = cm_entity.get("description", "").lower()
    assert "sip options" in desc
    assert "does not guarantee audio media quality" in desc or "not establish call completion" in desc


def test_avaya_communication_manager_polling_constraints():
    """Verify Communication Manager template enforces hourly and 5-minute polling limits for CPU safety."""
    assert CM_TEMPLATE.is_file(), "Communication Manager template must exist"
    with open(CM_TEMPLATE) as f:
        data = yaml.safe_load(f)

    templates = data.get("zabbix_export", {}).get("templates", [])
    assert len(templates) > 0
    tmpl = templates[0]
    assert tmpl.get("template") == "Nawari Avaya Communication Manager by SNMP"

    items = {item.get("key"): item for item in tmpl.get("items", [])}

    # Hourly IP voice stats items (delay must be >= 1h)
    hourly_keys = [
        "avaya.cm.ip_voice.loss_pct",
        "avaya.cm.ip_voice.peak_jitter",
        "avaya.cm.ip_voice.peak_delay",
        "avaya.cm.ip_voice.avg_jitter",
        "avaya.cm.ip_voice.call_count",
        "avaya.cm.ip_voice.codec",
        "avaya.cm.ip_voice.echo_cancellation",
        "avaya.cm.ip_voice.network_region",
        "avaya.cm.alarms.active_count"
    ]
    for k in hourly_keys:
        assert k in items, f"Missing CM item {k}"
        delay = items[k].get("delay")
        assert delay in ("1h", "3600s", "3600"), f"Item {k} delay '{delay}' violates >= 1h polling limit"

    # Call rate items (delay must be >= 5m)
    call_rate_keys = [
        "avaya.cm.call_rate.attempts",
        "avaya.cm.call_rate.completed"
    ]
    for k in call_rate_keys:
        assert k in items, f"Missing CM item {k}"
        delay = items[k].get("delay")
        assert delay in ("5m", "300s", "300"), f"Item {k} delay '{delay}' violates >= 5m polling limit"


def test_avaya_g450_media_gateway_appliance_model():
    """Verify Avaya G450 Media Gateway template monitors physical chassis, environmental sensors, and trunk state."""
    assert G450_TEMPLATE.is_file(), "G450 template must exist"
    with open(G450_TEMPLATE) as f:
        data = yaml.safe_load(f)

    templates = data.get("zabbix_export", {}).get("templates", [])
    assert len(templates) > 0
    tmpl = templates[0]
    assert tmpl.get("template") == "Nawari Avaya G450 Media Gateway by SNMP"

    items = {item.get("key"): item for item in tmpl.get("items", [])}

    assert "system.uptime" in items
    assert "avaya.g450.cm_registration_state" in items
    assert "avaya.g450.psu.status.1" in items
    assert "avaya.g450.psu.status.2" in items
    assert "avaya.g450.fan_tray.status" in items
    assert "avaya.g450.temperature" in items
    assert "ifOperStatus.e1.1" in items

    desc = tmpl.get("description", "").lower()
    assert "physical telecommunications appliance" in desc
    assert "dsp" in desc


def test_avaya_observability_architecture_documents():
    """Verify comprehensive documentation exists for compatibility matrix, CMS integration, WFO, and voice quality."""
    assert COMPATIBILITY_MATRIX.is_file(), "Compatibility matrix document must exist"
    with open(COMPATIBILITY_MATRIX) as f:
        content = f.read()
    assert "10.2.156.131" in content
    assert "10.2.156.22" in content
    assert "10.2.156.26" in content
    assert "avCmMeasIpVoStatSumDataLstHrTable" in content
    assert "Informix" in content
    assert "WFO" in content

    assert CMS_INTEGRATION.is_file(), "CMS integration document must exist"
    with open(CMS_INTEGRATION) as f:
        cms_content = f.read()
    assert "Informix" in cms_content
    assert "read-only" in cms_content.lower()
    assert "calls_offered" in cms_content
    assert "calls_answered" in cms_content
    assert "calls_abandoned" in cms_content
    assert "service level" in cms_content.lower()

    assert WFO_OBSERVABILITY.is_file(), "WFO observability document must exist"
    with open(WFO_OBSERVABILITY) as f:
        wfo_content = f.read()
    assert "product categor" in wfo_content.lower()
    assert "operational metadata only" in wfo_content.lower() or "audio content exclusion" in wfo_content.lower()

    assert VOICE_QUALITY_SPEC.is_file(), "Voice quality specification must exist"
    with open(VOICE_QUALITY_SPEC) as f:
        vq_content = f.read()
    assert "ITU-T G.107" in vq_content
    assert "RFC 3611" in vq_content
    assert "NOT INSTRUMENTED" in vq_content
    assert "SYNTHETIC — ASTERISK" in vq_content
