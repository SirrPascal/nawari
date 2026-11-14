"""Telemetry Foundation & Feature Extraction Engine for Nawari Analytics.

Standardizes heterogeneous telemetry from network devices, Avaya PBX, synthetic voice,
endpoint agents, and dynamic topology into normalized, provenance-tagged observations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DomainType(str, Enum):
    NETWORK = "NETWORK"
    VOICE_SIGNALING = "VOICE_SIGNALING"
    VOICE_MEDIA = "VOICE_MEDIA"
    ENDPOINT = "ENDPOINT"
    SYSTEM = "SYSTEM"
    TOPOLOGY = "TOPOLOGY"


class TelemetryProvenance(str, Enum):
    LIVE_SNMP = "LIVE_SNMP"
    GATEWAY_ENDPOINT = "GATEWAY_ENDPOINT"
    ASTERISK_AMI = "ASTERISK_AMI"
    AVAYA_SBCE = "AVAYA_SBCE"
    MOCK_FIXTURE = "MOCK_FIXTURE"
    SIMULATED_PROVENANCE = "SIMULATED_PROVENANCE"


@dataclass(frozen=True)
class TelemetryObservation:
    """Normalized, immutable telemetry observation record."""

    entity_id: str
    metric_name: str
    value: Optional[float]
    unit: str
    timestamp: float
    domain: DomainType
    provenance: TelemetryProvenance
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Returns True if value is not None and not NaN or Infinite."""
        if self.value is None:
            return False
        return not (math.isnan(self.value) or math.isinf(self.value))


@dataclass
class AlignedBucket:
    """Represents a discrete time bucket with aggregated/sampled metrics."""

    bucket_start: float
    bucket_end: float
    sample_count: int
    mean_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    is_missing: bool = False


