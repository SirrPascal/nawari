"""Command-line interface for Nawari declarative provisioning and observability."""

import argparse
import logging
import sys

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings
from services.api.provisioning.reconciler import Reconciler
from services.api.provisioning.schema import load_desired_state_from_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nawari.cli")


def cmd_status(args) -> int:
    """Check connectivity to Zabbix API and print environment stats."""
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)

    try:
        version = client.get_api_version()
        client.connect()
        groups = client.get_host_groups()
        hosts = client.get_hosts()
        templates = client.get_templates()

        print("\n======================================================================")
        print("NAWARI MONITORING PLATFORM STATUS")
        print("======================================================================")
        print(f"Zabbix URL:      {settings.zabbix.url}")
        print(f"Zabbix Version:  {version}")
        print(f"Auth Type:       {'Bearer Token' if client.is_token_auth else 'User/Password'}")
        print(f"Host Groups:     {len(groups)}")
        print(f"Monitored Hosts: {len(hosts)}")
        print(f"Templates:       {len(templates)}")
        print("======================================================================\n")
        return 0
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return 1
    finally:
        client.disconnect()


def cmd_plan(args) -> int:
    """Compute and display dry-run diff against live Zabbix state."""
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)

    try:
        client.connect()
        state = load_desired_state_from_dir(settings.provisioning_dir)
        reconciler = Reconciler(client)
        report = reconciler.plan(state)
        print("\n" + report.render_text() + "\n")
        return 0
    except Exception as e:
        logger.error(f"Plan computation failed: {e}")
        return 1
    finally:
        client.disconnect()


def cmd_apply(args) -> int:
    """Execute idempotent reconciliation."""
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)

    try:
        client.connect()
        state = load_desired_state_from_dir(settings.provisioning_dir)
        reconciler = Reconciler(client)
        
        # Pass 1: Apply changes
        report1 = reconciler.apply(state)
        print("\n" + report1.render_text() + "\n")

        # Pass 2: Verify idempotency contract (exit gate)
        logger.info("Executing verification pass to confirm idempotency...")
        report2 = reconciler.plan(state)
        if report2.has_changes:
            logger.error("IDEMPOTENCY FAILURE: Second pass detected lingering changes!")
            print(report2.render_text())
            return 2

        logger.info("Idempotency contract verified: 0 changes detected on secondary pass.")
        return 0
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return 1
    finally:
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nawari",
        description="Nawari Observability & Configuration Engine"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status command
    subparsers.add_parser("status", help="Check Zabbix API connectivity and entity counts")

    # plan command
    subparsers.add_parser("plan", help="Dry-run diff between desired state and Zabbix")

    # apply command
    subparsers.add_parser("apply", help="Idempotently apply desired state to Zabbix")

    args = parser.parse_args()

    if args.command == "status":
        sys.exit(cmd_status(args))
    elif args.command == "plan":
        sys.exit(cmd_plan(args))
    elif args.command == "apply":
        sys.exit(cmd_apply(args))


if __name__ == "__main__":
    main()

