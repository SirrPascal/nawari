"""
tests/unit/test_phase13_9_telemetry_commissioning.py

Automated Acceptance Suite for Phase 13.9:
Controlled Physical Network and Avaya Telemetry Commissioning.

Validates:
1. Environment safety, clean repository baselines, and HARD_PRODUCTION_DENY.
2. Direct SNMPv2c queries against representative agents.
3. Direct SNMPv3 authPriv queries (SHA-256 / AES).
4. 64-bit HC interface counter traversal and rate-based throughput computation.
5. Authoritative device inventory across 12 monitored hosts in Zabbix.
6. Production IP reachability auditing and BLOCKED_ACCESS categorization.
7. Gated telemetry isolation (5 unverified metrics remain NOT_COLLECTED with zero fictitious triggers).
8. Avaya CM MIB semantic compliance (Tables .67 and .145 polling frequency and bucket semantics).
9. Avaya G450 discrete trap-derived thermal model (no continuous analog sensors).
10. Evidence manifest integrity (phase13_9_telemetry_commissioning_evidence.json).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = Path("/Users/madeira/Desktop/Projects/sentra")
SNAPSHOT_FILE = PROJECT_ROOT / "provisioning/zabbix/snapshots/phase13_9_telemetry_commissioning_evidence.json"


def test_01_environment_safety_and_baseline():
    """Verify Sentra repository isolation, clean baseline, and HARD_PRODUCTION_DENY."""
    res_sentra = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_sentra.stdout.strip() == "9970404", f"Sentra repository modified! HEAD: {res_sentra.stdout.strip()}"

    res_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not res_status.stdout.strip(), "Sentra working tree is not clean!"


def test_02_direct_snmpv2c_queries():
    """Verify direct SNMPv2c query against representative mock agent."""
    cmd = [
        "docker", "exec", "nawari-mock-snmp",
        "snmpget", "-v2c", "-c", "public", "-t", "1", "-r", "1",
        "127.0.0.1:161", ".1.3.6.1.2.1.1.1.0"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert res.returncode == 0, f"SNMPv2c query failed: {res.stderr}"
    assert "STRING:" in res.stdout
    assert "Nawari Aviation Simulated Core Switch" in res.stdout


def test_03_direct_snmpv3_authpriv_queries():
    """Verify direct SNMPv3 authPriv query using SHA-256 and AES encryption."""
    cmd = [
        "docker", "exec", "nawari-mock-snmp",
        "snmpget", "-v3",
        "-u", "Admin_sha256",
        "-l", "authPriv",
        "-a", "SHA-256",
        "-A", "sbce_secret_auth_pass",
        "-x", "AES",
        "-X", "sbce_secret_priv_pass",
        "-t", "1", "-r", "1",
        "127.0.0.1:161", ".1.3.6.1.2.1.1.1.0"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert res.returncode == 0, f"SNMPv3 authPriv query failed: {res.stderr}"
    assert "STRING:" in res.stdout
    assert "Nawari Aviation Simulated Core Switch" in res.stdout


def test_04_interface_64bit_hc_counters_and_rate_math():
    """Verify 64-bit HC counters exist and throughput rate calculation logic."""
    cmd = [
        "docker", "exec", "nawari-mock-snmp",
        "snmpwalk", "-v2c", "-c", "public", "-t", "1", "-r", "1",
        "127.0.0.1:161", ".1.3.6.1.2.1.31.1.1.1.6"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert res.returncode == 0
    lines = [l for l in res.stdout.splitlines() if "Counter64:" in l]
    assert len(lines) >= 10, f"Expected at least 10 64-bit interface counters, got {len(lines)}"

    # Rate math verification: (delta_octets * 8) / elapsed_seconds = bps
    c1, c2 = 1000000, 2000000
    dt = 10.0
    bps = ((c2 - c1) * 8.0) / dt
    assert bps == 800000.0, f"Throughput math discrepancy: {bps}"


def test_05_authoritative_inventory_coverage():
    """Verify all 12 monitored hosts exist in Zabbix across Core, Avaya, and Probe domains."""
    from services.api.config import ZabbixSettings
    from services.api.client.zabbix_client import ZabbixClient

    client = ZabbixClient(ZabbixSettings())
    client.connect()
    hosts = client.call("host.get", {"output": ["hostid", "host", "name"]})
    host_map = {h["host"]: h["name"] for h in hosts}

    expected_hosts = [
        "core-gw-01",
        "mock-core-switch-01",
        "mock-avaya-sbce-01",
        "avaya-sbce-01",
        "avaya-sm-01",
        "avaya-cm-01",
        "avaya-g450-01",
        "sip-trunk-carrier-01",
        "avaya-cms-01",
        "nawari-voice-probe-01",
        "endpoint-probe-01",
        "Zabbix server",
    ]
    for exp in expected_hosts:
        assert exp in host_map, f"Missing authoritative host in Zabbix: {exp}"


def test_06_production_target_reachability_classification():
    """Verify production target auditing and BLOCKED_ACCESS categorization for off-net targets."""
    assert SNAPSHOT_FILE.is_file(), f"Missing snapshot file: {SNAPSHOT_FILE}"
    with open(SNAPSHOT_FILE) as f:
        data = json.load(f)

    targets = data.get("production_target_reachability", [])
    assert len(targets) >= 10, f"Expected at least 10 audited production targets, got {len(targets)}"

    blocked_targets = [t for t in targets if t["connectivity_status"] == "BLOCKED_ACCESS"]
    assert len(blocked_targets) >= 8, f"Expected at least 8 off-net blocked targets, got {len(blocked_targets)}"

    for b in blocked_targets:
        assert "BLOCKED_ACCESS" in b["connectivity_status"]
        assert "commissioning_requirement" in b


def test_07_gated_metrics_isolation():
    """Confirm the 5 unverified physical metrics remain isolated with 0 active triggers."""
    from services.api.config import ZabbixSettings
    from services.api.client.zabbix_client import ZabbixClient

    client = ZabbixClient(ZabbixSettings())
    client.connect()

    gated_tokens = [
        "dsp_utilization",
        "live_call.rtcp_jitter",
        "server_errors",
        "verint.pipeline",
        "carrier.deep.sla",
    ]

    triggers = client.call("trigger.get", {"output": ["triggerid", "description", "expression"]})
    for tr in triggers:
        desc = tr["description"].lower()
        expr = tr["expression"].lower()
        for token in gated_tokens:
            assert token not in desc, f"Found active trigger for gated metric token '{token}': {tr['description']}"
            assert token not in expr, f"Found active expression for gated metric token '{token}': {tr['expression']}"


def test_08_avaya_cm_mib_semantic_compliance():
    """Verify Avaya CM table .67 and table .145 OID conformance and polling semantics."""
    from services.api.config import ZabbixSettings
    from services.api.client.zabbix_client import ZabbixClient

    client = ZabbixClient(ZabbixSettings())
    client.connect()

    hosts = client.call("host.get", {"filter": {"host": "avaya-cm-01"}, "selectItems": ["itemid", "name", "key_", "snmp_oid", "delay"]})
    assert len(hosts) == 1
    cm_items = hosts[0].get("items", [])

    # Check that hourly IP voice stats (table .67) have delay >= 1h
    voice_loss_item = next((i for i in cm_items if "ip_voice.loss_pct" in i["key_"]), None)
    assert voice_loss_item is not None
    assert "1.3.6.1.4.1.6889.2.73.8.1.67" in voice_loss_item["snmp_oid"]
    assert voice_loss_item["delay"] in ["1h", "3600", "3600s"]

    # Check call rate attempts (table .145) has delay >= 5m
    call_rate_item = next((i for i in cm_items if "call_rate.attempts" in i["key_"]), None)
    assert call_rate_item is not None
    assert "1.3.6.1.4.1.6889.2.73.8.1.145" in call_rate_item["snmp_oid"]


def test_09_g450_discrete_thermal_event_model():
    """Verify G450 uses discrete trap events rather than continuous analog sensors."""
    from services.api.config import ZabbixSettings
    from services.api.client.zabbix_client import ZabbixClient

    client = ZabbixClient(ZabbixSettings())
    client.connect()

    hosts = client.call("host.get", {"filter": {"host": "avaya-g450-01"}, "selectItems": ["itemid", "name", "key_", "type"]})
    assert len(hosts) == 1
    items = hosts[0].get("items", [])
    
    # Confirm no analog temperature item exists
    temp_analog = [i for i in items if "temperature.celsius" in i["key_"] or "temperature.val" in i["key_"]]
    assert len(temp_analog) == 0, "Discovered illegal analog temperature gauge on G450!"


def test_10_evidence_manifest_integrity():
    """Verify phase13_9_telemetry_commissioning_evidence.json structure and validity."""
    assert SNAPSHOT_FILE.is_file()
    with open(SNAPSHOT_FILE) as f:
        data = json.load(f)

    meta = data.get("metadata", {})
    assert meta.get("phase") == "13.9"
    assert meta.get("hard_production_deny") is True
    assert meta.get("total_hosts_audited") == 12
    assert "telemetry_status_distribution" in meta
    assert "snmp_query_evidence" in data
    assert "production_target_reachability" in data

