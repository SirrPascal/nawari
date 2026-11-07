"""IP Route Table, OSPF, and BGP MIB Parsers for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ipaddress
import re
from typing import Any

from services.topology.identity import normalize_ip_address
from services.topology.models.subnet import RoutingAdjacency


@dataclass
class RouteEntry:
    dest_cidr: str
    next_hop: str
    if_index: int
    route_type: str = "remote"      # local, remote, invalid
    protocol: str = "connected"     # local, static, ospf, bgp, rip, other
    metric: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RouteParser:
    """Parses IP CIDR route table (1.3.6.1.2.1.4.24.4.1) and routing protocols."""

    PROTO_MAP = {
        1: "other",
        2: "local",
        3: "netmgmt",
        4: "icmp",
        5: "egp",
        6: "ggp",
        7: "hello",
        8: "rip",
        9: "isIs",
        10: "esIs",
        11: "ciscoIgrp",
        12: "bbnSpfIgp",
        13: "ospf",
        14: "bgp",
        15: "idpr",
        16: "ciscoEigrp",
    }

    TYPE_MAP = {
        1: "other",
        2: "invalid",
        3: "local",
        4: "remote",
    }

    OSPF_STATE_MAP = {
        1: "DOWN",
        2: "ATTEMPT",
        3: "INIT",
        4: "2WAY",
        5: "EXSTART",
        6: "EXCHANGE",
        7: "LOADING",
        8: "FULL",
    }

    BGP_STATE_MAP = {
        1: "IDLE",
        2: "CONNECT",
        3: "ACTIVE",
        4: "OPENSENT",
        5: "OPENCONFIRM",
        6: "ESTABLISHED",
    }

    @classmethod
    def parse_cidr_route_table(cls, raw_entries: list[dict[str, Any]]) -> list[RouteEntry]:
        """Parse structured rows or SNMP varbinds from ipCidrRouteTable."""
        if not raw_entries:
            return []

        # If entries already structured
        if "dest_cidr" in raw_entries[0] and "next_hop" in raw_entries[0]:
            routes = []
            for item in raw_entries:
                routes.append(
                    RouteEntry(
                        dest_cidr=str(item["dest_cidr"]),
                        next_hop=str(item["next_hop"]),
                        if_index=int(item.get("if_index", 1)),
                        route_type=str(item.get("route_type", "remote")),
                        protocol=str(item.get("protocol", "connected")),
                        metric=int(item.get("metric", 1)),
                    )
                )
            return routes

        # Parsing OID varbinds
        # Table OID: 1.3.6.1.2.1.4.24.4.1.<col>.<dest_ip>.<mask_ip>.<tos>.<next_hop_ip>
        indexed_data: dict[str, dict[str, Any]] = {}
        pattern = re.compile(
            r"^1\.3\.6\.1\.2\.1\.4\.24\.4\.1\.(\d+)\.(\d+\.\d+\.\d+\.\d+)\.(\d+\.\d+\.\d+\.\d+)\.\d+\.(\d+\.\d+\.\d+\.\d+)$"
        )

        for vb in raw_entries:
            oid = vb.get("oid", "")
            val = vb.get("value")
            match = pattern.match(oid)
            if not match:
                continue

            col = int(match.group(1))
            dest_ip = match.group(2)
            mask_ip = match.group(3)
            next_hop = match.group(4)
            key = f"{dest_ip}/{mask_ip}/{next_hop}"

            if key not in indexed_data:
                try:
                    net = ipaddress.IPv4Network(f"{dest_ip}/{mask_ip}", strict=False)
                    cidr = str(net)
                except ValueError:
                    cidr = f"{dest_ip}/{mask_ip}"
                indexed_data[key] = {
                    "dest_cidr": cidr,
                    "next_hop": next_hop,
                    "if_index": 1,
                    "metric": 1,
                    "protocol": "other",
                    "route_type": "remote",
                }

            if col == 5:  # ipCidrRouteIfIndex
                try:
                    indexed_data[key]["if_index"] = int(val)
                except (ValueError, TypeError):
                    pass
            elif col == 6:  # ipCidrRouteType
                try:
                    indexed_data[key]["route_type"] = cls.TYPE_MAP.get(int(val), "remote")
                except (ValueError, TypeError):
                    pass
            elif col == 7:  # ipCidrRouteProto
                try:
                    indexed_data[key]["protocol"] = cls.PROTO_MAP.get(int(val), "other")
                except (ValueError, TypeError):
                    pass
            elif col == 11:  # ipCidrRouteMetric1
                try:
                    indexed_data[key]["metric"] = int(val)
                except (ValueError, TypeError):
                    pass

        return [RouteEntry(**data) for data in indexed_data.values()]

    @classmethod
    def parse_ospf_neighbors(
        cls, local_device_id: str, local_ip: str, raw_entries: list[dict[str, Any]]
    ) -> list[RoutingAdjacency]:
        """Parse OSPF neighbour entries into RoutingAdjacency models."""
        adjacencies = []
        for item in raw_entries:
            rem_ip = normalize_ip_address(item.get("remote_ip") or item.get("ospfNbrIpAddr"))
            if not rem_ip:
                continue
            state_raw = item.get("state") or item.get("ospfNbrState", 8)
            if isinstance(state_raw, int):
                state = cls.OSPF_STATE_MAP.get(state_raw, "UNKNOWN")
            else:
                state = str(state_raw).upper()

            adj_id = f"adj-ospf-{local_device_id}-{rem_ip.replace('.', '_')}"
            adjacencies.append(
                RoutingAdjacency(
                    adjacency_id=adj_id,
                    local_device_id=local_device_id,
                    remote_device_id=item.get("remote_device_id"),
                    protocol="OSPF",
                    local_ip=local_ip,
                    remote_ip=rem_ip,
                    state=state,
                    area_or_asn=str(item.get("area_id", "0.0.0.0")),
                    metric=int(item.get("metric", 10)),
                )
            )
        return adjacencies

    @classmethod
    def parse_bgp_peers(
        cls, local_device_id: str, local_ip: str, raw_entries: list[dict[str, Any]]
    ) -> list[RoutingAdjacency]:
        """Parse BGP peer entries into RoutingAdjacency models."""
        adjacencies = []
        for item in raw_entries:
            rem_ip = normalize_ip_address(item.get("remote_ip") or item.get("bgpPeerRemoteAddr"))
            if not rem_ip:
                continue
            state_raw = item.get("state") or item.get("bgpPeerState", 6)
            if isinstance(state_raw, int):
                state = cls.BGP_STATE_MAP.get(state_raw, "UNKNOWN")
            else:
                state = str(state_raw).upper()

            asn = str(item.get("peer_as") or item.get("bgpPeerRemoteAs", ""))
            adj_id = f"adj-bgp-{local_device_id}-{rem_ip.replace('.', '_')}"
            adjacencies.append(
                RoutingAdjacency(
                    adjacency_id=adj_id,
                    local_device_id=local_device_id,
                    remote_device_id=item.get("remote_device_id"),
                    protocol="BGP",
                    local_ip=local_ip,
                    remote_ip=rem_ip,
                    state=state,
                    area_or_asn=asn,
                    metric=int(item.get("metric", 0)),
                )
            )
        return adjacencies

