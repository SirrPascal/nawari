#!/usr/bin/env python3
"""
Zabbix AlertScript for Microsoft 365 Exchange Online Email Delivery.
Compatible with Zabbix 7.4 Script Media Types.
Executes STARTTLS on port 587 with strict certificate validation and OAuth/SMTP AUTH.

Usage (invoked by Zabbix Server):
  python3 zabbix_m365_oauth_sender.py "{ALERT.SENDTO}" "{ALERT.SUBJECT}" "{ALERT.MESSAGE}"
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path if needed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.integrations.m365_email_provider import (
    M365EmailConfig,
    M365EmailProvider,
    mask_secret,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Zabbix-M365-AlertScript] %(message)s",
)
logger = logging.getLogger("zabbix_m365_alertscript")


def main() -> int:
    if len(sys.argv) < 4:
        logger.error("Usage: zabbix_m365_oauth_sender.py <sendto> <subject> <message>")
        return 1

    sendto = sys.argv[1].strip()
    subject = sys.argv[2].strip()
    message = sys.argv[3].strip()

    if not sendto:
        logger.error("Recipient address is empty; aborting delivery.")
        return 1

    # Load configuration
    config = M365EmailConfig.from_env()

    if not config.is_configured:
        logger.warning(
            "Microsoft 365 Email Provider is not yet configured with tenant credentials. "
            "Alert email suppressed safely. Configure M365_SMTP_USER and M365_SMTP_PASSWORD."
        )
        # Return 0 so Zabbix alert daemon does not continuously enter crash-retry loop
        return 0

    provider = M365EmailProvider(config)
    logger.info(f"Dispatching notification via Microsoft 365 to: {sendto}")

    # Detect if message contains HTML tags
    is_html = "<html" in message.lower() or "<b" in message.lower() or "<p" in message.lower()
    html_body = message if is_html else None
    text_body = message if not is_html else None

    result = provider.send_notification(
        to_addresses=[sendto],
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    if result.success:
        logger.info(f"Successfully delivered notification to {sendto} (Attempt {result.attempts_used})")
        return 0
    else:
        logger.error(f"Failed to deliver notification to {sendto}: {result.error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

