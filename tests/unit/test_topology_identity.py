"""Unit tests for Topology Models, Identity Cascade and Evidentiary Scoring."""

from __future__ import annotations

import pytest

from services.topology.identity import (
    EvidentiaryScorer,
    generate_dependency_id,
    generate_device_id,
    generate_interface_id,
    generate_link_id,
    generate_subnet_id,
    normalize_ip_address,
    normalize_mac_address,
)
from services.topology.models import (
    ConfidenceLevel,
    Criticality,
    Device,
    DeviceType,
    DiscoveryProtocol,
    FailureImpact,
    Interface,
    Layer2Link,
    OperStatus,
    RoutingAdjacency,
    ServiceDependency,
    Subnet,
    TopologyChange,
)


def test_normalize_mac_address():
    assert normalize_mac_address("00:1A:2B:3C:4D:5E") == "00:1a:2b:3c:4d:5e"
    assert normalize_mac_address("001a.2b3c.4d5e") == "00:1a:2b:3c:4d:5e"
    assert normalize_mac_address("00-1A-2B-3C-4D-5E") == "00:1a:2b:3c:4d:5e"
    assert normalize_mac_address("invalid-mac") is None
    assert normalize_mac_address(None) is None


def test_normalize_ip_address():
    assert normalize_ip_address(" 10.2.156.45 ") == "10.2.156.45"
    assert normalize_ip_address("2001:db8::1") == "2001:db8::1"
    assert normalize_ip_address("999.999.999.999") is None
    assert normalize_ip_address(None) is None


def test_generate_device_id_cascade():
    # 1. Chassis MAC has highest priority
    id_mac = generate_device_id(
        chassis_mac="00:1A:2B:3C:4D:5E",
        serial_number="FOC12345678",
        zabbix_host_id=10105,
        management_ip="10.2.156.45",
    )
    assert id_mac.startswith("dev-")
    # Same MAC produces identical ID
    assert id_mac == generate_device_id(chassis_mac="001a.2b3c.4d5e")

    # 2. Serial number priority when no MAC
    id_serial = generate_device_id(
        serial_number="FOC12345678",
        zabbix_host_id=10105,
        management_ip="10.2.156.45",
    )
    assert id_serial.startswith("dev-")
    assert id_serial != id_mac
    assert id_serial == generate_device_id(serial_number="foc12345678")

    # 3. Zabbix host ID priority when no MAC or Serial
    id_zbx = generate_device_id(
        zabbix_host_id=10105,
        management_ip="10.2.156.45",
    )
    assert id_zbx.startswith("dev-")
    assert id_zbx != id_serial
    assert id_zbx == generate_device_id(zabbix_host_id=10105)

    # 4. Management IP priority
    id_ip = generate_device_id(management_ip="10.2.156.45")
    assert id_ip.startswith("dev-")
    assert id_ip == generate_device_id(management_ip="10.2.156.45")

    # 5. Missing all raises ValueError
    with pytest.raises(ValueError):
        generate_device_id()


def test_deterministic_ids():
    if_id = generate_interface_id("dev-1234567890abcdef", 101)
    assert if_id == "if-dev-1234567890abcdef-101"

    # Undirected link ID ensures symmetry
    link1 = generate_link_id("if-a-1", "if-b-2")
    link2 = generate_link_id("if-b-2", "if-a-1")
    assert link1 == link2
    assert link1 == "link-if-a-1-if-b-2"

    sub_id = generate_subnet_id("10.100.20.0/24")
    assert sub_id.startswith("sub-")
    assert sub_id == generate_subnet_id("10.100.20.0/24")

    dep_id = generate_dependency_id("voice-sip", "dev-cisco01")
    assert dep_id == "dep-voice-sip-dev-cisco01"


def test_evidentiary_scorer():
    score, level = EvidentiaryScorer.score_link("LLDP", is_reciprocal=True)
    assert score >= 0.95
    assert level == ConfidenceLevel.CONFIRMED

    score_cdp, level_cdp = EvidentiaryScorer.score_link("CDP", is_reciprocal=True)
    assert score_cdp >= 0.95
    assert level_cdp == ConfidenceLevel.CONFIRMED

    score_unidir, level_unidir = EvidentiaryScorer.score_link("LLDP", is_reciprocal=False)
    assert 0.75 <= score_unidir < 0.95
    assert level_unidir == ConfidenceLevel.PROBABLE

    score_fdb, level_fdb = EvidentiaryScorer.score_link("BRIDGE_FDB", is_reciprocal=False)
    assert 0.50 <= score_fdb < 0.75
    assert level_fdb == ConfidenceLevel.INFERRED

    score_trace, level_trace = EvidentiaryScorer.score_link("ENDPOINT_TRACEROUTE")
    assert level_trace == ConfidenceLevel.INFERRED


def test_models_dataclass_serialization():
    dev = Device(
        device_id="dev-cisco9500",
        canonical_name="sw-core-01.nbo.kenya-airways.com",
        management_ip="10.2.156.45",
        vendor="Cisco",
        model="Catalyst 9500-48Y4C",
        device_type=DeviceType.CORE_ROUTER,
        confidence_score=0.98,
    )
    assert dev.confidence_level == ConfidenceLevel.CONFIRMED
    d_dict = dev.to_dict()
    assert d_dict["vendor"] == "Cisco"
    restored_dev = Device.from_dict(d_dict)
    assert restored_dev.canonical_name == dev.canonical_name

    iface = Interface(
        interface_id="if-dev-cisco9500-1",
        device_id="dev-cisco9500",
        if_index=1,
        if_name="TenGigabitEthernet1/0/1",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    assert iface.is_operational is True
    assert iface.to_dict()["speed_bps"] == 10_000_000_000

    link = Layer2Link(
        link_id="link-1-2",
        source_interface_id="if-dev-cisco9500-1",
        target_interface_id="if-dev-access01-24",
        discovery_protocol=DiscoveryProtocol.LLDP,
        confidence=0.98,
    )
    assert link.to_dict()["confidence"] == 0.98

    dep = ServiceDependency(
        dependency_id="dep-voice-sw01",
        service_id="voice-synthetic-probe",
        dependent_type="DEVICE",
        dependent_id="dev-cisco9500",
        criticality=Criticality.CRITICAL,
        failure_impact=FailureImpact.TOTAL_OUTAGE,
    )
    assert dep.to_dict()["failure_impact"] == "TOTAL_OUTAGE"

    change = TopologyChange(
        change_type="LINK_DOWN",
        target_entity_type="INTERFACE",
        target_entity_id="if-dev-cisco9500-1",
        before_state={"oper_status": 1},
        after_state={"oper_status": 2},
    )
    assert change.to_dict()["change_type"] == "LINK_DOWN"

