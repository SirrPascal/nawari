"""tests/unit/test_phase13_8b_threshold_implementation.py

Phase 13.8B Automated Unit & Staging Implementation Test Suite.
Validates:
1. Live Zabbix API Dual-Expression Recovery Mode (recovery_mode == 1) across all eligible triggers.
2. Prototype Tagging & Resolution of Discovered Triggers (54/54 tagged with notification_class).
3. Hysteresis Deadband Integrity (anti-flapping margins between problem and recovery expressions).
4. Strict Gating of Unverified Hardware Telemetry (Gated Telemetry Register isolation).
5. Snapshot Change Manifest Completeness (11 batches, zero errors).
6. Sentra Isolation and Repository Boundary Integrity.
"""

import json
from pathlib import Path
import subprocess
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = PROJECT_ROOT.parent / "sentra"
SNAPSHOT_DIR = PROJECT_ROOT / "provisioning/zabbix/snapshots"
CHANGE_MANIFEST_PATH = SNAPSHOT_DIR / "phase13_8b_change_manifest.json"
HYSTERESIS_RESULTS_PATH = SNAPSHOT_DIR / "phase13_8b_runtime_hysteresis_results.json"

NAWARI_TEMPLATE_IDS = [
    "10784",  # Nawari Generic SNMP Base
    "10786",  # Nawari Network Device by SNMP
    "10788",  # Nawari Avaya SBCE by SNMP
    "10790",  # Nawari Voice Synthetic Probe by Zabbix Trapper
    "10792",  # Template Nawari Endpoint Probe by Zabbix Trapper
    "10226",  # Network Generic Device by SNMP
    "10796",  # Nawari Avaya CMS and WFO by Trapper
    "10797",  # Nawari SIP Trunk by Trapper
    "10795",  # Nawari Avaya Session Manager by SNMP
    "10793",  # Nawari Avaya Communication Manager by SNMP
    "10794",  # Nawari Avaya G450 Media Gateway by SNMP
]

GATED_METRICS = [
    "avaya.g450.dsp_utilization_pct",
    "avaya.cm.live_call.rtcp_jitter",
    "avaya.sbce.transcoding_sessions",
    "avaya.sm.trace_buffer_dropped",
    "ems.sip.server_errors",
    "wfo.verint.pipeline_status",
    "carrier.deep.sla_pct",
]


@pytest.fixture(scope="module")
def zabbix_client():
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()
    return client


def test_01_template_triggers_dual_expression_recovery_mode(zabbix_client):
    """Verify that all eligible Nawari template triggers use dual-expression recovery (recovery_mode == 1)."""
    triggers = zabbix_client.call("trigger.get", {
        "output": ["triggerid", "description", "recovery_mode", "expression", "recovery_expression"],
        "templateids": NAWARI_TEMPLATE_IDS,
        "inherited": False,
    })
    assert len(triggers) == 68, f"Expected exactly 68 non-inherited template triggers, found {len(triggers)}"

    # Trigger 21712 ("System name has changed") is an informational change event where recovery_mode is 0
    eligible = [t for t in triggers if t["triggerid"] != "21712"]
    assert len(eligible) == 67

    for t in eligible:
        assert str(t["recovery_mode"]) == "1", (
            f"Trigger {t['triggerid']} ('{t['description']}') must have recovery_mode == 1, found {t['recovery_mode']}"
        )
        assert len(t.get("recovery_expression", "").strip()) > 0, (
            f"Trigger {t['triggerid']} ('{t['description']}') must have non-empty recovery_expression"
        )


def test_02_template_prototypes_dual_expression_and_tags(zabbix_client):
    """Verify that all template prototypes have recovery_mode == 1 and notification_class tags."""
    prototypes = zabbix_client.call("triggerprototype.get", {
        "output": ["triggerid", "description", "recovery_mode", "expression", "recovery_expression"],
        "selectTags": "extend",
        "templateids": NAWARI_TEMPLATE_IDS,
        "inherited": False,
    })
    assert len(prototypes) == 11, f"Expected 11 template prototypes, found {len(prototypes)}"

    for p in prototypes:
        assert str(p["recovery_mode"]) == "1", (
            f"Prototype {p['triggerid']} ('{p['description']}') must have recovery_mode == 1"
        )
        assert len(p.get("recovery_expression", "").strip()) > 0, (
            f"Prototype {p['triggerid']} ('{p['description']}') must have non-empty recovery_expression"
        )
        tags = {t["tag"]: t["value"] for t in p.get("tags", [])}
        assert "notification_class" in tags, (
            f"Prototype {p['triggerid']} ('{p['description']}') is missing 'notification_class' tag"
        )
        assert tags["notification_class"] in [
            "total_outage", "service_outage", "degradation", "component_failure", "monitoring_failure", "informational"
        ]


def test_03_all_template_triggers_have_notification_class_tags(zabbix_client):
    """Verify 100% notification_class tag coverage across all template triggers."""
    triggers = zabbix_client.call("trigger.get", {
        "output": ["triggerid", "description"],
        "selectTags": "extend",
        "templateids": NAWARI_TEMPLATE_IDS,
        "inherited": False,
    })
    for t in triggers:
        tags = {tag["tag"]: tag["value"] for tag in t.get("tags", [])}
        assert "notification_class" in tags, (
            f"Template trigger {t['triggerid']} ('{t['description']}') missing notification_class tag"
        )
        assert tags["notification_class"] in [
            "total_outage", "service_outage", "degradation", "component_failure",
            "monitoring_failure", "synthetic_failure", "informational"
        ]


