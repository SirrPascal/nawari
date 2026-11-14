"""
Nawari Phase 8 — Incident Data Models & 9-Stage Lifecycle Definitions (Workstream 8D)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class IncidentStage(str, Enum):
    DETECTED = "DETECTED"
    CREATED = "CREATED"
    ENRICHED = "ENRICHED"
    CLASSIFIED = "CLASSIFIED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Confidence(str, Enum):
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    SUSPECTED = "SUSPECTED"


class RootCauseDomain(str, Enum):
    NETWORK_CORE = "NETWORK_CORE"
    NETWORK_ACCESS = "NETWORK_ACCESS"
    VOICE_SIP = "VOICE_SIP"
    VOICE_MEDIA = "VOICE_MEDIA"
    ENDPOINT_WIFI = "ENDPOINT_WIFI"
    SERVICE_APPLICATION = "SERVICE_APPLICATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class IncidentEvidence:
    evidence_type: str
    description: str
    timestamp: float = field(default_factory=time.time)
    metric_value: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Incident:
    incident_id: str
    fingerprint: str
    title: str
    root_cause_domain: RootCauseDomain
    fault_entity_id: str
    site_id: str
    severity: Severity
    confidence: Confidence
    status: IncidentStage = IncidentStage.DETECTED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    acknowledged_at: Optional[float] = None
    acknowledged_by: Optional[str] = None
    recovery_started_at: Optional[float] = None
    nominal_cycles: int = 0
    resolved_at: Optional[float] = None
    closed_at: Optional[float] = None
    mttr_seconds: Optional[float] = None
    evidence: List[IncidentEvidence] = field(default_factory=list)
    symptoms_count: int = 0
    external_ticket_id: Optional[str] = None
    deep_link: str = ""

    def add_evidence(self, evidence: IncidentEvidence) -> None:
        self.evidence.append(evidence)
        self.symptoms_count += 1
        self.updated_at = time.time()
