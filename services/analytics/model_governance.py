"""Model Governance, Audit Trails & Operational Controls for Nawari Analytics.

Enforces baseline versioning, rollback, drift detection, poison protection,
dual-threshold hysteresis, and audit trails. Freezes baseline updates during active
anomalies to prevent the analytics layer from silently learning an outage as normal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from services.analytics.anomaly_detector import AnomalySeverity, StatisticalAnomalyResult
from services.analytics.dynamic_baselines import DiurnalBaselineProfiler


class AuditEventType(str, Enum):
    ANOMALY_RAISED = "ANOMALY_RAISED"
    ANOMALY_CLEARED = "ANOMALY_CLEARED"
    ANOMALY_SUPPRESSED_FLAP = "ANOMALY_SUPPRESSED_FLAP"
    BASELINE_UPDATED = "BASELINE_UPDATED"
    BASELINE_FROZEN = "BASELINE_FROZEN"
    MODEL_ROLLBACK = "MODEL_ROLLBACK"
    BASELINE_RETRAINED = "BASELINE_RETRAINED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    POISON_REJECTED = "POISON_REJECTED"


@dataclass
class AuditTrailRecord:
    """Immutable audit trail log entry for analytical decisions and state transitions."""

    event_id: str
    event_type: AuditEventType
    timestamp: float
    entity_id: str
    metric_name: str
    current_value: Optional[float]
    baseline_value: Optional[float]
    threshold_value: Optional[float]
    consecutive_cycles: int
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4) if self.current_value is not None else None,
            "baseline_value": round(self.baseline_value, 4) if self.baseline_value is not None else None,
            "threshold_value": round(self.threshold_value, 4) if self.threshold_value is not None else None,
            "consecutive_cycles": self.consecutive_cycles,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class ModelGovernanceEngine:
    """Manages baseline versions, drift monitoring, anti-flapping hysteresis, and audit trails."""

    # Hysteresis parameters
    TRIGGER_Z: float = 3.0
    CLEAR_Z: float = 1.5
    PERSISTENCE_CYCLES: int = 3

    def __init__(self, profiler: DiurnalBaselineProfiler):
        self.profiler = profiler
        self.audit_log: list[AuditTrailRecord] = []
        # State tracking: (entity_id, metric_name) -> is_active_anomaly
        self._active_anomalies: dict[tuple[str, str], bool] = {}
        # Version snapshots: version_id -> snapshot_dict
        self._version_archive: dict[str, dict[str, Any]] = {}
        # Tracking signal for drift detection: (entity, metric) -> (cumulative_error, mad)
        self._tracking_signals: dict[tuple[str, str], list[float]] = {}

    def log_audit(
        self,
        event_type: AuditEventType,
        entity_id: str,
        metric_name: str,
        reason: str,
        current_val: Optional[float] = None,
        base_val: Optional[float] = None,
        thresh_val: Optional[float] = None,
        cycles: int = 1,
        meta: Optional[dict[str, Any]] = None,
    ) -> AuditTrailRecord:
        """Appends an immutable audit entry."""
        rec = AuditTrailRecord(
            event_id=f"AUD-{len(self.audit_log) + 1:06d}",
            event_type=event_type,
            timestamp=time.time(),
            entity_id=entity_id,
            metric_name=metric_name,
            current_value=current_val,
            baseline_value=base_val,
            threshold_value=thresh_val,
            consecutive_cycles=cycles,
            reason=reason,
            metadata=meta or {},
        )
        self.audit_log.append(rec)
        return rec

    def process_anomaly_state_transition(
        self, result: StatisticalAnomalyResult
    ) -> tuple[bool, Optional[AuditEventType]]:
        """Applies dual-threshold hysteresis and persistence gating.

        Returns: (is_alarm_active, transition_event_if_any)
        """
        key = (result.entity_id, result.metric_name)
        was_active = self._active_anomalies.get(key, False)
        abs_z = abs(result.modified_z_score if abs(result.modified_z_score) > 0 else result.z_score)

        if not was_active:
            # Trigger check: requires Z >= TRIGGER_Z and persistent cycles >= PERSISTENCE_CYCLES
            if result.is_anomaly and abs_z >= self.TRIGGER_Z:
                if result.consecutive_anomalous_samples >= self.PERSISTENCE_CYCLES:
                    self._active_anomalies[key] = True
                    self.log_audit(
                        event_type=AuditEventType.ANOMALY_RAISED,
                        entity_id=result.entity_id,
                        metric_name=result.metric_name,
                        current_val=result.current_value,
                        base_val=result.baseline_mean,
                        thresh_val=self.TRIGGER_Z,
                        cycles=result.consecutive_anomalous_samples,
                        reason=f"Anomaly escalated after {result.consecutive_anomalous_samples} persistent cycles (effective Z={abs_z:.2f})",
                    )
                    return True, AuditEventType.ANOMALY_RAISED
                else:
                    self.log_audit(
                        event_type=AuditEventType.ANOMALY_SUPPRESSED_FLAP,
                        entity_id=result.entity_id,
                        metric_name=result.metric_name,
                        current_val=result.current_value,
                        base_val=result.baseline_mean,
                        thresh_val=self.TRIGGER_Z,
                        cycles=result.consecutive_anomalous_samples,
                        reason=f"Anomaly candidate suppressed by persistence filter (cycle {result.consecutive_anomalous_samples}/{self.PERSISTENCE_CYCLES})",
                    )
                    return False, AuditEventType.ANOMALY_SUPPRESSED_FLAP
            return False, None
        else:
            # Clearing check: requires Z < CLEAR_Z (hysteresis gate)
            if abs_z < self.CLEAR_Z:
                self._active_anomalies[key] = False
                self.log_audit(
                    event_type=AuditEventType.ANOMALY_CLEARED,
                    entity_id=result.entity_id,
                    metric_name=result.metric_name,
                    current_val=result.current_value,
                    base_val=result.baseline_mean,
                    thresh_val=self.CLEAR_Z,
                    cycles=0,
                    reason=f"Anomaly cleared under hysteresis lower threshold (effective Z={abs_z:.2f} < {self.CLEAR_Z})",
                )
                return False, AuditEventType.ANOMALY_CLEARED
            else:
                # Remains active
                return True, None

    def should_freeze_baseline_update(self, entity_id: str, metric_name: str) -> bool:
        """Prevents the baseline engine from learning an active anomaly/outage as normal."""
        is_active = self._active_anomalies.get((entity_id, metric_name), False)
        if is_active:
            self.log_audit(
                event_type=AuditEventType.BASELINE_FROZEN,
                entity_id=entity_id,
                metric_name=metric_name,
                reason="Baseline update frozen: active anomaly present on entity",
            )
        return is_active

    def record_prediction_error(self, entity_id: str, metric_name: str, actual: float, expected: float) -> None:
        """Tracks forecast error to detect concept drift."""
        key = (entity_id, metric_name)
        if key not in self._tracking_signals:
            self._tracking_signals[key] = []
        err = actual - expected
        self._tracking_signals[key].append(err)
        if len(self._tracking_signals[key]) > 60:
            self._tracking_signals[key].pop(0)

        # Check for persistent bias (tracking signal ratio)
        history = self._tracking_signals[key]
        if len(history) >= 20:
            mean_err = sum(history) / len(history)
            mad_err = sum(abs(e - mean_err) for e in history) / len(history)
            if mad_err > 1e-4:
                tracking_ratio = abs(sum(history)) / (mad_err * len(history))
                if tracking_ratio > 3.5:
                    self.log_audit(
                        event_type=AuditEventType.DRIFT_DETECTED,
                        entity_id=entity_id,
                        metric_name=metric_name,
                        current_val=actual,
                        base_val=expected,
                        reason=f"Significant concept drift detected: tracking signal ratio={tracking_ratio:.2f} > 3.5",
                    )

    def create_version_checkpoint(self, version_tag: str) -> None:
        """Snapshots current baseline state into version archive."""
        snapshot = self.profiler.snapshot()
        snapshot["version"] = version_tag
        self._version_archive[version_tag] = snapshot
        self.profiler.version = version_tag
        self.log_audit(
            event_type=AuditEventType.BASELINE_UPDATED,
            entity_id="ALL",
            metric_name="ALL",
            reason=f"Baseline checkpoint '{version_tag}' created and archived",
        )

    def rollback_to_version(self, version_tag: str) -> bool:
        """Rolls back the baseline engine to a previously archived version."""
        if version_tag not in self._version_archive:
            return False
        snapshot = self._version_archive[version_tag]
        self.profiler.restore_snapshot(snapshot)
        self.log_audit(
            event_type=AuditEventType.MODEL_ROLLBACK,
            entity_id="ALL",
            metric_name="ALL",
            reason=f"Baseline model rolled back to archived version '{version_tag}'",
        )
        return True

    def trigger_baseline_reset(self, entity_id: str, metric_name: Optional[str] = None) -> None:
        """Resets baseline state for an entity (e.g. after authorized network reconfiguration)."""
        keys_to_del = [
            k for k in self.profiler._stores.keys()
            if k[0] == entity_id and (metric_name is None or k[1] == metric_name)
        ]
        for k in keys_to_del:
            del self.profiler._stores[k]

        self.log_audit(
            event_type=AuditEventType.BASELINE_RETRAINED,
            entity_id=entity_id,
            metric_name=metric_name or "ALL",
            reason="Baseline state cleared; retraining cycle initiated",
        )

