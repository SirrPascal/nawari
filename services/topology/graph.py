"""Topology Graph Engine & Relational Adjacency Graph for Nawari Network Intelligence."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
from typing import Any

from services.topology.identity import (
    EvidentiaryScorer,
    generate_device_id,
    generate_interface_id,
    generate_link_id,
)
from services.topology.models import (
    ConfidenceLevel,
    Device,
    DeviceType,
    DiscoveryProtocol,
    Interface,
    Layer2Link,
    LinkStatus,
    LinkType,
    OperStatus,
    RoutingAdjacency,
    ServiceDependency,
    Subnet,
)


class TopologyGraph:
    """In-memory and relational adjacency graph representing Layer 2 & Layer 3 network topology."""

    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}
        self.interfaces: dict[str, Interface] = {}
        self.links: dict[str, Layer2Link] = {}
        self.subnets: dict[str, Subnet] = {}
        self.routing_adjacencies: dict[str, RoutingAdjacency] = {}
        self.service_dependencies: dict[str, ServiceDependency] = {}

        # Adjacency indexes for fast O(1) graph traversal:
        # device_id -> set of interface_ids
        self._device_interfaces: dict[str, set[str]] = {}
        # interface_id -> set of link_ids
        self._interface_links: dict[str, set[str]] = {}
        # device_id -> set of peer device_ids
        self._device_neighbors: dict[str, set[str]] = {}
        # MAC -> interface_id
        self._mac_to_interface: dict[str, str] = {}
        # IP -> device_id
        self._ip_to_device: dict[str, str] = {}

    # --------------------------------------------------------------------------
    # Device Operations
    # --------------------------------------------------------------------------

    def add_device(self, device: Device) -> Device:
        self.devices[device.device_id] = device
        if device.device_id not in self._device_interfaces:
            self._device_interfaces[device.device_id] = set()
        if device.device_id not in self._device_neighbors:
            self._device_neighbors[device.device_id] = set()
        if device.management_ip:
            self._ip_to_device[device.management_ip] = device.device_id
        return device

    def get_device(self, device_id: str) -> Device | None:
        return self.devices.get(device_id)

    def find_device_by_ip(self, ip: str) -> Device | None:
        dev_id = self._ip_to_device.get(ip.strip())
        return self.devices.get(dev_id) if dev_id else None

    # --------------------------------------------------------------------------
    # Interface Operations
    # --------------------------------------------------------------------------

    def add_interface(self, interface: Interface) -> Interface:
        if interface.device_id not in self.devices:
            raise KeyError(f"Device {interface.device_id} not found in topology graph")
        self.interfaces[interface.interface_id] = interface
        self._device_interfaces[interface.device_id].add(interface.interface_id)
        if interface.interface_id not in self._interface_links:
            self._interface_links[interface.interface_id] = set()
        if interface.mac_address:
            self._mac_to_interface[interface.mac_address.lower()] = interface.interface_id
        return interface

    def get_interface(self, interface_id: str) -> Interface | None:
        return self.interfaces.get(interface_id)

    def get_device_interfaces(self, device_id: str) -> list[Interface]:
        if_ids = self._device_interfaces.get(device_id, set())
        return [self.interfaces[i] for i in if_ids if i in self.interfaces]

    # --------------------------------------------------------------------------
    # Layer 2 Link Operations & Reciprocal Reconciliation
    # --------------------------------------------------------------------------

    def add_link(
        self,
        source_if_id: str,
        target_if_id: str,
        discovery_protocol: DiscoveryProtocol | str = DiscoveryProtocol.LLDP,
        link_type: LinkType | str = LinkType.TRUNK,
        is_reciprocal: bool = False,
        evidence_metadata: dict[str, Any] | None = None,
    ) -> Layer2Link:
        if source_if_id not in self.interfaces:
            raise KeyError(f"Source interface {source_if_id} not found in topology")
        if target_if_id not in self.interfaces:
            raise KeyError(f"Target interface {target_if_id} not found in topology")

        link_id = generate_link_id(source_if_id, target_if_id)
        existing = self.links.get(link_id)

        # If existing link observed again from reciprocal direction
        if existing:
            # Check if this confirms reciprocity
            if existing.source_interface_id == target_if_id and existing.target_interface_id == source_if_id:
                is_reciprocal = True

        score, _ = EvidentiaryScorer.score_link(
            str(discovery_protocol),
            is_reciprocal=is_reciprocal,
            extra_evidence=evidence_metadata,
        )

        status = LinkStatus.ACTIVE if is_reciprocal or score >= 0.75 else LinkStatus.DEGRADED_UNIDIRECTIONAL

        link = Layer2Link(
            link_id=link_id,
            source_interface_id=source_if_id,
            target_interface_id=target_if_id,
            discovery_protocol=discovery_protocol,
            link_type=link_type,
            is_bidirectional=is_reciprocal,
            confidence=score,
            evidence_metadata=evidence_metadata or {},
            status=status,
        )
        self.links[link_id] = link
        self._interface_links[source_if_id].add(link_id)
        self._interface_links[target_if_id].add(link_id)

        # Update neighbor graph
        src_dev = self.interfaces[source_if_id].device_id
        dst_dev = self.interfaces[target_if_id].device_id
        self._device_neighbors[src_dev].add(dst_dev)
        self._device_neighbors[dst_dev].add(src_dev)

        return link

    def get_link(self, link_id: str) -> Layer2Link | None:
        return self.links.get(link_id)

    # --------------------------------------------------------------------------
    # Subnets & Adjacencies
    # --------------------------------------------------------------------------

    def add_subnet(self, subnet: Subnet) -> Subnet:
        self.subnets[subnet.subnet_id] = subnet
        return subnet

    def add_routing_adjacency(self, adj: RoutingAdjacency) -> RoutingAdjacency:
        self.routing_adjacencies[adj.adjacency_id] = adj
        if adj.remote_device_id and adj.local_device_id in self.devices and adj.remote_device_id in self.devices:
            self._device_neighbors[adj.local_device_id].add(adj.remote_device_id)
            self._device_neighbors[adj.remote_device_id].add(adj.local_device_id)
        return adj

    # --------------------------------------------------------------------------
    # Service Dependencies
    # --------------------------------------------------------------------------

    def add_service_dependency(self, dep: ServiceDependency) -> ServiceDependency:
        self.service_dependencies[dep.dependency_id] = dep
        return dep

    def get_service_dependencies(self, service_id: str) -> list[ServiceDependency]:
        return [
            d for d in self.service_dependencies.values() if d.service_id == service_id
        ]

    # --------------------------------------------------------------------------
    # Graph Traversal: Shortest Path & Upstream Chain
    # --------------------------------------------------------------------------

    def find_path(self, src_device_id: str, dst_device_id: str) -> list[str]:
        """Breadth-First Search (BFS) returning shortest list of device IDs between src and dst."""
        if src_device_id not in self.devices or dst_device_id not in self.devices:
            return []
        if src_device_id == dst_device_id:
            return [src_device_id]

        queue: deque[list[str]] = deque([[src_device_id]])
        visited: set[str] = {src_device_id}

        while queue:
            current_path = queue.popleft()
            node = current_path[-1]

            for neighbor in self._device_neighbors.get(node, set()):
                if neighbor == dst_device_id:
                    return current_path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(current_path + [neighbor])

        return []

    def get_upstream_path(self, device_id: str) -> list[tuple[Device, Interface]]:
        """Traverse upwards toward CORE_ROUTER or DIST_SWITCH, returning (device, uplink_interface) pairs."""
        upstream: list[tuple[Device, Interface]] = []
        visited: set[str] = set()
        curr_id = device_id

        while curr_id and curr_id not in visited:
            visited.add(curr_id)
            curr_dev = self.devices.get(curr_id)
            if not curr_dev:
                break

            # If reached core, stop
            if curr_dev.device_type in (DeviceType.CORE_ROUTER.value, DeviceType.CORE_ROUTER):
                break

            # Find uplink interface on current device
            uplink_if = None
            for iface in self.get_device_interfaces(curr_id):
                if iface.is_uplink:
                    uplink_if = iface
                    break

            if not uplink_if:
                # Fallback: check links
                break

            upstream.append((curr_dev, uplink_if))

            # Find peer device through uplink's links
            peer_dev_id = None
            for link_id in self._interface_links.get(uplink_if.interface_id, set()):
                link = self.links[link_id]
                peer_if_id = (
                    link.target_interface_id
                    if link.source_interface_id == uplink_if.interface_id
                    else link.source_interface_id
                )
                peer_if = self.interfaces.get(peer_if_id)
                if peer_if:
                    peer_dev_id = peer_if.device_id
                    break

            curr_id = peer_dev_id  # type: ignore

        return upstream

    # --------------------------------------------------------------------------
    # Grafana Node Graph Panel Serialization
    # --------------------------------------------------------------------------

    def to_node_graph(
        self, site_id: str | None = None, service_id: str | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Export topology graph into Grafana Node Graph compatible JSON structure."""
        filtered_devices = {
            did: d
            for did, d in self.devices.items()
            if (not site_id or d.site_id == site_id)
        }

        nodes = []
        for d in filtered_devices.values():
            # Determine health color
            color = "green"
            status_text = "Operational"
            if d.confidence_score < 0.75:
                color = "orange"
                status_text = "Unverified"

            nodes.append(
                {
                    "id": d.device_id,
                    "title": d.canonical_name,
                    "subTitle": f"{d.vendor} {d.model or ''} ({d.device_type})".strip(),
                    "mainStat": status_text,
                    "secondaryStat": f"Site: {d.site_id}",
                    "color": color,
                    "metadata": {
                        "management_ip": d.management_ip,
                        "vendor": d.vendor,
                        "site_id": d.site_id,
                        "confidence": d.confidence_score,
                    },
                }
            )

        edges = []
        for l in self.links.values():
            src_if = self.interfaces.get(l.source_interface_id)
            tgt_if = self.interfaces.get(l.target_interface_id)
            if not src_if or not tgt_if:
                continue
            if src_if.device_id not in filtered_devices or tgt_if.device_id not in filtered_devices:
                continue

            edge_color = "green"
            if l.status == LinkStatus.DEGRADED_UNIDIRECTIONAL.value or l.confidence < 0.75:
                edge_color = "orange"
            elif l.status == LinkStatus.DEGRADED.value:
                edge_color = "red"

            speed_str = ""
            if src_if.speed_bps:
                gbps = src_if.speed_bps / 1_000_000_000
                speed_str = f"{gbps:.0f} Gbps" if gbps >= 1 else f"{src_if.speed_bps / 1_000_000:.0f} Mbps"

            edges.append(
                {
                    "id": l.link_id,
                    "source": src_if.device_id,
                    "target": tgt_if.device_id,
                    "mainStat": speed_str or l.link_type,
                    "secondaryStat": f"{l.discovery_protocol} ({int(l.confidence * 100)}%)",
                    "color": edge_color,
                    "metadata": {
                        "source_interface": src_if.if_name,
                        "target_interface": tgt_if.if_name,
                        "discovery_protocol": l.discovery_protocol,
                        "confidence": l.confidence,
                        "is_bidirectional": l.is_bidirectional,
                    },
                }
            )

        return {"nodes": nodes, "edges": edges}

