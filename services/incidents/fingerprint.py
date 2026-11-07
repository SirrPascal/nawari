"""
Nawari Phase 8 — Incident Fingerprinting & Deduplication (Workstream 8D)
Generates deterministic fingerprints and prevents alert storms by grouping related symptoms.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional, Dict

from services.incidents.models import (
    Incident,
    IncidentStage,
    IncidentEvidence,
    RootCauseDomain,
    Severity,
    Confidence,
)


class IncidentDeduplicator:
    def __init__(self, debounce_window_seconds: float = 300.0):
        self.debounce_window_seconds = debounce_window_seconds
        self._active_incidents_by_fingerprint: Dict[str, Incident] = {}
        self._incident_counter: int = 1000

    @staticmethod
    def calculate_fingerprint(
        root_cause_domain: RootCauseDomain,
        fault_entity_id: str,
        site_id: str,
    ) -> str:
        raw_key = f"{root_cause_domain.value}|{fault_entity_id.strip().lower()}|{site_id.strip().upper()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def process_symptom(
        self,
        root_cause_domain: RootCauseDomain,
        fault_entity_id: str,
        site_id: str,
        severity: Severity,
        confidence: Confidence,
        title: str,
        evidence: Optional[IncidentEvidence] = None,
        deep_link: str = "",
    ) -> tuple[Incident, bool]:
        """
        Processes an incoming symptom.
        Returns:
            (incident, is_new)
            is_new is True if a new incident was created, False if deduplicated/grouped.
        """
        now = time.time()
        fp = self.calculate_fingerprint(root_cause_domain, fault_entity_id, site_id)

        existing = self._active_incidents_by_fingerprint.get(fp)
        if existing and existing.status not in (IncidentStage.CLOSED, IncidentStage.RESOLVED):
            # Group under existing incident
            if evidence:
                existing.add_evidence(evidence)
            else:
                existing.symptoms_count += 1
                existing.updated_at = now

            # Escalate severity if new symptom is higher
            severity_order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
            if severity_order.index(severity) > severity_order.index(existing.severity):
                existing.severity = severity

            return existing, False

        # Create new incident
        date_str = time.strftime("%Y%m%d", time.gmtime(now))
        self._incident_counter += 1
        incident_id = f"INC-{date_str}-{self._incident_counter}"

        inc = Incident(
            incident_id=incident_id,
            fingerprint=fp,
            title=title,
            root_cause_domain=root_cause_domain,
            fault_entity_id=fault_entity_id,
            site_id=site_id,
            severity=severity,
            confidence=confidence,
            status=IncidentStage.CREATED,
            created_at=now,
            updated_at=now,
            deep_link=deep_link or f"https://mon-grafana01.kenya-airways.com/d/nawari-incidents?var-inc={incident_id}",
        )
        if evidence:
            inc.add_evidence(evidence)
        else:
            inc.symptoms_count = 1

        self._active_incidents_by_fingerprint[fp] = inc
        return inc, True

    def get_incident_by_fingerprint(self, fingerprint: str) -> Optional[Incident]:
        return self._active_incidents_by_fingerprint.get(fingerprint)
