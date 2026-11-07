"""Integration tests for Phase 9 Network Intelligence, Topology API, and Assurance Correlation."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
import pytest

from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import HypothesisStatus, RootCauseDomain
from services.topology.api import TopologyAPI
from services.topology.change_detector import TopologyChangeDetector
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
    ServiceDependency,
    TopologyChange,
)


@pytest.fixture
def enterprise_topology_api():
    """Create a TopologyAPI instance configured with a populated Kenya Airways topology."""
    graph = TopologyGraph()
    change_detector = TopologyChangeDetector()

    # Devices
    core_sw = Device(
        device_id="dev-sw-core-01",
        canonical_name="sw-core-01.nbo.kenya-airways.com",
        management_ip="10.2.156.45",
        vendor="Cisco",
        model="Catalyst 9500-48Y4C",
        device_type=DeviceType.DIST_SWITCH,
        site_id="NBO-HQ",
    )
    acc_sw = Device(
        device_id="dev-sw-acc-t1a",
        canonical_name="sw-acc-t1a.nbo.kenya-airways.com",
        management_ip="10.2.156.90",
        vendor="Cisco",
        model="Catalyst 2960X",
        device_type=DeviceType.ACCESS_SWITCH,
        site_id="NBO-HQ",
    )
    sbce = Device(
        device_id="dev-sbce-01",
        canonical_name="sbce-edge-01.nbo.kenya-airways.com",
        management_ip="10.2.156.60",
        vendor="Avaya",
        model="SBCE 8.1",
        device_type=DeviceType.SBC,
        site_id="NBO-HQ",
    )

    graph.add_device(core_sw)
    graph.add_device(acc_sw)
    graph.add_device(sbce)

    # Interfaces
    core_if1 = Interface(
        interface_id="if-core-1",
        device_id=core_sw.device_id,
        if_index=1,
        if_name="TenGigabitEthernet1/0/1",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
    )
    acc_if48 = Interface(
        interface_id="if-acc-48",
        device_id=acc_sw.device_id,
        if_index=48,
        if_name="GigabitEthernet1/0/48",
        oper_status=OperStatus.UP,
        speed_bps=1_000_000_000,
        is_uplink=True,
    )
    sbce_if0 = Interface(
        interface_id="if-sbce-0",
        device_id=sbce.device_id,
        if_index=1,
        if_name="eth0",
        oper_status=OperStatus.UP,
        speed_bps=10_000_000_000,
        is_uplink=True,
    )

    for iface in (core_if1, acc_if48, sbce_if0):
        graph.add_interface(iface)

    # Links
    graph.add_link(
        core_if1.interface_id,
        acc_if48.interface_id,
        discovery_protocol=DiscoveryProtocol.LLDP,
        link_type=LinkType.TRUNK,
        is_reciprocal=True,
    )

    # Service Dependency
    graph.add_service_dependency(
        ServiceDependency(
            dependency_id="dep-voice-core",
            service_id="voice-telephony-sip",
            dependent_type="DEVICE",
            dependent_id=core_sw.device_id,
            criticality=Criticality.CRITICAL,
            failure_impact=FailureImpact.TOTAL_OUTAGE,
        )
    )

    # Topology Change Event
    change_detector.changes_log.append(
        TopologyChange(
            change_type=ChangeType.LINK_UP,
            target_entity_type="INTERFACE",
            target_entity_id="if-core-1",
            after_state={"oper_status": 1},
        )
    )

    api = TopologyAPI(graph=graph, change_detector=change_detector)
    return api, graph, change_detector


def test_topology_api_graph_and_inventory(enterprise_topology_api):
    api, graph, _ = enterprise_topology_api

    # 1. GET /api/v1/topology/graph
    status, data = api.dispatch("GET", "/api/v1/topology/graph")
    assert status == HTTPStatus.OK
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 1

    # 2. GET /api/v1/topology/devices/{device_id}
    dev_status, dev_data = api.dispatch("GET", "/api/v1/topology/devices/dev-sw-core-01")
    assert dev_status == HTTPStatus.OK
    assert dev_data["device"]["canonical_name"] == "sw-core-01.nbo.kenya-airways.com"
    assert len(dev_data["interfaces"]) == 1

    # 3. GET /api/v1/topology/devices/nonexistent (404)
    dev_404_status, _ = api.dispatch("GET", "/api/v1/topology/devices/dev-ghost")
    assert dev_404_status == HTTPStatus.NOT_FOUND


def test_topology_api_path_and_blast_radius(enterprise_topology_api):
    api, graph, _ = enterprise_topology_api

    # 1. Path between core switch and access switch
    params = {"source": ["dev-sw-core-01"], "destination": ["dev-sw-acc-t1a"]}
    path_status, pdata = api.dispatch("GET", "/api/v1/topology/path", query_params=params)
    assert path_status == HTTPStatus.OK
    assert pdata["hop_count"] == 1
    assert pdata["path"] == ["dev-sw-core-01", "dev-sw-acc-t1a"]

    # Path by IP
    params_ip = {"source": ["10.2.156.45"], "destination": ["10.2.156.90"]}
    path_ip_status, ip_pdata = api.dispatch("GET", "/api/v1/topology/path", query_params=params_ip)
    assert path_ip_status == HTTPStatus.OK
    assert ip_pdata["path"] == ["dev-sw-core-01", "dev-sw-acc-t1a"]

    # 2. Blast radius of core switch failure
    params_dev = {"device_id": ["dev-sw-core-01"]}
    blast_status, bdata = api.dispatch("GET", "/api/v1/topology/blast-radius", query_params=params_dev)
    assert blast_status == HTTPStatus.OK
    assert bdata["root_cause_type"] == "DEVICE"
    assert bdata["total_impacted_devices"] >= 2
    assert bdata["severity"] == "CRITICAL"
    assert any(s["service_id"] == "voice-telephony-sip" for s in bdata["impacted_services"])

    # 3. Blast radius of interface failure
    params_if = {"interface_id": ["if-core-1"]}
    if_blast_status, if_bdata = api.dispatch("GET", "/api/v1/topology/blast-radius", query_params=params_if)
    assert if_blast_status == HTTPStatus.OK
    assert if_bdata["root_cause_type"] == "INTERFACE"

    # 4. SPOF query
    spof_status, spofs = api.dispatch("GET", "/api/v1/topology/spof")
    assert spof_status == HTTPStatus.OK
    spof_list = spofs["spofs"]
    assert len(spof_list) >= 1
    assert any(s["device_id"] == "dev-sw-acc-t1a" for s in spof_list)


def test_topology_api_changes_endpoint(enterprise_topology_api):
    api, _, change_detector = enterprise_topology_api

    status, changes_data = api.dispatch("GET", "/api/v1/topology/changes")
    assert status == HTTPStatus.OK
    changes = changes_data["changes"]
    assert len(changes) >= 1
    assert changes[0]["change_type"] == "LINK_UP"


def test_topology_assurance_correlation():
    """Verify CrossDomainCorrelator incorporates topology changes and elevates confidence."""
    correlator = CrossDomainCorrelator()

    # Case 1: Standalone topology link outage generates confirmed incident
    topo_change = TopologyChange(
        change_type="LINK_DOWN",
        target_entity_type="INTERFACE",
        target_entity_id="TenGigabitEthernet1/0/1",
        before_state={"oper_status": 1},
        after_state={"oper_status": 2},
    )

    report = correlator.correlate(topology_changes=[topo_change])
    assert len(report.hypotheses) == 1
    hyp = report.hypotheses[0]
    assert hyp.status == HypothesisStatus.CONFIRMED
    assert hyp.root_cause_domain == RootCauseDomain.NETWORK_LINK
    assert hyp.confidence >= 0.98
    assert any(e.source == "topology.change_detector" for e in hyp.evidence)


def test_topology_sql_schema_file():
    """Verify SQL schema file exists, has correct tables and constraints."""
    schema_path = Path("/Users/madeira/Desktop/Projects/nawari/docker/postgresql/initdb/05-topology-schema.sql")
    assert schema_path.exists()
    content = schema_path.read_text()

    expected_tables = [
        "topology_devices",
        "topology_interfaces",
        "topology_layer2_links",
        "topology_subnets",
        "topology_routing_adjacencies",
        "topology_service_dependencies",
        "topology_changes",
    ]

    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in content, f"Missing table {table}"

    assert "REFERENCES topology_devices(device_id)" in content
    assert "REFERENCES topology_interfaces(interface_id)" in content
    assert "CREATE INDEX IF NOT EXISTS idx_topo_" in content
