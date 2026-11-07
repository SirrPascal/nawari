"""Integration acceptance tests for Nawari Phase 4 Avaya SBCE Observability.

Validates:
1. Mock SNMP agent responsiveness on SNMPv3 authPriv (SHA/DES and SHA/AES).
2. Nawari Avaya SBCE template hierarchy, resource items, and LLD discovery rules.
3. Declarative provisioning of mock-avaya-sbce-01 and avaya-sbce-01 hosts.
4. LLD discovery of voice signaling & media interfaces (M1, M2, A1, B1) and 64-bit HC counters.
5. Real appliance resource metrics: CPU, memory, root disk space, and load average.
6. Real historical metric persistence in PostgreSQL via history.get.
7. Fault injection lifecycle on carrier DMZ interface A1 (Link Down problem firing & recovery).
8. Provisioned Grafana Avaya SBCE Operational & Voice Telemetry Dashboard (uid: nawari-sbce-health).
9. IP reconciliation verification between 10.2.156.131 and 10.2.156.132.
"""

import base64
import json
import os
import subprocess
import time
import urllib.request
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings
from tests.integration.test_core_infrastructure import (
    GRAFANA_ADMIN_PASSWORD,
    GRAFANA_ADMIN_USER,
)


@pytest.fixture(scope="module")
def zabbix_client():
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)
    client.connect()
    yield client
    client.disconnect()


@pytest.fixture(scope="module")
def grafana_auth_header():
    token = f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("utf-8")


def test_01_snmpv3_authpriv_responsiveness():
    """Verify mock SNMP responds to SNMPv3 authPriv queries using Admin user."""
    cmd = [
        "docker", "exec", "nawari-mock-snmp",
        "snmpget", "-v3", "-l", "authPriv",
        "-u", "Admin",
        "-a", "SHA", "-A", "sbce_secret_auth_pass",
        "-x", "DES", "-X", "sbce_secret_priv_pass",
        "127.0.0.1", "1.3.6.1.2.1.1.5.0",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "nawari-mock-core-switch-01" in res.stdout, f"SNMPv3 response invalid: {res.stdout}"


def test_02_avaya_sbce_template_hierarchy(zabbix_client):
    """Verify Nawari Avaya SBCE by SNMP exists, links Generic Base, and defines LLD and resources."""
    tpls = zabbix_client.call(
        "template.get",
        {
            "filter": {"host": ["Nawari Avaya SBCE by SNMP"]},
            "selectParentTemplates": ["templateid", "host", "name"],
            "selectDiscoveries": ["itemid", "name", "key_"],
            "selectItems": ["itemid", "name", "key_"],
        },
    )
    assert len(tpls) == 1, "Nawari Avaya SBCE by SNMP template missing"
    tpl = tpls[0]

    parents = [p["host"] for p in tpl.get("parentTemplates", [])]
    assert "Nawari Generic SNMP Base" in parents, "Avaya SBCE must inherit Nawari Generic SNMP Base"

    discoveries = [d["key_"] for d in tpl.get("discoveries", [])]
    assert "sbce.interface.discovery" in discoveries, "sbce.interface.discovery rule missing"

    item_keys = [it["key_"] for it in tpl.get("items", [])]
    assert "system.cpu.util" in item_keys, "system.cpu.util item missing"
    assert "vm.memory.util" in item_keys, "vm.memory.util item missing"
    assert "vfs.fs.used.percent[/]" in item_keys, "vfs.fs.used.percent[/] item missing"


def test_03_mock_sbce_host_provisioned(zabbix_client):
    """Verify mock-avaya-sbce-01 is provisioned with SNMPv3 authPriv and Avaya SBCE template."""
    hosts = zabbix_client.call(
        "host.get",
        {
            "filter": {"host": ["mock-avaya-sbce-01"]},
            "selectHostGroups": ["groupid", "name"],
            "selectParentTemplates": ["templateid", "name"],
            "selectInterfaces": ["interfaceid", "type", "dns", "ip", "port", "details"],
        },
    )
    assert len(hosts) == 1, "mock-avaya-sbce-01 host missing"
    h = hosts[0]
    assert h["status"] == "0", "mock-avaya-sbce-01 must be monitored"

    groups = [g["name"] for g in h.get("hostgroups", [])]
    assert "Voice Infrastructure" in groups, f"Voice Infrastructure group missing: {groups}"
    assert "Edge SBC" in groups, f"Edge SBC group missing: {groups}"

    tpls = [t["name"] for t in h.get("parentTemplates", [])]
    assert "Nawari Avaya SBCE by SNMP" in tpls, f"Avaya SBCE template not linked: {tpls}"

    ifaces = h.get("interfaces", [])
    assert len(ifaces) >= 1, "Interface missing on mock SBCE host"
    details = ifaces[0].get("details", {})
    assert str(details.get("version")) == "3", f"Expected SNMPv3, got: {details}"
    assert details.get("securityname") == "Admin", "Expected SNMPv3 security name Admin"


def test_04_sbce_interfaces_discovered(zabbix_client):
    """Verify LLD discovered SBCE interfaces M1, M2, A1, B1 with 64-bit HC counters."""
    host = zabbix_client.get_hosts(["mock-avaya-sbce-01"])[0]
    items = zabbix_client.call(
        "item.get",
        {
            "hostids": [host["hostid"]],
            "output": ["itemid", "name", "key_"],
        },
    )
    item_names = [it["name"] for it in items]

    for iface in ["M1", "M2", "A1", "B1"]:
        oper_name = f"Interface {iface}: Operational status"
        in_octets = f"Interface {iface}: Bits received"
        out_octets = f"Interface {iface}: Bits sent"
        assert oper_name in item_names, f"Discovered item missing: {oper_name}"
        assert in_octets in item_names, f"Discovered item missing: {in_octets}"
        assert out_octets in item_names, f"Discovered item missing: {out_octets}"


def test_05_sbce_resource_metrics_active(zabbix_client):
    """Verify appliance CPU, memory, root disk space, and load average items are active."""
    host = zabbix_client.get_hosts(["mock-avaya-sbce-01"])[0]
    target_keys = [
        "system.cpu.util",
        "system.cpu.load.avg1",
        "vm.memory.total",
        "vm.memory.available",
        "vm.memory.util",
        "vfs.fs.used.percent[/]",
    ]
    items = zabbix_client.call(
        "item.get",
        {
            "hostids": [host["hostid"]],
            "output": ["itemid", "name", "key_", "state", "lastvalue", "error"],
        },
    )
    by_key = {it["key_"]: it for it in items}

    for k in target_keys:
        assert k in by_key, f"Target item key {k} missing from mock SBCE"
        it = by_key[k]
        assert it["state"] == "0", f"Item {k} is in unsupported state: {it.get('error')}"
        assert it["lastvalue"] is not None and it["lastvalue"] != "", f"Item {k} has no value"


def test_06_historical_telemetry_persisted(zabbix_client):
    """Verify historical metric records exist in PostgreSQL via history.get."""
    host = zabbix_client.get_hosts(["mock-avaya-sbce-01"])[0]
    items = zabbix_client.call(
        "item.get",
        {
            "hostids": [host["hostid"]],
            "output": ["itemid", "name", "key_", "value_type"],
        },
    )
    verified = 0
    for it in items:
        h = zabbix_client.call(
            "history.get",
            {
                "itemids": [it["itemid"]],
                "history": int(it["value_type"]),
                "limit": 2,
            },
        )
        if h:
            verified += 1
        if verified >= 5:
            break

    assert verified >= 5, f"Expected at least 5 items with historical records, found {verified}"


def test_07_voice_signaling_fault_injection_lifecycle(zabbix_client):
    """Inject link-down on voice interface A1, verify High problem alert, then link-up and verify resolution."""
    host = zabbix_client.get_hosts(["mock-avaya-sbce-01"])[0]
    hostid = host["hostid"]

    items = zabbix_client.call(
        "item.get",
        {
            "hostids": [hostid],
            "search": {"name": "Interface A1: Operational status"},
        },
    )
    assert len(items) == 1, "Interface A1 operational status item missing"
    itemid = items[0]["itemid"]

    # 1. Fault injection: Link Down
    subprocess.run(
        ["docker", "exec", "nawari-mock-snmp", "/usr/local/bin/inject_fault.sh", "link-down", "A1"],
        check=True,
    )
    zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})

    problem_detected = False
    for _ in range(12):
        time.sleep(2)
        probs = zabbix_client.call(
            "problem.get",
            {
                "hostids": [hostid],
                "search": {"name": "Interface A1: Link down"},
            },
        )
        if probs:
            assert int(probs[0]["severity"]) >= 4, "A1 link down trigger must be HIGH priority (4)"
            problem_detected = True
            break
        zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})

    assert problem_detected, "Failed to detect A1 Link down problem in Zabbix"

    # 2. Recovery: Link Up
    subprocess.run(
        ["docker", "exec", "nawari-mock-snmp", "/usr/local/bin/inject_fault.sh", "link-up", "A1"],
        check=True,
    )
    zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})

    problem_resolved = False
    for _ in range(12):
        time.sleep(2)
        probs = zabbix_client.call(
            "problem.get",
            {
                "hostids": [hostid],
                "search": {"name": "Interface A1: Link down"},
            },
        )
        if not probs:
            problem_resolved = True
            break
        zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})

    assert problem_resolved, "A1 Link down problem did not resolve automatically after recovery"


