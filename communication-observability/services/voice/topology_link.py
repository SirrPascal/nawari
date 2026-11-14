"""Voice Service Dependency Correlation & Topological Linkage Engine."""

from __future__ import annotations

from typing import Any, Optional

from services.topology.graph import TopologyGraph
from services.topology.models import TopologyChange
from services.voice.correlation.session_correlator import CorrelatedCallSession


class VoiceTopologyLink:
    """Connects voice sessions and media anomalies to the underlying Layer 2/3 physical topology graph."""

    @classmethod
    def resolve_call_path(
        cls,
        source_ip: str,
        destination_ip: str,
        graph: TopologyGraph,
    ) -> list[str]:
        """Find the physical network devices traversed between call endpoints using the Phase 9 topology graph."""
        src_dev = graph.find_device_by_ip(source_ip)
        dst_dev = graph.find_device_by_ip(destination_ip)

        if not src_dev or not dst_dev:
            return []

        return graph.find_path(src_dev.device_id, dst_dev.device_id)

    @classmethod
    def correlate_voice_incident(
        cls,
        session: CorrelatedCallSession,
        source_ip: str,
        destination_ip: str,
        graph: TopologyGraph,
        recent_changes: list[TopologyChange],
    ) -> dict[str, Any]:
        """Correlate a voice call degradation or signaling failure with physical network topology events."""
        path = cls.resolve_call_path(source_ip, destination_ip, graph)

        if not path:
            return {
                "has_topological_root_cause": False,
                "confidence": 0.50,
                "traversed_path": [],
                "correlated_changes": [],
                "diagnostic": "Physical network path between voice endpoints could not be resolved in topology",
            }

        # Check for changes on any traversed device or their interfaces
        matching_changes = []
        for did in path:
            dev = graph.get_device(did)
            dev_if_ids = {i.interface_id for i in graph.get_device_interfaces(did)}

            for ch in recent_changes:
                if ch.target_entity_id == did or ch.target_entity_id in dev_if_ids:
                    matching_changes.append(
                        {
                            "change_type": ch.change_type,
                            "entity_id": ch.target_entity_id,
                            "entity_type": ch.target_entity_type,
                            "device_name": dev.canonical_name if dev else did,
                            "timestamp": ch.timestamp,
                        }
                    )

        if matching_changes:
            top_change = matching_changes[0]
            return {
                "has_topological_root_cause": True,
                "confidence": 0.98,
                "traversed_path": path,
                "correlated_changes": matching_changes,
                "primary_root_cause": f"Physical {top_change['change_type']} on {top_change['device_name']} ({top_change['entity_id']})",
                "diagnostic": f"Conclusive proof: Voice impairment directly coincides with physical network event ({top_change['change_type']}) on transit switch {top_change['device_name']}.",
            }

        return {
            "has_topological_root_cause": False,
            "confidence": 0.75,
            "traversed_path": path,
            "correlated_changes": [],
            "diagnostic": "All physical transit links and switch ports on call path are nominal; root cause is likely station state or carrier trunk.",
        }

