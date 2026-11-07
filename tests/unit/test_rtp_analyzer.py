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


def test_unidirectional_media_invalidates_mos():
    """Verify that one-way audio (TRANSMIT_ONLY or RECEIVE_ONLY) invalidates conversational MOS."""
    # Transmit only (remote silence / firewall drop)
    metrics_tx = RtpAnalyzer.from_metrics(
        jitter_ms=2.0,
        loss_pct=0.0,
        rtt_ms=15.0,
        packets_sent=250,
        packets_received=0,
    )
    assert not metrics_tx.is_valid
    assert metrics_tx.verification_level.value == "TRANSMIT_ONLY"
    assert metrics_tx.estimated_mos is None
    assert metrics_tx.r_factor is None
    # Packet loss cannot be claimed as 0.0% when 0 packets are received
    assert metrics_tx.loss_pct is None

    # Receive only (local mute / egress drop)
    metrics_rx = RtpAnalyzer.from_metrics(
        jitter_ms=2.0,
        loss_pct=0.0,
        rtt_ms=15.0,
        packets_sent=0,
        packets_received=250,
    )
    assert not metrics_rx.is_valid
    assert metrics_rx.verification_level.value == "RECEIVE_ONLY"
    assert metrics_rx.estimated_mos is None


def test_no_media_invalidates_mos():
    """Verify that NO_MEDIA stream invalidates conversational MOS."""
    metrics_none = RtpAnalyzer.from_metrics(
        jitter_ms=0.0,
        loss_pct=0.0,
        rtt_ms=0.0,
        packets_sent=0,
        packets_received=0,
    )
    assert not metrics_none.is_valid
    assert metrics_none.verification_level.value == "NO_MEDIA"
    assert metrics_none.estimated_mos is None
    assert metrics_none.r_factor is None


def test_codec_impairment_comparison():
    """Verify ITU-T G.107 equipment impairment: G.729A has intrinsic impairment vs G.711u."""
    r_g711, mos_g711, _ = RtpAnalyzer.calculate_estimated_mos(
        jitter_ms=5.0, loss_pct=1.0, rtt_ms=30.0, codec="G.711u"
    )
    r_g729, mos_g729, _ = RtpAnalyzer.calculate_estimated_mos(
        jitter_ms=5.0, loss_pct=1.0, rtt_ms=30.0, codec="G.729A"
    )

    assert r_g711 is not None and r_g729 is not None
    assert mos_g711 is not None and mos_g729 is not None
    # G.729A has base Ie=11 impairment, so its R-factor and MOS must be strictly lower than G.711u
    assert r_g729 < r_g711
    assert mos_g729 < mos_g711
    assert mos_g711 >= 4.2
    assert mos_g729 <= 4.0


def test_delay_impairment_knee_point():
    """Verify non-linear delay penalty when mouth-to-ear latency exceeds 177.3ms."""
    # Baseline delay within 100ms
    r_low_delay, mos_low, d_low = RtpAnalyzer.calculate_estimated_mos(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=40.0
    )
    # Severe delay well above 177.3ms knee point (e.g. satellite / cross-continent transit: RTT 350ms)
    r_high_delay, mos_high, d_high = RtpAnalyzer.calculate_estimated_mos(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=350.0
    )

    assert d_low is not None and d_low < 100.0
    assert d_high is not None and d_high > 177.3
    assert r_high_delay is not None and r_low_delay is not None
    assert r_high_delay < r_low_delay
    assert mos_high is not None and mos_low is not None
    assert mos_high < mos_low
