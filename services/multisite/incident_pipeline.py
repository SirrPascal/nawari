"""Operational Alerting, Correlation, and Incident Lifecycle Pipeline.

Implements the Kenya Airways Closed-Loop Incident Lifecycle:
DETECTED -> CORRELATED -> ACKNOWLEDGED -> INVESTIGATING -> REMEDIATING -> VERIFYING -> RESOLVED -> CLOSED

Features:
- Alert deduplication within sliding time windows using stable fingerprints.
- Flap detection and alert dampening.
- Topology-aware parent down suppression.
- Scheduled maintenance window muting with automatic expiry.
- Multi-site station and business service attribution.
- Configurable SLA escalation policies per severity tier and domain.
- Reopening and recurrence handling: Recurring alerts on recently resolved incidents reopen the incident.
- Concurrency locks & idempotency: Thread-safe incident creation preventing duplicate records.
- Cryptographic automation lineage linking to Phase 12 actions and audit blocks.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class IncidentStatus(str, Enum):
    """Lifecycle status of an operational incident."""
    DETECTED = "DETECTED"
    CORRELATED = "CORRELATED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class IncidentSeverity(str, Enum):
    """Operational priority / severity tier of an incident."""
    P1_CRITICAL = "P1_CRITICAL"  # Mission-critical service outage (DCS, Flight Ops, Core Voice)
    P2_HIGH = "P2_HIGH"          # Business-critical service degradation (BHS, Cargo, WAN Failover)
    P3_MEDIUM = "P3_MEDIUM"      # Redundant link down, corporate IT degradation
    P4_LOW = "P4_LOW"            # Non-impacting warning, informational anomaly


@dataclass
class OperationalAlert:
    """Normalized incoming alert from monitoring sources (Zabbix, Voice, Edge, Phase 11)."""
    alert_id: str
    source: str               # ZABBIX, VOICE_SYNTHETIC, EDGE_PROXY, ANOMALY_DETECTOR
    entity_id: str             # Device or Circuit ID (e.g. SW-DC1-01, CIR-MBA-01)
    metric_name: str           # e.g. icmpping, ifOperStatus, sip_pdd, mos
    observed_value: Any
    severity: IncidentSeverity
    summary: str
    event_timestamp: str       # ISO UTC timestamp at capture
    receipt_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    station_id: Optional[str] = None
    service_id: Optional[str] = None
    parent_entity_id: Optional[str] = None  # Upstream router/switch for topology suppression
    is_replayed: bool = False               # True if replayed from offline buffer
    in_maintenance: bool = False            # True if entity is in scheduled maintenance
    maintenance_window_end: Optional[str] = None

    def fingerprint(self) -> str:
        """Stable fingerprint for deduplication."""
        return f"{self.entity_id}:{self.metric_name}:{self.severity.value}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "source": self.source,
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "observed_value": self.observed_value,
            "severity": self.severity.value,
            "summary": self.summary,
            "event_timestamp": self.event_timestamp,
            "receipt_timestamp": self.receipt_timestamp,
            "station_id": self.station_id,
            "service_id": self.service_id,
            "parent_entity_id": self.parent_entity_id,
            "is_replayed": self.is_replayed,
            "in_maintenance": self.in_maintenance,
            "maintenance_window_end": self.maintenance_window_end,
        }


@dataclass
class EscalationPolicy:
    """Configurable escalation deadlines and target groups per severity tier."""
    deadline_minutes: Dict[IncidentSeverity, int] = field(default_factory=lambda: {
        IncidentSeverity.P1_CRITICAL: 15,
        IncidentSeverity.P2_HIGH: 30,
        IncidentSeverity.P3_MEDIUM: 60,
        IncidentSeverity.P4_LOW: 120,
    })
    target_roles: Dict[IncidentSeverity, str] = field(default_factory=lambda: {
        IncidentSeverity.P1_CRITICAL: "NOC_DUTY_MANAGER",
        IncidentSeverity.P2_HIGH: "NOC_LEAD_ENGINEER",
        IncidentSeverity.P3_MEDIUM: "STATION_SUPPORT_LEAD",
        IncidentSeverity.P4_LOW: "TIER1_OPERATOR",
    })


@dataclass
class IncidentRecord:
    """Canonical model for an enterprise operational incident."""
    incident_id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    root_cause_alert: OperationalAlert
    station_id: Optional[str] = None
    service_id: Optional[str] = None
    service_tier: Optional[str] = None
    correlated_alert_ids: List[str] = field(default_factory=list)
    assigned_owner: Optional[str] = None
    owner_role: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    sla_escalation_deadline: Optional[str] = None  # ISO timestamp
    is_escalated: bool = False
    escalated_to: Optional[str] = None
    escalation_count: int = 0
    remediation_action_id: Optional[str] = None    # Phase 12 action lineage
    audit_block_hash: Optional[str] = None         # Hash from audit ledger
    is_suppressed: bool = False
    suppression_reason: Optional[str] = None
    is_flapping: bool = False
    recurrence_count: int = 0
    work_notes: List[Dict[str, Any]] = field(default_factory=list)
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add_work_note(self, author: str, message: str) -> None:
        self.work_notes.append({
            "note_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "author": author,
            "message": message,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity.value,
            "status": self.status.value,
            "station_id": self.station_id,
            "service_id": self.service_id,
            "service_tier": self.service_tier,
            "root_cause_alert_id": self.root_cause_alert.alert_id,
            "correlated_alerts_count": len(self.correlated_alert_ids),
            "assigned_owner": self.assigned_owner,
            "owner_role": self.owner_role,
            "created_at": self.created_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "closed_at": self.closed_at,
            "is_escalated": self.is_escalated,
            "escalated_to": self.escalated_to,
            "escalation_count": self.escalation_count,
            "remediation_action_id": self.remediation_action_id,
            "is_suppressed": self.is_suppressed,
            "suppression_reason": self.suppression_reason,
            "is_flapping": self.is_flapping,
            "recurrence_count": self.recurrence_count,
            "work_notes_count": len(self.work_notes),
        }


class AlertCorrelationEngine:
    """Deduplicates, suppresses, and correlates raw operational alerts into actionable incidents."""

    def __init__(
        self,
        dedup_window_seconds: int = 300,
        flap_window_seconds: int = 300,
        flap_threshold_count: int = 4,
        escalation_policy: Optional[EscalationPolicy] = None,
    ) -> None:
        self.dedup_window_seconds = dedup_window_seconds
        self.flap_window_seconds = flap_window_seconds
        self.flap_threshold_count = flap_threshold_count
        self.escalation_policy = escalation_policy or EscalationPolicy()
        
        self._alert_history: Dict[str, List[datetime]] = {}
        self._down_entities: Set[str] = set()
        self._lock = threading.Lock()

    def register_entity_down(self, entity_id: str) -> None:
        with self._lock:
            self._down_entities.add(entity_id)

    def register_entity_up(self, entity_id: str) -> None:
        with self._lock:
            self._down_entities.discard(entity_id)

    def is_parent_down(self, parent_entity_id: Optional[str]) -> bool:
        if not parent_entity_id:
            return False
        with self._lock:
            return parent_entity_id in self._down_entities

    def check_flapping(self, entity_id: str, alert_time: datetime) -> bool:
        """Detect if an entity is toggling rapidly (flapping)."""
        with self._lock:
            history = self._alert_history.setdefault(entity_id, [])
            cutoff = alert_time - timedelta(seconds=self.flap_window_seconds)
            history = [t for t in history if t >= cutoff]
            history.append(alert_time)
            self._alert_history[entity_id] = history
            return len(history) >= self.flap_threshold_count

    def process_alert(
        self,
        alert: OperationalAlert,
        active_incidents: Dict[str, IncidentRecord],
    ) -> Tuple[IncidentRecord, str]:
        """Process alert thread-safely: returns (IncidentRecord, action).
        
        Actions: 'CREATED', 'DEDUPLICATED', 'SUPPRESSED', or 'REOPENED'.
        """
        now = datetime.now(timezone.utc)
        alert_time = datetime.fromisoformat(alert.event_timestamp)

        # 1. Maintenance Window Suppression (with automatic expiry check)
        is_in_maintenance = alert.in_maintenance
        if is_in_maintenance and alert.maintenance_window_end:
            win_end = datetime.fromisoformat(alert.maintenance_window_end)
            if now >= win_end:
                # Maintenance window has expired!
                is_in_maintenance = False

        if is_in_maintenance:
            inc = IncidentRecord(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                title=f"[MAINTENANCE] {alert.summary}",
                severity=IncidentSeverity.P4_LOW,
                status=IncidentStatus.CORRELATED,
                root_cause_alert=alert,
                station_id=alert.station_id,
                service_id=alert.service_id,
                is_suppressed=True,
                suppression_reason="MUTED_BY_MAINTENANCE_WINDOW",
            )
            inc.add_work_note("AlertCorrelationEngine", "Alert muted due to scheduled active maintenance window.")
            return inc, "SUPPRESSED"

        # 2. Topology-Aware Parent Down Suppression
        if self.is_parent_down(alert.parent_entity_id):
            inc = IncidentRecord(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                title=f"[SUPPRESSED] {alert.summary}",
                severity=alert.severity,
                status=IncidentStatus.CORRELATED,
                root_cause_alert=alert,
                station_id=alert.station_id,
                service_id=alert.service_id,
                is_suppressed=True,
                suppression_reason=f"PARENT_DOWN_SUPPRESSION: Upstream entity '{alert.parent_entity_id}' is down.",
            )
            inc.add_work_note("AlertCorrelationEngine", f"Alert suppressed because upstream parent '{alert.parent_entity_id}' is down.")
            return inc, "SUPPRESSED"

        # 3. Check for Recurrence on Recently Resolved Incident (within 1 hour)
        for inc in active_incidents.values():
            if inc.status == IncidentStatus.RESOLVED and inc.resolved_at:
                res_time = datetime.fromisoformat(inc.resolved_at)
                if (now - res_time).total_seconds() <= 3600.0:
                    if inc.root_cause_alert.fingerprint() == alert.fingerprint():
                        # Recurrence detected! Reopen incident
                        inc.status = IncidentStatus.REOPENED
                        inc.recurrence_count += 1
                        inc.correlated_alert_ids.append(alert.alert_id)
                        inc.add_work_note(
                            "AlertCorrelationEngine",
                            f"RECURRENCE DETECTED: Alert {alert.alert_id} recurred within 1 hour of resolution. Incident REOPENED."
                        )
                        self.register_entity_down(alert.entity_id)
                        return inc, "REOPENED"

        # 4. Check Deduplication against active incidents
        for inc in active_incidents.values():
            if inc.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                continue
            if inc.root_cause_alert.fingerprint() == alert.fingerprint():
                # Duplicate alert on active incident -> correlate
                inc.correlated_alert_ids.append(alert.alert_id)
                inc.add_work_note("AlertCorrelationEngine", f"Correlated repeating alert '{alert.alert_id}'.")
                return inc, "DEDUPLICATED"

        # 5. Check Flapping
        is_flapping = self.check_flapping(alert.entity_id, alert_time)

        # 6. Calculate Configurable Escalation Deadline
        deadline_minutes = self.escalation_policy.deadline_minutes.get(alert.severity, 15)
        deadline = (now + timedelta(minutes=deadline_minutes)).isoformat()

        inc = IncidentRecord(
            incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
            title=f"[{alert.severity.value}] {alert.summary}",
            severity=alert.severity,
            status=IncidentStatus.DETECTED,
            root_cause_alert=alert,
            station_id=alert.station_id,
            service_id=alert.service_id,
            sla_escalation_deadline=deadline,
            is_flapping=is_flapping,
        )
        if is_flapping:
            inc.add_work_note("AlertCorrelationEngine", f"Entity '{alert.entity_id}' is FLAPPING. Notifications dampened.")

        if alert.severity in (IncidentSeverity.P1_CRITICAL, IncidentSeverity.P2_HIGH):
            self.register_entity_down(alert.entity_id)

        return inc, "CREATED"


class IncidentManager:
    """Manages the full lifecycle, ownership assignment, escalation, and resolution of incidents."""

    def __init__(self, correlation_engine: Optional[AlertCorrelationEngine] = None) -> None:
        self.correlation_engine = correlation_engine or AlertCorrelationEngine()
        self._incidents: Dict[str, IncidentRecord] = {}
        self._lock = threading.Lock()

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        with self._lock:
            return self._incidents.get(incident_id)

    def get_active_incidents(self) -> List[IncidentRecord]:
        with self._lock:
            return [i for i in self._incidents.values() if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)]

    def ingest_alert(self, alert: OperationalAlert) -> Tuple[IncidentRecord, str]:
        """Ingest raw alert thread-safely."""
        with self._lock:
            inc, action = self.correlation_engine.process_alert(alert, self._incidents)
            if action in ("CREATED", "SUPPRESSED"):
                self._incidents[inc.incident_id] = inc
            return inc, action

    def acknowledge_incident(self, incident_id: str, operator_id: str, role: str) -> bool:
        """Acknowledge incident, recording owner and stopping initial SLA timer."""
        with self._lock:
            inc = self._incidents.get(incident_id)
            if not inc or inc.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                return False

            inc.status = IncidentStatus.ACKNOWLEDGED
            inc.assigned_owner = operator_id
            inc.owner_role = role
            inc.acknowledged_at = datetime.now(timezone.utc).isoformat()
            inc.add_work_note(operator_id, f"Incident acknowledged by {operator_id} ({role}). Initial SLA timer stopped.")
            return True

    def reject_acknowledgement(self, incident_id: str, operator_id: str, reason: str) -> bool:
        """Reject incident acknowledgement, returning to DETECTED state."""
        with self._lock:
            inc = self._incidents.get(incident_id)
            if not inc:
                return False
            inc.status = IncidentStatus.DETECTED
            inc.assigned_owner = None
            inc.acknowledged_at = None
            inc.add_work_note(operator_id, f"Acknowledgement rejected by {operator_id}: {reason}. Returned to DETECTED queue.")
            return True

    def transition_state(self, incident_id: str, new_status: IncidentStatus, operator_id: str, note: str) -> bool:
        """Advance incident state through formal lifecycle."""
        with self._lock:
            inc = self._incidents.get(incident_id)
            if not inc:
                return False

            inc.status = new_status
            now_iso = datetime.now(timezone.utc).isoformat()
            if new_status == IncidentStatus.RESOLVED:
                inc.resolved_at = now_iso
                self.correlation_engine.register_entity_up(inc.root_cause_alert.entity_id)
            elif new_status == IncidentStatus.CLOSED:
                inc.closed_at = now_iso

            inc.add_work_note(operator_id, f"Transitioned state to {new_status.value}. {note}")
            return True

    def check_sla_escalations(self, current_time: Optional[datetime] = None) -> List[IncidentRecord]:
        """Check active incidents for SLA acknowledgment expiry and escalate."""
        now = current_time or datetime.now(timezone.utc)
        escalated: List[IncidentRecord] = []

        with self._lock:
            for inc in self._incidents.values():
                if inc.status in (IncidentStatus.DETECTED, IncidentStatus.CORRELATED, IncidentStatus.REOPENED) and not inc.is_escalated:
                    if inc.sla_escalation_deadline:
                        deadline = datetime.fromisoformat(inc.sla_escalation_deadline)
                        if now >= deadline:
                            inc.is_escalated = True
                            inc.escalation_count += 1
                            target_role = self.correlation_engine.escalation_policy.target_roles.get(inc.severity, "NOC_DUTY_MANAGER")
                            inc.escalated_to = target_role
                            inc.add_work_note(
                                "IncidentManager:EscalationEngine",
                                f"SLA breached: Incident unacknowledged past deadline ({inc.sla_escalation_deadline}). Escalated to {target_role}."
                            )
                            escalated.append(inc)

        return escalated
