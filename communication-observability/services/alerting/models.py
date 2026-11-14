"""
Nawari Alerting Framework — Data Models & Lifecycle Definitions
Provides standardized severity, lifecycle states, evidence classifications, and alert rules.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class AlertSeverity(str, Enum):
    """Zabbix / Nawari operational severity tiers."""
    INFO = "INFO"
    WARNING = "WARNING"
    AVERAGE = "AVERAGE"
    HIGH = "HIGH"
    DISASTER = "DISASTER"


class AlertState(str, Enum):
    """Operational lifecycle state of an alert instance."""
    PENDING = "PENDING"
    FIRING = "FIRING"
    SUPPRESSED = "SUPPRESSED"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


class AlertEvidence(str, Enum):
    """Truth-in-telemetry evidence classification for alert rules."""
    VERIFIED_LIVE = "VERIFIED_LIVE"
    VERIFIED_INTEGRATION = "VERIFIED_INTEGRATION"
    CONFIGURED_UNVERIFIED = "CONFIGURED_UNVERIFIED"
    SIMULATED = "SIMULATED"
    SYNTHETIC = "SYNTHETIC"
    NOT_COLLECTED = "NOT_COLLECTED"
    UNSUPPORTED = "UNSUPPORTED"
    RESEARCH_REQUIRED = "RESEARCH_REQUIRED"


@dataclass
class AlertRule:
    """Formal specification of an operational alert rule."""
    alert_id: str
    name: str
    component: str
    description: str
    severity: AlertSeverity
    metric_key: str
    evaluator: Callable[[Any, Dict[str, Any]], bool]
    trigger_expression: str
    recovery_expression: str
    evaluation_interval_seconds: int = 60
    pending_duration_seconds: int = 120
    stale_data_threshold_seconds: int = 900
    deduplication_key: str = ""
    runbook: str = ""
    evidence_class: AlertEvidence = AlertEvidence.VERIFIED_INTEGRATION
    enabled: bool = True
    is_synthetic: bool = False

    def __post_init__(self):
        if not self.deduplication_key:
            self.deduplication_key = f"{self.component}:{self.alert_id}"


@dataclass
class AlertInstance:
    """Active or resolved instance of an evaluated alert rule."""
    alert_id: str
    entity_id: str
    site_id: str
    current_state: AlertState = AlertState.PENDING
    observed_value: Any = None
    first_observed_at: float = field(default_factory=time.time)
    last_observed_at: float = field(default_factory=time.time)
    firing_started_at: Optional[float] = None
    resolved_at: Optional[float] = None
    nominal_recovery_cycles: int = 0
    required_recovery_cycles: int = 3
    fingerprint: str = ""
    last_notification_sent_at: Optional[float] = None
    notification_count: int = 0
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.fingerprint:
            raw = f"{self.alert_id}|{self.entity_id}|{self.site_id}"
            self.fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def firing_duration_seconds(self) -> float:
        if self.firing_started_at is None:
            return 0.0
        end_time = self.resolved_at or time.time()
        return max(0.0, end_time - self.firing_started_at)
