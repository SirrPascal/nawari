"""Unit tests for Topology Graph, Path Finding, Dependency Engine, and Change Detector."""

from __future__ import annotations

import time
import pytest

from services.topology.change_detector import TopologyChangeDetector
from services.topology.dependency import DependencyEngine
from services.topology.graph import TopologyGraph
from services.topology.models import (
    ChangeType,
    Criticality,
    Device,
    DeviceType,
    DiscoveryProtocol,
    FailureImpact,
    Interface,
    LinkType,
    OperStatus,
    RoutingAdjacency,
    ServiceDependency,
)


@pytest.fixture
def enterprise_topology():
    """Build a realistic Kenya Airways enterprise campus topology:

    Core Router -> Core Switch -> Access Switch T1A -> Workstation & SBCE Edge.
    """
    graph = TopologyGraph()

    # 1. Devices
    core_router = Device(
        device_id="dev-rtr-core-01",
        canonical_name="rtr-core-01.nbo.kenya-airways.com",
        management_ip="10.2.156.1",
        vendor="Cisco",
        model="ASR 1001-X",
        device_type=DeviceType.CORE_ROUTER,
    )
    core_sw = Device(
        device_id="dev-sw-core-01",
        canonical_name="sw-core-01.nbo.kenya-airways.com",
        management_ip="10.2.156.45",
        vendor="Cisco",
        model="Catalyst 9500-48Y4C",
        device_type=DeviceType.DIST_SWITCH,
    )
    access_sw = Device(
        device_id="dev-sw-acc-t1a",
        canonical_name="sw-acc-t1a.nbo.kenya-airways.com",
        management_ip="10.2.156.90",
        vendor="Cisco",
        model="Catalyst 2960X",
        device_type=DeviceType.ACCESS_SWITCH,
    )
    sbce = Device(
        device_id="dev-sbce-01",
        canonical_name="sbce-edge-01.nbo.kenya-airways.com",
        management_ip="10.2.156.60",
        vendor="Avaya",
        model="SBCE 8.1",
        device_type=DeviceType.SBC,
    )

    graph.add_device(core_router)
    graph.add_device(core_sw)
    graph.add_device(access_sw)
    graph.add_device(sbce)

    # 2. Interfaces
    # Core Router: TenGig0/0/0
    rtr_if = Interface(
        interface_id="if-rtr-1",
        device_id=core_router.device_id,
        if_index=1,
        if_name="TenGigabitEthernet0/0/0",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    # Core Switch: Te1/0/1 (downlink from router) & Te1/0/2 (uplink to access) & Te1/0/10 (to SBCE)
    core_if1 = Interface(
        interface_id="if-core-1",
        device_id=core_sw.device_id,
        if_index=1,
        if_name="TenGigabitEthernet1/0/1",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
        is_uplink=True,
    )
    core_if2 = Interface(
        interface_id="if-core-2",
        device_id=core_sw.device_id,
        if_index=2,
        if_name="TenGigabitEthernet1/0/2",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    core_if10 = Interface(
        interface_id="if-core-10",
        device_id=core_sw.device_id,
        if_index=10,
        if_name="TenGigabitEthernet1/0/10",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    # Access Switch: Gi1/0/48 (uplink to core)
    acc_if48 = Interface(
        interface_id="if-acc-48",
        device_id=access_sw.device_id,
        if_index=48,
        if_name="GigabitEthernet1/0/48",
        oper_status=OperStatus.UP,
        speed_bps=1_000_000_000,
        is_uplink=True,
    )
    # SBCE: eth0 (to core switch)
    sbce_if0 = Interface(
        interface_id="if-sbce-0",
        device_id=sbce.device_id,
        if_index=1,
        if_name="eth0",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
        is_uplink=True,
    )

    for iface in (rtr_if, core_if1, core_if2, core_if10, acc_if48, sbce_if0):
        graph.add_interface(iface)

    # 3. Links
    # Router <-> Core Switch
    graph.add_link(
        rtr_if.interface_id,
        core_if1.interface_id,
        discovery_protocol=DiscoveryProtocol.LLDP,
        link_type=LinkType.ROUTED,
        is_reciprocal=True,
    )
    # Core Switch <-> Access Switch
    graph.add_link(
        core_if2.interface_id,
        acc_if48.interface_id,
        discovery_protocol=DiscoveryProtocol.LLDP,
        link_type=LinkType.TRUNK,
        is_reciprocal=True,
    )
    # Core Switch <-> SBCE
    graph.add_link(
        core_if10.interface_id,
        sbce_if0.interface_id,
        discovery_protocol=DiscoveryProtocol.CDP,
        link_type=LinkType.TRUNK,
        is_reciprocal=True,
    )

    # 4. Service Dependencies
    graph.add_service_dependency(
        ServiceDependency(
            dependency_id="dep-voice-sbce",
            service_id="voice-telephony-sip",
            dependent_type="DEVICE",
            dependent_id=sbce.device_id,
            criticality=Criticality.CRITICAL,
            failure_impact=FailureImpact.TOTAL_OUTAGE,
        )
    )
    graph.add_service_dependency(
        ServiceDependency(
            dependency_id="dep-voice-coresw",
            service_id="voice-telephony-sip",
            dependent_type="DEVICE",
            dependent_id=core_sw.device_id,
            criticality=Criticality.CRITICAL,
            failure_impact=FailureImpact.TOTAL_OUTAGE,
        )
    )

    return graph


def test_topology_graph_path_finding(enterprise_topology: TopologyGraph):
    path = enterprise_topology.find_path("dev-rtr-core-01", "dev-sbce-01")
    assert path == ["dev-rtr-core-01", "dev-sw-core-01", "dev-sbce-01"]

    path_acc = enterprise_topology.find_path("dev-rtr-core-01", "dev-sw-acc-t1a")
    assert path_acc == ["dev-rtr-core-01", "dev-sw-core-01", "dev-sw-acc-t1a"]

    # Non-existent device returns empty
    assert enterprise_topology.find_path("dev-rtr-core-01", "dev-nonexistent") == []


def test_upstream_path_traversal(enterprise_topology: TopologyGraph):
    # From access switch up to core router
    upstream = enterprise_topology.get_upstream_path("dev-sw-acc-t1a")
    assert len(upstream) >= 1
    dev, iface = upstream[0]
    assert dev.device_id == "dev-sw-acc-t1a"
    assert iface.is_uplink is True


def test_to_node_graph_serialization(enterprise_topology: TopologyGraph):
    node_graph = enterprise_topology.to_node_graph()
    assert "nodes" in node_graph
    assert "edges" in node_graph
    assert len(node_graph["nodes"]) == 4
    assert len(node_graph["edges"]) == 3

    # Check node fields
    first_node = node_graph["nodes"][0]
    assert "id" in first_node
    assert "title" in first_node
    assert "mainStat" in first_node
    assert "color" in first_node


def test_blast_radius_engine(enterprise_topology: TopologyGraph):
    engine = DependencyEngine(enterprise_topology)

    # Core switch failure impacts downstream switches, SBCE, and voice service
    report = engine.calculate_device_blast_radius("dev-sw-core-01")
    assert report.total_impacted_devices >= 3
    assert report.severity == "CRITICAL"
    assert any(s["service_id"] == "voice-telephony-sip" for s in report.impacted_services)

    # Single Points of Failure detection
    spofs = engine.identify_single_points_of_failure()
    assert len(spofs) >= 1
    # Access switch and SBCE both have only 1 uplink
    dev_ids = [s["device_id"] for s in spofs]
    assert "dev-sw-acc-t1a" in dev_ids


def test_topology_change_detector(enterprise_topology: TopologyGraph):
    detector = TopologyChangeDetector(flap_threshold=3, flap_window_seconds=300)

    # Simulate snapshots: modify an interface state
    prev_devs = dict(enterprise_topology.devices)
    curr_devs = dict(enterprise_topology.devices)

    prev_ifaces = {i.interface_id: Interface.from_dict(i.to_dict()) for i in enterprise_topology.interfaces.values()}
    curr_ifaces = {i.interface_id: Interface.from_dict(i.to_dict()) for i in enterprise_topology.interfaces.values()}

    # Interface 1 goes DOWN
    curr_ifaces["if-core-1"].oper_status = OperStatus.DOWN

    changes = detector.diff_snapshots(
        prev_devs,
        curr_devs,
        prev_ifaces,
        curr_ifaces,
        enterprise_topology.links,
        enterprise_topology.links,
    )

    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.LINK_DOWN
    assert changes[0].target_entity_id == "if-core-1"

    # Query recent changes for entity
    recent = detector.find_recent_changes_for_entity("if-core-1", within_seconds=60)
    assert len(recent) == 1
    assert recent[0].change_type == ChangeType.LINK_DOWN

