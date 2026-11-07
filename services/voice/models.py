"""Data models for Nawari Voice Observability and Synthetic Voice Testing."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class CallOutcome(str, Enum):
    """Categorized result of a synthetic voice test call."""

    ANSWERED = "ANSWERED"
    BUSY = "BUSY"
    CONGESTION = "CONGESTION"
    NO_ANSWER = "NO_ANSWER"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    DRY_RUN = "DRY_RUN"


@dataclass
class MediaQualityMetrics:
    """RTCP voice quality telemetry and estimated MOS metrics.

    CRITICAL RULE:
    When RTCP data is absent or incomplete, is_valid MUST be False,
    and mos_score and r_factor MUST remain None.
    Healthy values must NEVER be fabricated or assumed.
    """

    jitter_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    rtt_ms: Optional[float] = None
    mos_score: Optional[float] = None
    r_factor: Optional[float] = None
    packets_sent: int = 0
    packets_received: int = 0
    is_valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SipSignalingMetrics:
    """SIP session establishment and teardown timing metrics."""

    setup_time_ms: float = 0.0
    ringing_time_ms: float = 0.0
    duration_seconds: float = 0.0
    sip_status_code: Optional[int] = None
    sip_status_reason: Optional[str] = None
    hangup_cause: Optional[int] = None
    hangup_cause_txt: Optional[str] = None
    channel: Optional[str] = None
    unique_id: Optional[str] = None
    action_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

