"""
Nawari Phase 8 — IT Service Management (ITSM) Adapter (Workstream 8E)
Integrates Nawari incidents with enterprise ticketing platforms (ServiceNow, Jira Service Management).
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from services.incidents.models import Incident, Severity
from services.integrations.base_adapter import BaseEnterpriseAdapter, AdapterResult


class ITSMAdapter(BaseEnterpriseAdapter):
    def __init__(
        self,
        provider: str = "servicenow",
        endpoint_url: str = "https://itsm.kenya-airways.com/api/now/table/incident",
        api_token: str = "test-token",
        failure_threshold: int = 5,
    ):
        super().__init__(
            name=f"itsm-{provider}",
            failure_threshold=failure_threshold,
            request_timeout_seconds=5.0,
            max_retries=2,
        )
        self.provider = provider
        self.endpoint_url = endpoint_url
        self.api_token = api_token

        # In-memory ticket database for testing/mocking
        self._tickets: Dict[str, Dict[str, Any]] = {}
        self._ticket_seq: int = 50000

    def map_severity_to_priority(self, severity: Severity) -> str:
        mapping = {
            Severity.CRITICAL: "P1-Critical",
            Severity.HIGH: "P2-High",
            Severity.MEDIUM: "P3-Medium",
            Severity.LOW: "P4-Low",
            Severity.INFO: "P5-Planning",
        }
        return mapping.get(severity, "P3-Medium")

    def create_ticket(self, incident: Incident) -> AdapterResult:
        idempotency_key = f"create-ticket-{incident.incident_id}"

        def _do_create() -> Dict[str, Any]:
            self._ticket_seq += 1
            ticket_id = f"KQ-INC-{self._ticket_seq}"
            priority = self.map_severity_to_priority(incident.severity)

            ticket_record = {
                "ticket_id": ticket_id,
                "incident_id": incident.incident_id,
                "short_description": f"[{priority}] {incident.title} ({incident.site_id})",
                "priority": priority,
                "state": "New",
                "assigned_group": "Network & Voice Engineering",
                "deep_link": incident.deep_link,
                "symptoms_count": incident.symptoms_count,
            }
            self._tickets[ticket_id] = ticket_record
            incident.external_ticket_id = ticket_id
            return ticket_record

        return self.execute_with_resilience("create_ticket", _do_create, idempotency_key=idempotency_key)

    def update_ticket(self, incident: Incident, note: str) -> AdapterResult:
        if not incident.external_ticket_id:
            return AdapterResult(success=False, error="Incident has no external ticket attached.")

        ticket_id = incident.external_ticket_id
        idempotency_key = f"update-ticket-{ticket_id}-{len(incident.evidence)}"

        def _do_update() -> Dict[str, Any]:
            if ticket_id not in self._tickets:
                raise KeyError(f"Ticket {ticket_id} not found in ITSM.")
            ticket = self._tickets[ticket_id]
            notes = ticket.setdefault("work_notes", [])
            notes.append(note)
            ticket["state"] = "In Progress"
            return ticket

        return self.execute_with_resilience("update_ticket", _do_update, idempotency_key=idempotency_key)

    def resolve_ticket(self, incident: Incident, resolution_notes: str) -> AdapterResult:
        if not incident.external_ticket_id:
            return AdapterResult(success=False, error="Incident has no external ticket attached.")

        ticket_id = incident.external_ticket_id
        idempotency_key = f"resolve-ticket-{ticket_id}"

        def _do_resolve() -> Dict[str, Any]:
            if ticket_id not in self._tickets:
                raise KeyError(f"Ticket {ticket_id} not found in ITSM.")
            ticket = self._tickets[ticket_id]
            ticket["state"] = "Resolved"
            ticket["close_notes"] = resolution_notes
            ticket["mttr_seconds"] = incident.mttr_seconds
            return ticket

        return self.execute_with_resilience("resolve_ticket", _do_resolve, idempotency_key=idempotency_key)

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        return self._tickets.get(ticket_id)
