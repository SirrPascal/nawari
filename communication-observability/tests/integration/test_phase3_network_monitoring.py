"""Integration acceptance tests for Nawari Phase 3 Network Monitoring Framework.

Validates:
1. Mock SNMP agent responsiveness on UDP 161 (Net-SNMP with IF-MIB dummy interfaces).
2. Nawari SNMP template hierarchy (Base + Network Device) and declarative linkage.
3. Low-level discovery (LLD) interface discovery and prototype item generation.
4. Real historical metric polling in PostgreSQL via history.get.
5. Automated fault injection, Problem alert firing on link-down, and automatic resolution.
6. Provisioned Grafana operational dashboards (Overview and Interface Traffic & Health).
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


def test_01_mock_snmp_container_healthy():
    """Verify that nawari-mock-snmp container is running and responds to SNMP queries."""
    res = subprocess.run(
        ["docker", "exec", "nawari-mock-snmp", "snmpget", "-v2c", "-c", "public", "127.0.0.1", "SNMPv2-MIB::sysName.0"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "nawari-mock-core-switch-01" in res.stdout, f"Unexpected sysName: {res.stdout}"


def test_02_template_hierarchy_present(zabbix_client):
    """Verify that Nawari Generic SNMP Base and Nawari Network Device by SNMP exist with linkage."""
    base_tpl = zabbix_client.call("template.get", {"filter": {"host": ["Nawari Generic SNMP Base"]}})
    assert len(base_tpl) == 1, "Nawari Generic SNMP Base template missing"

    net_tpl = zabbix_client.call(
        "template.get",
        {
            "filter": {"host": ["Nawari Network Device by SNMP"]},
            "selectParentTemplates": ["templateid", "host", "name"],
            "selectDiscoveries": ["itemid", "name", "key_"],
        },
    )
    assert len(net_tpl) == 1, "Nawari Network Device by SNMP template missing"
    parents = [p["host"] for p in net_tpl[0].get("parentTemplates", [])]
    assert "Nawari Generic SNMP Base" in parents, "Template hierarchy linkage missing"

    discoveries = [d["key_"] for d in net_tpl[0].get("discoveries", [])]
    assert "net.if.discovery" in discoveries, "net.if.discovery rule missing in network template"


def test_03_mock_host_provisioned_and_linked(zabbix_client):
    """Verify that mock-core-switch-01 is provisioned, monitored, and links the network template."""
    hosts = zabbix_client.call(
        "host.get",
        {
            "filter": {"host": ["mock-core-switch-01"]},
            "selectHostGroups": ["groupid", "name"],
            "selectParentTemplates": ["templateid", "name"],
            "selectInterfaces": ["interfaceid", "type", "dns", "ip", "port", "useip"],
        },
    )
    assert len(hosts) == 1, "mock-core-switch-01 host missing in Zabbix"
    h = hosts[0]
    assert h["status"] == "0", "mock-core-switch-01 should be monitored (status 0)"

    group_names = [g["name"] for g in h.get("hostgroups", [])]
    assert "Core Network" in group_names, f"Core Network group missing: {group_names}"

    tpl_names = [t["name"] for t in h.get("parentTemplates", [])]
    assert "Nawari Network Device by SNMP" in tpl_names, f"Network template not linked: {tpl_names}"

    assert len(h.get("interfaces", [])) >= 1, "SNMP interface missing on mock host"
    iface = h["interfaces"][0]
    assert iface["dns"] == "mock-snmp" or iface["ip"] != "", "Interface endpoint invalid"


def test_04_lld_interface_discovery_executed(zabbix_client):
    """Verify that LLD rule has run and discovered interfaces while filtering loopback."""
    hosts = zabbix_client.call("host.get", {"filter": {"host": ["mock-core-switch-01"]}})
    hostid = hosts[0]["hostid"]

    llds = zabbix_client.call(
        "discoveryrule.get",
        {"hostids": [hostid], "filter": {"key_": ["net.if.discovery"]}},
    )
    assert len(llds) == 1, "Discovery rule net.if.discovery missing on host"
    assert llds[0]["error"] == "", f"Discovery rule reported error: {llds[0]['error']}"

    # Verify discovered interface items
    items = zabbix_client.call("item.get", {"hostids": [hostid], "output": ["itemid", "name", "key_"]})
    assert len(items) >= 45, f"Expected at least 45 discovered items, found {len(items)}"

    # Check key discovered interface names
    all_names = " ".join([it["name"] for it in items])
    assert "ge-0-0-1" in all_names, "Interface ge-0-0-1 not discovered"
    assert "ge-0-0-2" in all_names, "Interface ge-0-0-2 not discovered"
    assert "sbc-ext0" in all_names, "Interface sbc-ext0 not discovered"
    # Ensure loopback was properly filtered out
    assert "Interface lo:" not in all_names, "Loopback interface should have been filtered out"


def test_05_item_prototypes_created(zabbix_client):
    """Verify that all required metric prototypes are instantiated for ge-0-0-1."""
    hosts = zabbix_client.call("host.get", {"filter": {"host": ["mock-core-switch-01"]}})
    hostid = hosts[0]["hostid"]

    items = zabbix_client.call("item.get", {"hostids": [hostid], "output": ["itemid", "name", "key_"]})
    ge1_keys = [it["key_"] for it in items if "ge-0-0-1" in it["name"] or ".12]" in it["key_"]]

    expected_keys_prefix = [
        "net.if.status[",
        "net.if.adminstatus[",
        "net.if.speed[",
        "net.if.in[",
        "net.if.out[",
        "net.if.in.errors[",
        "net.if.out.errors[",
        "net.if.in.discards[",
        "net.if.out.discards[",
    ]
    for pfx in expected_keys_prefix:
        assert any(pfx in k for k in ge1_keys), f"Missing prototype metric {pfx} on ge-0-0-1"


def test_06_real_historical_telemetry_collected(zabbix_client):
    """Verify that real telemetry is polled and stored in PostgreSQL history tables."""
    hosts = zabbix_client.call("host.get", {"filter": {"host": ["mock-core-switch-01"]}})
    hostid = hosts[0]["hostid"]

    # Check system identity item history
    sysname_items = zabbix_client.call(
        "item.get", {"hostids": [hostid], "filter": {"key_": ["system.name"]}}
    )
    assert len(sysname_items) == 1
    h_text = zabbix_client.call(
        "history.get",
        {"itemids": [sysname_items[0]["itemid"]], "history": 1, "limit": 10},
    )
    assert len(h_text) > 0, "No historical data recorded for system.name in PostgreSQL"
    assert "nawari-mock-core-switch-01" in h_text[0]["value"]

    # Check system uptime item history (float history type 0)
    uptime_items = zabbix_client.call(
        "item.get",
        {"hostids": [hostid], "filter": {"key_": ["system.uptime[sysUpTime.0]"]}},
    )
    assert len(uptime_items) == 1
    h_float = zabbix_client.call(
        "history.get",
        {"itemids": [uptime_items[0]["itemid"]], "history": 0, "limit": 10},
    )
    assert len(h_float) > 0, "No historical data recorded for system.uptime in PostgreSQL"
    assert float(h_float[0]["value"]) > 0

    # Check interface operational status history (uint history type 3)
    status_items = zabbix_client.call(
        "item.get",
        {"hostids": [hostid], "filter": {"key_": ["net.if.status[ifOperStatus.12]"]}},
    )
    assert len(status_items) == 1
    h_uint = zabbix_client.call(
        "history.get",
        {"itemids": [status_items[0]["itemid"]], "history": 3, "limit": 10},
    )
    assert len(h_uint) > 0, "No historical data recorded for ge-0-0-1 operational status"


def test_07_trigger_prototypes_and_thresholds(zabbix_client):
    """Verify that trigger prototypes for link down, high util, and error rates are instantiated."""
    hosts = zabbix_client.call("host.get", {"filter": {"host": ["mock-core-switch-01"]}})
    hostid = hosts[0]["hostid"]

    triggers = zabbix_client.call(
        "trigger.get",
        {"hostids": [hostid], "output": ["triggerid", "description", "priority", "status"]},
    )
    assert len(triggers) >= 15, f"Expected at least 15 triggers, found {len(triggers)}"

    descriptions = [tr["description"] for tr in triggers]
    assert any("Interface ge-0-0-1: Link down" in d for d in descriptions)
    assert any("High bandwidth utilization" in d for d in descriptions)
    assert any("High error rate" in d for d in descriptions)


def test_08_fault_injection_and_problem_lifecycle(zabbix_client):
    """Verify end-to-end fault injection: link-down triggers active Problem, link-up auto-resolves."""
    hosts = zabbix_client.call("host.get", {"filter": {"host": ["mock-core-switch-01"]}})
    hostid = hosts[0]["hostid"]

    # Locate trigger for ge-0-0-1 link down
    triggers = zabbix_client.call(
        "trigger.get",
        {
            "hostids": [hostid],
            "filter": {"description": ["Interface ge-0-0-1: Link down"]},
            "output": ["triggerid", "description", "value"],
        },
    )
    assert len(triggers) == 1, "Link down trigger for ge-0-0-1 missing"
    triggerid = triggers[0]["triggerid"]

    # Locate item for ge-0-0-1 operational status
    items = zabbix_client.call(
        "item.get",
        {"hostids": [hostid], "filter": {"key_": ["net.if.status[ifOperStatus.12]"]}},
    )
    itemid = items[0]["itemid"]

    # 1. Inject link down
    subprocess.run(
        ["docker", "exec", "nawari-mock-snmp", "/usr/local/bin/inject_fault.sh", "link-down", "ge-0-0-1"],
        check=True,
    )
    time.sleep(5)  # Allow Net-SNMP cache to refresh

    # Poll interface status
    zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})
    
    # Wait for problem to be registered (async task manager dispatch)
    problem_detected = False
    for _ in range(6):
        time.sleep(2)
        problems = zabbix_client.call("problem.get", {"objectids": [triggerid]})
        if len(problems) > 0:
            problem_detected = True
            break
    assert problem_detected, "Expected active problem event for ge-0-0-1 link down within 12s"
    assert "Interface ge-0-0-1: Link down" in problems[0]["name"]

    # 2. Restore link up
    subprocess.run(
        ["docker", "exec", "nawari-mock-snmp", "/usr/local/bin/inject_fault.sh", "link-up", "ge-0-0-1"],
        check=True,
    )
    time.sleep(5)  # Allow Net-SNMP cache to refresh

    # Poll interface status again
    zabbix_client.call("task.create", {"type": 6, "request": {"itemid": itemid}})

    # Wait for problem to resolve automatically
    problem_resolved = False
    for _ in range(6):
        time.sleep(2)
        problems_after = zabbix_client.call("problem.get", {"objectids": [triggerid]})
        if len(problems_after) == 0:
            problem_resolved = True
            break
    assert problem_resolved, f"Expected problem to be resolved within 12s, but found {problems_after}"


def test_09_grafana_dashboards_provisioned(grafana_auth_header):
    """Verify that both Phase 3 Grafana dashboards are provisioned and accessible."""
    req = urllib.request.Request(
        "http://127.0.0.1:3001/api/search?type=dash-db",
        headers={"Authorization": grafana_auth_header},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        dashboards = json.loads(response.read().decode("utf-8"))
        uids = [d.get("uid") for d in dashboards]
        assert "nawari-net-overview" in uids, "nawari-net-overview dashboard not found in Grafana"
        assert "nawari-interface-health" in uids, "nawari-interface-health dashboard not found in Grafana"
