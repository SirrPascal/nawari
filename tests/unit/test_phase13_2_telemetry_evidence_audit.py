"""
tests/unit/test_phase13_2_telemetry_evidence_audit.py

Automated test suite enforcing the Phase 13.2 Telemetry Evidence, OID Validation,
and Dashboard Integrity Audit invariants for Kenya Airways Avaya observability.
"""

import json
from pathlib import Path
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = ROOT_DIR / "provisioning/zabbix/templates"
DOCS_MONITORING_DIR = ROOT_DIR / "docs/monitoring"
GRAFANA_DASHBOARDS_DIR = ROOT_DIR / "docker/grafana/dashboards"

CM_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_cm.yaml"
SM_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_sm.yaml"
G450_TEMPLATE = TEMPLATES_DIR / "template_nawari_avaya_g450.yaml"
SBCE_TEMPLATE = TEMPLATES_DIR / "nawari_avaya_sbce.yaml"

REGISTER_FILE = DOCS_MONITORING_DIR / "avaya-metric-source-register.yaml"
AUDIT_DOC = DOCS_MONITORING_DIR / "phase13-2-telemetry-evidence-audit.md"


def test_communication_manager_official_cm81_oids():
    """Verify Communication Manager template uses official Avaya 6889.2.73 enterprise MIB OIDs."""
    assert CM_TEMPLATE.is_file(), "CM template must exist"
    with open(CM_TEMPLATE) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    # 1. Alarms table must use official Avaya Aura CM MIB avCmAlarmsTable (.8.1.5)
    alarms_item = items["avaya.cm.alarms.active_count"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.5" in alarms_item["snmp_oid"]
    assert alarms_item["delay"] in ("1h", "3600s", "3600")

    # 2. Call rate must use official avCmListMeasCallRateTotalTable (.8.1.145)
    attempts_item = items["avaya.cm.call_rate.attempts"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.145" in attempts_item["snmp_oid"]
    assert attempts_item["delay"] in ("5m", "300s", "300")

    completed_item = items["avaya.cm.call_rate.completed"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.145" in completed_item["snmp_oid"]
    assert completed_item["delay"] in ("5m", "300s", "300")

    # 3. IP Voice tables must use official .77 and .66 tables with delay >= 1h
    loss_item = items["avaya.cm.ip_voice.loss_pct"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.77" in loss_item["snmp_oid"]
    assert loss_item["delay"] in ("1h", "3600s", "3600")

    jitter_item = items["avaya.cm.ip_voice.avg_jitter"]
    assert "1.3.6.1.4.1.6889.2.73.8.1.66" in jitter_item["snmp_oid"]
    assert jitter_item["delay"] in ("1h", "3600s", "3600")


def test_session_manager_collection_demarcation():
    """Verify Session Manager does not falsely claim SNMP for SIP Entity states and OPTIONS RTT."""
    assert SM_TEMPLATE.is_file(), "SM template must exist"
    with open(SM_TEMPLATE) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    # Host resources must use SNMP
    for host_k in ["system.cpu.util", "vm.memory.util", "system.uptime", "tcp.established"]:
        assert items[host_k]["type"] == "SNMP_AGENT", f"{host_k} must be SNMP_AGENT"

    # SIP Entity Monitoring items must be TRAP, NOT SNMP_AGENT
    cm_entity = items["avaya.sm.sip_entity.status.cm"]
    assert cm_entity["type"] == "TRAP"
    assert "snmp_oid" not in cm_entity

    sbce_entity = items["avaya.sm.sip_entity.status.sbce"]
    assert sbce_entity["type"] == "TRAP"
    assert "snmp_oid" not in sbce_entity

    options_rtt = items["avaya.sm.sip_entity.rtt.cm"]
    assert options_rtt["type"] == "TRAP"
    assert "snmp_oid" not in options_rtt

    tags = {t["tag"]: t["value"] for t in options_rtt.get("tags", [])}
    assert tags.get("provenance") == "NAWARI_SIP_PROBE"


def test_g450_discrete_thermal_events_and_dsp_gate():
    """Verify G450 models temperature as discrete event traps and gates DSP channels."""
    assert G450_TEMPLATE.is_file(), "G450 template must exist"
    with open(G450_TEMPLATE) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    # Temperature must be discrete event TRAP (not continuous float gauge)
    temp_item = items["avaya.g450.temperature"]
    assert temp_item["type"] == "TRAP"
    assert temp_item["value_type"] == "UNSIGNED"
    assert "snmp_oid" not in temp_item
    assert "trap" in temp_item["description"].lower()

    # Power supply and fan tray must be TRAP
    assert items["avaya.g450.psu.status.1"]["type"] == "TRAP"
    assert items["avaya.g450.fan_tray.status"]["type"] == "TRAP"


def test_sbce_ems_provenance_and_audit_status():
    """Verify SBCE EMS statistics are categorized as CONFIGURED_UNVERIFIED pending physical connection."""
    assert SBCE_TEMPLATE.is_file(), "SBCE template must exist"
    with open(SBCE_TEMPLATE) as f:
        data = yaml.safe_load(f)

    tmpl = data["zabbix_export"]["templates"][0]
    items = {item["key"]: item for item in tmpl.get("items", [])}

    ems_keys = [
        "avaya.sbce.ems.active_calls",
        "avaya.sbce.ems.active_registrations",
        "avaya.sbce.ems.active_srtp_calls",
        "avaya.sbce.ems.direct_media_calls",
        "avaya.sbce.ems.license_utilization_pct",
    ]
    for k in ems_keys:
        assert k in items
        item = items[k]
        assert item["type"] == "TRAP"
        tags = {t["tag"]: t["value"] for t in item.get("tags", [])}
        assert tags.get("provenance") == "CONFIGURED_UNVERIFIED"


def test_null_integrity_and_absence_of_zero_filling():
    """Verify no dashboard panel coerses missing telemetry to zero or fills missing series with 0."""
    dashboards = list(GRAFANA_DASHBOARDS_DIR.rglob("*.json"))
    assert len(dashboards) >= 24

    for dp in dashboards:
        with open(dp) as f:
            d = json.load(f)

        panels = [p for p in d.get("panels", []) if p.get("type") != "row"]
        for p in panels:
            title = p.get("title", "")
            targets = p.get("targets", [])

            for t in targets:
                # Disallow Prometheus or vector(0)
                expr = str(t.get("expr", ""))
                assert "vector(0)" not in expr, f"Panel '{title}' in {dp.name} contains vector(0)"

                # Disallow COALESCE(..., 0) for operational telemetry
                sql = str(t.get("rawSql", ""))
                if "COALESCE" in sql:
                    # Only allow subtitle text or default speed if specified, not metric 0
                    assert "COALESCE(model, '')" in sql or "COALESCE(src_if.speed_bps" in sql, (
                        f"Panel '{title}' in {dp.name} contains invalid COALESCE zero-fill"
                    )

            # Check value mappings for null -> 0
            mappings = p.get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
            for m in mappings:
                if m.get("type") == "special":
                    assert m.get("options", {}).get("match") != "null" or "0" not in str(m.get("options", {}).get("result", {})), (
                        f"Panel '{title}' maps null to 0"
                    )


def test_metric_evidence_register_completeness_and_truth():
    """Verify metric evidence register covers all 200 panels with accurate validation statuses."""
    assert REGISTER_FILE.is_file(), "Evidence register must exist"
    with open(REGISTER_FILE) as f:
        reg = yaml.safe_load(f)

    assert reg.get("standard") == "Nawari Phase 13.2 Telemetry Evidence & Integration Audit"
    summary = reg.get("summary", {})
    assert summary.get("total_dashboards") == 24
    assert summary.get("total_panels") == 200

    status_counts = summary.get("status_counts", {})
    # Critical truth invariant: 0 panels can be VERIFIED_LIVE while Phase 8.2 is gated
    assert status_counts.get("VERIFIED_LIVE", 0) == 0, "No panel can be VERIFIED_LIVE while physical commissioning is gated"

    assert status_counts.get("VERIFIED_INTEGRATION", 0) == 160
    assert status_counts.get("CONFIGURED_UNVERIFIED", 0) == 19
    assert status_counts.get("NOT_COLLECTED", 0) == 3
    assert status_counts.get("SIMULATED", 0) == 18

    # Verify audit documentation file exists
    assert AUDIT_DOC.is_file(), "Phase 13.2 audit document must exist"
    with open(AUDIT_DOC) as f:
        doc = f.read()
    assert "1.3.6.1.4.1.6889.2.73.8.1.5" in doc
    assert "1.3.6.1.4.1.6889.2.73.8.1.145" in doc
    assert "CONFIGURED_UNVERIFIED" in doc
    assert "HARD_PRODUCTION_DENY" in doc

