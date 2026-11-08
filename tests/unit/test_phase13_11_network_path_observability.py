"""tests/unit/test_phase13_11_network_path_observability.py
========================================================
Comprehensive unit test suite for Phase 13.11:
Network Path & WAN Observability, Paris Traceroute, and Outstation Probing.
"""

import asyncio
import struct
import pytest
from services.endpoint.models import DnsResolutionStatus, HopResponseStatus, PathTelemetry
from services.endpoint.path.hop_analyzer import HopAnalyzer
from services.endpoint.path.models import MplsLabelEntry
from services.endpoint.path.mpls import MplsLabelParser
from services.endpoint.path.traceroute import ParisTraceroute
from services.endpoint.probes.dns import DnsProbe
from services.endpoint.probes.tcp import TcpProbe, TcpConnectStatus
from services.endpoint.probes.http import HttpProbe, HttpStatusOutcome
from services.multisite.wan_voice_probes import TransWanVoiceProber, VoiceTrunkStatus, SipOptionsResult


def test_paris_traceroute_checksum_invariance():
    """Verify RFC 1071 16-bit one's complement compensation invariant across TTL probes."""
    flow_id = 0x12345678
    p1 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=1, target_constant_sum=0xABCD)
    p2 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=2, target_constant_sum=0xABCD)
    p3 = ParisTraceroute.calculate_paris_checksum_compensation(flow_id, sequence=3, target_constant_sum=0xABCD)

    c1 = ParisTraceroute.rfc1071_checksum(p1)
    c2 = ParisTraceroute.rfc1071_checksum(p2)
    c3 = ParisTraceroute.rfc1071_checksum(p3)

    assert c1 == c2 == c3, f"Checksum compensation failed: {hex(c1)} != {hex(c2)} != {hex(c3)}"