def test_04_zero_untagged_discovered_triggers_on_staging_hosts(zabbix_client):
    """Verify that all 54 discovered interface triggers on mock lab hosts inherit notification_class."""
    discovered = zabbix_client.call("trigger.get", {
        "output": ["triggerid", "description", "flags", "recovery_mode"],
        "selectTags": "extend",
        "filter": {"flags": ["4"]},
    })
    assert len(discovered) == 54, f"Expected 54 discovered triggers, found {len(discovered)}"

    untagged = [
        t for t in discovered
        if not any(tag["tag"] == "notification_class" for tag in t.get("tags", []))
    ]
    assert len(untagged) == 0, f"Found {len(untagged)} untagged discovered triggers: {untagged}"


def test_05_hysteresis_deadband_specification(zabbix_client):
    """Verify deadband margins in key metric triggers to prevent threshold flapping."""
    # 1. ICMP Ping Loss: Problem > 20%, Recovery < 5% (deadband [5, 20])
    trig_icmp_loss = zabbix_client.call("trigger.get", {
        "triggerids": ["32575"],
        "output": ["expression", "recovery_expression"],
    })[0]
    assert ">20" in trig_icmp_loss["expression"]
    assert "<5" in trig_icmp_loss["recovery_expression"]

    # 2. SBCE CPU: Problem > 85%, Recovery < 70% (deadband [70, 85])
    trig_cpu = zabbix_client.call("trigger.get", {
        "triggerids": ["32626"],
        "output": ["expression", "recovery_expression"],
    })[0]
    assert ">85" in trig_cpu["expression"]
    assert "<70" in trig_cpu["recovery_expression"]

    # 3. SBCE Disk: Problem > 85%, Recovery < 75% (deadband [75, 85])
    trig_disk = zabbix_client.call("trigger.get", {
        "triggerids": ["32628"],
        "output": ["expression", "recovery_expression"],
    })[0]
    assert ">85" in trig_disk["expression"]
    assert "<75" in trig_disk["recovery_expression"]

    # 4. WFO Spool Disk: Problem < 15%, Recovery > 20% (deadband [15, 20])
    trig_wfo = zabbix_client.call("trigger.get", {
        "triggerids": ["32737"],
        "output": ["expression", "recovery_expression"],
    })[0]
    assert "<15" in trig_wfo["expression"]
    assert ">20" in trig_wfo["recovery_expression"]


def test_06_gated_telemetry_isolation(zabbix_client):
    """Verify that unverified/gated telemetry metrics have ZERO active items or triggers."""
    items = zabbix_client.call("item.get", {
        "output": ["itemid", "name", "key_"],
        "filter": {"key_": GATED_METRICS},
    })
    assert len(items) == 0, f"Gated telemetry items MUST NOT exist in staging Zabbix: {items}"


def test_07_change_manifest_integrity():
    """Verify that the change manifest file exists and confirms 100% implementation success."""
    assert CHANGE_MANIFEST_PATH.exists(), f"Missing change manifest at {CHANGE_MANIFEST_PATH}"
    with open(CHANGE_MANIFEST_PATH) as f:
        manifest = json.load(f)

    assert manifest["phase"] == "13.8B"
    summary = manifest["summary"]
    assert summary["total_batches"] == 11
    assert summary["records_count"] == 79
    assert summary["triggers_updated"] == 68
    assert summary["prototypes_updated"] == 11
    assert summary["template_triggers_recovery_mode_1"] == 67
    assert summary["template_triggers_tagged"] == 68
    assert summary["template_prototypes_recovery_mode_1"] == 11
    assert summary["template_prototypes_tagged"] == 11
    assert summary["discovered_triggers_tagged"] == 54
    assert summary["untagged_discovered_resolved"] is True

    # Ensure zero ERROR records in manifest
    errors = [r for r in manifest["records"] if r["status"] == "ERROR"]
    assert len(errors) == 0, f"Found {len(errors)} error records in manifest: {errors}"


def test_08_runtime_hysteresis_results():
    """Verify that runtime hysteresis testing passed all scenarios."""
    assert HYSTERESIS_RESULTS_PATH.exists(), f"Missing hysteresis results at {HYSTERESIS_RESULTS_PATH}"
    with open(HYSTERESIS_RESULTS_PATH) as f:
        res = json.load(f)

    assert res["phase"] == "13.8B"
    assert res["all_passed"] is True
    assert res["total_scenarios"] >= 3
    for s in res["results"]:
        assert s["status"] == "PASS"


def test_09_sentra_repository_isolation():
    """Verify that Sentra repository was not modified and remains at commit 9970404."""
    assert SENTRA_ROOT.exists(), f"Sentra repository not found at {SENTRA_ROOT}"
    res_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_status.stdout.strip() == "", "Sentra repository must have clean working tree"

    res_rev = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_rev.stdout.strip() == "9970404", f"Sentra must be at 9970404, found {res_rev.stdout.strip()}"

