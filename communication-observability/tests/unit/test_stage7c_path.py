"""Unit test suite for Stage 7C: Network Path Discovery and Analysis.

Validates:
1. Paris Traceroute checksum compensation and flow-hashing invariance.
2. RFC 4950 MPLS label stack extraction and parser.
3. CoPP Guard algorithm (distinguishing Control Plane Policing from true network drop).
4. Loss Onset Localization algorithm (pinpointing true packet drop inception).
5. Latency Jump Detection (Delta RTT > 40ms threshold).
6. Path Hashing and Route Change divergence index calculation.
"""

import asyncio
import hashlib
import struct
from unittest.mock import MagicMock

import pytest

from services.endpoint.models import HopResponseStatus, PathTelemetry
from services.endpoint.os_platform.base import PlatformAdapter
from services.endpoint.path.hop_analyzer import HopAnalyzer
from services.endpoint.path.models import MplsLabelEntry
from services.endpoint.path.mpls import MplsLabelParser
from services.endpoint.path.traceroute import ParisTraceroute


# =====================================================================
# 1. Paris Traceroute Flow-Hashing & Invariance Tests
# =====================================================================

def test_paris_checksum_compensation_invariance():
    """Verify Paris Traceroute payload maintains identical 16-bit 1's complement checksum."""
    flow_id = 0x12345678
    target_sum = 0xABCD

    p1 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=1, target_constant_sum=target_sum)
    p2 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=2, target_constant_sum=target_sum)
    p100 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=100, target_constant_sum=target_sum)

    # All payloads must be 8 bytes: 4 flow_id + 2 seq + 2 comp
    assert len(p1) == 8
    assert len(p2) == 8
    assert len(p100) == 8

    # Checksums must be strictly identical across all probe sequences
    c1 = ParisTraceroute.rfc1071_checksum(p1)
    c2 = ParisTraceroute.rfc1071_checksum(p2)
    c100 = ParisTraceroute.rfc1071_checksum(p100)

    assert c1 == c2 == c100


# =====================================================================
# 2. RFC 4950 MPLS ICMP Extension & Tag Parser Tests
# =====================================================================

def test_rfc4950_mpls_binary_parser():
    """Verify binary parsing of RFC 4950 ICMP Extension Objects."""
    # Build 2-entry MPLS stack
    # Entry 1: Label=1001, Exp=5, BOS=0, TTL=64
    raw_1 = (1001 << 12) | (5 << 9) | (0 << 8) | 64
    # Entry 2: Label=2002, Exp=0, BOS=1, TTL=63
    raw_2 = (2002 << 12) | (0 << 9) | (1 << 8) | 63

    # Header: Length=12 (4 header + 8 payload), Class-Num=1 (MPLS), Class-Type=1
    payload = struct.pack("!HBBII", 12, 1, 1, raw_1, raw_2)

    entries = MplsLabelParser.parse_rfc4950(payload)
    assert len(entries) == 2

    e1 = entries[0]
    assert e1.label == 1001
    assert e1.exp == 5
    assert e1.bos == 0
    assert e1.ttl == 64

    e2 = entries[1]
    assert e2.label == 2002
    assert e2.exp == 0
    assert e2.bos == 1
    assert e2.ttl == 63


def test_rfc4950_mpls_invalid_headers():
    """Verify malformed or non-MPLS extension objects are safely discarded."""
    # Too short
    assert MplsLabelParser.parse_rfc4950(b"\x00\x02\x01") == []
    # Wrong Class-Num (Class-Num=2 is not MPLS)
    wrong_class = struct.pack("!HBB", 8, 2, 1) + b"\x00" * 4
    assert MplsLabelParser.parse_rfc4950(wrong_class) == []


def test_traceroute_text_mpls_parser():
    """Verify textual MPLS label tag parsing from standard traceroute output."""
    sample = " 4  172.16.1.1  14.2 ms [MPLS: Label 1002 Exp 3 S 1 TTL 64]  14.5 ms"
    entries = MplsLabelParser.parse_text_tag(sample)
    assert len(entries) == 1
    assert entries[0].label == 1002
    assert entries[0].exp == 3
    assert entries[0].bos == 1
    assert entries[0].ttl == 64


