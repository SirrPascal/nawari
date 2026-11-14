"""Chronological SIP Call-Flow Ladder Builder for Visual Observability."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class LadderHop:
    timestamp: float
    source_node: str
    target_node: str
    message_label: str
    phase: str  # SETUP, ALERTING, CONNECTED, TEARDOWN, FAILED
    status_code: Optional[int] = None
    latency_delta_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SIPCallLadder:
    call_id: str
    nodes: list[str] = field(default_factory=list)
    hops: list[LadderHop] = field(default_factory=list)
    _last_hop_time: Optional[float] = None

    def add_node_if_missing(self, node: str) -> None:
        if node not in self.nodes:
            self.nodes.append(node)

    def add_hop(
        self,
        timestamp: float,
        source_node: str,
        target_node: str,
        message_label: str,
        phase: str,
        status_code: Optional[int] = None,
    ) -> LadderHop:
        self.add_node_if_missing(source_node)
        self.add_node_if_missing(target_node)

        delta = 0.0
        if self._last_hop_time is not None and timestamp >= self._last_hop_time:
            delta = round((timestamp - self._last_hop_time) * 1000.0, 2)
        self._last_hop_time = timestamp

        hop = LadderHop(
            timestamp=timestamp,
            source_node=source_node,
            target_node=target_node,
            message_label=message_label,
            phase=phase,
            status_code=status_code,
            latency_delta_ms=delta,
        )
        self.hops.append(hop)
        return hop

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "nodes": self.nodes,
            "total_hops": len(self.hops),
            "hops": [h.to_dict() for h in self.hops],
        }

    def to_mermaid(self) -> str:
        """Export ladder as Mermaid sequence diagram."""
        lines = ["sequenceDiagram", "    autonumber"]
        for node in self.nodes:
            lines.append(f'    participant {node.replace("-", "_")} as "{node}"')
        for hop in self.hops:
            src = hop.source_node.replace("-", "_")
            tgt = hop.target_node.replace("-", "_")
            arrow = "->>"
            lines.append(f"    {src}{arrow}{tgt}: {hop.message_label} (+{hop.latency_delta_ms}ms)")
        return "\n".join(lines)

