"""
Nawari Zabbix Problem & Event Ingestion Consumer.
Ingests active problems and recovery events from Zabbix 7.4 JSON-RPC API,
correlates them across communication topology, and evaluates composite
Aviation Business Service impacts without duplicate notifications.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from services.assurance.models import RootCauseDomain, ServiceHealthState
from services.multisite.incident_pipeline import IncidentStatus

logger = logging.getLogger("nawari.zabbix_consumer")


class ZabbixSeverity(int, Enum):
    NOT_CLASSIFIED = 0
    INFORMATION = 1
    WARNING = 2
    AVERAGE = 3
    HIGH = 4
    DISASTER = 5


@dataclass
class IngestedZabbixProblem:
    event_id: str
    object_id: str  # Trigger ID
    name: str
    severity: ZabbixSeverity
    clock: int
    r_event_id: str = "0"
    r_clock: int = 0
    acknowledged: bool = False
    tags: Dict[str, str] = field(default_factory=dict)
    host_name: str = ""
    host_ip: str = ""
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_recovered(self) -> bool:
        return self.r_event_id != "0" or self.r_clock > 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.clock


@dataclass
class CompositeServiceIncident:
    incident_id: str
    service_id: str
    service_name: str
    title: str
    severity: ZabbixSeverity
    status: IncidentStatus
    root_cause_domain: RootCauseDomain
    created_at: float
    resolved_at: Optional[float] = None
    underlying_problems: List[IngestedZabbixProblem] = field(default_factory=list)
    affected_components: Set[str] = field(default_factory=set)
    root_cause_candidate: str = ""
    notification_dispatched: bool = False

    def add_problem(self, problem: IngestedZabbixProblem) -> None:
        if not any(p.event_id == problem.event_id for p in self.underlying_problems):
            self.underlying_problems.append(problem)
            comp = problem.tags.get("component") or problem.host_name
            if comp:
                self.affected_components.add(comp)
            # Escalate composite severity if incoming problem is higher
            if problem.severity.value > self.severity.value:
                self.severity = problem.severity


class ZabbixProblemConsumer:
    """Consumes Zabbix problems idempotently and builds composite service incidents."""

    def __init__(
        self,
        zabbix_client: Any,
        notification_handler: Optional[Any] = None,
        emit_composite_notifications: bool = True,
    ):
        self.zabbix_client = zabbix_client
        self.notification_handler = notification_handler
        self.emit_composite_notifications = emit_composite_notifications

        # State stores
        self.ingested_problems: Dict[str, IngestedZabbixProblem] = {}  # eventid -> Problem
        self.active_composite_incidents: Dict[str, CompositeServiceIncident] = {}  # service_id -> Incident
        self.resolved_composite_incidents: Dict[str, CompositeServiceIncident] = {}
        self.processed_event_ids: Set[str] = set()

        # Telephony dependency order for root-cause attribution:
        # Upstream components take precedence over downstream symptoms
        self.telephony_hierarchy = [
            "sm-core",
            "cm-core",
            "sbce-core",
            "sip-trunk",
            "g450-gateway",
            "voice-probe",
            "contact-centre",
            "call-recording",
        ]

    def poll_zabbix_problems(self, limit: int = 100) -> List[IngestedZabbixProblem]:
        """Poll active and recently resolved problems via Zabbix API problem.get."""
        if not self.zabbix_client:
            return []

        params: Dict[str, Any] = {
            "output": ["eventid", "objectid", "name", "severity", "clock", "r_eventid", "r_clock", "acknowledged"],
            "selectTags": "extend",
            "selectAcknowledges": "extend",
            "recent": True,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            "limit": limit,
        }

        try:
            if hasattr(self.zabbix_client, "call"):
                res = self.zabbix_client.call("problem.get", params)
            elif hasattr(self.zabbix_client, "request"):
                res = self.zabbix_client.request("problem.get", params)
            else:
                res = []

            problems: List[IngestedZabbixProblem] = []
            if isinstance(res, list):
                for item in res:
                    tags = {t.get("tag"): t.get("value") for t in item.get("tags", []) if "tag" in t}
                    prob = IngestedZabbixProblem(
                        event_id=str(item.get("eventid")),
                        object_id=str(item.get("objectid")),
                        name=item.get("name", "Unknown Problem"),
                        severity=ZabbixSeverity(int(item.get("severity", 0))),
                        clock=int(item.get("clock", time.time())),
                        r_event_id=str(item.get("r_eventid", "0")),
                        r_clock=int(item.get("r_clock", 0)),
                        acknowledged=bool(int(item.get("acknowledged", 0))),
                        tags=tags,
                        raw_payload=item,
                    )
                    problems.append(prob)
            return problems
        except Exception as e:
            logger.error(f"Failed to fetch problems from Zabbix API: {e}")
            return []

    def ingest_problems(self, problems: List[IngestedZabbixProblem]) -> Dict[str, Any]:
        """Process incoming Zabbix problems idempotently and correlate service impacts."""
        new_problems_count = 0
        recovered_problems_count = 0

        for p in problems:
            # Check if this problem is a recovery event
            if p.is_recovered:
                if p.event_id in self.ingested_problems:
                    existing = self.ingested_problems[p.event_id]
                    existing.r_event_id = p.r_event_id
                    existing.r_clock = p.r_clock
                    recovered_problems_count += 1
                    self._check_composite_incident_recovery(existing)
                continue

            # Active problem
            if p.event_id not in self.ingested_problems:
                self.ingested_problems[p.event_id] = p
                self.processed_event_ids.add(p.event_id)
                new_problems_count += 1
                self._correlate_problem(p)

        return {
            "ingested_count": len(problems),
            "new_problems": new_problems_count,
            "recovered_problems": recovered_problems_count,
            "active_composite_incidents": len(self.active_composite_incidents),
        }

    def _correlate_problem(self, problem: IngestedZabbixProblem) -> None:
        """Correlate problem into high-level Aviation Business Service."""
        # 1. Map problem to Business Service
        service_id, service_name = self._map_service(problem)
        if not service_id:
            return

        # 2. Check if an active composite incident exists for this service
        incident = self.active_composite_incidents.get(service_id)
        now = time.time()

        if incident is None:
            # Create new composite incident
            incident = CompositeServiceIncident(
                incident_id=f"INC-{service_id}-{int(now)}",
                service_id=service_id,
                service_name=service_name,
                title=f"{service_name} Service Degradation: {problem.name}",
                severity=problem.severity,
                status=IncidentStatus.DETECTED,
                root_cause_domain=self._map_root_cause_domain(problem),
                created_at=now,
                root_cause_candidate=problem.name,
            )
            incident.add_problem(problem)
            self.active_composite_incidents[service_id] = incident

            # Dispatch composite notification if enabled (and NOT a duplicate of device alert)
            if self.emit_composite_notifications and self.notification_handler:
                self._dispatch_composite_notification(incident, "COMPOSITE_SERVICE_DEGRADED")
                incident.notification_dispatched = True
        else:
            # Add to existing incident (correlated)
            incident.add_problem(problem)
            incident.status = IncidentStatus.CORRELATED

            # Re-evaluate root cause based on hierarchy
            self._reevaluate_root_cause(incident)

    def _reevaluate_root_cause(self, incident: CompositeServiceIncident) -> None:
        """Determines the most likely root-cause candidate based on component hierarchy."""
        best_candidate = incident.root_cause_candidate
        highest_rank = -1

        for p in incident.underlying_problems:
            comp = p.tags.get("component", "").lower()
            rank = -1
            for i, h in enumerate(self.telephony_hierarchy):
                if h in comp or h in p.name.lower():
                    rank = i
                    break
            if rank != -1 and (highest_rank == -1 or rank < highest_rank):
                highest_rank = rank
                best_candidate = f"{p.name} (on {p.host_name or comp})"

        incident.root_cause_candidate = best_candidate

    def _check_composite_incident_recovery(self, recovered_problem: IngestedZabbixProblem) -> None:
        """Checks if all underlying problems for a composite incident are cleared."""
        for service_id, incident in list(self.active_composite_incidents.items()):
            if any(p.event_id == recovered_problem.event_id for p in incident.underlying_problems):
                # Check if all problems in this incident are recovered
                all_clear = all(
                    (self.ingested_problems.get(p.event_id) and self.ingested_problems[p.event_id].is_recovered)
                    for p in incident.underlying_problems
                )

                if all_clear:
                    now = time.time()
                    incident.status = IncidentStatus.RESOLVED
                    incident.resolved_at = now
                    self.resolved_composite_incidents[incident.incident_id] = incident
                    del self.active_composite_incidents[service_id]

                    if self.emit_composite_notifications and self.notification_handler and incident.notification_dispatched:
                        self._dispatch_composite_notification(incident, "COMPOSITE_SERVICE_RECOVERED")

    def _map_service(self, problem: IngestedZabbixProblem) -> tuple[str, str]:
        """Maps Zabbix problem tags/name to canonical Aviation Business Service."""
        comp = problem.tags.get("component", "").lower()
        scope = problem.tags.get("scope", "").lower()
        name = problem.name.lower()

        if any(k in comp or k in name for k in ["sbce", "session manager", "sm", "sip", "trunk", "cm", "g450", "voice", "contact-centre", "recording", "cms", "wfo"]):
            return "SRV-VOICE-CORP", "Kenya Airways Voice Contact Centre & Telephony"
        elif any(k in comp or k in name for k in ["wan", "router", "switch", "gateway", "outstation"]):
            return "SRV-WAN-OUTSTATIONS", "Outstation Ground Operations Connectivity"
        elif "dcs" in name or "checkin" in name:
            return "SRV-DCS-CHECKIN", "Departure Control & Passenger Check-in"
        return "SRV-INFRA-CORE", "Core Airline Enterprise Infrastructure"

    def _map_root_cause_domain(self, problem: IngestedZabbixProblem) -> RootCauseDomain:
        comp = problem.tags.get("component", "").lower()
        if "sip" in comp or "voice" in comp or "call" in comp:
            return RootCauseDomain.VOICE_SIGNALING
        if "network" in comp or "interface" in comp or "infrastructure" in comp:
            return RootCauseDomain.NETWORK_INFRASTRUCTURE
        if "management" in comp or "contact-centre" in comp:
            return RootCauseDomain.APPLICATION_SERVICE
        return RootCauseDomain.UNKNOWN

    def _dispatch_composite_notification(self, incident: CompositeServiceIncident, event_type: str) -> None:
        """Dispatches high-level business service notification via registered handler."""
        if not self.notification_handler:
            return
        try:
            self.notification_handler(incident, event_type)
        except Exception as e:
            logger.error(f"Error dispatching composite notification for {incident.incident_id}: {e}")