# =====================================================================
# 3. CoPP Guard & Hop Classification Tests
# =====================================================================

def test_copp_guard_intermediate_router_timeout():
    """Verify intermediate router dropping ICMP TTL Expired is classified as TIMEOUT_COPP."""
    # Hop 1: Gateway (responsive)
    # Hop 2: Core Router (0 received, dropped by CoPP)
    # Hop 3: Aggregation Router (responsive)
    # Hop 4: Destination Avaya SBCE (responsive, 0% loss)
    raw_hops = [
        {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.1, 1.2, 1.0], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 2, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},
        {"hop_index": 3, "ip_address": "10.50.0.1", "rtts_ms": [15.2, 15.0, 15.1], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 4, "ip_address": "10.0.0.1", "rtts_ms": [20.1, 20.3, 20.0], "probes_sent": 3, "probes_received": 3},
    ]

    path = HopAnalyzer.analyze_hops(
        raw_hops=raw_hops,
        target_id="sbce",
        destination_ip="10.0.0.1",
        protocol="UDP",
    )

    assert path.total_hops == 4
    # Hop 2 must be classified as TIMEOUT_COPP
    hop2 = path.hops[1]
    assert hop2.hop_index == 2
    assert hop2.status == HopResponseStatus.TIMEOUT_COPP
    assert hop2.loss_pct == 100.0
    # Invariant: TIMEOUT_COPP must have None RTT
    assert hop2.rtt_avg_ms is None
    assert hop2.delta_rtt_ms is None

    # Downstream was healthy, so no loss onset hop
    assert path.loss_onset_hop is None
    assert path.end_to_end_loss_pct == 0.0
    assert path.end_to_end_rtt_ms is not None


# =====================================================================
# 4. Loss Onset Localization Tests
# =====================================================================

def test_loss_onset_localization_true_outage():
    """Verify persistent packet loss localizes the exact failure link."""
    # Hop 1: 192.168.1.1 (healthy)
    # Hop 2: 10.10.1.1 (healthy)
    # Hop 3: 172.16.1.1 (dropped: 100% loss)
    # Hop 4: 10.0.0.1 (destination unreachable: 100% loss)
    raw_hops = [
        {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.5, 1.4, 1.6], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 2, "ip_address": "10.10.1.1", "rtts_ms": [5.1, 5.2, 5.0], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 3, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},
        {"hop_index": 4, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},
    ]

    path = HopAnalyzer.analyze_hops(
        raw_hops=raw_hops,
        target_id="sbce",
        destination_ip="10.0.0.1",
        protocol="UDP",
    )

    # Not CoPP: Downstream is also dead!
    assert path.hops[2].status == HopResponseStatus.UNREACHABLE
    assert path.hops[3].status == HopResponseStatus.UNREACHABLE
    # Loss onset must point to Hop 3
    assert path.loss_onset_hop == 3
    assert path.end_to_end_loss_pct == 100.0
    assert path.end_to_end_rtt_ms is None


# =====================================================================
# 5. Latency Jump Detection Tests
# =====================================================================

