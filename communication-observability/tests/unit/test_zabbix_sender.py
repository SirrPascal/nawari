"""Unit tests for pure Python Zabbix Sender implementation."""

import json
import pytest

from services.voice.models import (
    CallOutcome,
    MediaQualityMetrics,
    MediaVerificationLevel,
    SipSignalingMetrics,
    SyntheticCallResult,
)
from services.voice.zabbix_sender import (
    ZabbixMetric,
    ZabbixSender,
    ZabbixSenderResponse,
)


def test_zabbix_metric_serialization():
    """Verify dictionary serialization for Zabbix metrics."""
    m1 = ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.mos", value=4.38, clock=1794076000)
    d1 = m1.to_dict()
    assert d1["host"] == "nawari-voice-probe-01"
    assert d1["key"] == "voice.synthetic.mos"
    assert d1["value"] == 4.38
    assert d1["clock"] == 1794076000


def test_zabbix_sender_response_parsing():
    """Verify regex parsing of Zabbix Server response packets."""
    raw = json.dumps({
        "response": "success",
        "info": "processed: 5; failed: 0; total: 5; seconds spent: 0.000120"
    })
    resp = ZabbixSenderResponse.parse(raw)
    assert resp.response == "success"
    assert resp.processed == 5
    assert resp.failed == 0
    assert resp.total == 5
    assert 0.0001 <= resp.seconds_spent <= 0.0002


def test_call_result_to_zabbix_metrics():
    """Verify transformation of SyntheticCallResult into Zabbix trapper metrics."""
    res = SyntheticCallResult(
        action_id="test-action-123",
        target="1001",
        outcome=CallOutcome.ANSWERED,
        success=True,
        timestamp_start=1794076000.0,
        timestamp_end=1794076003.5,
        duration_seconds=3.5,
        signaling=SipSignalingMetrics(
            setup_time_ms=150.0,
            sip_status_code=200,
            sip_status_reason="OK",
        ),
        media=MediaQualityMetrics(
            jitter_ms=4.5,
            loss_pct=0.2,
            rtt_ms=25.0,
            one_way_delay_ms=41.5,
            estimated_mos=4.35,
            r_factor=91.8,
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            is_valid=True,
        ),
    )

    sender = ZabbixSender()
    # Mock socket communication to capture the metrics list
    captured = []
    sender.send = lambda metrics: captured.extend(metrics) or ZabbixSenderResponse(response="success", info="processed: 7; failed: 0; total: 7; seconds spent: 0.0001")

    sender.send_call_result(res, host="test-probe")

    keys = {m.key: m.value for m in captured}
    assert keys["voice.synthetic.outcome"] == "ANSWERED"
    assert keys["voice.synthetic.sip_status"] == 200
    assert keys["voice.synthetic.setup_time"] == 150.0
    assert keys["voice.synthetic.duration"] == 3.5
    assert keys["voice.synthetic.media_status"] == "BIDIRECTIONAL"
    assert keys["voice.synthetic.mos"] == 4.35
    assert keys["voice.synthetic.r_factor"] == 91.8
    assert keys["voice.synthetic.jitter"] == 4.5
    assert keys["voice.synthetic.packet_loss"] == 0.2
    assert keys["voice.synthetic.rtt"] == 25.0
    assert keys["voice.synthetic.one_way_delay"] == 41.5


def test_call_result_without_media_omits_invalid_metrics():
    """Verify that when media is invalid (e.g. signaling-only), MOS metrics are NOT dispatched."""
    res = SyntheticCallResult(
        action_id="test-action-456",
        target="1002",
        outcome=CallOutcome.ANSWERED,
        success=True,
        timestamp_start=1794076000.0,
        timestamp_end=1794076003.0,
        duration_seconds=3.0,
        signaling=SipSignalingMetrics(
            setup_time_ms=200.0,
            sip_status_code=200,
        ),
        media=MediaQualityMetrics(is_valid=False),
    )

    sender = ZabbixSender()
    captured = []
    sender.send = lambda metrics: captured.extend(metrics) or ZabbixSenderResponse(response="success", info="processed: 4; failed: 0; total: 4; seconds spent: 0.0001")

    sender.send_call_result(res, host="test-probe")

    keys = {m.key for m in captured}
    assert "voice.synthetic.outcome" in keys
    assert "voice.synthetic.sip_status" in keys
    assert "voice.synthetic.setup_time" in keys
    assert "voice.synthetic.media_status" in keys
    # MOS and RTCP metrics must NOT be present when is_valid is False
    assert "voice.synthetic.mos" not in keys
    assert "voice.synthetic.r_factor" not in keys
    assert "voice.synthetic.jitter" not in keys


def test_send_voice_event():
    """Verify transmission of CanonicalVoiceEvent through ZabbixSender."""
    from services.voice.telemetry_schema import (
        CanonicalVoiceEvent,
        DataCompleteness,
        EndpointIdentifiers,
        MediaTelemetry,
        MilestoneTimestamps,
        SignalingTelemetry,
    )

    ev = CanonicalVoiceEvent(
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=1700000000.0, hungup=1700000010.0),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=105.0,
            duration_seconds=10.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            estimated_mos=4.38,
            r_factor=91.0,
            jitter_ms=1.8,
            loss_pct=0.0,
            rtt_ms=12.0,
            estimated_one_way_delay_ms=25.6,
            data_completeness=DataCompleteness.COMPLETE,
        ),
    )

    sender = ZabbixSender()
    captured = []
    sender.send = lambda metrics: captured.extend(metrics) or ZabbixSenderResponse(
        response="success", info=f"processed: {len(metrics)}; failed: 0; total: {len(metrics)}; seconds spent: 0.0001"
    )

    resp = sender.send_voice_event(ev)
    assert resp.response == "success"
    assert len(captured) >= 8
    keys = {m.key: m.value for m in captured}
    assert keys["voice.synthetic.outcome"] == "ANSWERED"
    assert keys["voice.synthetic.mos"] == 4.38
    assert keys["voice.synthetic.media_status"] == "BIDIRECTIONAL"
