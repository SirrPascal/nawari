"""Unit tests for Canonical Voice Telemetry Schema (v1.0)."""

import pytest
import time
from services.voice.models import (
    CallOutcome,
    MediaQualityMetrics,
    MediaVerificationLevel,
    SipSignalingMetrics,
    SyntheticCallResult,
)
from services.voice.telemetry_schema import (
    CanonicalVoiceEvent,
    CorrelationIdentifiers,
    DataCompleteness,
    EndpointIdentifiers,
    MeasurementConfidence,
    MediaTelemetry,
    MilestoneTimestamps,
    SignalingTelemetry,
)
from services.voice.zabbix_sender import ZabbixMetric


def test_canonical_voice_event_validation_success():
    """Verify validation passes on a well-formed event."""
    event = CanonicalVoiceEvent(
        collection_timestamp=1700000010.0,
        device_id="nawari-voice-probe-01",
        service_id="voice-service-default",
        correlation=CorrelationIdentifiers(
            action_id="act-test-01",
            sip_call_id="call-123@10.2.156.131",
            unique_id="1700000000.1",
        ),
        endpoints=EndpointIdentifiers(
            destination="1001",
            caller="nawari-probe",
        ),
        timestamps=MilestoneTimestamps(
            initiated=1700000000.0,
            hungup=1700000010.0,
        ),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=120.0,
            duration_seconds=10.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            codec="G.711u",
            packets_transmitted=500,
            packets_received=498,
            jitter_ms=2.1,
            loss_pct=0.4,
            rtt_ms=15.0,
            estimated_one_way_delay_ms=29.2,
            estimated_mos=4.38,
            r_factor=91.5,
            data_completeness=DataCompleteness.COMPLETE,
            measurement_confidence=MeasurementConfidence.HIGH,
        ),
    )
    event.validate()
    d = event.to_dict()
    assert d["schema_version"] == "1.0"
    assert d["signaling"]["outcome"] == "ANSWERED"
    assert d["media"]["estimated_mos"] == 4.38
    assert d["media"]["verification_level"] == "BIDIRECTIONAL"


def test_canonical_voice_event_validation_invariants():
    """Verify invariants: positive timestamps, ordered times, bounds, and incomplete RTCP MOS rule."""
    # Empty destination
    with pytest.raises(ValueError, match="endpoints.destination"):
        ev = CanonicalVoiceEvent(
            device_id="test",
            endpoints=EndpointIdentifiers(destination=""),
            timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
        )
        ev.validate()

    # Hungup preceding initiated
    with pytest.raises(ValueError, match="cannot precede"):
        ev = CanonicalVoiceEvent(
            device_id="test",
            endpoints=EndpointIdentifiers(destination="1001"),
            timestamps=MilestoneTimestamps(initiated=120.0, hungup=100.0),
        )
        ev.validate()

    # Loss percentage out of range
    with pytest.raises(ValueError, match="loss_pct out of range"):
        ev = CanonicalVoiceEvent(
            device_id="test",
            endpoints=EndpointIdentifiers(destination="1001"),
            timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
            media=MediaTelemetry(
                verification_level=MediaVerificationLevel.BIDIRECTIONAL,
                loss_pct=150.0,
            ),
        )
        ev.validate()

    # Incomplete RTCP cannot have estimated_mos
    with pytest.raises(ValueError, match="estimated_mos cannot be present"):
        ev = CanonicalVoiceEvent(
            device_id="test",
            endpoints=EndpointIdentifiers(destination="1001"),
            timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
            media=MediaTelemetry(
                verification_level=MediaVerificationLevel.BIDIRECTIONAL,
                data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA,
                estimated_mos=4.2,
            ),
        )
        ev.validate()


def test_conversion_from_call_result():
    """Test from_call_result with healthy call."""
    now = time.time()
    call_res = SyntheticCallResult(
        target="1001",
        action_id="act-synth-001",
        outcome=CallOutcome.ANSWERED,
        success=True,
        timestamp_start=now - 5.0,
        timestamp_end=now,
        duration_seconds=5.0,
        signaling=SipSignalingMetrics(
            sip_status_code=200,
            sip_status_reason="OK",
            setup_time_ms=180.0,
            sip_call_id="sip-abc-123",
            channel="PJSIP/1001-00000001",
            dest_channel="PJSIP/1001-00000002",
        ),
        media=MediaQualityMetrics(
            is_valid=True,
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            packets_sent=250,
            packets_received=250,
            jitter_ms=1.5,
            loss_pct=0.0,
            rtt_ms=12.0,
            one_way_delay_ms=28.0,
            estimated_mos=4.41,
            r_factor=92.8,
            codec="G.711u",
        ),
    )

    event = CanonicalVoiceEvent.from_call_result(call_res)
    assert event.endpoints.destination == "1001"
    assert event.correlation.action_id == "act-synth-001"
    assert event.correlation.sip_call_id == "sip-abc-123"
    assert event.signaling.outcome == CallOutcome.ANSWERED
    assert event.signaling.sip_status_code == 200
    assert event.media.verification_level == MediaVerificationLevel.BIDIRECTIONAL
    assert event.media.data_completeness == DataCompleteness.COMPLETE
    assert event.media.measurement_confidence == MeasurementConfidence.HIGH
    assert event.media.estimated_mos == 4.41


def test_to_zabbix_metrics_export():
    """Test conversion of CanonicalVoiceEvent to Zabbix trapper metrics."""
    event = CanonicalVoiceEvent(
        collection_timestamp=1700000010.0,
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=1700000000.0, hungup=1700000010.0),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=150.0,
            duration_seconds=10.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            jitter_ms=2.5,
            loss_pct=0.1,
            rtt_ms=14.0,
            estimated_one_way_delay_ms=27.0,
            estimated_mos=4.35,
            r_factor=90.0,
            data_completeness=DataCompleteness.COMPLETE,
        ),
    )

    metrics = event.to_zabbix_metrics()
    metric_keys = {m.key: m.value for m in metrics}
    assert metric_keys["voice.synthetic.outcome"] == "ANSWERED"
    assert metric_keys["voice.synthetic.sip_status"] == 200
    assert metric_keys["voice.synthetic.duration"] == 10.0
    assert metric_keys["voice.synthetic.setup_time"] == 150.0
    assert metric_keys["voice.synthetic.media_status"] == "BIDIRECTIONAL"
    assert metric_keys["voice.synthetic.mos"] == 4.35
    assert metric_keys["voice.synthetic.r_factor"] == 90.0
    assert metric_keys["voice.synthetic.jitter"] == 2.5
    assert metric_keys["voice.synthetic.packet_loss"] == 0.1
    assert metric_keys["voice.synthetic.rtt"] == 14.0
    assert metric_keys["voice.synthetic.one_way_delay"] == 27.0
