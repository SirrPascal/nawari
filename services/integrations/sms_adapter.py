"""
Nawari Phase 8 — Enterprise SMS Notification Adapter (Workstream 8E)
Dispatches urgent SMS alerts for CRITICAL unacknowledged incidents with rate throttling.
"""

from __future__ import annotations

import time
from typing import Dict, Any, List, Optional

from services.incidents.models import Incident, Severity
from services.integrations.base_adapter import BaseEnterpriseAdapter, AdapterResult


class SMSAdapter(BaseEnterpriseAdapter):
    def __init__(
        self,
        provider: str = "generic_gateway",
        sender_id: str = "NAWARI-NOC",
        rate_limit_seconds: float = 60.0,
        failure_threshold: int = 5,
    ):
        super().__init__(
            name=f"sms-{provider}",
            failure_threshold=failure_threshold,
            request_timeout_seconds=5.0,
            max_retries=2,
        )
        self.sender_id = sender_id
        self.rate_limit_seconds = rate_limit_seconds
        self._last_sent_by_number: Dict[str, float] = {}
        self.sent_messages: List[Dict[str, Any]] = []

    def send_sms(self, phone_number: str, message: str) -> AdapterResult:
        idempotency_key = f"sms-{phone_number}-{hash(message)}"
        now = time.time()

        # Rate limiting check
        last_sent = self._last_sent_by_number.get(phone_number, 0.0)
        if now - last_sent < self.rate_limit_seconds:
            return AdapterResult(
                success=False,
                error=f"SMS to {phone_number} throttled by rate limit ({self.rate_limit_seconds}s)",
            )

        def _do_send() -> Dict[str, Any]:
            record = {
                "to": phone_number,
                "from": self.sender_id,
                "message": message[:160],  # Single SMS segment
                "timestamp": now,
            }
            self.sent_messages.append(record)
            self._last_sent_by_number[phone_number] = now
            return record

        return self.execute_with_resilience("send_sms", _do_send, idempotency_key=idempotency_key)

    def send_incident_page(self, incident: Incident, phone_number: str) -> AdapterResult:
        if incident.severity != Severity.CRITICAL:
            return AdapterResult(
                success=False,
                error=f"SMS paging suppressed: Incident {incident.incident_id} is {incident.severity.value}, not CRITICAL.",
            )

        msg = f"[CRITICAL P1] {incident.title} ({incident.site_id}) - Details: {incident.deep_link}"
        return self.send_sms(phone_number, msg)
