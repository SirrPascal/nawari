"""CLI Interface for Nawari Controlled Synthetic Voice Testing."""

import argparse
import json
import sys
from typing import Optional

from services.voice.config import get_voice_settings
from services.voice.models import SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner
from services.voice.safety import CallSafetyManager, CircuitBreakerState


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
    call_parser.add_argument("--caller-id", help="Override outbound Caller ID")
    call_parser.add_argument("--json", action="store_true", help="Output results strictly in JSON format")

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

    elif parsed.command == "call":
        req = SyntheticCallRequest(
            target=parsed.target,
            timeout_seconds=parsed.timeout,
            dry_run=parsed.dry_run,
            live=parsed.live,
            confirm_live_call=parsed.confirm_live_call,
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

