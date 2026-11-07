"""Command-line interface for Nawari Voice Service Assurance & Incident Correlation.

Provides operator commands to trigger synthetic voice probes, publish canonical
telemetry to Zabbix, correlate cross-domain infrastructure alarms, and output
actionable service assurance diagnostics.
"""

import argparse
import json
import sys
import time
from typing import Optional

from services.api.client import ZabbixClient
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import HypothesisStatus, ServiceHealthState
from services.voice.models import SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner
from services.voice.telemetry_schema import CanonicalVoiceEvent
from services.voice.zabbix_sender import ZabbixSender


def format_assurance_report(report_dict: dict) -> str:
    """Format an assurance report as a clean ANSI console summary."""
    state = report_dict.get("health_state", "UNKNOWN")
    score = report_dict.get("health_score", 0.0)

    # State colors
    if state == "HEALTHY":
        state_str = f"\033[92m[ {state} ] (Score: {score}/100)\033[0m"
    elif state == "DEGRADED":
        state_str = f"\033[93m[ {state} ] (Score: {score}/100)\033[0m"
    elif state == "CRITICAL":
        state_str = f"\033[91m[ {state} ] (Score: {score}/100)\033[0m"
    else:
        state_str = f"\033[90m[ {state} ] (Score: {score}/100)\033[0m"

    lines = [
        "================================================================================",
        "                   NAWARI VOICE SERVICE ASSURANCE AUDIT REPORT",
        "================================================================================",
        f"Report ID:    {report_dict.get('report_id')}",
        f"Service ID:   {report_dict.get('service_id')}",
        f"Target Host:  {report_dict.get('target_host')}",
        f"Health State: {state_str}",
        "--------------------------------------------------------------------------------",
        "DOMAIN METRICS SUMMARY:",
        f"  Signaling: Outcome={report_dict['signaling_summary'].get('outcome')} | "
        f"SIP Code={report_dict['signaling_summary'].get('sip_status_code')} | "
        f"Setup Latency={report_dict['signaling_summary'].get('setup_time_ms')}ms",
        f"  Media:     Level={report_dict['media_summary'].get('verification_level')} | "
        f"MOS={report_dict['media_summary'].get('estimated_mos')} | "
        f"Jitter={report_dict['media_summary'].get('jitter_ms')}ms | "
        f"Loss={report_dict['media_summary'].get('loss_pct')}%",
        f"  Infra:     Active Alarms={report_dict['infrastructure_summary'].get('active_problems_count')} "
        f"(Link={report_dict['infrastructure_summary'].get('link_problems_count')}, "
        f"CPU={report_dict['infrastructure_summary'].get('cpu_problems_count')})",
    ]

    ep_summary = report_dict.get("endpoint_summary", {})
    if ep_summary.get("total_endpoints", 0) > 0:
        lines.append(
            f"  Endpoints: Total={ep_summary.get('total_endpoints')} | "
            f"Degraded={ep_summary.get('degraded_endpoints')} | "
            f"DNS Failures={ep_summary.get('dns_failures')}"
        )

    path_summary = report_dict.get("path_summary", {})
    if path_summary.get("total_traces", 0) > 0:
        lines.append(
            f"  Paths:     Traces={path_summary.get('total_traces')} | "
            f"Diverged={path_summary.get('routes_diverged')} | "
            f"Hops w/ Loss={path_summary.get('hops_with_loss')}"
        )

    lines.extend([
        "--------------------------------------------------------------------------------",
        "CORRELATED INCIDENT HYPOTHESES:",
    ])

    for idx, hyp in enumerate(report_dict.get("hypotheses", []), 1):
        status = hyp.get("status")
        domain = hyp.get("root_cause_domain")
        conf = hyp.get("confidence", 0.0)
        lines.append(f"  [{idx}] {hyp.get('title')} (Status: {status}, Domain: {domain}, Confidence: {conf*100:.0f}%)")
        lines.append(f"      Summary: {hyp.get('summary')}")
        if hyp.get("evidence"):
            lines.append("      Evidence:")
            for ev in hyp.get("evidence", []):
                lines.append(f"        - [{ev.get('domain')}] {ev.get('identifier')}: {ev.get('description')}")
        if hyp.get("remediation_recommendations"):
            lines.append("      Recommendations:")
            for rec in hyp.get("remediation_recommendations", []):
                lines.append(f"        * {rec}")

    lines.append("================================================================================")
    return "\n".join(lines)


def cmd_audit(args: argparse.Namespace) -> int:
    """Execute synthetic call probe, publish to Zabbix, correlate and output report."""
    print(f"[*] Initiating Nawari Voice Service Assurance Audit against target: {args.target}")

    runner = SyntheticCallRunner()
    req = SyntheticCallRequest(
        target=args.target,
        timeout_seconds=args.timeout,
        dry_run=args.dry_run,
    )

    # 1. Execute synthetic probe
    call_result = runner.execute_call(req)
    print(f"[*] Synthetic call completed: outcome={call_result.outcome.value}, duration={call_result.duration_seconds:.2f}s")

    # 2. Convert to Canonical Voice Telemetry Event
    event = CanonicalVoiceEvent.from_call_result(call_result, device_id=args.host)

    # 3. Publish to Zabbix Trapper
    if not args.no_zabbix_publish:
        sender = ZabbixSender(host=args.zabbix_server, port=args.zabbix_port)
        try:
            resp = sender.send_voice_event(event)
            print(f"[*] Telemetry published to Zabbix Trapper: {resp.info}")
        except Exception as e:
            print(f"[!] Warning: Failed to publish metrics to Zabbix: {e}", file=sys.stderr)

    # 4. Connect to Zabbix API to query active problems
    client = None
    if not args.offline:
        try:
            from services.api.config import get_settings
            settings = get_settings()
            client = ZabbixClient(settings.zabbix)
            client.connect()
        except Exception as e:
            print(f"[*] Note: Zabbix API client unauthenticated ({e}); proceeding with local correlation.")

    correlator = CrossDomainCorrelator(zabbix_client=client)
    report = correlator.correlate(event)

    if args.json:
        print(report.to_json(indent=2))
    else:
        print(format_assurance_report(report.to_dict()))

    return 0 if report.health_state != ServiceHealthState.CRITICAL else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Nawari Voice Service Assurance CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Run end-to-end synthetic probe and service assurance audit")
    audit_parser.add_argument("--target", default="1001", help="Diagnostic destination number (default: 1001)")
    audit_parser.add_argument("--timeout", type=float, default=10.0, help="Call timeout in seconds")
    audit_parser.add_argument("--dry_run", action="store_true", help="Execute in dry-run mode")
    audit_parser.add_argument("--host", default="nawari-voice-probe-01", help="Zabbix host name for probe")
    audit_parser.add_argument("--zabbix_server", default="127.0.0.1", help="Zabbix server IP (default: 127.0.0.1)")
    audit_parser.add_argument("--zabbix_port", type=int, default=10051, help="Zabbix trapper port (default: 10051)")
    audit_parser.add_argument("--no_zabbix_publish", action="store_true", help="Skip publishing to Zabbix trapper")
    audit_parser.add_argument("--offline", action="store_true", help="Skip querying live Zabbix API")
    audit_parser.add_argument("--json", action="store_true", help="Output report as formatted JSON")

    args = parser.parse_args()
    if args.command == "audit":
        sys.exit(cmd_audit(args))


if __name__ == "__main__":
    main()
