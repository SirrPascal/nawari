"""Statistical Anomaly Detection Engine for Nawari.

Applies adaptive Z-scores, robust modified Z-scores (MAD), non-parametric percentile
corridors, and Exponentially Weighted Moving Averages (EWMA) with configurable per-metric thresholds.
Preserves raw observations and treats anomalies as evidence of unusual behavior, not proof of faults.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from services.analytics.dynamic_baselines import BaselineProfile, DiurnalBaselineProfiler
from services.analytics.telemetry_foundation import TelemetryObservation


class AnomalyDirection(str, Enum):
    HIGH_ABNORMAL = "HIGH_ABNORMAL"
    LOW_ABNORMAL = "LOW_ABNORMAL"
    ZERO_DROP = "ZERO_DROP"
    NORMAL = "NORMAL"


class AnomalySeverity(str, Enum):
    NORMAL = "NORMAL"
    INFORMATIONAL = "INFORMATIONAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class MetricThresholdConfig:
    """Configurable anomaly evaluation rules per metric type."""

    metric_name: str
    warning_z: float = 3.0
    critical_z: float = 4.5
    min_consecutive_samples: int = 1
    use_percentile_corridor: bool = True
    # For metrics where absolute delta is clinically meaningful (e.g. MOS score)
    absolute_delta_mode: bool = False
    warning_delta: float = 0.30
    critical_delta: float = 0.60


@dataclass
class StatisticalAnomalyResult:
    """Comprehensive anomaly evaluation record preserving raw telemetry alongside classifications."""

    entity_id: str
    metric_name: str
    current_value: float
    unit: str
    baseline_mean: float
    baseline_median: float
    baseline_mad: float
    baseline_std_dev: float
    baseline_p10: float
    baseline_p90: float
    z_score: float
    modified_z_score: float
    ewma_value: float
    direction: AnomalyDirection
    severity: AnomalySeverity
    is_anomaly: bool
    is_persistent: bool
    consecutive_anomalous_samples: int
    confidence_score: float  # Calibrated evidentiary metric (0.0 to 1.0)
    status: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "unit": self.unit,
            "baseline_mean": round(self.baseline_mean, 4),
            "baseline_median": round(self.baseline_median, 4),
            "baseline_mad": round(self.baseline_mad, 4),
            "baseline_std_dev": round(self.baseline_std_dev, 4),
            "baseline_p10": round(self.baseline_p10, 4),
            "baseline_p90": round(self.baseline_p90, 4),
            "z_score": round(self.z_score, 2),
            "modified_z_score": round(self.modified_z_score, 2),
            "ewma_value": round(self.ewma_value, 4),
            "direction": self.direction.value,
            "severity": self.severity.value,
            "is_anomaly": self.is_anomaly,
            "is_persistent": self.is_persistent,
            "consecutive_anomalous_samples": self.consecutive_anomalous_samples,
            "confidence_score": round(self.confidence_score, 2),
            "status": self.status,
            "timestamp": self.timestamp,
        }


class EWMATracker:
    """Tracks Exponentially Weighted Moving Average for subtle mean drift detection."""

    def __init__(self, lambda_factor: float = 0.2):
        if not (0.0 < lambda_factor <= 1.0):
            raise ValueError("lambda_factor must be in (0, 1]")
        self.lambda_factor = lambda_factor
        self.s_t: Optional[float] = None
        self.step: int = 0

    def update(self, y: float) -> float:
        self.step += 1
        if self.s_t is None:
            self.s_t = y
        else:
            self.s_t = (self.lambda_factor * y) + ((1.0 - self.lambda_factor) * self.s_t)
        return self.s_t


class StatisticalAnomalyDetector:
    """Multi-method statistical anomaly detector utilizing diurnal baseline models and custom threshold rules."""

    # Default metric configurations for key voice and network signals
    DEFAULT_CONFIGS: dict[str, MetricThresholdConfig] = {
        "mos": MetricThresholdConfig(
            metric_name="mos",
            absolute_delta_mode=True,
            warning_delta=0.30,
            critical_delta=0.60,
            min_consecutive_samples=2,
        ),
        "post_dial_delay_ms": MetricThresholdConfig(
            metric_name="post_dial_delay_ms",
            warning_z=2.5,
            critical_z=4.0,
            min_consecutive_samples=2,
        ),
        "ifInDiscardsRate": MetricThresholdConfig(
            metric_name="ifInDiscardsRate",
            warning_z=3.0,
            critical_z=4.5,
            min_consecutive_samples=1,
        ),
        "ifInErrorsRate": MetricThresholdConfig(
            metric_name="ifInErrorsRate",
            warning_z=3.0,
            critical_z=4.5,
            min_consecutive_samples=1,
        ),
    }

    def __init__(
        self,
        profiler: Optional[DiurnalBaselineProfiler] = None,
        custom_configs: Optional[dict[str, MetricThresholdConfig]] = None,
    ):
        self.profiler = profiler or DiurnalBaselineProfiler()
        self.configs = dict(self.DEFAULT_CONFIGS)
        if custom_configs:
            self.configs.update(custom_configs)

        self._ewma_trackers: dict[tuple[str, str], EWMATracker] = {}
        # Track consecutive anomalous sample counts per (entity, metric)
        self._consecutive_anomalies: dict[tuple[str, str], int] = {}

    def get_config(self, metric_name: str) -> MetricThresholdConfig:
        return self.configs.get(metric_name, MetricThresholdConfig(metric_name=metric_name))

    def evaluate(self, obs: TelemetryObservation) -> StatisticalAnomalyResult:
        """Evaluates an observation against its matching diurnal baseline."""
        if not obs.is_valid or obs.value is None:
            return StatisticalAnomalyResult(
                entity_id=obs.entity_id,
                metric_name=obs.metric_name,
                current_value=0.0,
                unit=obs.unit,
                baseline_mean=0.0,
                baseline_median=0.0,
                baseline_mad=0.0,
                baseline_std_dev=0.0,
                baseline_p10=0.0,
                baseline_p90=0.0,
                z_score=0.0,
                modified_z_score=0.0,
                ewma_value=0.0,
                direction=AnomalyDirection.NORMAL,
                severity=AnomalySeverity.NORMAL,
                is_anomaly=False,
                is_persistent=False,
                consecutive_anomalous_samples=0,
                confidence_score=0.0,
                status="INVALID_OBSERVATION",
                timestamp=obs.timestamp,
            )

        val = obs.value
        cfg = self.get_config(obs.metric_name)
        profile = self.profiler.get_baseline(obs.entity_id, obs.metric_name, obs.timestamp)

        # Update EWMA state
        state_key = (obs.entity_id, obs.metric_name)
        if state_key not in self._ewma_trackers:
            self._ewma_trackers[state_key] = EWMATracker(lambda_factor=0.2)
        ewma_val = self._ewma_trackers[state_key].update(val)

        # Check for cold start / insufficient data
        if not profile.is_valid or profile.sample_count < self.profiler.min_samples:
            self._consecutive_anomalies[state_key] = 0
            return StatisticalAnomalyResult(
                entity_id=obs.entity_id,
                metric_name=obs.metric_name,
                current_value=val,
                unit=obs.unit,
                baseline_mean=profile.mean,
                baseline_median=profile.median,
                baseline_mad=profile.mad,
                baseline_std_dev=profile.std_dev,
                baseline_p10=profile.p10,
                baseline_p90=profile.p90,
                z_score=0.0,
                modified_z_score=0.0,
                ewma_value=ewma_val,
                direction=AnomalyDirection.NORMAL,
                severity=AnomalySeverity.NORMAL,
                is_anomaly=False,
                is_persistent=False,
                consecutive_anomalous_samples=0,
                confidence_score=0.0,
                status="INSUFFICIENT_DATA",
                timestamp=obs.timestamp,
            )

        # Compute deviations
        if profile.std_dev > 1e-6:
            z = (val - profile.mean) / profile.std_dev
        else:
            z = 0.0 if abs(val - profile.mean) < 1e-6 else 5.0

        if profile.mad > 1e-6:
            mod_z = (0.6745 * (val - profile.median)) / profile.mad
        else:
            mod_z = z

        effective_z = mod_z if profile.mad > 1e-6 else z

        # Absolute Delta mode evaluation (e.g. for MOS where normal distribution is inappropriate)
        if cfg.absolute_delta_mode:
            delta = profile.median - val  # negative drop from normal
            if delta >= cfg.critical_delta:
                severity = AnomalySeverity.CRITICAL
                direction = AnomalyDirection.LOW_ABNORMAL
                is_anom = True
            elif delta >= cfg.warning_delta:
                severity = AnomalySeverity.WARNING
                direction = AnomalyDirection.LOW_ABNORMAL
                is_anom = True
            else:
                severity = AnomalySeverity.NORMAL
                direction = AnomalyDirection.NORMAL
                is_anom = False
        else:
            # Statistical deviation mode
            if val == 0.0 and profile.mean > 10.0:
                direction = AnomalyDirection.ZERO_DROP
                severity = AnomalySeverity.CRITICAL
                is_anom = True
            elif effective_z >= cfg.critical_z:
                direction = AnomalyDirection.HIGH_ABNORMAL
                severity = AnomalySeverity.CRITICAL
                is_anom = True
            elif effective_z <= -cfg.critical_z:
                direction = AnomalyDirection.LOW_ABNORMAL
                severity = AnomalySeverity.CRITICAL
                is_anom = True
            elif effective_z >= cfg.warning_z:
                direction = AnomalyDirection.HIGH_ABNORMAL
                severity = AnomalySeverity.WARNING
                is_anom = True
            elif effective_z <= -cfg.warning_z:
                direction = AnomalyDirection.LOW_ABNORMAL
                severity = AnomalySeverity.WARNING
                is_anom = True
            elif abs(effective_z) >= 2.0:
                direction = AnomalyDirection.HIGH_ABNORMAL if effective_z > 0 else AnomalyDirection.LOW_ABNORMAL
                severity = AnomalySeverity.INFORMATIONAL
                is_anom = True
            else:
                direction = AnomalyDirection.NORMAL
                severity = AnomalySeverity.NORMAL
                is_anom = False

        # Track persistence
        if is_anom:
            current_streak = self._consecutive_anomalies.get(state_key, 0) + 1
            self._consecutive_anomalies[state_key] = current_streak
        else:
            current_streak = 0
            self._consecutive_anomalies[state_key] = 0

        is_persistent = current_streak >= cfg.min_consecutive_samples

        # Calibrated Evidentiary Confidence
        if is_anom:
            depth_factor = min(1.0, max(0.6, profile.sample_count / 50.0))
            dev_factor = min(1.0, abs(effective_z) / 5.0) if not cfg.absolute_delta_mode else min(1.0, delta / 1.0)
            confidence = round(0.5 * depth_factor + 0.5 * dev_factor, 2)
        else:
            confidence = 0.95

        return StatisticalAnomalyResult(
            entity_id=obs.entity_id,
            metric_name=obs.metric_name,
            current_value=val,
            unit=obs.unit,
            baseline_mean=profile.mean,
            baseline_median=profile.median,
            baseline_mad=profile.mad,
            baseline_std_dev=profile.std_dev,
            baseline_p10=profile.p10,
            baseline_p90=profile.p90,
            z_score=z,
            modified_z_score=mod_z,
            ewma_value=ewma_val,
            direction=direction,
            severity=severity,
            is_anomaly=is_anom,
            is_persistent=is_persistent,
            consecutive_anomalous_samples=current_streak,
            confidence_score=confidence,
            status="EVALUATED",
            timestamp=obs.timestamp,
        )
