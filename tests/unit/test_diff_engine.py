"""Unit tests for the deterministic diff engine."""

import pytest

from services.api.client.models import HostGroup, InterfaceType, MacroType
from services.api.provisioning.diff import ActionType, DiffEngine, EntityType
from services.api.provisioning.schema import (
    DesiredHost,
    DesiredHostGroup,
    DesiredInterface,
    DesiredMacro,
)


def test_diff_host_groups_all_missing():
    desired = [
        DesiredHostGroup(name="Voice Infrastructure"),
        DesiredHostGroup(name="Core Network"),
    ]
    live = []
    diffs = DiffEngine.diff_host_groups(desired, live)
    assert len(diffs) == 2
    assert all(d.action == ActionType.CREATE for d in diffs)


def test_diff_host_groups_partial_match():
    desired = [
        DesiredHostGroup(name="Voice Infrastructure"),
        DesiredHostGroup(name="Core Network"),
    ]
    live = [HostGroup(groupid="10", name="Voice Infrastructure")]
    diffs = DiffEngine.diff_host_groups(desired, live)
    assert len(diffs) == 2
    noop = next(d for d in diffs if d.entity_name == "Voice Infrastructure")
    create = next(d for d in diffs if d.entity_name == "Core Network")
    assert noop.action == ActionType.NOOP
    assert noop.target_id == "10"
    assert create.action == ActionType.CREATE


def test_diff_hosts_create_needed():
    desired = [
        DesiredHost(
            host="sbce-01",
            name="SBCE Primary",
            groups=["Voice"],
            templates=["SNMP Device"],
        )
    ]
    live = []
    diffs = DiffEngine.diff_hosts(
        desired_hosts=desired,
        live_hosts=live,
        template_name_to_id={"SNMP Device": "100"},
        group_name_to_id={"Voice": "20"},
    )
    assert len(diffs) == 1
    assert diffs[0].action == ActionType.CREATE
    assert diffs[0].entity_name == "sbce-01"


def test_diff_hosts_noop_when_synchronized():
    desired = [
        DesiredHost(
            host="sbce-01",
            name="SBCE Primary",
            groups=["Voice"],
            templates=["SNMP Device"],
            interfaces=[DesiredInterface(ip="10.2.1.200", port="161", type=InterfaceType.SNMP)],
            macros=[DesiredMacro(macro="{$COMMUNITY}", value="secret123", type=MacroType.TEXT)],
        )
    ]
    live = [
        {
            "hostid": "1001",
            "host": "sbce-01",
            "name": "SBCE Primary",
            "status": "0",
            "description": "",
            "hostgroups": [{"groupid": "20", "name": "Voice"}],
            "parentTemplates": [{"templateid": "100", "host": "SNMP Device"}],
            "interfaces": [
                {
                    "interfaceid": "500",
                    "main": "1",
                    "type": str(int(InterfaceType.SNMP)),
                    "ip": "10.2.1.200",
                    "port": "161",
                    "details": {},
                }
            ],
            "macros": [
                {
                    "hostmacroid": "800",
                    "macro": "{$COMMUNITY}",
                    "value": "secret123",
                    "type": str(int(MacroType.TEXT)),
                }
            ],
        }
    ]
    diffs = DiffEngine.diff_hosts(
        desired_hosts=desired,
        live_hosts=live,
        template_name_to_id={"SNMP Device": "100"},
        group_name_to_id={"Voice": "20"},
    )
    assert len(diffs) == 1
    assert diffs[0].action == ActionType.NOOP
    assert diffs[0].target_id == "1001"


def test_diff_hosts_detects_property_updates():
    desired = [
        DesiredHost(
            host="sbce-01",
            name="SBCE New Name",
            description="Updated description",
            groups=["Voice", "Edge SBC"],
        )
    ]
    live = [
        {
            "hostid": "1001",
            "host": "sbce-01",
            "name": "SBCE Old Name",
            "description": "Old description",
            "status": "0",
            "hostgroups": [{"groupid": "20", "name": "Voice"}],
            "parentTemplates": [],
            "interfaces": [],
            "macros": [],
        }
    ]
    diffs = DiffEngine.diff_hosts(
        desired_hosts=desired,
        live_hosts=live,
        template_name_to_id={},
        group_name_to_id={"Voice": "20", "Edge SBC": "21"},
    )
    assert len(diffs) == 1
    assert diffs[0].action == ActionType.UPDATE
    details = diffs[0].details
    assert "name" in details
    assert "description" in details
    assert "groups" in details

