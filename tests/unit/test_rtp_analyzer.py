"""Unit tests for ITU-T G.107 E-model MOS and RTCP Voice Telemetry Analyzer."""

import pytest

from services.voice.rtp_analyzer import RtpAnalyzer


def test_e_model_ideal_conditions():
    """Verify E-model calculation under near-ideal LAN/VoIP conditions."""
    # Jitter 2ms, Loss 0%, RTT 10ms
    r_factor, mos = RtpAnalyzer.calculate_mos(jitter_ms=2.0, loss_pct=0.0, rtt_ms=10.0)
    assert r_factor is not None
    assert mos is not None
    assert 92.0 <= r_factor <= 93.2
    assert 4.35 <= mos <= 4.42


def test_e_model_moderate_impairment():
    """Verify E-model behavior with typical WAN latency, jitter, and packet loss."""
    # Jitter 15ms, Loss 2.0%, RTT 120ms
    r_factor, mos = RtpAnalyzer.calculate_mos(jitter_ms=15.0, loss_pct=2.0, rtt_ms=120.0)
    assert r_factor is not None
    assert mos is not None
    assert 70.0 <= r_factor <= 88.0
    assert 3.6 <= mos <= 4.3



def test_e_model_severe_impairment():
    """Verify E-model degradation under poor network conditions."""
    # Jitter 50ms, Loss 10.0%, RTT 300ms
    r_factor, mos = RtpAnalyzer.calculate_mos(jitter_ms=50.0, loss_pct=10.0, rtt_ms=300.0)
    assert r_factor is not None
    assert mos is not None
    assert 40.0 <= r_factor <= 60.0
    assert 2.0 <= mos <= 3.2


def test_e_model_catastrophic_conditions():
    """Verify E-model clips to minimum MOS 1.0 under catastrophic loss."""
    r_factor, mos = RtpAnalyzer.calculate_mos(jitter_ms=200.0, loss_pct=60.0, rtt_ms=1000.0)
    assert r_factor == 0.0
    assert mos == 1.0


def test_critical_rule_missing_rtcp_is_unknown():
    """CRITICAL DIRECTIVE: When RTCP data is absent, MOS and R-factor MUST NOT be fabricated."""
    # None inputs
    metrics = RtpAnalyzer.from_metrics(jitter_ms=None, loss_pct=None, rtt_ms=None)
    assert not metrics.is_valid
    assert metrics.mos_score is None
    assert metrics.r_factor is None

    # Partial missing input
    metrics_partial = RtpAnalyzer.from_metrics(jitter_ms=10.0, loss_pct=None)
    assert not metrics_partial.is_valid
    assert metrics_partial.mos_score is None
    assert metrics_partial.r_factor is None

    # Empty AMI event list
    empty_events = RtpAnalyzer.parse_ami_rtcp_events([])
    assert not empty_events.is_valid
    assert empty_events.mos_score is None
    assert empty_events.r_factor is None


def test_ami_rtcp_event_parsing():
    """Verify extraction and averaging of RTCP events from Asterisk AMI stream."""
    events = [
        {
            "Event": "Newchannel",
            "Channel": "PJSIP/avaya-001",
        },
        {
            "Event": "RTCPReceived",
            "Channel": "PJSIP/avaya-001",
            "FractionLost": "2",  # 2 / 256 = ~0.78%
            "Jitter": "0.005",    # 5 ms
            "RTT": "0.040",       # 40 ms
            "PacketsSent": "250",
            "PacketsReceived": "248",
        },
        {
            "Event": "RTCPSent",
            "Channel": "PJSIP/avaya-001",
            "FractionLost": "0",
            "Jitter": "0.004",    # 4 ms
            "RTT": "0.038",       # 38 ms
            "PacketsSent": "300",
            "PacketsReceived": "298",
        },
        {
            "Event": "Hangup",
            "Channel": "PJSIP/avaya-001",
        },
    ]

    metrics = RtpAnalyzer.parse_ami_rtcp_events(events)
    assert metrics.is_valid
    assert metrics.jitter_ms is not None and metrics.jitter_ms > 0
    assert metrics.loss_pct is not None
    assert metrics.rtt_ms is not None
    assert metrics.mos_score is not None
    assert 4.0 <= metrics.mos_score <= 4.5
    assert metrics.packets_sent == 300
    assert metrics.packets_received == 298
