"""Metric-Aware Recovery Verifier for Operational Incidents.

Enforces the Mandatory Recovery Verification Invariant:
A successful Phase 12 remediation action or self-clearing alert does NOT
automatically close an incident. Incident closure strictly requires
>= N consecutive healthy observations with source-specific telemetry freshness.

Key Safeguards:
- Freshness windows defined per telemetry source (TCP Probe: 30s, SNMP: 90s, Agent: 180s).
- Event-time validation: checks elapsed time between event capture and evaluation.
- Replayed telemetry rejection: Replayed data from outstation store-and-forward
  buffers is strictly prohibited from counting as fresh live recovery observations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TelemetrySourceType(str, Enum):
    """Categorization of monitoring sources with distinct freshness requirements."""
    SYNTHETIC_PROBE = "SYNTHETIC_PROBE" # Synthetic TCP/HTTP probe (runs every 10-15s)
    VOICE_PROBE = "VOICE_PROBE"         # Synthetic SIP/RTP test call (runs every 15-30s)
    SNMP_POLLING = "SNMP_POLLING"       # Zabbix interface SNMP polling (runs every 60s)
    ENDPOINT_AGENT = "ENDPOINT_AGENT"   # Desktop/terminal agent telemetry (runs every 120s)
    CUSTOM = "CUSTOM"


@dataclass
class TelemetrySourceProfile:
    """Freshness threshold and consecutive observation requirements per source."""
    source_type: TelemetrySourceType
    max_freshness_seconds: float
    required_consecutive_healthy: int = 3


# Standard source profiles for Kenya Airways monitoring fleet
STANDARD_SOURCE_PROFILES = {
    TelemetrySourceType.SYNTHETIC_PROBE: TelemetrySourceProfile(TelemetrySourceType.SYNTHETIC_PROBE, max_freshness_seconds=30.0, required_consecutive_healthy=3),
    TelemetrySourceType.VOICE_PROBE: TelemetrySourceProfile(TelemetrySourceType.VOICE_PROBE, max_freshness_seconds=30.0, required_consecutive_healthy=3),
    TelemetrySourceType.SNMP_POLLING: TelemetrySourceProfile(TelemetrySourceType.SNMP_POLLING, max_freshness_seconds=90.0, required_consecutive_healthy=3),
    TelemetrySourceType.ENDPOINT_AGENT: TelemetrySourceProfile(TelemetrySourceType.ENDPOINT_AGENT, max_freshness_seconds=180.0, required_consecutive_healthy=3),
}


@dataclass
class RecoveryObservation:
    """Individual telemetry observation recorded for recovery validation."""
    observation_id: str
    source_type: TelemetrySourceType
    event_timestamp: str       # ISO UTC timestamp at capture
    receipt_timestamp: str     # ISO UTC timestamp at gateway/verifier
    health_value: float        # 0.0 to 1.0 (>= 0.85 considered healthy)
    is_replayed: bool = False  # True if replayed from offline buffer
    metric_evidence: Dict[str, Any] = field(default_factory=dict)
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_healthy(self) -> bool:
        return self.health_value >= 0.85


class MetricAwareRecoveryVerifier:
    """Evaluates fresh observations to determine whether an incident can be safely resolved."""

    def __init__(self, profiles: Optional[Dict[TelemetrySourceType, TelemetrySourceProfile]] = None) -> None:
        self.profiles = profiles or STANDARD_SOURCE_PROFILES
        # incident_id -> List[RecoveryObservation]
        self._observations: Dict[str, List[RecoveryObservation]] = {}

    def record_observation(
        self,
        incident_id: str,
        observation: RecoveryObservation,
    ) -> Dict[str, Any]:
        """Record an observation and evaluate its immediate validity."""
        obs_list = self._observations.setdefault(incident_id, [])
        obs_list.append(observation)

        profile = self.profiles.get(observation.source_type, TelemetrySourceProfile(observation.source_type, 60.0, 3))
        
        # Calculate event age
        event_time = datetime.fromisoformat(observation.event_timestamp)
        now = datetime.now(timezone.utc)
        age_seconds = (now - event_time).total_seconds()
        is_fresh = age_seconds <= profile.max_freshness_seconds

        return {
            "observation_id": observation.observation_id,
            "incident_id": incident_id,
            "source_type": observation.source_type.value,
            "is_healthy": observation.is_healthy(),
            "is_replayed": observation.is_replayed,
            "age_seconds": round(age_seconds, 2),
            "is_fresh": is_fresh,
            "accepted_for_recovery": is_fresh and not observation.is_replayed and observation.is_healthy(),
        }

    def evaluate_recovery(
        self,
        incident_id: str,
        source_type: Optional[TelemetrySourceType] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify whether an incident meets the strict consecutive fresh healthy criteria."""
        obs_list = self._observations.get(incident_id, [])
        now = evaluation_time or datetime.now(timezone.utc)

        if not obs_list:
            return False, "NO_OBSERVATIONS_RECORDED", {"consecutive_healthy": 0, "required": 3}

        # Use the source type of the last observation if not specified
        primary_source = source_type or obs_list[-1].source_type
        profile = self.profiles.get(primary_source, TelemetrySourceProfile(primary_source, 60.0, 3))

        # Inspect observations in reverse chronological order
        consecutive_fresh_healthy = 0
        rejection_reasons = []

        for obs in reversed(obs_list):
            if obs.source_type != primary_source:
                continue

            # Check 1: Replayed data guard
            if obs.is_replayed:
                rejection_reasons.append(f"Observation '{obs.observation_id}' rejected: REPLAYED historical telemetry cannot prove live recovery.")
                break

            # Check 2: Freshness window guard
            event_time = datetime.fromisoformat(obs.event_timestamp)
            age_seconds = (now - event_time).total_seconds()
            if age_seconds > profile.max_freshness_seconds:
                rejection_reasons.append(f"Observation '{obs.observation_id}' rejected: STALE telemetry ({age_seconds:.1f}s > allowed {profile.max_freshness_seconds}s).")
                break

            # Check 3: Health threshold
            if not obs.is_healthy():
                rejection_reasons.append(f"Observation '{obs.observation_id}' rejected: Unhealthy state (health={obs.health_value:.2f} < 0.85).")
                break

            consecutive_fresh_healthy += 1
            if consecutive_fresh_healthy >= profile.required_consecutive_healthy:
                break

        is_recovered = consecutive_fresh_healthy >= profile.required_consecutive_healthy
        if is_recovered:
            reason = f"VERIFIED_RECOVERY: {consecutive_fresh_healthy} consecutive fresh healthy observations confirmed from {primary_source.value}."
        else:
            reason = f"INSUFFICIENT_EVIDENCE: Only {consecutive_fresh_healthy}/{profile.required_consecutive_healthy} fresh healthy observations. {'; '.join(rejection_reasons)}"

        details = {
            "incident_id": incident_id,
            "source_type": primary_source.value,
            "consecutive_fresh_healthy": consecutive_fresh_healthy,
            "required_consecutive": profile.required_consecutive_healthy,
            "max_allowed_freshness_seconds": profile.max_freshness_seconds,
            "total_observations_recorded": len(obs_list),
            "rejection_reasons": rejection_reasons,
        }

        return is_recovered, reason, details

