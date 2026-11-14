"""Command-line interface and entry point for the Nawari Endpoint Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import List, Optional

from services.endpoint.config import AgentConfig
from services.endpoint.core.identity import IdentityManager, mask_agent_id
from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.runner import EndpointAgentRunner

logger = setup_agent_logger()

AGENT_VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nawari-agent",
        description="Nawari Endpoint-to-Service Network Observability Agent (Stage 7A)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run the continuous probe agent daemon")
    run_parser.add_argument("--interval", type=int, help="Poll interval in seconds")
    run_parser.add_argument("--json", action="store_true", help="Output logs in JSON format")

    # run-once command
    run_once_parser = subparsers.add_parser("run-once", help="Execute a single diagnostic cycle and exit")
    run_once_parser.add_argument("--json", action="store_true", help="Output telemetry report as JSON")

    # Target consolidated-agent interface. Keep run-once as a compatibility alias.
    test_parser = subparsers.add_parser("test", help="Execute endpoint diagnostics and exit")
    test_parser.add_argument("--all", action="store_true", help="Execute every enabled diagnostic")
    test_parser.add_argument("--json", action="store_true", help="Output telemetry report as JSON")

    # info command
    subparsers.add_parser("info", help="Display platform capabilities and agent identity")

    # health command
    subparsers.add_parser("health", help="Display runtime health diagnostics")
    subparsers.add_parser("status", help="Display current agent runtime status")
    subparsers.add_parser("version", help="Display agent version")

    # Invoked by the Windows Service Control Manager through the MSI ServiceInstall entry.
    subparsers.add_parser("service", help=argparse.SUPPRESS)
    subparsers.add_parser("credential-store", help=argparse.SUPPRESS)

    # re-register command
    re_reg_parser = subparsers.add_parser("re-register", help="Force generation of a new persistent agent identity")
    re_reg_parser.add_argument("--force", action="store_true", help="Confirm re-registration")

    return parser


def handle_info(config: AgentConfig) -> int:
    adapter = get_platform_adapter()
    id_mgr = IdentityManager(state_path=f"{config.state_dir}/agent_identity.json")
    caps = adapter.get_capabilities()

    print("======================================================================")
    print("NAWARI ENDPOINT AGENT (STAGE 7A CORE BASELINE)")
    print("======================================================================")
    print(f"Agent ID (Masked)    : {mask_agent_id(id_mgr.agent_id)}")
    print(f"Enrolled At          : {id_mgr.identity.enrolled_at}")
    print(f"Re-registrations     : {id_mgr.identity.re_registration_count}")
    print(f"Hostname             : {config.hostname}")
    print(f"Operating System     : {caps.os_name} {caps.os_version} ({caps.architecture})")
    print(f"Supports Raw ICMP    : {caps.supports_raw_icmp}")
    print(f"Supports Non-Priv ICMP: {caps.supports_unprivileged_icmp}")
    print(f"Supports Wi-Fi Diag  : {caps.supports_wifi_diagnostics}")
    print(f"Gateway Discovery    : {caps.supports_gateway_discovery}")
    print(f"DNS Discovery        : {caps.supports_dns_discovery}")
    if caps.requires_elevation_for:
        print(f"Elevation Needed For : {', '.join(caps.requires_elevation_for)}")
    else:
        print("Elevation Needed For : None (Full Zero-Privilege Operation)")
    print(f"Configured Targets   : {len(config.targets)}")
    for t in config.targets:
        print(f"  - [{t.target_id}] {t.target_name} -> {t.destination}:{t.port or '-'} ({t.protocol.value})")
    print("======================================================================")
    return 0


def handle_re_register(config: AgentConfig, force: bool) -> int:
    id_mgr = IdentityManager(state_path=f"{config.state_dir}/agent_identity.json")
    old_id = id_mgr.agent_id
    if not force:
        print(f"Current Agent ID: {mask_agent_id(old_id)}")
        print("To confirm re-registration, pass --force.")
        return 1

    new_identity = id_mgr.re_register(force=True)
    print("Successfully re-registered agent.")
    print(f"New Agent ID: {mask_agent_id(new_identity.agent_id)}")
    print(f"Re-registration count: {new_identity.re_registration_count}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = AgentConfig.load_from_env()
    enable_uploader = config.environment.value == "PHYSICAL_PRODUCTION"

    if args.command == "version":
        print(f"Nawari Endpoint Agent {AGENT_VERSION}")
        return 0

    if args.command == "service":
        if os.name != "nt":
            print("The service command is supported only on Windows.", file=sys.stderr)
            return 2
        from services.endpoint.windows_service import run_service_dispatcher

        return run_service_dispatcher()

    if args.command == "credential-store":
        if os.name != "nt":
            print("Credential storage is supported only on Windows.", file=sys.stderr)
            return 2
        from services.endpoint.windows_credentials import store_token_from_stdin

        store_token_from_stdin()
        return 0

    if args.command == "info":
        return handle_info(config)

    elif args.command == "re-register":
        return handle_re_register(config, args.force)

    elif args.command in ("health", "status"):
        runner = EndpointAgentRunner(config=config, enable_uploader=enable_uploader)
        health = runner.lifecycle.get_health()
        print(json.dumps(health, indent=2))
        return 0

    elif args.command in ("run-once", "test"):
        runner = EndpointAgentRunner(config=config, enable_uploader=enable_uploader)
        report = asyncio.run(runner.run_once())
        if args.json:
            print(report.to_json())
        else:
            print(f"Diagnostic cycle complete for agent {mask_agent_id(report.metadata.agent_id)}")
            print(f"Gateway reachable: {report.local_network.gateway_is_reachable} (RTT: {report.local_network.gateway_rtt_ms}ms, Loss: {report.local_network.gateway_loss_pct}%)")
            print(f"Active interface : {report.local_network.interface_name} ({report.local_network.interface_type.value}, IP: {report.local_network.local_ip})")
            if report.local_network.wifi:
                print(f"Wi-Fi link       : SSID={report.local_network.wifi.ssid}, RSSI={report.local_network.wifi.rssi_dbm}dBm, Quality={report.local_network.wifi.signal_quality_pct}%")
            print(f"Service probes   : {len(report.service_probes)} executed")
            for sp in report.service_probes:
                print(f"  - {sp.target_id}: reachable={sp.is_reachable}, RTT={sp.icmp_rtt_ms}ms, Loss={sp.icmp_loss_pct}%")
        return 0

    elif args.command == "run":
        if args.interval:
            # Reconstruct config with updated interval
            config = AgentConfig.load_from_dict({**config.to_dict(), "poll_interval_seconds": args.interval})
        runner = EndpointAgentRunner(config=config, enable_uploader=enable_uploader)
        try:
            asyncio.run(runner.start())
            return 0
        except (KeyboardInterrupt, SystemExit):
            return 0


if __name__ == "__main__":
    sys.exit(main())