def test_copp_guard_intermediate_hop():
    """Verify silent intermediate hop followed by successful destination is classified as TIMEOUT_COPP."""
    raw_hops = [
        {"hop_index": 1, "ip_address": "10.2.1.254", "rtts_ms": [1.5], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},  # Silent
        {"hop_index": 3, "ip_address": "10.2.156.131", "rtts_ms": [12.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_telemetry = HopAnalyzer.analyze_hops(raw_hops, "sbce", "10.2.156.131")

    assert path_telemetry.total_hops == 3
    assert path_telemetry.end_to_end_loss_pct == 0.0
    hop2 = path_telemetry.hops[1]
    assert hop2.status == HopResponseStatus.TIMEOUT_COPP
    assert hop2.loss_pct == 100.0
    # Downstream reached cleanly: CoPP guard prevents attributing end-to-end failure to hop 2
    assert path_telemetry.loss_onset_hop is None


def test_loss_onset_localization():
    """Verify loss onset correctly localized to first failing hop when packet loss persists downstream."""
    raw_hops = [
        {"hop_index": 1, "ip_address": "10.2.1.254", "rtts_ms": [1.2], "probes_sent": 3, "probes_received": 3},
        {"hop_index": 2, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},
        {"hop_index": 3, "ip_address": None, "rtts_ms": [], "probes_sent": 3, "probes_received": 0},
    ]
    path_telemetry = HopAnalyzer.analyze_hops(raw_hops, "sbce", "10.2.156.131")

    assert path_telemetry.hops[1].status == HopResponseStatus.UNREACHABLE
    assert path_telemetry.hops[2].status == HopResponseStatus.UNREACHABLE
    assert path_telemetry.loss_onset_hop == 2
    assert path_telemetry.end_to_end_loss_pct == 100.0


def test_latency_jump_localization():
    """Verify delta RTT against previous responsive hop flags latency jumps > 40ms."""
    raw_hops = [
        {"hop_index": 1, "ip_address": "10.2.1.254", "rtts_ms": [2.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": "196.201.214.1", "rtts_ms": [58.0], "probes_sent": 1, "probes_received": 1}, # +56ms jump
        {"hop_index": 3, "ip_address": "10.2.156.131", "rtts_ms": [60.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_telemetry = HopAnalyzer.analyze_hops(
        raw_hops,
        "sbce",
        "10.2.156.131",
        latency_jump_threshold_ms=40.0,
    )

    assert path_telemetry.latency_onset_hop == 2
    hop2 = path_telemetry.hops[1]
    assert hop2.delta_rtt_ms == 56.0


def test_mpls_label_stack_rfc4950():
    """Verify parsing and validation of RFC 4950 MPLS label extensions."""
    raw_1 = (1001 << 12) | (5 << 9) | (0 << 8) | 64
    raw_2 = (2002 << 12) | (0 << 9) | (1 << 8) | 63
    payload = struct.pack("!HBBII", 12, 1, 1, raw_1, raw_2)

    entries = MplsLabelParser.parse_rfc4950(payload)
    assert len(entries) == 2
    assert entries[0].label == 1001
    assert entries[0].exp == 5
    assert entries[0].bos == 0
    assert entries[0].ttl == 64

    assert entries[1].label == 2002
    assert entries[1].exp == 0
    assert entries[1].bos == 1
    assert entries[1].ttl == 63


def test_path_hashing_and_route_churn():
    """Verify path hash calculation and route divergence detection."""
    raw_1 = [
        {"hop_index": 1, "ip_address": "10.2.1.254", "rtts_ms": [1.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": "196.201.214.1", "rtts_ms": [5.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 3, "ip_address": "10.2.156.131", "rtts_ms": [10.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_1 = HopAnalyzer.analyze_hops(raw_1, "sbce", "10.2.156.131")

    raw_2 = [
        {"hop_index": 1, "ip_address": "10.2.1.254", "rtts_ms": [1.0], "probes_sent": 1, "probes_received": 1},
        {"hop_index": 2, "ip_address": "196.201.214.5", "rtts_ms": [5.0], "probes_sent": 1, "probes_received": 1}, # Diverged IP
        {"hop_index": 3, "ip_address": "10.2.156.131", "rtts_ms": [10.0], "probes_sent": 1, "probes_received": 1},
    ]
    path_2 = HopAnalyzer.analyze_hops(
        raw_2,
        "sbce",
        "10.2.156.131",
        previous_path_hash=path_1.path_hash,
        previous_responsive_ips=["10.2.1.254", "196.201.214.1", "10.2.156.131"],
    )

    assert path_1.path_hash != path_2.path_hash
    assert path_2.has_route_changed is True
    assert path_2.divergent_hop_index == 2


def test_endpoint_probes_dns_tcp_http():
    """Verify endpoint application synthetic probes execute cleanly using asyncio.run."""
    async def _run_probes():
        dns_probe = DnsProbe(timeout_seconds=2.0)
        dns_res = await dns_probe.probe("localhost", record_type="A")
        assert dns_res.status in (DnsResolutionStatus.NOERROR, DnsResolutionStatus.SUCCESS)
        assert len(dns_res.resolved_ips) > 0

        tcp_probe = TcpProbe(default_timeout_seconds=2.0)
        tcp_res = await tcp_probe.probe("127.0.0.1", destination_port=8088)
        assert tcp_res.status == TcpConnectStatus.SUCCESS

        http_probe = HttpProbe(default_timeout_seconds=3.0)
        http_res = await http_probe.probe("http://127.0.0.1:8088")
        assert http_res.status_outcome == HttpStatusOutcome.SUCCESS
        assert http_res.status_code == 200

    asyncio.run(_run_probes())


def test_trans_wan_voice_prober_optimal():
    """Verify TransWanVoiceProber computes optimal voice metrics for low-loss, low-RTT outstations."""
    wan_prober = TransWanVoiceProber()
    res = wan_prober.execute_probe(
        station_id="MBA-AIRPORT",
        circuit_id="CIRCUIT-MPLS-SAFARICOM-MBA-01",
        rtt_ms=35.0,
        jitter_ms=3.0,
        packet_loss_percent=0.2,
    )
    assert res.status == VoiceTrunkStatus.OPTIMAL
    assert res.r_factor > 80.0
    assert res.mos_score >= 4.0
    assert res.failover_recommended is False


def test_trans_wan_voice_prober_degraded_failover():
    """Verify TransWanVoiceProber recommends failover under severe degradation."""
    wan_prober = TransWanVoiceProber()
    res = wan_prober.execute_probe(
        station_id="KIS-AIRPORT",
        circuit_id="CIRCUIT-MPLS-TELKOM-KIS-01",
        rtt_ms=280.0,
        jitter_ms=45.0,
        packet_loss_percent=8.5,
    )
    assert res.status in (VoiceTrunkStatus.DEGRADED, VoiceTrunkStatus.CRITICAL_FAILOVER)
    assert res.failover_recommended is True
    assert res.r_factor < 70.0


def test_sip_options_reachability_guard():
    """Verify SIP OPTIONS establishes signaling reachability only and does not claim RTP media."""
    options_res = SipOptionsResult(
        probe_id="probe-sip-01",
        station_id="LHR-TERMINAL4",
        circuit_id="CIRCUIT-DIA-BT-LHR-01",
        rtt_ms=168.2,
        response_code=200,
        signaling_reachable=True,
    )
    assert options_res.signaling_reachable is True
    assert options_res.proves_voice_media is False
    assert "does NOT prove" in options_res.evidence_note
