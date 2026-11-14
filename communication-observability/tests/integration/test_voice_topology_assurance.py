"""Integration tests for Workstream 10F: Voice Service Dependency Correlation with Phase 9 Topology."""

from __future__ import annotations

import pytest

from services.topology.graph import TopologyGraph
from services.topology.models import (
    ChangeType,
    Device,
    DeviceType,
    DiscoveryProtocol,
    Interface,
    LinkType,
    OperStatus,
    TopologyChange,
)
from services.voice.correlation import SessionCorrelator
from services.voice.topology_link import VoiceTopologyLink


@pytest.fixture
def voice_network_topology():
    """Build topology connecting Voice Monitoring Host -> Cisco Core Switch -> Avaya SBCE 8.1."""
    graph = TopologyGraph()

    # 1. Monitoring Host (runs Asterisk & Ingestion Gateway)
    mon_host = Device(
        device_id="dev-mon01",
        canonical_name="mon-grafana01.nbo.kenya-airways.com",
        management_ip="10.2.1.58",
        vendor="Linux",
        model="Ubuntu Server 24.04",
        device_type=DeviceType.SERVER,
    )

    # 2. Cisco Core Switch (Pride Centre)
    core_sw = Device(
        device_id="dev-core-sw",
        canonical_name="sw-core-01.nbo.kenya-airways.com",
        management_ip="10.2.156.45",
        vendor="Cisco",
        model="Catalyst 9500-48Y4C",
        device_type=DeviceType.DIST_SWITCH,
    )

    # 3. Avaya SBCE 8.1 Appliance
    sbce = Device(
        device_id="dev-sbce",
        canonical_name="sbce-edge-01.nbo.kenya-airways.com",
        management_ip="10.2.156.60",
        vendor="Avaya",
        model="SBCE 8.1",
        device_type=DeviceType.SBC,
    )

    graph.add_device(mon_host)
    graph.add_device(core_sw)
    graph.add_device(sbce)

    # Interfaces
    mon_if = Interface(
        interface_id="if-mon-eth0",
        device_id=mon_host.device_id,
        if_index=1,
        if_name="eth0",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
        is_uplink=True,
    )
    core_if_mon = Interface(
        interface_id="if-core-te1",
        device_id=core_sw.device_id,
        if_index=1,
        if_name="TenGigabitEthernet1/0/1",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    core_if_sbce = Interface(
        interface_id="if-core-te10",
        device_id=core_sw.device_id,
        if_index=10,
        if_name="TenGigabitEthernet1/0/10",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    sbce_if = Interface(
        interface_id="if-sbce-eth0",
        device_id=sbce.device_id,
        if_index=1,
        if_name="eth0",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
        is_uplink=True,
    )

    for iface in (mon_if, core_if_mon, core_if_sbce, sbce_if):
        graph.add_interface(iface)

    # Links
    graph.add_link(
        mon_if.interface_id,
        core_if_mon.interface_id,
        discovery_protocol=DiscoveryProtocol.LLDP,
        link_type=LinkType.TRUNK,
        is_reciprocal=True,
    )
    graph.add_link(
        core_if_sbce.interface_id,
        sbce_if.interface_id,
        discovery_protocol=DiscoveryProtocol.CDP,
        link_type=LinkType.TRUNK,
        is_reciprocal=True,
    )

    return graph


def test_voice_path_resolution(voice_network_topology: TopologyGraph):
    path = VoiceTopologyLink.resolve_call_path("10.2.1.58", "10.2.156.60", voice_network_topology)
    assert path == ["dev-mon01", "dev-core-sw", "dev-sbce"]


def test_voice_incident_correlated_with_physical_link_down(voice_network_topology: TopologyGraph):
    correlator = SessionCorrelator()
    sess = correlator.get_or_create_session(
        sip_call_id="call-voice-degrade-01",
        caller="1001",
        callee="4286",
    )

    # Physical change on the Core Switch interface to SBCE
    link_down_event = TopologyChange(
        change_type=ChangeType.LINK_DOWN,
        target_entity_type="INTERFACE",
        target_entity_id="if-core-te10",
        before_state={"oper_status": 1},
        after_state={"oper_status": 2},
    )

    res = VoiceTopologyLink.correlate_voice_incident(
        session=sess,
        source_ip="10.2.1.58",
        destination_ip="10.2.156.60",
        graph=voice_network_topology,
        recent_changes=[link_down_event],
    )

    assert res["has_topological_root_cause"] is True
    assert res["confidence"] == 0.98
    assert "LINK_DOWN" in res["primary_root_cause"]
    assert "sw-core-01.nbo.kenya-airways.com" in res["primary_root_cause"]
    assert len(res["correlated_changes"]) == 1


def test_voice_incident_when_physical_path_is_nominal(voice_network_topology: TopologyGraph):
    correlator = SessionCorrelator()
    sess = correlator.get_or_create_session(
        sip_call_id="call-nominal-path-02",
        caller="1001",
        callee="2398",
    )

    res = VoiceTopologyLink.correlate_voice_incident(
        session=sess,
        source_ip="10.2.1.58",
        destination_ip="10.2.156.60",
        graph=voice_network_topology,
        recent_changes=[],  # Zero physical changes
    )

    assert res["has_topological_root_cause"] is False
    assert res["confidence"] == 0.75
    assert "nominal" in res["diagnostic"]

