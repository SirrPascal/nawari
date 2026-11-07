"""Unit tests for Nawari configuration and desired-state schema models."""

import os
from pathlib import Path
import pytest

from services.api.client.models import (
    InterfaceType,
    MacroType,
    SNMPAuthProtocol,
    SNMPPrivProtocol,
    SNMPSecurityLevel,
    SNMPVersion,
)
from services.api.config import resolve_secret_reference
from services.api.provisioning.schema import (
    DesiredHost,
    DesiredHostGroup,
    DesiredInterface,
    DesiredInterfaceDetails,
    DesiredMacro,
    load_desired_state_from_dir,
)


def test_resolve_secret_reference():
    os.environ["TEST_SECRET_ABC"] = "resolved_value_123"
    try:
        assert resolve_secret_reference("no_vars") == "no_vars"
        assert resolve_secret_reference("${TEST_SECRET_ABC}") == "resolved_value_123"
        assert resolve_secret_reference("prefix_${TEST_SECRET_ABC}_suffix") == "prefix_resolved_value_123_suffix"
        assert resolve_secret_reference("${NON_EXISTENT_VAR:-fallback}") == "fallback"
        assert resolve_secret_reference("${NON_EXISTENT_VAR}") == ""
    finally:
        os.environ.pop("TEST_SECRET_ABC", None)


def test_desired_interface_details_snmpv3():
    data = {
        "version": 3,
        "securityname": "test_user",
        "securitylevel": "authPriv",
        "authprotocol": "SHA256",
        "authpassphrase": "auth_secret_phrase",
        "privprotocol": "AES256",
        "privpassphrase": "priv_secret_phrase",
    }
    details = DesiredInterfaceDetails.from_dict(data)
    assert details.version == SNMPVersion.SNMP_V3
    assert details.securitylevel == SNMPSecurityLevel.AUTH_PRIV
    assert details.authprotocol == SNMPAuthProtocol.SHA256
    assert details.privprotocol == SNMPPrivProtocol.AES256
    assert details.securityname == "test_user"

    d = details.to_dict()
    assert d["version"] == 3
    assert d["securityname"] == "test_user"
    assert d["securitylevel"] == 2
    assert d["authpassphrase"] == "auth_secret_phrase"
    assert d["privpassphrase"] == "priv_secret_phrase"


def test_desired_interface_snmpv2():
    data = {
        "type": "snmp",
        "ip": "10.2.1.50",
        "port": 161,
        "details": {
            "version": 2,
            "community": "public",
        },
    }
    iface = DesiredInterface.from_dict(data)
    assert iface.type == InterfaceType.SNMP
    assert iface.ip == "10.2.1.50"
    assert iface.port == "161"
    assert iface.details is not None
    assert iface.details.version == SNMPVersion.SNMP_V2C
    assert iface.details.community == "public"


def test_desired_macro_formatting():
    m1 = DesiredMacro.from_dict({"macro": "MY_MACRO", "value": "val1"})
    assert m1.macro == "{$MY_MACRO}"
    assert m1.type == MacroType.TEXT

    m2 = DesiredMacro.from_dict({"macro": "{$SECRET_KEY}", "value": "secret", "type": "secret"})
    assert m2.macro == "{$SECRET_KEY}"
    assert m2.type == MacroType.SECRET


def test_desired_host_parsing():
    data = {
        "host": "test-sbce-01",
        "name": "Test SBC",
        "groups": ["Voice Infrastructure", "Edge SBC"],
        "templates": ["Network Generic Device by SNMP"],
        "interfaces": [{"type": "snmp", "ip": "10.0.0.1", "port": 161}],
        "macros": [{"macro": "{$SNMP_PORT}", "value": "161"}],
        "tags": [{"tag": "env", "value": "test"}],
    }
    dh = DesiredHost.from_dict(data)
    assert dh.host == "test-sbce-01"
    assert dh.name == "Test SBC"
    assert len(dh.groups) == 2
    assert len(dh.templates) == 1
    assert len(dh.interfaces) == 1
    assert len(dh.macros) == 1
    assert len(dh.tags) == 1
