"""Dynamic Multi-Seasonal Baselines & Temporal Profiling Engine for Nawari.

Computes online streaming mean/variance via Welford's algorithm and outlier-resistant
dispersion via Median Absolute Deviation (MAD) across independent diurnal and weekly buckets.
Strictly isolates sample counts per temporal bucket and enforces cold-start gating (N >= 30).
"""

from __future__ import annotations

import datetime
import math
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from services.analytics.telemetry_foundation import TelemetryObservation


class DayType(str, Enum):
    WEEKDAY = "WEEKDAY"
    WEEKEND = "WEEKEND"


@dataclass
class WelfordStats:
    """Exact online single-pass mean and variance calculator using Welford's algorithm."""

    count: int = 0
    mean: float = 0.0
    M2: float = 0.0

    def update(self, x: float) -> None:
        """Update online statistics with a new scalar observation."""
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.M2 += delta * delta2

    @property
    def sample_variance(self) -> float:
        """Computes unbiased sample variance (Bessel's correction)."""
        if self.count < 2:
            return 0.0
        return self.M2 / (self.count - 1)

    @property
    def standard_deviation(self) -> float:
        """Computes sample standard deviation."""
        return math.sqrt(max(0.0, self.sample_variance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "std_dev": round(self.standard_deviation, 4),
            "sample_variance": round(self.sample_variance, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WelfordStats:
        ws = cls()
        ws.count = int(data.get("count", 0))
        ws.mean = float(data.get("mean", 0.0))
        var = float(data.get("sample_variance", 0.0))
        ws.M2 = var * (ws.count - 1) if ws.count > 1 else 0.0
        return ws


@dataclass
class RobustStats:
    """Outlier-resistant dispersion metrics using rolling window MAD and percentiles."""

    window_size: int = 120
    samples: list[float] = field(default_factory=list)

    def add(self, x: float) -> None:
        self.samples.append(x)
        if len(self.samples) > self.window_size:
            self.samples.pop(0)

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def median(self) -> float:
        if not self.samples:
            return 0.0
        s = sorted(self.samples)
        n = len(s)
        mid = n // 2
        if n % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2.0

    @property
    def mad(self) -> float:
        """Median Absolute Deviation (MAD = median(|x - median(X)|))."""
        if not self.samples:
            return 0.0
        med = self.median
        deviations = sorted(abs(x - med) for x in self.samples)
        n = len(deviations)
        mid = n // 2
        if n % 2 == 1:
            return deviations[mid]
        return (deviations[mid - 1] + deviations[mid]) / 2.0

    def percentile(self, p: float) -> float:
        """Computes the p-th percentile (0.0 to 100.0)."""
        if not self.samples:
            return 0.0
        s = sorted(self.samples)
        k = (len(s) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return s[int(k)]
        d0 = s[int(f)] * (c - k)
        d1 = s[int(c)] * (k - f)
        return d0 + d1


@dataclass
class BaselineProfile:
    """Historical operational baseline for a specific time bucket."""

    entity_id: str
    metric_name: str
    day_type: str  # "WEEKDAY" or "WEEKEND"
    bucket_index: int  # e.g. hour 0..23 or 15m slot 0..95
    granularity: str  # "HOURLY" or "15MIN"
    sample_count: int
    mean: float
    std_dev: float
    median: float
    mad: float
    p10: float
    p90: float
    is_valid: bool = True
    status: str = "VALID"
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)

    def upper_bound(self, sigma_multiplier: float = 2.5) -> float:
        """Upper statistical control limit."""
        return round(self.mean + (sigma_multiplier * self.std_dev), 4)

    def lower_bound(self, sigma_multiplier: float = 2.5, min_floor: float = 0.0) -> float:
        """Lower statistical control limit, floored at min_floor."""
        val = self.mean - (sigma_multiplier * self.std_dev)
        return round(max(min_floor, val), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "day_type": self.day_type,
            "bucket_index": self.bucket_index,
            "granularity": self.granularity,
            "sample_count": self.sample_count,
            "mean": round(self.mean, 4),
            "std_dev": round(self.std_dev, 4),
            "median": round(self.median, 4),
            "mad": round(self.mad, 4),
            "p10": round(self.p10, 4),
            "p90": round(self.p90, 4),
            "is_valid": self.is_valid,
            "status": self.status,
            "version": self.version,
            "upper_bound_2_5s": self.upper_bound(2.5),
            "lower_bound_2_5s": self.lower_bound(2.5),
        }


class DiurnalBaselineProfiler:
    """Maintains multi-seasonal baselines (diurnal buckets x 2 day types).

    Refinements enforced:
    1. Sample counts are strictly independent per (entity, metric, day_type, bucket).
    2. Missing data, gaps, and maintenance flags are never counted towards baseline samples.
    3. Cold-start guard enforces N >= min_samples per bucket before declaring baseline valid.
    4. Supports profile versioning, snapshotting, and rollback.
    """

    MIN_SAMPLES_REQUIRED: int = 30

    def __init__(
        self,
        granularity: str = "HOURLY",
        min_samples: int = MIN_SAMPLES_REQUIRED,
        version: str = "1.0.0",
    ):
        if granularity not in ("HOURLY", "15MIN"):
            raise ValueError("granularity must be 'HOURLY' or '15MIN'")
        self.granularity = granularity
        self.min_samples = min_samples
        self.version = version
        # key: (entity_id, metric_name, day_type, bucket_index) -> (WelfordStats, RobustStats)
        self._stores: dict[tuple[str, str, str, int], tuple[WelfordStats, RobustStats]] = {}
        # Maintenance windows / paused entities: entity_id -> until_timestamp
        self._maintenance_windows: dict[str, float] = {}

    def set_maintenance_window(self, entity_id: str, until_timestamp: float) -> None:
        """Suppresses baseline updates for an entity during scheduled maintenance."""
        self._maintenance_windows[entity_id] = until_timestamp

    def is_under_maintenance(self, entity_id: str, timestamp: float) -> bool:
        until = self._maintenance_windows.get(entity_id, 0.0)
        return timestamp <= until

    def get_time_coords(self, timestamp: float) -> tuple[str, int]:
        """Maps epoch timestamp to day_type (WEEKDAY/WEEKEND) and bucket_index."""
        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        day_type = DayType.WEEKEND.value if dt.weekday() >= 5 else DayType.WEEKDAY.value
        if self.granularity == "HOURLY":
            bucket = dt.hour
        else:  # "15MIN"
            bucket = (dt.hour * 4) + (dt.minute // 15)
        return day_type, bucket

    def record_observation(self, obs: TelemetryObservation) -> bool:
        """Ingests an observation into its specific bucket.

        Returns True if recorded, False if rejected (missing, invalid, or under maintenance).
        """
        if not obs.is_valid or obs.value is None:
            return False

        if self.is_under_maintenance(obs.entity_id, obs.timestamp):
            return False

        # Ignore obvious poisoned or broken NaN/Inf telemetry
        if math.isnan(obs.value) or math.isinf(obs.value):
            return False

        day_type, bucket = self.get_time_coords(obs.timestamp)
        key = (obs.entity_id, obs.metric_name, day_type, bucket)

        if key not in self._stores:
            self._stores[key] = (WelfordStats(), RobustStats())

        welford, robust = self._stores[key]
        welford.update(obs.value)
        robust.add(obs.value)
        return True

    def get_baseline(
        self, entity_id: str, metric_name: str, timestamp: float
    ) -> BaselineProfile:
        """Retrieves the baseline profile for the specific temporal bucket."""
        day_type, bucket = self.get_time_coords(timestamp)
        key = (entity_id, metric_name, day_type, bucket)

        if key not in self._stores:
            return BaselineProfile(
                entity_id=entity_id,
                metric_name=metric_name,
                day_type=day_type,
                bucket_index=bucket,
                granularity=self.granularity,
                sample_count=0,
                mean=0.0,
                std_dev=0.0,
                median=0.0,
                mad=0.0,
                p10=0.0,
                p90=0.0,
                is_valid=False,
                status="INSUFFICIENT_DATA",
                version=self.version,
            )

        welford, robust = self._stores[key]
        # Strictly require N >= min_samples in THIS specific bucket
        if welford.count < self.min_samples:
            return BaselineProfile(
                entity_id=entity_id,
                metric_name=metric_name,
                day_type=day_type,
                bucket_index=bucket,
                granularity=self.granularity,
                sample_count=welford.count,
                mean=welford.mean,
                std_dev=welford.standard_deviation,
                median=robust.median,
                mad=robust.mad,
                p10=robust.percentile(10),
                p90=robust.percentile(90),
                is_valid=False,
                status="INSUFFICIENT_DATA",
                version=self.version,
            )

        return BaselineProfile(
            entity_id=entity_id,
            metric_name=metric_name,
            day_type=day_type,
            bucket_index=bucket,
            granularity=self.granularity,
            sample_count=welford.count,
            mean=welford.mean,
            std_dev=welford.standard_deviation,
            median=robust.median,
            mad=robust.mad,
            p10=robust.percentile(10),
            p90=robust.percentile(90),
            is_valid=True,
            status="VALID",
            version=self.version,
        )

    def snapshot(self) -> dict[str, Any]:
        """Creates a serializable snapshot of all baseline state for governance and rollback."""
        data: dict[str, Any] = {
            "version": self.version,
            "granularity": self.granularity,
            "min_samples": self.min_samples,
            "timestamp": time.time(),
            "stores": {},
        }
        for (ent, met, day, b_idx), (welford, robust) in self._stores.items():
            k_str = f"{ent}::{met}::{day}::{b_idx}"
            data["stores"][k_str] = {
                "welford": welford.to_dict(),
                "samples": list(robust.samples),
            }
        return data

    def restore_snapshot(self, snapshot_data: dict[str, Any]) -> None:
        """Restores baseline state from a verified snapshot."""
        self.version = snapshot_data.get("version", self.version)
        self.granularity = snapshot_data.get("granularity", self.granularity)
        self.min_samples = snapshot_data.get("min_samples", self.min_samples)
        self._stores.clear()

        stores = snapshot_data.get("stores", {})
        for k_str, s_data in stores.items():
            parts = k_str.split("::")
            if len(parts) == 4:
                ent, met, day, b_idx_s = parts
                b_idx = int(b_idx_s)
                welford = WelfordStats.from_dict(s_data.get("welford", {}))
                robust = RobustStats(samples=list(s_data.get("samples", [])))
                self._stores[(ent, met, day, b_idx)] = (welford, robust)