class TimeBucketAligner:
    """Aligns irregular timestamped telemetry into uniform discrete time intervals.

    Never invents or zero-fills data when evidence is missing; explicit gap tagging is enforced.
    """

    def __init__(self, bucket_size_seconds: float = 60.0):
        if bucket_size_seconds <= 0:
            raise ValueError("bucket_size_seconds must be positive")
        self.bucket_size = bucket_size_seconds

    def align(
        self,
        observations: list[TelemetryObservation],
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> list[AlignedBucket]:
        """Aligns a list of observations for a single metric into uniform time buckets."""
        valid_obs = [obs for obs in observations if obs.is_valid]
        if not valid_obs and start_time is None:
            return []

        t_min = start_time if start_time is not None else min(obs.timestamp for obs in valid_obs)
        t_max = end_time if end_time is not None else max(obs.timestamp for obs in valid_obs)

        # Snap to bucket boundaries
        first_bucket = math.floor(t_min / self.bucket_size) * self.bucket_size
        last_bucket = math.ceil(t_max / self.bucket_size) * self.bucket_size
        if last_bucket <= first_bucket:
            last_bucket = first_bucket + self.bucket_size

        # Group observations by bucket
        buckets_data: dict[float, list[float]] = {}
        curr = first_bucket
        while curr < last_bucket:
            buckets_data[curr] = []
            curr += self.bucket_size

        for obs in valid_obs:
            b_key = math.floor(obs.timestamp / self.bucket_size) * self.bucket_size
            if b_key in buckets_data and obs.value is not None:
                buckets_data[b_key].append(obs.value)

        # Construct aligned output series
        result: list[AlignedBucket] = []
        for b_start in sorted(buckets_data.keys()):
            values = buckets_data[b_start]
            b_end = b_start + self.bucket_size
            if values:
                result.append(
                    AlignedBucket(
                        bucket_start=b_start,
                        bucket_end=b_end,
                        sample_count=len(values),
                        mean_value=round(sum(values) / len(values), 4),
                        min_value=min(values),
                        max_value=max(values),
                        is_missing=False,
                    )
                )
            else:
                result.append(
                    AlignedBucket(
                        bucket_start=b_start,
                        bucket_end=b_end,
                        sample_count=0,
                        mean_value=None,
                        min_value=None,
                        max_value=None,
                        is_missing=True,
                    )
                )

        return result


class FeatureExtractor:
    """Normalizes multi-domain raw records into TelemetryObservation format."""

    @staticmethod
    def extract_from_network_interface(
        device_id: str,
        interface_name: str,
        metrics: dict[str, Any],
        timestamp: float,
        provenance: TelemetryProvenance = TelemetryProvenance.LIVE_SNMP,
    ) -> list[TelemetryObservation]:
        """Extracts normalized interface metrics (in_octets, out_octets, in_discards, in_errors)."""
        observations: list[TelemetryObservation] = []
        mapping = [
            ("ifInOctetsRate", "bps"),
            ("ifOutOctetsRate", "bps"),
            ("ifInDiscardsRate", "pps"),
            ("ifOutDiscardsRate", "pps"),
            ("ifInErrorsRate", "pps"),
            ("ifOutErrorsRate", "pps"),
            ("bandwidth_utilization_pct", "%"),
        ]

        entity_id = f"{device_id}::{interface_name}"
        for metric_key, unit in mapping:
            val = metrics.get(metric_key)
            if val is not None:
                try:
                    f_val = float(val)
                except (ValueError, TypeError):
                    f_val = None
                observations.append(
                    TelemetryObservation(
                        entity_id=entity_id,
                        metric_name=metric_key,
                        value=f_val,
                        unit=unit,
                        timestamp=timestamp,
                        domain=DomainType.NETWORK,
                        provenance=provenance,
                        metadata={"device_id": device_id, "interface": interface_name},
                    )
                )
        return observations

    @staticmethod
    def extract_from_voice_session(
        call_id: str,
        trunk_name: str,
        metrics: dict[str, Any],
        timestamp: float,
        provenance: TelemetryProvenance = TelemetryProvenance.ASTERISK_AMI,
    ) -> list[TelemetryObservation]:
        """Extracts voice signaling and media metrics (PDD, TTA, MOS, jitter, burst_loss)."""
        observations: list[TelemetryObservation] = []
        signaling_metrics = [
            ("post_dial_delay_ms", "ms"),
            ("time_to_alerting_ms", "ms"),
            ("time_to_answer_ms", "ms"),
            ("teardown_duration_ms", "ms"),
        ]
        media_metrics = [
            ("mos", "score"),
            ("r_factor", "rating"),
            ("jitter_ms", "ms"),
            ("packet_loss_pct", "%"),
            ("burst_loss_density_pct", "%"),
            ("jitter_buffer_discard_pct", "%"),
        ]

        entity_id = f"voice_trunk::{trunk_name}"
        for key, unit in signaling_metrics:
            val = metrics.get(key)
            if val is not None:
                observations.append(
                    TelemetryObservation(
                        entity_id=entity_id,
                        metric_name=key,
                        value=float(val),
                        unit=unit,
                        timestamp=timestamp,
                        domain=DomainType.VOICE_SIGNALING,
                        provenance=provenance,
                        metadata={"call_id": call_id, "trunk": trunk_name},
                    )
                )

        for key, unit in media_metrics:
            val = metrics.get(key)
            if val is not None:
                observations.append(
                    TelemetryObservation(
                        entity_id=entity_id,
                        metric_name=key,
                        value=float(val),
                        unit=unit,
                        timestamp=timestamp,
                        domain=DomainType.VOICE_MEDIA,
                        provenance=provenance,
                        metadata={"call_id": call_id, "trunk": trunk_name},
                    )
                )

        return observations

    @staticmethod
    def extract_from_avaya_sbce(
        sbce_id: str,
        metrics: dict[str, Any],
        timestamp: float,
        provenance: TelemetryProvenance = TelemetryProvenance.AVAYA_SBCE,
    ) -> list[TelemetryObservation]:
        """Extracts SBCE session capacity and resource metrics."""
        observations: list[TelemetryObservation] = []
        mapping = [
            ("active_sessions", "sessions"),
            ("session_utilization_pct", "%"),
            ("cpu_utilization_pct", "%"),
            ("memory_utilization_pct", "%"),
            ("cps_rate", "cps"),
        ]
        for key, unit in mapping:
            val = metrics.get(key)
            if val is not None:
                observations.append(
                    TelemetryObservation(
                        entity_id=sbce_id,
                        metric_name=key,
                        value=float(val),
                        unit=unit,
                        timestamp=timestamp,
                        domain=DomainType.SYSTEM,
                        provenance=provenance,
                        metadata={"sbce_id": sbce_id},
                    )
                )
        return observations

