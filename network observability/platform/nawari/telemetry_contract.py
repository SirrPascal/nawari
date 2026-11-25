"""Nawari Telemetry Accuracy and Evidence Provenance Data Contract.

Enforces RFC 2681 (Round-trip Delay), RFC 1812 (Router Requirements), and
strict measurement provenance across all Nawari telemetry systems.

Rules:
1. Measured RTT is monotonic elapsed time (t_reply - t_send).
2. Timeouts contribute strictly to packet loss; RTT is None (unavailable), never 0.0ms.
3. Protocol distinction:
   - ICMP RTT: Layer 3 packet bounce.
   - TCP Connect: Layer 4 SYN/SYN-ACK handshake.
   - DNS Lookup: Application-layer resolver query time.
   - HTTP/HTTPS: Layer 7 multi-phase timing (DNS, Connect, TLS, TTFB, Transfer, Total).
4. Four canonical evidence categories:
   - OBSERVED: Directly measured telemetry.
   - SUPPORTED_INFERENCE: Derived from multi-node correlated facts.
   - CANDIDATE_HYPOTHESIS: Plausible candidate under evaluation.
   - INCONCLUSIVE: Insufficient telemetry or unmonitored path segment.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import time
from typing import Any, Dict, List, Optional


class EvidenceCategory(str, enum.Enum):
    OBSERVED = "observed"
    SUPPORTED_INFERENCE = "supported_inference"
    CANDIDATE_HYPOTHESIS = "candidate_hypothesis"
    INCONCLUSIVE = "inconclusive"


class MeasurementState(str, enum.Enum):
    """Explicit canonical measurement and collection health states.
    
    These represent evidence and telemetry availability, NOT operational service health.
    """
    MEASURED_FRESH = "MEASURED_FRESH"
    MEASURED_STALE = "MEASURED_STALE"
    NO_DATA = "NO_DATA"
    SOURCE_UNREACHABLE = "SOURCE_UNREACHABLE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    COLLECTION_ERROR = "COLLECTION_ERROR"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SYNTHETIC = "SYNTHETIC"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class OperationalHealth(str, enum.Enum):
    """Operational health of an observed service or infrastructure component."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass
class SampleDistribution:
    """Statistical distribution of multi-sample probe measurements."""
    samples_sent: int
    samples_received: int
    packet_loss_pct: float
    min_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    median_ms: Optional[float] = None
    max_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    std_dev_ms: Optional[float] = None
    raw_samples: List[float] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples_sent": self.samples_sent,
            "samples_received": self.samples_received,
            "packet_loss_pct": self.packet_loss_pct,
            "min_ms": self.min_ms,
            "mean_ms": self.mean_ms,
            "median_ms": self.median_ms,
            "max_ms": self.max_ms,
            "p95_ms": self.p95_ms,
            "std_dev_ms": self.std_dev_ms,
            "raw_samples": self.raw_samples,
        }


def calculate_sample_distribution(samples: List[float], sent: int) -> SampleDistribution:
    """Computes exact min, mean, median, max, p95, std_dev, and packet loss ratio.
    
    RFC 2681 compliance: If 0 samples received, all latency distribution fields
    are None (unavailable), and packet_loss_pct is 100.0%.
    """
    total_sent = max(1, sent)
    valid_samples = [float(s) for s in samples if s is not None and s >= 0.0]
    received = len(valid_samples)

    if received == 0:
        return SampleDistribution(
            samples_sent=total_sent,
            samples_received=0,
            packet_loss_pct=100.0,
            min_ms=None,
            mean_ms=None,
            median_ms=None,
            max_ms=None,
            p95_ms=None,
            std_dev_ms=None,
            raw_samples=[],
        )

    loss_pct = round(((total_sent - received) / total_sent) * 100.0, 2)
    sorted_samples = sorted(valid_samples)
    min_ms = round(sorted_samples[0], 2)
    max_ms = round(sorted_samples[-1], 2)
    mean_ms = round(sum(sorted_samples) / received, 2)

    # True median calculation
    if received % 2 == 1:
        median_ms = round(sorted_samples[received // 2], 2)
    else:
        mid = received // 2
        median_ms = round((sorted_samples[mid - 1] + sorted_samples[mid]) / 2.0, 2)

    # 95th Percentile calculation
    p95_idx = int(math.ceil(0.95 * received)) - 1
    p95_idx = max(0, min(received - 1, p95_idx))
    p95_ms = round(sorted_samples[p95_idx], 2)

    # Sample standard deviation
    if received > 1:
        variance = sum((x - mean_ms) ** 2 for x in sorted_samples) / (received - 1)
        std_dev_ms = round(math.sqrt(max(0.0, variance)), 2)
    else:
        std_dev_ms = 0.0

    return SampleDistribution(
        samples_sent=total_sent,
        samples_received=received,
        packet_loss_pct=loss_pct,
        min_ms=min_ms,
        mean_ms=mean_ms,
        median_ms=median_ms,
        max_ms=max_ms,
        p95_ms=p95_ms,
        std_dev_ms=std_dev_ms,
        raw_samples=valid_samples,
    )


@dataclasses.dataclass
class MeasurementRecord:
    """Unified, strongly-typed Measurement and Evidence Provenance Record."""
    metric_name: str
    value: Optional[float]
    unit: str
    source_system: str
    source_agent_id: str
    destination: Optional[str] = None
    destination_type: Optional[str] = None  # gateway, internet, saas, router, switchport, local
    protocol: str = "ICMP"
    test_run_id: Optional[str] = None
    distribution: Optional[SampleDistribution] = None
    evidence_category: str = EvidenceCategory.OBSERVED.value
    quality: str = "measured"  # measured, inferred, stale, counter_reset, timeout
    measurement_state: str = MeasurementState.MEASURED_FRESH.value
    operational_health: str = OperationalHealth.HEALTHY.value
    freshness_sec: float = 0.0
    observed_at: float = dataclasses.field(default_factory=time.time)
    raw_evidence_ref: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "source_system": self.source_system,
            "source_agent_id": self.source_agent_id,
            "destination": self.destination,
            "destination_type": self.destination_type,
            "protocol": self.protocol,
            "test_run_id": self.test_run_id,
            "distribution": self.distribution.to_dict() if self.distribution else None,
            "evidence_category": self.evidence_category,
            "quality": self.quality,
            "measurement_state": self.measurement_state,
            "operational_health": self.operational_health,
            "freshness_sec": round(self.freshness_sec, 1),
            "observed_at": self.observed_at,
            "raw_evidence_ref": self.raw_evidence_ref or {},
        }

