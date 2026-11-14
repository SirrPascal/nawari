"""Unit tests for Workstream 10C: RFC 3611 RTCP-XR, Extended E-Model, and SDP Inspector."""

from __future__ import annotations

import pytest

from services.voice.models import MediaVerificationLevel
from services.voice.rtp import (
    ExtendedEModelEngine,
    RTCPXRAnalyzer,
    RTCPXRVoIPMetrics,
    SDPInspector,
)


def test_rtcp_xr_voip_metrics_parsing():
    raw_data = {
        "loss_rate_pct": 1.5,
        "discard_rate_pct": 0.8,
        "burst_density_pct": 25.0,
        "burst_duration_ms": 60.0,
        "round_trip_delay_ms": 45.0,
        "end_system_delay_ms": 20.0,
    }
    metrics = RTCPXRAnalyzer.parse_voip_metrics_block(raw_data)
    assert metrics.is_valid is True
    assert metrics.loss_rate_pct == 1.5
    assert metrics.discard_rate_pct == 0.8
    assert metrics.burst_duration_ms == 60.0
    assert metrics.round_trip_delay_ms == 45.0


def test_rtcp_xr_degradation_diagnostics():
    # 1. Jitter buffer discard dominant
    jb_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=0.2,
        discard_rate_pct=3.5,
        round_trip_delay_ms=50.0,
        is_valid=True,
    )
    diags1 = RTCPXRAnalyzer.diagnose_media_degradation(jb_metrics)
    assert any("Jitter Buffer Discard Dominant" in d for d in diags1)

    # 2. Micro-burst loss
    burst_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=4.0,
        burst_duration_ms=65.0,
        burst_density_pct=35.0,
        round_trip_delay_ms=40.0,
        is_valid=True,
    )
    diags2 = RTCPXRAnalyzer.diagnose_media_degradation(burst_metrics)
    assert any("Micro-burst loss pattern detected" in d for d in diags2)

    # 3. High mouth-to-ear delay
    delay_metrics = RTCPXRVoIPMetrics(
        round_trip_delay_ms=280.0,  # one-way = 140
        end_system_delay_ms=30.0,   # total = 170ms > 150ms
        is_valid=True,
    )
    diags3 = RTCPXRAnalyzer.diagnose_media_degradation(delay_metrics)
    assert any("Excessive mouth-to-ear delay" in d for d in diags3)


def test_extended_emodel_calculation_and_invariants():
    # 1. Healthy G.711 stream (Low delay, zero loss)
    healthy_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=0.0,
        discard_rate_pct=0.0,
        round_trip_delay_ms=20.0,
        end_system_delay_ms=10.0,
        is_valid=True,
    )
    r, mos = ExtendedEModelEngine.calculate_r_and_mos(
        healthy_metrics,
        codec="G.711u",
        verification_level=MediaVerificationLevel.BIDIRECTIONAL,
    )
    assert r is not None and r > 90.0
    assert mos is not None and mos >= 4.3

    # 2. Degraded G.729 stream (High packet loss + discard)
    lossy_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=5.0,
        discard_rate_pct=2.0,
        round_trip_delay_ms=120.0,
        end_system_delay_ms=25.0,
        is_valid=True,
    )
    r_loss, mos_loss = ExtendedEModelEngine.calculate_r_and_mos(
        lossy_metrics,
        codec="G.729a",
        verification_level=MediaVerificationLevel.BIDIRECTIONAL,
    )
    assert r_loss is not None and r_loss < 70.0
    assert mos_loss is not None and mos_loss < 3.6

    # 3. STRICT INVARIANT GUARD: Missing or unverified media MUST yield None
    r_invalid, mos_invalid = ExtendedEModelEngine.calculate_r_and_mos(
        healthy_metrics,
        codec="G.711u",
        verification_level=MediaVerificationLevel.TRANSMIT_ONLY,  # Not bidirectional
    )
    assert r_invalid is None
    assert mos_invalid is None

    r_none, mos_none = ExtendedEModelEngine.calculate_r_and_mos(None)
    assert r_none is None
    assert mos_none is None


def test_sdp_inspector_offer_answer():
    offer_sdp = """v=0
o=nawari 123 123 IN IP4 10.2.1.58
s=-
c=IN IP4 10.2.1.58
t=0 0
m=audio 10002 RTP/AVP 0 8 18
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:18 G729/8000
a=ptime:20
"""

    answer_sdp = """v=0
o=AvayaCM 456 456 IN IP4 10.2.156.60
s=-
c=IN IP4 10.2.156.60
t=0 0
m=audio 20042 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=ptime:20
"""

    # 1. Clean negotiation matching PCMU
    res = SDPInspector.compare_offer_answer(offer_sdp, answer_sdp)
    assert res["negotiation_success"] is True
    assert res["selected_payload_type"] == 0
    assert "PCMU" in res["selected_codec"]
    assert res["has_anomalies"] is False

    # 2. Codec mismatch (answer offers only Opus, offer only G.711)
    mismatch_answer = """v=0
o=Other 789 789 IN IP4 10.2.156.99
s=-
c=IN IP4 10.2.156.99
t=0 0
m=audio 30000 RTP/AVP 111
a=rtpmap:111 opus/48000/2
a=ptime:20
"""
    res_mismatch = SDPInspector.compare_offer_answer(offer_sdp, mismatch_answer)
    assert res_mismatch["negotiation_success"] is False
    assert "Codec Mismatch" in res_mismatch["error"]

    # 3. Asymmetric ptime anomaly
    asymm_answer = """v=0
o=AvayaCM 456 456 IN IP4 10.2.156.60
s=-
c=IN IP4 10.2.156.60
t=0 0
m=audio 20042 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=ptime:30
"""
    res_asymm = SDPInspector.compare_offer_answer(offer_sdp, asymm_answer)
    assert res_asymm["negotiation_success"] is True
    assert res_asymm["has_anomalies"] is True
    assert any("Asymmetric packetization time" in a for a in res_asymm["anomalies"])