def test_latency_jump_localization():
    """Verify delay spike (> 40ms) is flagged at the exact inception hop."""
    # Hop 1: 2.0 ms
    # Hop 2: 8.0 ms (Delta = +6.0 ms)
    # Hop 3: 65.0 ms (Delta = +57.0 ms -> Latency Jump!)
    # Hop 4: 70.0 ms (Delta = +5.0 ms)
    raw_hops = [
        {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [2.0, 2.0, 2.0], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 2, "ip_address": "10.10.1.1", "rtts_ms": [8.0, 8.0, 8.0], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 3, "ip_address": "172.16.1.1", "rtts_ms": [65.0, 65.0, 65.0], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 4, "ip_address": "10.0.0.1", "rtts_ms": [70.0, 70.0, 70.0], "probes_sent": 3, "probes_received": 3},
    ]

    path = HopAnalyzer.analyze_hops(
        raw_hops=raw_hops,
        target_id="sbce",
        destination_ip="10.0.0.1",
        protocol="UDP",
        latency_jump_threshold_ms=40.0,
    )

    assert path.hops[0].delta_rtt_ms == 2.0
    assert path.hops[1].delta_rtt_ms == 6.0
    assert path.hops[2].delta_rtt_ms == 57.0
    assert path.hops[3].delta_rtt_ms == 5.0

    assert path.latency_onset_hop == 3


# =====================================================================
# 6. Path Hashing & Route Change Divergence Tests
# =====================================================================

def test_path_hashing_and_route_divergence():
    """Verify SHA-256 path signature and divergent hop calculation."""
    # Trace 1
    raw_1 = [
        {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": "10.1.1.1", "rtts_ms": [5.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 3, "ip_address": "10.0.0.1", "rtts_ms": [10.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_1 = HopAnalyzer.analyze_hops(raw_1, "sbce", "10.0.0.1")
    assert path_1.has_route_changed is False

    expected_hash_1 = hashlib.sha256("192.168.1.1:10.1.1.1:10.0.0.1".encode("utf-8")).hexdigest()
    assert path_1.path_hash == expected_hash_1

    # Trace 2: Route diverted at Hop 2 (10.1.1.1 -> 10.2.2.2)
    raw_2 = [
        {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": "10.2.2.2", "rtts_ms": [5.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 3, "ip_address": "10.0.0.1", "rtts_ms": [10.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_2 = HopAnalyzer.analyze_hops(
        raw_2,
        "sbce",
        "10.0.0.1",
        previous_path_hash=path_1.path_hash,
        previous_responsive_ips=["192.168.1.1", "10.1.1.1", "10.0.0.1"],
    )

    assert path_2.has_route_changed is True
    # Hop 2 was the divergent hop
    assert path_2.divergent_hop_index == 2
    assert path_2.path_hash != path_1.path_hash


def test_empty_raw_hops_handling():
    """Verify empty raw hop trace returns safe default PathTelemetry."""
    path = HopAnalyzer.analyze_hops([], "sbce", "10.0.0.1")
    assert path.total_hops == 0
    assert path.end_to_end_loss_pct == 100.0
    assert path.end_to_end_rtt_ms is None
    assert path.loss_onset_hop == 1


# =====================================================================
# 7. ParisTraceroute Coordinator Tests
# =====================================================================

def test_paris_traceroute_coordinator():
    """Verify ParisTraceroute coordinates with mock platform adapter and retains history."""
    async def _test():
        mock_adapter = MagicMock(spec=PlatformAdapter)
        mock_adapter.trace_path.return_value = [
            {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.0, 1.1, 1.0], "probes_sent": 3, "probes_received": 3},
            {"hop_index": 2, "ip_address": "10.0.0.1", "rtts_ms": [10.0, 10.1, 9.9], "probes_sent": 3, "probes_received": 3},
        ]

        tracer = ParisTraceroute(adapter=mock_adapter)
        res1 = await tracer.trace("sbce", "10.0.0.1")

        assert res1.total_hops == 2
        assert res1.has_route_changed is False
        assert mock_adapter.trace_path.called

        # Second trace with route change
        mock_adapter.trace_path.return_value = [
            {"hop_index": 1, "ip_address": "192.168.1.1", "rtts_ms": [1.0, 1.1, 1.0], "probes_sent": 3, "probes_received": 3},
            {"hop_index": 2, "ip_address": "10.99.99.1", "rtts_ms": [12.0, 12.1, 11.9], "probes_sent": 3, "probes_received": 3},
        ]
        res2 = await tracer.trace("sbce", "10.0.0.1")
        assert res2.has_route_changed is True

    asyncio.run(_test())

