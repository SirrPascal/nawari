#!/usr/bin/env python3
"""
scripts/test_m365_email.py

Manual test utility for validating Microsoft 365 SMTP connectivity, STARTTLS negotiation,
authentication configuration, and alert template rendering.

Usage:
  # Check connection and STARTTLS only (no email sent):
  python scripts/test_m365_email.py --check-only

  # Send test operational alert notification:
  python scripts/test_m365_email.py --to operator@kenya-airways.com --mock
"""

import argparse
import sys
from services.integrations.m365_email_provider import M365Config, M365EmailProvider


def main():
    parser = argparse.ArgumentParser(description="Test Microsoft 365 Email Alert Integration")
    parser.add_argument("--check-only", action="store_true", help="Test socket and STARTTLS without sending mail")
    parser.add_argument("--to", type=str, help="Destination recipient email address")
    parser.add_argument("--mock", action="store_true", default=True, help="Simulate send without hitting production SMTP server")
    args = parser.parse_args()

    config = M365Config.from_env()
    provider = M365EmailProvider(config)

    print("======================================================================")
    print("NAWARI MICROSOFT 365 EMAIL INTEGRATION TEST")
    print(f"Target Host: {config.smtp_host}:{config.smtp_port} (STARTTLS)")
    print(f"Auth Mode:   {config.auth_mode.value}")
    print(f"User / From: {config.smtp_user or '<NOT SET>'} / {config.smtp_from or '<NOT SET>'}")
    print(f"Status:      {provider.status.value}")
    print("======================================================================")

    if args.check_only:
        print("[CHECK] Testing network reachability and STARTTLS handshake...")
        success, msg = provider.check_connection()
        print(f"Result: {'PASS' if success else 'FAIL'} - {msg}")
        sys.exit(0 if success else 1)

    recipient = args.to or "noc-test@kenya-airways.com"
    test_alert = {
        "alert_id": "ALERT-SBCE-001",
        "name": "Avaya SBCE Appliance Unreachable",
        "severity": "DISASTER",
        "component": "SBCE",
        "entity_id": "sbce-pride-01.jki.kenya-airways.com",
        "site_id": "NBO-JKIA",
        "observed_value": 0,
        "description": "Avaya SBCE signaling and management IP is unresponsive to ICMP/SNMP polling.",
        "runbook": "Inspect SBCE hypervisor VM host and check firewall port 161/443.",
        "evidence_class": "VERIFIED_INTEGRATION",
        "fingerprint": "sbce-001-test-fprint",
    }

    print(f"[TEST] Rendering and dispatching sample operational alert to {recipient} (mock={args.mock})...")
    ok = provider.send_notification("NEW_ALERT", test_alert, [recipient], mock_transport=args.mock)
    if ok:
        print("[SUCCESS] Operational notification processed and recorded successfully.")
    else:
        print("[FAILURE] Failed to deliver operational notification.")
        sys.exit(1)


if __name__ == "__main__":
    main()

