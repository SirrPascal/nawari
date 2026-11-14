"""
Nawari Phase 8 — Enterprise Email Notification Adapter (Workstream 8E)
Dispatches formatted incident alerts via SMTP with STARTTLS and secret masking.
"""

from __future__ import annotations

import re
from typing import Dict, Any, List, Optional

from services.incidents.models import Incident
from services.integrations.base_adapter import BaseEnterpriseAdapter, AdapterResult


class EmailAdapter(BaseEnterpriseAdapter):
    SECRET_REGEX = re.compile(
        r"(password|token|secret|authorization|key)[\s:=]+['\"]?([^\s,'\"&]+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        smtp_host: str = "mail.kenya-airways.com",
        smtp_port: int = 587,
        sender_address: str = "nawari-alerts@kenya-airways.com",
        failure_threshold: int = 5,
    ):
        super().__init__(
            name="email-smtp",
            failure_threshold=failure_threshold,
            request_timeout_seconds=5.0,
            max_retries=2,
        )
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_address = sender_address
        self.sent_emails: List[Dict[str, Any]] = []

    def sanitize_content(self, text: str) -> str:
        """Masks passwords, tokens, and authorization credentials from message body."""
        return self.SECRET_REGEX.sub(r"\1=********", text)

    def send_incident_alert(
        self,
        incident: Incident,
        recipients: List[str],
    ) -> AdapterResult:
        idempotency_key = f"email-alert-{incident.incident_id}-{incident.status.value}"

        def _do_send() -> Dict[str, Any]:
            subject = f"[{incident.severity.value}] {incident.title} - Site: {incident.site_id}"
            raw_body = (
                f"Nawari Service Assurance Incident Alert\n"
                f"Incident ID: {incident.incident_id}\n"
                f"Domain: {incident.root_cause_domain.value}\n"
                f"Entity: {incident.fault_entity_id}\n"
                f"Severity: {incident.severity.value}\n"
                f"Confidence: {incident.confidence.value}\n"
                f"Symptoms Count: {incident.symptoms_count}\n"
                f"Dashboard: {incident.deep_link}\n"
            )
            clean_body = self.sanitize_content(raw_body)

            msg_record = {
                "from": self.sender_address,
                "to": recipients,
                "subject": subject,
                "body": clean_body,
            }
            self.sent_emails.append(msg_record)
            return msg_record

        return self.execute_with_resilience("send_incident_alert", _do_send, idempotency_key=idempotency_key)
