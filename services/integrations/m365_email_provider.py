"""
Nawari Microsoft 365 Email Notification Provider.
Implements enterprise email alert delivery via Microsoft 365 (smtp.office365.com:587)
with STARTTLS, TLS certificate validation, modern authentication (OAuth2 / Basic abstraction),
secret masking, bounded retry with exponential backoff, and rich actionable notification templates.
"""

from __future__ import annotations

import base64
import html
import logging
import os
import re
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nawari.notifications.m365")


class M365AuthMode(str, Enum):
    BASIC = "BASIC"
    OAUTH2 = "OAUTH2"


class ProviderStatus(str, Enum):
    DISABLED = "DISABLED"
    UNCONFIGURED = "UNCONFIGURED"
    HEALTHY = "HEALTHY"
    AUTHENTICATED = "AUTHENTICATED"
    FAILED_TEMPORARY = "FAILED_TEMPORARY"
    FAILED_PERMANENT = "FAILED_PERMANENT"


@dataclass
class M365Config:
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_secure: bool = False  # False means STARTTLS on 587, NOT plaintext!
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    auth_mode: M365AuthMode = M365AuthMode.BASIC
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_id: Optional[str] = None
    oauth_token: Optional[str] = None
    delivery_enabled: bool = False
    max_retries: int = 3
    initial_backoff_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> M365Config:
        return cls(
            smtp_host=os.getenv("SMTP_HOST", "smtp.office365.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_secure=os.getenv("SMTP_SECURE", "false").lower() == "true",
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_pass=os.getenv("SMTP_PASS", ""),
            smtp_from=os.getenv("SMTP_FROM", ""),
            auth_mode=M365AuthMode.OAUTH2 if os.getenv("SMTP_AUTH_MODE", "").upper() == "OAUTH2" else M365AuthMode.BASIC,
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            delivery_enabled=os.getenv("SMTP_DELIVERY_ENABLED", "false").lower() == "true",
        )


class M365EmailProvider:
    """Enterprise Microsoft 365 Email Notification Adapter."""

    SECRET_PATTERN = re.compile(
        r"(pass(word)?|secret|token|bearer|key|authorization)[\s:=]+['\"]?([^\s,'\"&]+)",
        re.IGNORECASE,
    )

    def __init__(self, config: Optional[M365Config] = None) -> None:
        self.config = config or M365Config.from_env()
        self.status = ProviderStatus.DISABLED
        self._sent_messages: List[Dict[str, Any]] = []
        self._delivery_errors: List[str] = []
        self._validate_startup()

    def _validate_startup(self) -> None:
        """Validates configuration on startup without crashing."""
        if not self.config.delivery_enabled:
            self.status = ProviderStatus.DISABLED
            logger.info("Microsoft 365 email notifications are DISABLED by default (delivery_enabled=False).")
            return

        if not self.config.smtp_user or (self.config.auth_mode == M365AuthMode.BASIC and not self.config.smtp_pass):
            self.status = ProviderStatus.UNCONFIGURED
            logger.warning(
                "Microsoft 365 email provider is UNCONFIGURED: SMTP_USER and SMTP_PASS/OAuth tokens are awaiting administrative handoff. Email channel held in safe state."
            )
            return

        self.status = ProviderStatus.HEALTHY
        logger.info("Microsoft 365 email provider initialized in %s auth mode.", self.config.auth_mode.value)

    def sanitize_logs(self, text: str) -> str:
        """Masks passwords, client secrets, and OAuth bearer tokens from logs."""
        return self.SECRET_PATTERN.sub(r"\1=********", str(text))

    def generate_xoauth2_string(self, user: str, token: str) -> str:
        """Formats the SASL XOAUTH2 authentication string for Modern Auth."""
        auth_string = f"user={user}\x01auth=Bearer {token}\x01\x01"
        return base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    def check_connection(self) -> Tuple[bool, str]:
        """
        Validates socket reachability and STARTTLS negotiation with Microsoft 365.
        Does NOT transmit credentials or send mail.
        """
        try:
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10.0) as server:
                server.ehlo()
                if not server.has_extn("STARTTLS"):
                    return False, "SMTP server does not support mandatory STARTTLS."
                server.starttls(context=context)
                server.ehlo()
                return True, "STARTTLS connection to smtp.office365.com verified with valid certificate."
        except Exception as e:
            sanitized = self.sanitize_logs(str(e))
            logger.error("M365 connection check failed: %s", sanitized)
            return False, f"Connection failed: {sanitized}"

    def render_notification(
        self,
        event_type: str,
        alert_dict: Dict[str, Any],
        dashboard_url: str = "http://10.102.10.20:3001/d/nawari-communication-overview",
    ) -> Tuple[str, str, str]:
        """
        Renders rich HTML and plain text email notifications.
        Returns: (subject, plain_text_body, html_body)
        """
        alert_id = alert_dict.get("alert_id", "ALERT-UNKNOWN")
        name = alert_dict.get("name", "Operational Alert")
        severity = alert_dict.get("severity", "WARNING").upper()
        entity_id = alert_dict.get("entity_id", "UNKNOWN-DEVICE")
        site_id = alert_dict.get("site_id", "GLOBAL")
        component = alert_dict.get("component", "COMMUNICATION")
        observed_val = alert_dict.get("observed_value", "N/A")
        desc = alert_dict.get("description", "")
        runbook = alert_dict.get("runbook", "Follow standard operational triage procedures.")
        evidence = alert_dict.get("evidence_class", "VERIFIED_INTEGRATION")
        fingerprint = alert_dict.get("fingerprint", "")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Severity banner colors
        severity_colors = {
            "DISASTER": "#b91c1c",
            "HIGH": "#c2410c",
            "AVERAGE": "#d97706",
            "WARNING": "#2563eb",
            "INFO": "#4b5563",
        }
        accent_color = severity_colors.get(severity, "#2563eb")

        subject_prefixes = {
            "NEW_ALERT": f"[NAWARI {severity}] {name} on {entity_id}",
            "SEVERITY_ESCALATION": f"[NAWARI ESCALATION {severity}] {name} on {entity_id}",
            "REPEAT_REMINDER": f"[NAWARI REMINDER {severity}] {name} on {entity_id} (Active)",
            "RECOVERY": f"[NAWARI RESOLVED] {name} on {entity_id} Recovered",
            "DELIVERY_FAILURE": f"[NAWARI DELIVERY FAILURE] Notification Failure for {alert_id}",
        }
        subject = subject_prefixes.get(event_type, f"[NAWARI ALERT] {name}")

        plain_text = (
            f"======================================================================\n"
            f"NAWARI SERVICE ASSURANCE PLATFORM — OPERATIONAL ALERT\n"
            f"Event: {event_type} | Severity: {severity}\n"
            f"======================================================================\n\n"
            f"Alert ID:       {alert_id}\n"
            f"Name:           {name}\n"
            f"Component:      {component}\n"
            f"Entity / Host:  {entity_id}\n"
            f"Site ID:        {site_id}\n"
            f"Observed Value: {observed_val}\n"
            f"Evidence Class: {evidence}\n"
            f"Timestamp:      {now_iso}\n"
            f"Fingerprint:    {fingerprint}\n\n"
            f"Description:\n{desc}\n\n"
            f"Recommended Investigation / Runbook:\n{runbook}\n\n"
            f"Dashboard Link: {dashboard_url}\n"
            f"----------------------------------------------------------------------\n"
            f"This is an automated operational notification. Do not reply to this email.\n"
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
    .container {{ max-width: 650px; margin: 0 auto; background-color: #1e293b; border-radius: 8px; overflow: hidden; border: 1px solid #334155; }}
    .header {{ background-color: {accent_color}; color: #ffffff; padding: 18px 24px; font-weight: bold; font-size: 18px; }}
    .body {{ padding: 24px; font-size: 14px; line-height: 1.6; color: #e2e8f0; }}
    .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; background-color: {accent_color}; color: #ffffff; }}
    .meta-table {{ width: 100%; border-collapse: collapse; margin: 18px 0; }}
    .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #334155; font-size: 13px; }}
    .meta-table td.label {{ color: #94a3b8; font-weight: 600; width: 35%; }}
    .runbook-box {{ background-color: #0f172a; border-left: 4px solid {accent_color}; padding: 12px 16px; margin: 16px 0; border-radius: 0 4px 4px 0; }}
    .btn {{ display: inline-block; padding: 10px 20px; background-color: #2563eb; color: #ffffff; text-decoration: none; border-radius: 4px; font-weight: bold; margin-top: 12px; }}
    .footer {{ padding: 16px 24px; background-color: #0f172a; color: #64748b; font-size: 11px; text-align: center; border-top: 1px solid #334155; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      [NAWARI] {html.escape(event_type)}: {html.escape(name)}
    </div>
    <div class="body">
      <p><span class="badge">{severity}</span> &nbsp; <b>{html.escape(component)}</b> on <code>{html.escape(entity_id)}</code> ({html.escape(site_id)})</p>
      <p>{html.escape(desc)}</p>
      
      <table class="meta-table">
        <tr><td class="label">Alert Identifier</td><td><code>{html.escape(alert_id)}</code></td></tr>
        <tr><td class="label">Observed Value</td><td><b>{html.escape(str(observed_val))}</b></td></tr>
        <tr><td class="label">Evidence Standard</td><td><code>{html.escape(evidence)}</code></td></tr>
        <tr><td class="label">Observed Timestamp</td><td>{html.escape(now_iso)}</td></tr>
        <tr><td class="label">Fingerprint Hash</td><td><code>{html.escape(fingerprint)}</code></td></tr>
      </table>

      <div class="runbook-box">
        <b>Recommended Triage & Runbook Action:</b><br/>
        {html.escape(runbook)}
      </div>

      <p><a href="{dashboard_url}" class="btn" style="color:#ffffff;">Open Grafana Operational Dashboard</a></p>
    </div>
    <div class="footer">
      Nawari Enterprise Service Assurance Platform &bull; Kenya Airways Observability &bull; Mon-Grafana01 Hub
    </div>
  </div>
</body>
</html>"""
        return subject, plain_text, html_body

    def send_notification(
        self,
        event_type: str,
        alert_dict: Dict[str, Any],
        recipients: List[str],
        dashboard_url: str = "http://10.102.10.20:3001/d/nawari-communication-overview",
        mock_transport: bool = False,
    ) -> bool:
        """
        Dispatches actionable alert email with retry and backoff.
        If mock_transport is True or delivery is disabled, message is safely recorded in memory.
        """
        subject, plain_text, html_body = self.render_notification(event_type, alert_dict, dashboard_url)

        msg_record = {
            "from": self.config.smtp_from or self.config.smtp_user or "nawari-alerts@kenya-airways.com",
            "to": recipients,
            "subject": subject,
            "plain_text": plain_text,
            "html": html_body,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "alert_id": alert_dict.get("alert_id"),
        }

        if mock_transport or not self.config.delivery_enabled or self.status in (ProviderStatus.DISABLED, ProviderStatus.UNCONFIGURED):
            self._sent_messages.append(msg_record)
            logger.info("Notification recorded in mock/safe outbox (alert: %s, to: %s)", alert_dict.get("alert_id"), recipients)
            return True

        # Production delivery loop with bounded exponential backoff
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        mime_msg = MIMEMultipart("alternative")
        mime_msg["Subject"] = subject
        mime_msg["From"] = msg_record["from"]
        mime_msg["To"] = ", ".join(recipients)
        mime_msg.attach(MIMEText(plain_text, "plain"))
        mime_msg.attach(MIMEText(html_body, "html"))

        for attempt in range(1, self.config.max_retries + 1):
            try:
                with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15.0) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()

                    if self.config.auth_mode == M365AuthMode.BASIC:
                        server.login(self.config.smtp_user, self.config.smtp_pass)
                    elif self.config.auth_mode == M365AuthMode.OAUTH2 and self.config.oauth_token:
                        auth_str = self.generate_xoauth2_string(self.config.smtp_user, self.config.oauth_token)
                        server.docmd("AUTH", f"XOAUTH2 {auth_str}")

                    server.sendmail(msg_record["from"], recipients, mime_msg.as_string())
                    self._sent_messages.append(msg_record)
                    self.status = ProviderStatus.HEALTHY
                    logger.info("Email notification delivered successfully to %s", recipients)
                    return True

            except Exception as e:
                sanitized_err = self.sanitize_logs(str(e))
                self._delivery_errors.append(f"Attempt {attempt}: {sanitized_err}")
                logger.warning("SMTP delivery failed (attempt %d/%d): %s", attempt, self.config.max_retries, sanitized_err)
                if attempt < self.config.max_retries:
                    sleep_time = self.config.initial_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        self.status = ProviderStatus.FAILED_TEMPORARY
        return False
