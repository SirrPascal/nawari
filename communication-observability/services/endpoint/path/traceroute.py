"""Paris Traceroute Engine: Deterministic Multi-Hop Flow-Hashed Path Tracing."""

from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Optional

from services.endpoint.models import PathTelemetry
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.os_platform.base import PlatformAdapter
from services.endpoint.path.hop_analyzer import HopAnalyzer

logger = logging.getLogger("nawari.endpoint.path.traceroute")


class ParisTraceroute:
    """Orchestrates deterministic, unprivileged network path tracing.

    Key Architectural Invariants:
    1. Paris Traceroute Flow-Hashing: Preserves constant 5-tuple / checksum compensation
       to eliminate ECMP load-balancer route flapping.
    2. Zero-RCE & Unprivileged Execution: Utilizes unprivileged platform facilities
       without invoking system shell interpreters.
    3. Route Churn Memory: Retains previous path signatures per target to detect
       routing divergency in subsequent execution cycles.
    """

    def __init__(
        self,
        adapter: Optional[PlatformAdapter] = None,
        default_max_hops: int = 30,
        default_timeout_seconds: float = 2.0,
    ) -> None:
        self.adapter = adapter or get_platform_adapter()
        self.default_max_hops = default_max_hops
        self.default_timeout_seconds = default_timeout_seconds
        # Target ID -> {"path_hash": str, "responsive_ips": List[str]}
        self._route_history: Dict[str, Dict[str, Any]] = {}

    async def trace(
        self,
        target_id: str,
        destination_ip: str,
        target_port: Optional[int] = None,
        protocol: str = "UDP",
        max_hops: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> PathTelemetry:
        """Execute directional path trace and return analyzed PathTelemetry."""
        hops_limit = max_hops or self.default_max_hops
        timeout = timeout_seconds or self.default_timeout_seconds

        # Retrieve previous route history for churn detection
        prev_history = self._route_history.get(target_id, {})
        prev_hash = prev_history.get("path_hash")
        prev_ips = prev_history.get("responsive_ips")

        # Execute unprivileged platform trace
        try:
            raw_hops = self.adapter.trace_path(
                destination_ip=destination_ip,
                max_hops=hops_limit,
                timeout_seconds=timeout,
                target_port=target_port,
                fixed_flow=True,
            )
        except Exception as exc:
            logger.warning(f"Error executing path trace to {destination_ip}: {exc}")
            raw_hops = []

        # Run topological and statistical analysis
        path_telemetry = HopAnalyzer.analyze_hops(
            raw_hops=raw_hops,
            target_id=target_id,
            destination_ip=destination_ip,
            protocol=protocol,
            previous_path_hash=prev_hash,
            previous_responsive_ips=prev_ips,
        )

        # Update route history
        responsive_ips = [
            h.ip_address for h in path_telemetry.hops if h.ip_address and h.rtt_avg_ms is not None
        ]
        self._route_history[target_id] = {
            "path_hash": path_telemetry.path_hash,
            "responsive_ips": responsive_ips,
        }

        return path_telemetry

    @staticmethod
    def calculate_paris_checksum_compensation(
        flow_id: int, sequence: int, target_constant_sum: int = 0xABCD
    ) -> bytes:
        """Generate a Paris Traceroute payload with constant 16-bit 1's complement checksum.

        Embeds flow_id (4 bytes) and sequence (2 bytes), then calculates a 2-byte
        compensation field such that the entire payload's 16-bit checksum remains
        strictly identical across all probe sequences.
        """
        base = flow_id.to_bytes(4, "big") + sequence.to_bytes(2, "big")
        partial_sum = sum(int.from_bytes(base[i : i + 2], "big") for i in range(0, 6, 2))
        diff = (target_constant_sum - partial_sum) & 0xFFFF
        return base + diff.to_bytes(2, "big")

    @staticmethod
    def rfc1071_checksum(data: bytes) -> int:
        """Compute standard RFC 1071 16-bit one's complement Internet checksum."""
        if len(data) % 2 != 0:
            data += b"\x00"
        s = sum(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return ~s & 0xFFFF

