"""High-level Orchestration Runner for Controlled Synthetic Voice Tests."""

import time
import uuid
from typing import Optional

from services.voice.ami_client import AmiClient, AmiError
from services.voice.config import VoiceSettings, get_voice_settings
from services.voice.correlator import VoiceEventCorrelator
from services.voice.models import (
    CallOutcome,
    MediaQualityMetrics,
    SipSignalingMetrics,
    SyntheticCallRequest,
    SyntheticCallResult,
)
from services.voice.safety import (
    CallSafetyManager,
    CircuitBreakerError,
    SafetyViolationError,
)


class SyntheticCallRunner:
    """Manages pre-flight safety gates, AMI session execution, and metric correlation."""

    def __init__(self, settings: Optional[VoiceSettings] = None):
        self.settings = settings or get_voice_settings()
        self.safety = CallSafetyManager(self.settings)

    def execute_call(self, request: SyntheticCallRequest) -> SyntheticCallResult:
        """Execute a controlled synthetic call with safety validation and telemetry capture."""
        action_id = request.action_id or f"nawari-{uuid.uuid4().hex[:8]}"
        t_start = time.time()

        # 1. Pre-call Safety Gate
        try:
            self.safety.validate_request(request)
        except CircuitBreakerError as e:
            return SyntheticCallResult(
                action_id=action_id,
                target=request.target,
                outcome=CallOutcome.CIRCUIT_BREAKER_TRIPPED,
                success=False,
                timestamp_start=t_start,
                timestamp_end=time.time(),
                duration_seconds=0.0,
                signaling=SipSignalingMetrics(action_id=action_id),
                media=MediaQualityMetrics(is_valid=False),
                error_message=str(e),
            )
        except SafetyViolationError as e:
            return SyntheticCallResult(
                action_id=action_id,
                target=request.target,
                outcome=CallOutcome.SAFETY_BLOCKED,
                success=False,
                timestamp_start=t_start,
                timestamp_end=time.time(),
                duration_seconds=0.0,
                signaling=SipSignalingMetrics(action_id=action_id),
                media=MediaQualityMetrics(is_valid=False),
                error_message=str(e),
            )

        # 2. Dry-Run Bypass
        if request.dry_run:
            t_end = time.time()
            return SyntheticCallResult(
                action_id=action_id,
                target=request.target,
                outcome=CallOutcome.DRY_RUN,
                success=True,
                timestamp_start=t_start,
                timestamp_end=t_end,
                duration_seconds=round(t_end - t_start, 2),
                signaling=SipSignalingMetrics(
                    action_id=action_id,
                    sip_status_code=200,
                    sip_status_reason="Dry Run Simulated OK",
                ),
                media=MediaQualityMetrics(is_valid=False),
                error_message=None,
            )

        # 3. Execution under Concurrency Lock
        events: list[dict[str, str]] = []
        error_msg: Optional[str] = None

        with self.safety.concurrency_lock():
            ami = AmiClient(
                host=self.settings.ami_host,
                port=self.settings.ami_port,
                username=self.settings.ami_user,
                secret=self.settings.ami_secret,
                timeout=self.settings.default_timeout_seconds,
            )

            try:
                ami.connect()
                ami.login()

                # Choose routing context and channel
                is_diagnostic = request.target in {"1001", "1002", "1003", "1004"}
                context = (
                    self.settings.diagnostic_context
                    if is_diagnostic
                    else self.settings.outbound_context
                )
                channel = f"Local/{request.target}@{context}"

                call_vars = {
                    "NAWARI_ACTION_ID": action_id,
                    **request.variables,
                }

                ami.originate(
                    channel=channel,
                    exten=request.target,
                    context=context,
                    priority=1,
                    timeout_ms=int(request.timeout_seconds * 1000),
                    caller_id=request.caller_id or self.settings.default_caller_id,
                    action_id=action_id,
                    variables=call_vars,
                )

                # Collect events until call completion (Hangup) or timeout
                events = ami.collect_events_until(
                    stop_predicate=lambda ev: ev.get("Event") == "Hangup",
                    max_duration_seconds=request.timeout_seconds,
                )

                # Ensure all opened channels are hung up cleanly if deadline was reached
                opened_channels = {
                    ev.get("Channel")
                    for ev in events
                    if ev.get("Event") == "Newchannel" and ev.get("Channel")
                }
                closed_channels = {
                    ev.get("Channel")
                    for ev in events
                    if ev.get("Event") == "Hangup" and ev.get("Channel")
                }
                for unclosed in (opened_channels - closed_channels):
                    try:
                        ami.hangup(unclosed)
                        extra = ami.collect_events_until(
                            stop_predicate=lambda ev: ev.get("Event") == "Hangup",
                            max_duration_seconds=2.0,
                        )
                        events.extend(extra)
                    except Exception:
                        pass


            except AmiError as e:
                error_msg = f"AMI Error: {e}"
            except Exception as e:
                error_msg = f"Unexpected Error: {e}"
            finally:
                ami.disconnect()

        t_end = time.time()

        # 4. Correlation & Metric Synthesis
        result = VoiceEventCorrelator.correlate(
            request=request,
            action_id=action_id,
            events=events,
            t_start=t_start,
            t_end=t_end,
            error_message=error_msg,
        )

        # 5. Record Result in Safety Manager (cooldown & circuit breaker)
        self.safety.record_call_completion(success=result.success)

        return result

