"""CLI Interface for Nawari Controlled Synthetic Voice Testing."""

import argparse
import json
import sys
from typing import Optional

from services.voice.config import get_voice_settings
from services.voice.models import SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner
from services.voice.safety import CallSafetyManager, CircuitBreakerState
from services.voice.sip_options_probe import SipOptionsProbe


def format_table_report(result_dict: dict) -> str:
    """Format call result into a clean terminal report."""
    signaling = result_dict.get("signaling", {})
    media = result_dict.get("media", {})

    lines = [
        "=" * 65,
        "NAWARI CONTROLLED SYNTHETIC VOICE TEST REPORT",
        "=" * 65,
        f"Action ID       : {result_dict.get('action_id')}",
        f"Target          : {result_dict.get('target')}",
        f"Outcome         : {result_dict.get('outcome')}",
        f"Success         : {'PASS' if result_dict.get('success') else 'FAIL'}",
        f"Duration        : {result_dict.get('duration_seconds')}s",
        "-" * 65,
        "SIP SIGNALING TELEMETRY:",
        f"  SIP Status    : {signaling.get('sip_status_code')} ({signaling.get('sip_status_reason')})",
        f"  Hangup Cause  : {signaling.get('hangup_cause')} ({signaling.get('hangup_cause_txt')})",
        f"  Setup Time    : {signaling.get('setup_time_ms')} ms",
        f"  Ringing Time  : {signaling.get('ringing_time_ms')} ms",
        f"  Channel       : {signaling.get('channel')}",
        "-" * 65,
        "MEDIA QUALITY TELEMETRY (ITU-T G.107):",
    ]

    if media.get("is_valid"):
        lines.extend([
            f"  MOS Score     : {media.get('mos_score')} / 4.5",
            f"  R-Factor      : {media.get('r_factor')} / 100.0",
            f"  Jitter        : {media.get('jitter_ms')} ms",
            f"  Packet Loss   : {media.get('loss_pct')} %",
            f"  RTT           : {media.get('rtt_ms')} ms",
            f"  Packets Tx/Rx : {media.get('packets_sent')} / {media.get('packets_received')}",
        ])
    else:
        lines.append("  Media Quality : UNKNOWN (No RTCP telemetry received on channel)")

    if result_dict.get("error_message"):
        lines.extend([
            "-" * 65,
            f"ERROR / REASON  : {result_dict.get('error_message')}",
        ])

    lines.append("=" * 65)
    return "\n".join(lines)


def main(args: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nawari-voice",
        description="Nawari Voice Observability & Controlled Synthetic Call Runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Call sub-command
    call_parser = subparsers.add_parser("call", help="Originate a controlled synthetic call")
    call_parser.add_argument("target", help="Destination extension or phone number")
    call_parser.add_argument(
        "--timeout", type=float, default=15.0, help="Maximum call duration in seconds (default: 15.0)"
    )
    call_parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight safety check without initiating call")
    call_parser.add_argument("--live", action="store_true", help="Enable live external trunk call mode")
    call_parser.add_argument(
        "--confirm-live-call",
        action="store_true",
        help="Explicit safety acknowledgment required for external trunk calls",
    )
    call_parser.add_argument("--peer", default="avaya-sbce-primary", help="Target Avaya peer entity")
    call_parser.add_argument("--stage", default="STAGE_2_CONTROLLED_INTERNAL_CALL", help="Staged testing tier")
    call_parser.add_argument("--caller-id", help="Override outbound Caller ID")
    call_parser.add_argument("--json", action="store_true", help="Output results strictly in JSON format")

    # Options sub-command
    opt_parser = subparsers.add_parser("options", help="Execute Stage 1 SIP OPTIONS qualification probe")
    opt_parser.add_argument(
        "--peer",
        default="avaya-sbce-primary",
        choices=["avaya-sbce-primary", "avaya-sbce-secondary", "avaya-sm-primary"],
        help="Target Avaya peer",
    )
    opt_parser.add_argument("--target", help="Override target IP address or hostname")
    opt_parser.add_argument("--port", type=int, default=5060, help="Target SIP port (default: 5060)")
    opt_parser.add_argument("--simulate", action="store_true", help="Simulate SIP OPTIONS response for offline testing")
    opt_parser.add_argument("--mock-status", type=int, default=200, help="Mock status code for simulation")
    opt_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # Circuit Breaker sub-command
    cb_parser = subparsers.add_parser("circuit-breaker", help="Inspect or reset circuit breaker")
    cb_parser.add_argument("action", choices=["status", "reset"], help="Action to execute")

    parsed = parser.parse_args(args)
    settings = get_voice_settings()
    runner = SyntheticCallRunner(settings)

    if parsed.command == "circuit-breaker":
        if parsed.action == "status":
            state = CircuitBreakerState.load(settings.circuit_breaker_state_path)
            print(json.dumps(state.__dict__, indent=2))
            return 0
        elif parsed.action == "reset":
            runner.safety.reset_circuit_breaker()
            print("Circuit breaker has been reset.")
            return 0

    elif parsed.command == "options":
        probe = SipOptionsProbe(settings, runner.safety)
        res = probe.probe(
            target_peer=parsed.peer,
            host=parsed.target,
            port=parsed.port,
            simulate=parsed.simulate,
            mock_status=parsed.mock_status,
        )
        res_dict = res.to_dict()
        if parsed.json:
            print(json.dumps(res_dict, indent=2))
        else:
            print("=" * 65)
            print("NAWARI STAGE 1 SIP OPTIONS QUALIFICATION REPORT")
            print("=" * 65)
            print(f"Target Peer     : {parsed.peer}")
            print(f"Destination     : {res.target_host}:{res.target_port}")
            print(f"Status Code     : {res.status_code} ({res.status_reason})")
            print(f"Round-Trip Time : {res.rtt_ms} ms")
            print(f"Reachability    : {'REACHABLE' if res.is_reachable else 'UNREACHABLE'}")
            print(f"Provenance      : {res.provenance}")
            if res.error_message:
                print(f"Error / Detail  : {res.error_message}")
            print("=" * 65)
        return 0 if res.is_reachable else 1

    elif parsed.command == "call":
        req = SyntheticCallRequest(
            target=parsed.target,
            timeout_seconds=parsed.timeout,
            dry_run=parsed.dry_run,
            live=parsed.live,
            confirm_live_call=parsed.confirm_live_call,
            stage=parsed.stage,
            target_entity=parsed.peer,
            caller_id=parsed.caller_id,
        )

        res = runner.execute_call(req)
        res_dict = res.to_dict()

        if parsed.json:
            print(json.dumps(res_dict, indent=2))
        else:
            print(format_table_report(res_dict))

        return 0 if res.success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

