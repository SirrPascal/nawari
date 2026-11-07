"""
Nawari Phase 8 — Incident Lifecycle & State Machine Controller (Workstream 8D)
Enforces the 9-stage lifecycle, flapping prevention, and SLA escalation tracking.
"""

from __future__ import annotations

import time
from typing import Optional

from services.incidents.models import (
    Incident,
    IncidentStage,
    Severity,
)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""
    pass


class IncidentLifecycleController:
    MIN_NOMINAL_CYCLES_FOR_RECOVERY: int = 3
    ESCALATION_CRITICAL_SECONDS: float = 15.0 * 60.0  # 15 minutes
    ESCALATION_HIGH_SECONDS: float = 30.0 * 60.0      # 30 minutes

    # Permitted stage transitions
    VALID_TRANSITIONS: dict[IncidentStage, set[IncidentStage]] = {
        IncidentStage.DETECTED: {IncidentStage.CREATED},
        IncidentStage.CREATED: {IncidentStage.ENRICHED, IncidentStage.CLASSIFIED, IncidentStage.ACKNOWLEDGED},
        IncidentStage.ENRICHED: {IncidentStage.CLASSIFIED, IncidentStage.ACKNOWLEDGED},
        IncidentStage.CLASSIFIED: {IncidentStage.ACKNOWLEDGED, IncidentStage.INVESTIGATING},
        IncidentStage.ACKNOWLEDGED: {IncidentStage.INVESTIGATING, IncidentStage.RECOVERING},
        IncidentStage.INVESTIGATING: {IncidentStage.RECOVERING, IncidentStage.ACKNOWLEDGED},
        IncidentStage.RECOVERING: {IncidentStage.RESOLVED, IncidentStage.INVESTIGATING},
        IncidentStage.RESOLVED: {IncidentStage.CLOSED, IncidentStage.INVESTIGATING},
        IncidentStage.CLOSED: set(),  # Terminal state
    }

    @classmethod
    def transition_to(
        cls,
        incident: Incident,
        target_stage: IncidentStage,
        actor: Optional[str] = None,
        force: bool = False,
    ) -> None:
        now = time.time()

        if not force and target_stage not in cls.VALID_TRANSITIONS.get(incident.status, set()):
            raise InvalidStateTransitionError(
                f"Cannot transition incident {incident.incident_id} from {incident.status.value} to {target_stage.value}"
            )

        # Validation rules per target stage
        if target_stage == IncidentStage.ACKNOWLEDGED:
            incident.acknowledged_at = now
            incident.acknowledged_by = actor or "operator"

        elif target_stage == IncidentStage.RECOVERING:
            if incident.recovery_started_at is None:
                incident.recovery_started_at = now

        elif target_stage == IncidentStage.RESOLVED:
            if not force and incident.nominal_cycles < cls.MIN_NOMINAL_CYCLES_FOR_RECOVERY:
                raise InvalidStateTransitionError(
                    f"Incident {incident.incident_id} cannot resolve: requires at least "
                    f"{cls.MIN_NOMINAL_CYCLES_FOR_RECOVERY} nominal verification cycles (current: {incident.nominal_cycles})"
                )
            incident.resolved_at = now

        elif target_stage == IncidentStage.CLOSED:
            incident.closed_at = now
            incident.mttr_seconds = incident.closed_at - incident.created_at

        incident.status = target_stage
        incident.updated_at = now

    @classmethod
    def record_nominal_cycle(
        cls,
        incident: Incident,
        telemetry_timestamp: Optional[float] = None,
        telemetry_status: str = "NOMINAL",
        max_staleness_seconds: float = 120.0,
    ) -> int:
        """
        Records a nominal monitoring cycle during recovery.
        Enforces that missing, silent, or stale telemetry cannot be interpreted as recovery.
        Automatically transitions to RESOLVED once minimum required nominal cycles are reached.
        """
        now = time.time()

        # Telemetry Freshness & Evidence Invariant:
        # Missing or unconfirmed telemetry CANNOT count as recovery!
        if telemetry_status in ("STALE", "NO_DATA", "UNREACHABLE", "UNKNOWN", "DEGRADED"):
            incident.nominal_cycles = 0
            incident.updated_at = now
            return 0

        if telemetry_timestamp is not None:
            age = abs(now - telemetry_timestamp)
            if age > max_staleness_seconds:
                incident.nominal_cycles = 0
                incident.updated_at = now
                return 0

        incident.nominal_cycles += 1
        incident.updated_at = now

        if incident.status == IncidentStage.RECOVERING and incident.nominal_cycles >= cls.MIN_NOMINAL_CYCLES_FOR_RECOVERY:
            cls.transition_to(incident, IncidentStage.RESOLVED)

        return incident.nominal_cycles

    @classmethod
    def record_degradation(cls, incident: Incident, reason: str = "") -> None:
        """
        Handles flapping or recurring degradation while in RECOVERING or RESOLVED stage.
        Resets nominal cycles and forces status back to INVESTIGATING.
        """
        now = time.time()
        incident.nominal_cycles = 0
        incident.updated_at = now
        incident.recovery_started_at = None

        if incident.status in (IncidentStage.RECOVERING, IncidentStage.RESOLVED):
            incident.status = IncidentStage.INVESTIGATING

    @classmethod
    def evaluate_escalation(cls, incident: Incident) -> tuple[bool, str]:
        """
        Determines whether the incident is in an unacknowledged breach window.
        Returns: (needs_escalation, reason)
        """
        if incident.status in (IncidentStage.ACKNOWLEDGED, IncidentStage.RESOLVED, IncidentStage.CLOSED):
            return False, "Acknowledged or resolved"

        elapsed = time.time() - incident.created_at

        if incident.severity == Severity.CRITICAL and elapsed > cls.ESCALATION_CRITICAL_SECONDS:
            return True, f"CRITICAL incident unacknowledged for {elapsed / 60.0:.1f}m (>15m SLA)"

        if incident.severity == Severity.HIGH and elapsed > cls.ESCALATION_HIGH_SECONDS:
            return True, f"HIGH incident unacknowledged for {elapsed / 60.0:.1f}m (>30m SLA)"

        return False, "Within acceptable response window"
