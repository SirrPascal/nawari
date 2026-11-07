"""Unit tests for LLDP, CDP, FDB, and Routing SNMP Table Parsers."""

from __future__ import annotations

from services.topology.discovery import (
    CDPParser,
    FDBParser,
    LLDPParser,
    RouteParser,
)


def test_lldp_rem_table_structured_and_varbind_parsing():
    # 1. Structured entries
    raw_structured = [
        {
            "local_if_index": 24,
            "remote_chassis_id": "00:1A:2B:3C:4D:99",
            "remote_port_id": "TenGigabitEthernet1/0/1",
            "remote_sys_name": "sw-dist-01.nbo.kenya-airways.com",
            "remote_port_desc": "Uplink to Core",
            "chassis_id_subtype": 4,
            "port_id_subtype": 5,
        }
    ]
    neighbors = LLDPParser.parse_rem_table(raw_structured)
    assert len(neighbors) == 1
    assert neighbors[0].local_if_index == 24
    assert neighbors[0].remote_chassis_id == "00:1a:2b:3c:4d:99"
    assert neighbors[0].remote_sys_name == "sw-dist-01.nbo.kenya-airways.com"

    # 2. OID varbinds
    # OID format: 1.0.8802.1.1.2.1.4.1.1.<col>.<timeMark>.<localIf>.<remIndex>
    varbinds = [
        {"oid": "1.0.8802.1.1.2.1.4.1.1.4.0.12.1", "value": 4},
        {"oid": "1.0.8802.1.1.2.1.4.1.1.5.0.12.1", "value": "00-26-98-11-22-33"},
        {"oid": "1.0.8802.1.1.2.1.4.1.1.6.0.12.1", "value": 5},
        {"oid": "1.0.8802.1.1.2.1.4.1.1.7.0.12.1", "value": "GigabitEthernet0/1"},
        {"oid": "1.0.8802.1.1.2.1.4.1.1.9.0.12.1", "value": "sbce-edge-01"},
    ]
    parsed_vb = LLDPParser.parse_rem_table(varbinds)
    assert len(parsed_vb) == 1
    assert parsed_vb[0].local_if_index == 12
    assert parsed_vb[0].remote_chassis_id == "00:26:98:11:22:33"
    assert parsed_vb[0].remote_port_id == "GigabitEthernet0/1"
    assert parsed_vb[0].remote_sys_name == "sbce-edge-01"


def test_cdp_cache_table_parsing():
    # 1. Structured
    raw_cdp = [
        {
            "local_if_index": 48,
            "remote_device_id": "sw-access-t1a.nbo.kenya-airways.com",
            "remote_port_id": "GigabitEthernet1/0/48",
            "remote_ip": "10.2.156.99",
            "remote_platform": "cisco WS-C2960X-48TD-L",
            "native_vlan": 10,
        }
    ]
    neighbors = CDPParser.parse_cache_table(raw_cdp)
    assert len(neighbors) == 1
    assert neighbors[0].local_if_index == 48
    assert neighbors[0].remote_device_id == "sw-access-t1a.nbo.kenya-airways.com"
    assert neighbors[0].native_vlan == 10

    # 2. OID varbinds
    # OID format: 1.3.6.1.4.1.9.9.23.1.2.1.1.<col>.<localIf>.<cacheIdx>
    varbinds = [
        {"oid": "1.3.6.1.4.1.9.9.23.1.2.1.1.4.2.1", "value": "10.2.156.105"},
        {"oid": "1.3.6.1.4.1.9.9.23.1.2.1.1.6.2.1", "value": "router-core-01"},
        {"oid": "1.3.6.1.4.1.9.9.23.1.2.1.1.7.2.1", "value": "TenGigabitEthernet0/0/0"},
        {"oid": "1.3.6.1.4.1.9.9.23.1.2.1.1.8.2.1", "value": "cisco ASR1001-X"},
        {"oid": "1.3.6.1.4.1.9.9.23.1.2.1.1.11.2.1", "value": 1},
    ]
    parsed_vb = CDPParser.parse_cache_table(varbinds)
    assert len(parsed_vb) == 1
    assert parsed_vb[0].local_if_index == 2
    assert parsed_vb[0].remote_device_id == "router-core-01"
    assert parsed_vb[0].remote_ip == "10.2.156.105"
    assert parsed_vb[0].remote_platform == "cisco ASR1001-X"


def test_fdb_table_parsing():
    raw_fdb = [
        {"mac_address": "00:11:22:33:44:55", "bridge_port": 1, "status": "learned"},
        {"mac_address": "aa:bb:cc:dd:ee:ff", "bridge_port": 2, "status": 3},
    ]
    port_map = {1: 101, 2: 102}
    entries = FDBParser.parse_fdb_table(raw_fdb, port_to_ifindex_map=port_map, default_vlan=20)
    assert len(entries) == 2
    assert entries[0].if_index == 101
    assert entries[0].vlan_id == 20
    assert entries[1].if_index == 102
    assert entries[1].status == "learned"

    # OID varbinds
    # OID format: 1.3.6.1.2.1.17.4.3.1.<col>.<mac 6 decimal octets>
    varbinds = [
        {"oid": "1.3.6.1.2.1.17.4.3.1.2.0.26.43.60.77.94", "value": 5},
        {"oid": "1.3.6.1.2.1.17.4.3.1.3.0.26.43.60.77.94", "value": 3},
    ]
    parsed_vb = FDBParser.parse_fdb_table(varbinds, port_to_ifindex_map={5: 24})
    assert len(parsed_vb) == 1
    assert parsed_vb[0].mac_address == "00:1a:2b:3c:4d:5e"
    assert parsed_vb[0].bridge_port == 5
    assert parsed_vb[0].if_index == 24
    assert parsed_vb[0].status == "learned"


def test_route_and_routing_adjacency_parsing():
    raw_routes = [
        {
            "dest_cidr": "10.100.0.0/16",
            "next_hop": "10.2.156.1",
            "if_index": 1,
            "protocol": "ospf",
            "metric": 10,
        }
    ]
    routes = RouteParser.parse_cidr_route_table(raw_routes)
    assert len(routes) == 1
    assert routes[0].dest_cidr == "10.100.0.0/16"
    assert routes[0].next_hop == "10.2.156.1"

    # OSPF neighbour parsing
    raw_ospf = [
        {
            "remote_ip": "10.2.156.2",
            "state": "FULL",
            "area_id": "0.0.0.0",
            "metric": 10,
            "remote_device_id": "dev-dist02",
        }
    ]
    adj = RouteParser.parse_ospf_neighbors("dev-core01", "10.2.156.1", raw_ospf)
    assert len(adj) == 1
    assert adj[0].protocol == "OSPF"
    assert adj[0].state == "FULL"
    assert adj[0].remote_ip == "10.2.156.2"

    # BGP peer parsing
    raw_bgp = [
        {
            "remote_ip": "196.201.214.1",
            "state": "ESTABLISHED",
            "peer_as": "36914",
            "metric": 0,
        }
    ]
    bgp_adj = RouteParser.parse_bgp_peers("dev-edge01", "196.201.214.2", raw_bgp)
    assert len(bgp_adj) == 1
    assert bgp_adj[0].protocol == "BGP"
    assert bgp_adj[0].state == "ESTABLISHED"
    assert bgp_adj[0].area_or_asn == "36914"

