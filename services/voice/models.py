"""Data models for Nawari Voice Observability, SIP Health, and Synthetic Voice Testing.

Supports multi-source telemetry correlation across signaling, channel lifecycle,
and bidirectional media verification.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class CallOutcome(str, Enum):
    """Categorized outcome of a synthetic voice test call."""

    ANSWERED = "ANSWERED"
    BUSY = "BUSY"
    CONGESTION = "CONGESTION"
    NO_ANSWER = "NO_ANSWER"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    DRY_RUN = "DRY_RUN"


class MediaVerificationLevel(str, Enum):
    """Verification level for voice audio streams.

    Distinguishes signaling success from real audio flow, enabling
    rapid isolation of one-way audio and missing RTP paths.
    """

    UNVERIFIED = "UNVERIFIED"         # Signaling-only probe or no media statistics
    NO_MEDIA = "NO_MEDIA"             # Channel answered, but 0 packets transmitted or received
    TRANSMIT_ONLY = "TRANSMIT_ONLY"   # Tx > 0, Rx == 0 (One-way audio symptom: remote silence)
    RECEIVE_ONLY = "RECEIVE_ONLY"     # Rx > 0, Tx == 0 (One-way audio symptom: local mute)
    BIDIRECTIONAL = "BIDIRECTIONAL"   # Both Tx > 0 and Rx > 0 confirmed


@dataclass
class MediaLifecycle:
    """Explicit 7-stage verification checklist for the voice media lifecycle.

    Guarantees that a successful SIP transaction is never confused with
    healthy bidirectional speech delivery.
    """

    signaling_established: bool = False   # 1. SIP 200 / 18x progress received
    channel_answered: bool = False        # 2. Asterisk channel state transitioned to Up
    rtp_tx_observed: bool = False         # 3. RTP transmitted packet count > 0
    rtp_rx_observed: bool = False         # 4. RTP received packet count > 0
    rtcp_received: bool = False           # 5. RTCP Sender/Receiver Reports captured
    bidirectional_media: bool = False     # 6. Both Tx and Rx verified > 0
    quality_calculated: bool = False      # 7. Valid E-model Estimated MOS generated

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass
class MediaQualityMetrics:
    """RTCP voice quality telemetry and estimated MOS metrics.

    CRITICAL ARCHITECTURAL DIRECTIVE:
    When RTCP data is absent or incomplete, is_valid MUST be False,
    and estimated_mos and r_factor MUST remain None.
    Healthy values must NEVER be fabricated or assumed.
    """

    jitter_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    rtt_ms: Optional[float] = None
    one_way_delay_ms: Optional[float] = None
    estimated_mos: Optional[float] = None
    r_factor: Optional[float] = None
    packets_sent: int = 0
    packets_received: int = 0
    codec: str = "G.711u"
    verification_level: MediaVerificationLevel = MediaVerificationLevel.UNVERIFIED
    is_valid: bool = False

    @property
    def mos_score(self) -> Optional[float]:
        """Backward-compatible alias for estimated_mos."""
        return self.estimated_mos

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mos_score"] = self.estimated_mos
        d["verification_level"] = self.verification_level.value
        return d


@dataclass
class SipSignalingMetrics:
    """SIP session establishment, teardown timing, and channel correlation metrics."""

    setup_time_ms: float = 0.0
    ringing_time_ms: float = 0.0
    duration_seconds: float = 0.0
    sip_status_code: Optional[int] = None
    sip_status_reason: Optional[str] = None
    hangup_cause: Optional[int] = None
    hangup_cause_txt: Optional[str] = None

    # Full Call Lifecycle Correlation Identifiers
    sip_call_id: Optional[str] = None
    action_id: str = ""
    unique_id: Optional[str] = None
    linked_id: Optional[str] = None
    channel: Optional[str] = None
    dest_channel: Optional[str] = None
    caller: Optional[str] = None
    destination: Optional[str] = None

    # Timestamps
    timestamp_initiated: Optional[float] = None
    timestamp_ringing: Optional[float] = None
    timestamp_answered: Optional[float] = None
    timestamp_hangup: Optional[float] = None

    # Media Lifecycle Stages
    lifecycle: MediaLifecycle = field(default_factory=MediaLifecycle)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lifecycle"] = self.lifecycle.to_dict()
        return d


@dataclass
class SyntheticCallRequest:
    """Specification for an active synthetic call execution."""

    target: str
    context: Optional[str] = None
    timeout_seconds: float = 15.0
    caller_id: Optional[str] = None
    dry_run: bool = False
    live: bool = False
    confirm_live_call: bool = False
    action_id: Optional[str] = None
    variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyntheticCallResult:
    """Complete correlated report of a synthetic call execution."""

    action_id: str
    target: str
    outcome: CallOutcome
    success: bool
    timestamp_start: float
    timestamp_end: float
    duration_seconds: float
    signaling: SipSignalingMetrics
    media: MediaQualityMetrics
    error_message: Optional[str] = None
    events_captured: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "target": self.target,
            "outcome": self.outcome.value,
            "success": self.success,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "signaling": self.signaling.to_dict(),
            "media": self.media.to_dict(),
            "error_message": self.error_message,
            "events_count": len(self.events_captured),
        }
