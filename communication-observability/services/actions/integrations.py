"""Integrations Layer & Simulation Adapters for Nawari Actions (Workstream 12F).

Provides connectors for Zabbix, ITSM/ServiceNow incident ticketing,
and isolated simulation adapters for network and telecom remediation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ITSMIncidentRecord:
    incident_id: str
    title: str
    severity: str
    target_entity: str
    state: str = "OPEN"
    work_notes: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolution_code: Optional[str] = None


class ITSMIntegrationAdapter:
    """Mock/sandbox connector for enterprise ITSM (ServiceNow / Jira Service Management)."""

    def __init__(self):
        self._incidents: dict[str, ITSMIncidentRecord] = {}

    def create_incident(
        self,
        alert_id: str,
        title: str,
        severity: str,
        target_entity: str,
    ) -> ITSMIncidentRecord:
        inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        inc = ITSMIncidentRecord(
            incident_id=inc_id,
            title=title,
            severity=severity,
            target_entity=target_entity,
            work_notes=[f"Incident created from alert {alert_id} for target {target_entity}"],
        )
        self._incidents[inc_id] = inc
        return inc

    def append_work_note(self, incident_id: str, note: str) -> bool:
        if incident_id not in self._incidents:
            return False
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        self._incidents[incident_id].work_notes.append(f"[{timestamp}] {note}")
        return True

    def resolve_incident(self, incident_id: str, resolution_code: str = "RESOLVED_AUTO") -> bool:
        if incident_id not in self._incidents:
            return False
        inc = self._incidents[incident_id]
        inc.state = "RESOLVED"
        inc.resolved_at = time.time()
        inc.resolution_code = resolution_code
        inc.work_notes.append(f"Incident marked resolved with code: {resolution_code}")
        return True

    def get_incident(self, incident_id: str) -> Optional[ITSMIncidentRecord]:
        return self._incidents.get(incident_id)


class ZabbixActionAdapter:
    """Connector for Zabbix API maintenance and trigger management."""

    def __init__(self):
        self._maintenance_entries: list[dict[str, Any]] = []
        self._acknowledged_events: list[dict[str, Any]] = []

    def set_host_maintenance(self, host_name: str, duration_seconds: int = 3600) -> dict[str, Any]:
        entry = {
            "host_name": host_name,
            "duration_seconds": duration_seconds,
            "created_at": time.time(),
            "status": "ACTIVE",
        }
        self._maintenance_entries.append(entry)
        return entry

    def acknowledge_event(self, event_id: str, message: str) -> dict[str, Any]:
        ack = {
            "event_id": event_id,
            "message": message,
            "timestamp": time.time(),
        }
        self._acknowledged_events.append(ack)
        return ack


class SimulationNetworkAdapter:
    """Isolated simulation adapter for network interface and carrier routing actions."""

    def __init__(self):
        self.interface_states: dict[str, dict[str, Any]] = {}
        self.routing_states: dict[str, str] = {"default_voice_outbound": "primary_safaricom"}

    def apply_interface_rate_limit(self, interface: str, rate_limit_kbps: int) -> dict[str, Any]:
        self.interface_states[interface] = {
            "rate_limit_kbps": rate_limit_kbps,
            "dampened": True,
            "updated_at": time.time(),
        }
        return self.interface_states[interface]

    def remove_interface_rate_limit(self, interface: str) -> dict[str, Any]:
        if interface in self.interface_states:
            self.interface_states[interface]["rate_limit_kbps"] = None
            self.interface_states[interface]["dampened"] = False
        return {"interface": interface, "status": "CLEARED"}

    def switch_outbound_trunk(self, new_trunk: str) -> dict[str, Any]:
        prev = self.routing_states.get("default_voice_outbound", "unknown")
        self.routing_states["default_voice_outbound"] = new_trunk
        return {"previous_trunk": prev, "active_trunk": new_trunk, "timestamp": time.time()}