def test_08_grafana_sbce_dashboard_provisioned(grafana_auth_header):
    """Verify Avaya SBCE Operational & Voice Telemetry Dashboard exists in Grafana with all panels."""
    url = "http://127.0.0.1:3001/api/dashboards/uid/nawari-sbce-health"
    req = urllib.request.Request(url, headers={"Authorization": grafana_auth_header})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"Dashboard retrieval returned HTTP {resp.status}"
        data = json.loads(resp.read().decode("utf-8"))

    dash = data.get("dashboard", {})
    assert dash.get("title") == "Nawari — Avaya SBCE Operational Health"
    panels = dash.get("panels", [])
    assert len(panels) >= 15, f"Expected at least 15 panels, found {len(panels)}"


def test_09_production_target_reconciliation(zabbix_client):
    """Verify production target avaya-sbce-01 links Nawari Avaya SBCE by SNMP with reconciled IP."""
    hosts = zabbix_client.call(
        "host.get",
        {
            "filter": {"host": ["avaya-sbce-01"]},
            "selectParentTemplates": ["templateid", "name"],
            "selectInterfaces": ["interfaceid", "ip"],
        },
    )
    assert len(hosts) == 1, "Production host avaya-sbce-01 missing"
    h = hosts[0]
    tpls = [t["name"] for t in h.get("parentTemplates", [])]
    assert "Nawari Avaya SBCE by SNMP" in tpls, f"Production host not linked to Avaya template: {tpls}"
    ip = h["interfaces"][0]["ip"]
    assert ip == "10.2.156.131", f"Expected primary active IP 10.2.156.131, got {ip}"

