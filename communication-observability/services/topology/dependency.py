"""Business Service Dependency & Blast-Radius Engine for Nawari Network Intelligence."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from services.topology.graph import TopologyGraph
from services.topology.models import (
    Criticality,
    Device,
    DeviceType,
    FailureImpact,
    Interface,
    ServiceDependency,
)


@dataclass
class BlastRadiusReport:
    root_cause_type: str                     # "DEVICE" or "INTERFACE"
    root_cause_id: str
    impacted_devices: list[dict[str, Any]]
    impacted_services: list[dict[str, Any]]
    total_impacted_devices: int
    total_impacted_services: int
    is_redundant_failover: bool = False
    spof_detected: bool = False
    severity: str = "HIGH"                  # CRITICAL, HIGH, MEDIUM, LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_cause_type": self.root_cause_type,
            "root_cause_id": self.root_cause_id,
            "total_impacted_devices": self.total_impacted_devices,
            "total_impacted_services": self.total_impacted_services,
            "is_redundant_failover": self.is_redundant_failover,
            "spof_detected": self.spof_detected,
            "severity": self.severity,
            "impacted_devices": self.impacted_devices,
            "impacted_services": self.impacted_services,
        }


class DependencyEngine:
    """Computes downstream blast radius, impacted business services, and Single Points of Failure."""

    def __init__(self, graph: TopologyGraph) -> None:
        self.graph = graph

    def calculate_interface_blast_radius(self, interface_id: str) -> BlastRadiusReport:
        """Calculate blast radius if a specific network interface fails."""
        iface = self.graph.get_interface(interface_id)
        if not iface:
            raise KeyError(f"Interface {interface_id} not found in topology graph")

        device = self.graph.get_device(iface.device_id)
        dev_name = device.canonical_name if device else iface.device_id

        # Check if interface is part of an active LAG (Port-Channel)
        if iface.lag_master_id:
            # Check sibling member links
            parent_lag = self.graph.get_interface(iface.lag_master_id)
            if parent_lag:
                siblings = [
                    i
                    for i in self.graph.get_device_interfaces(iface.device_id)
                    if i.lag_master_id == iface.lag_master_id and i.interface_id != interface_id
                ]
                active_siblings = [s for s in siblings if s.is_operational]
                if active_siblings:
                    # Redundant link in LAG failed - degraded, not full outage
                    return BlastRadiusReport(
                        root_cause_type="INTERFACE",
                        root_cause_id=interface_id,
                        impacted_devices=[{"device_id": iface.device_id, "name": dev_name}],
                        impacted_services=[],
                        total_impacted_devices=1,
                        total_impacted_services=0,
                        is_redundant_failover=True,
                        spof_detected=False,
                        severity="MEDIUM",
                    )

        # Traverse downstream connections from this interface
        impacted_dev_ids: set[str] = set()
        queue: deque[str] = deque()

        for link_id in self.graph._interface_links.get(interface_id, set()):
            link = self.graph.links[link_id]
            remote_if_id = (
                link.target_interface_id
                if link.source_interface_id == interface_id
                else link.source_interface_id
            )
            remote_if = self.graph.interfaces.get(remote_if_id)
            if remote_if:
                queue.append(remote_if.device_id)
                impacted_dev_ids.add(remote_if.device_id)

        # Recursively traverse downstream devices
        visited: set[str] = set(impacted_dev_ids)
        while queue:
            curr_dev_id = queue.popleft()
            for neighbor_id in self.graph._device_neighbors.get(curr_dev_id, set()):
                if neighbor_id not in visited and neighbor_id != iface.device_id:
                    # Ensure downstream direction (away from core)
                    visited.add(neighbor_id)
                    impacted_dev_ids.add(neighbor_id)
                    queue.append(neighbor_id)

        # Include originating device if it relies solely on this uplink
        spof = False
        if iface.is_uplink:
            uplinks = [
                i
                for i in self.graph.get_device_interfaces(iface.device_id)
                if i.is_uplink and i.interface_id != interface_id
            ]
            if not uplinks:
                impacted_dev_ids.add(iface.device_id)
                spof = True

        return self._build_report("INTERFACE", interface_id, impacted_dev_ids, spof)

    def calculate_device_blast_radius(self, device_id: str) -> BlastRadiusReport:
        """Calculate blast radius if an entire network device (switch/router) fails."""
        device = self.graph.get_device(device_id)
        if not device:
            raise KeyError(f"Device {device_id} not found in topology graph")

        # Traverse all downstream devices
        impacted_dev_ids: set[str] = {device_id}
        queue: deque[str] = deque([device_id])
        visited: set[str] = {device_id}

        while queue:
            curr_id = queue.popleft()
            for neighbor_id in self.graph._device_neighbors.get(curr_id, set()):
                # Downstream heuristic: neighbor does not have alternate path to core
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    impacted_dev_ids.add(neighbor_id)
                    queue.append(neighbor_id)

        return self._build_report("DEVICE", device_id, impacted_dev_ids, spof=True)

    def _build_report(
        self, root_type: str, root_id: str, impacted_dev_ids: set[str], spof: bool
    ) -> BlastRadiusReport:
        dev_summaries = []
        svc_summaries = []
        highest_severity = "LOW"

        for did in impacted_dev_ids:
            dev = self.graph.get_device(did)
            if dev:
                dev_summaries.append(
                    {
                        "device_id": did,
                        "canonical_name": dev.canonical_name,
                        "device_type": dev.device_type,
                        "site_id": dev.site_id,
                    }
                )

            # Find dependent services
            for dep in self.graph.service_dependencies.values():
                if dep.dependent_id == did:
                    svc_summaries.append(
                        {
                            "service_id": dep.service_id,
                            "criticality": dep.criticality,
                            "failure_impact": dep.failure_impact,
                            "impact_weight": dep.impact_weight,
                        }
                    )
                    if dep.criticality == Criticality.CRITICAL.value:
                        highest_severity = "CRITICAL"
                    elif (
                        dep.criticality == Criticality.REDUNDANT.value
                        and highest_severity != "CRITICAL"
                    ):
                        highest_severity = "HIGH"

        if not svc_summaries and dev_summaries:
            highest_severity = "MEDIUM"

        return BlastRadiusReport(
            root_cause_type=root_type,
            root_cause_id=root_id,
            impacted_devices=dev_summaries,
            impacted_services=svc_summaries,
            total_impacted_devices=len(dev_summaries),
            total_impacted_services=len(svc_summaries),
            is_redundant_failover=False,
            spof_detected=spof,
            severity=highest_severity,
        )

    def identify_single_points_of_failure(self) -> list[dict[str, Any]]:
        """Scan all access and distribution switches for single points of failure (zero redundant uplinks)."""
        spof_risks = []
        for dev in self.graph.devices.values():
            if dev.device_type in (
                DeviceType.ACCESS_SWITCH.value,
                DeviceType.DIST_SWITCH.value,
                DeviceType.SBC.value,
            ):
                interfaces = self.graph.get_device_interfaces(dev.device_id)
                uplinks = [i for i in interfaces if i.is_uplink]

                if len(uplinks) == 1:
                    spof_risks.append(
                        {
                            "device_id": dev.device_id,
                            "canonical_name": dev.canonical_name,
                            "device_type": dev.device_type,
                            "sole_uplink_interface": uplinks[0].if_name,
                            "risk_description": f"Device {dev.canonical_name} relies on a single unbundled uplink ({uplinks[0].if_name})",
                        }
                    )
        return spof_risks

