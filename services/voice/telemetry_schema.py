"""Canonical Voice Telemetry Event Schema (v1.0).

Defines the normalized data exchange model for voice communications observability.
Decouples telemetry producers (Asterisk, Avaya SBCE, Session Manager, passive sniffers)
from consumers (Zabbix, Grafana, Service Assurance Correlation Engine).
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from services.voice.models import (
    CallOutcome,
    MediaVerificationLevel,
    SyntheticCallResult,
)


class DataCompleteness(str, Enum):
    """Integrity and completeness classification of voice telemetry."""

    COMPLETE = "COMPLETE"                     # Full signaling and bidirectional RTCP captured
    PARTIAL_SIGNALING_ONLY = "SIGNALING_ONLY"  # Signaling terminated before media (busy, congestion, uncompleted)
    PARTIAL_MISSING_MEDIA = "MISSING_MEDIA"   # Call was answered, but 0 RTP or no RTCP reports were captured
    MALFORMED = "MALFORMED"                   # Corrupt or invalid telemetry


class MeasurementConfidence(str, Enum):
    """Reliability assessment of media quality calculations."""

    HIGH = "HIGH"       # >= 100 RTCP packets across both transmit and receive streams
    MEDIUM = "MEDIUM"   # < 100 packets, short duration call probe
    LOW = "LOW"         # Asymmetric telemetry or missing one stream
    UNKNOWN = "UNKNOWN" # No RTCP data present; quality could not be measured


@dataclass
class CorrelationIdentifiers:
    """Multi-layer session correlation keys."""

    action_id: str
    sip_call_id: Optional[str] = None
    unique_id: Optional[str] = None
    linked_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EndpointIdentifiers:
    """Participant addressing and channel routing information."""

    destination: str
    caller: Optional[str] = None
    ingress_channel: Optional[str] = None
    egress_channel: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MilestoneTimestamps:
    """Millisecond-precision epoch timestamps for call lifecycle events."""

    initiated: float
    hungup: float
    ringing: Optional[float] = None
    answered: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalingTelemetry:
    """SIP session establishment and teardown telemetry."""

    outcome: CallOutcome
    setup_time_ms: float = 0.0
    duration_seconds: float = 0.0
    sip_status_code: Optional[int] = None
    sip_status_reason: Optional[str] = None
    hangup_cause: Optional[int] = None
    hangup_cause_txt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d


@dataclass
class MediaTelemetry:
    """RTP packet stream and RTCP performance metrics."""

    verification_level: MediaVerificationLevel
    codec: str = "G.711u"
    packetization_ms: float = 20.0
    packets_transmitted: int = 0
    packets_received: int = 0

    jitter_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    rtt_ms: Optional[float] = None

    # Delays: distinguish measured vs estimated delay
    measured_one_way_delay_ms: Optional[float] = None   # From synchronized clocks / RTCP XR
    estimated_one_way_delay_ms: Optional[float] = None  # Inferred via (RTT/2) + 2*jitter + 20ms

    # Quality: estimated via ITU-T G.107 E-model
    estimated_mos: Optional[float] = None
    r_factor: Optional[float] = None

    data_completeness: DataCompleteness = DataCompleteness.COMPLETE
    measurement_confidence: MeasurementConfidence = MeasurementConfidence.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verification_level"] = self.verification_level.value
        d["data_completeness"] = self.data_completeness.value
        d["measurement_confidence"] = self.measurement_confidence.value
        return d


@dataclass
class CanonicalVoiceEvent:
    """Versioned canonical voice quality and service assurance event (v1.0)."""

    schema_version: str = "1.0"
    event_id: str = field(default_factory=lambda: f"vce-{uuid.uuid4().hex[:12]}")
    collection_timestamp: float = field(default_factory=lambda: 0.0)
    event_source: str = "nawari.synthetic_probe"
    device_id: str = "nawari-voice-probe-01"
    service_id: str = "voice-service-default"

    correlation: CorrelationIdentifiers = field(
        default_factory=lambda: CorrelationIdentifiers(action_id="")
    )
    endpoints: EndpointIdentifiers = field(
        default_factory=lambda: EndpointIdentifiers(destination="")
    )
    timestamps: MilestoneTimestamps = field(
        default_factory=lambda: MilestoneTimestamps(initiated=0.0, hungup=0.0)
    )
    signaling: SignalingTelemetry = field(
        default_factory=lambda: SignalingTelemetry(outcome=CallOutcome.FAILED)
    )
    media: MediaTelemetry = field(
        default_factory=lambda: MediaTelemetry(
            verification_level=MediaVerificationLevel.UNVERIFIED
        )
    )

    def validate(self) -> None:
        """Validate payload integrity, boundaries, and timestamps."""
        if not self.event_id:
            raise ValueError("event_id must not be empty")
        if not self.device_id:
            raise ValueError("device_id must not be empty")
        if not self.endpoints.destination:
            raise ValueError("endpoints.destination must not be empty")
        if self.timestamps.initiated <= 0:
            raise ValueError("timestamps.initiated must be a positive epoch timestamp")
        if self.timestamps.hungup < self.timestamps.initiated:
            raise ValueError("timestamps.hungup cannot precede timestamps.initiated")

        # Validate loss percentage bounds
        if self.media.loss_pct is not None:
            if not (0.0 <= self.media.loss_pct <= 100.0):
                raise ValueError(f"media.loss_pct out of range: {self.media.loss_pct}")

        # Validate MOS bounds
        if self.media.estimated_mos is not None:
            if not (1.0 <= self.media.estimated_mos <= 4.5):
                raise ValueError(f"media.estimated_mos out of range: {self.media.estimated_mos}")

        # Invariant: If incomplete RTCP, estimated_mos must remain None
        if self.media.data_completeness != DataCompleteness.COMPLETE:
            if self.media.estimated_mos is not None:
                raise ValueError("estimated_mos cannot be present when data_completeness is not COMPLETE")

    def to_zabbix_metrics(self, host: Optional[str] = None) -> list[Any]:
        """Convert canonical voice event fields into Zabbix trapper metrics."""
        from services.voice.zabbix_sender import ZabbixMetric

        target_host = host or self.device_id
        now = int(self.collection_timestamp) if self.collection_timestamp > 0 else None

        metrics = [
            ZabbixMetric(target_host, "voice.synthetic.outcome", self.signaling.outcome.value, now),
            ZabbixMetric(target_host, "voice.synthetic.duration", self.signaling.duration_seconds, now),
            ZabbixMetric(target_host, "voice.synthetic.media_status", self.media.verification_level.value, now),
        ]

        if self.signaling.sip_status_code is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.sip_status", self.signaling.sip_status_code, now))

        if self.signaling.setup_time_ms > 0:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.setup_time", self.signaling.setup_time_ms, now))

        if self.media.estimated_mos is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.mos", self.media.estimated_mos, now))

        if self.media.r_factor is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.r_factor", self.media.r_factor, now))

        if self.media.jitter_ms is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.jitter", self.media.jitter_ms, now))

        if self.media.loss_pct is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.packet_loss", self.media.loss_pct, now))

        if self.media.rtt_ms is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.rtt", self.media.rtt_ms, now))

        if self.media.estimated_one_way_delay_ms is not None:
            metrics.append(ZabbixMetric(target_host, "voice.synthetic.one_way_delay", self.media.estimated_one_way_delay_ms, now))

        return metrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "collection_timestamp": self.collection_timestamp,
            "event_source": self.event_source,
            "device_id": self.device_id,
            "service_id": self.service_id,
            "correlation": self.correlation.to_dict(),
            "endpoints": self.endpoints.to_dict(),
            "timestamps": self.timestamps.to_dict(),
            "signaling": self.signaling.to_dict(),
            "media": self.media.to_dict(),
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_call_result(
        cls,
        result: SyntheticCallResult,
        device_id: str = "nawari-voice-probe-01",
        service_id: str = "voice-service-default",
        event_source: str = "nawari.synthetic_probe",
    ) -> "CanonicalVoiceEvent":
        """Convert a SyntheticCallResult into a validated CanonicalVoiceEvent."""
        sig = result.signaling
        med = result.media

        # Classify data completeness
        if result.outcome != CallOutcome.ANSWERED:
            completeness = DataCompleteness.PARTIAL_SIGNALING_ONLY
            confidence = MeasurementConfidence.UNKNOWN
        elif not med.is_valid:
            completeness = DataCompleteness.PARTIAL_MISSING_MEDIA
            confidence = MeasurementConfidence.UNKNOWN
        else:
            completeness = DataCompleteness.COMPLETE
            total_pkts = med.packets_sent + med.packets_received
            confidence = (
                MeasurementConfidence.HIGH
                if total_pkts >= 100
                else MeasurementConfidence.MEDIUM
            )

        correlation = CorrelationIdentifiers(
            action_id=result.action_id,
            sip_call_id=sig.sip_call_id,
            unique_id=sig.unique_id,
            linked_id=sig.linked_id,
        )

        endpoints = EndpointIdentifiers(
            destination=result.target,
            caller=sig.caller,
            ingress_channel=sig.channel,
            egress_channel=sig.dest_channel,
        )

        timestamps = MilestoneTimestamps(
            initiated=sig.timestamp_initiated or result.timestamp_start,
            ringing=sig.timestamp_ringing,
            answered=sig.timestamp_answered,
            hungup=sig.timestamp_hangup or result.timestamp_end,
        )

        signaling = SignalingTelemetry(
            outcome=result.outcome,
            setup_time_ms=sig.setup_time_ms,
            duration_seconds=result.duration_seconds,
            sip_status_code=sig.sip_status_code,
            sip_status_reason=sig.sip_status_reason,
            hangup_cause=sig.hangup_cause,
            hangup_cause_txt=sig.hangup_cause_txt,
        )

        media = MediaTelemetry(
            verification_level=med.verification_level,
            codec=med.codec,
            packetization_ms=20.0,
            packets_transmitted=med.packets_sent,
            packets_received=med.packets_received,
            jitter_ms=med.jitter_ms,
            loss_pct=med.loss_pct,
            rtt_ms=med.rtt_ms,
            measured_one_way_delay_ms=None,  # Unmeasured without NTP synchronized endpoints
            estimated_one_way_delay_ms=med.one_way_delay_ms,
            estimated_mos=med.estimated_mos,
            r_factor=med.r_factor,
            data_completeness=completeness,
            measurement_confidence=confidence,
        )

        event = cls(
            collection_timestamp=result.timestamp_end,
            event_source=event_source,
            device_id=device_id,
            service_id=service_id,
            correlation=correlation,
            endpoints=endpoints,
            timestamps=timestamps,
            signaling=signaling,
            media=media,
        )
        event.validate()
        return event
