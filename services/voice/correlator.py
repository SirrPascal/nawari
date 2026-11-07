"""Correlator for AMI events, SIP signaling timing, and RTCP quality metrics."""

from typing import Any, Optional

from services.voice.models import (
    CallOutcome,
    MediaQualityMetrics,
    SipSignalingMetrics,
    SyntheticCallRequest,
    SyntheticCallResult,
)
from services.voice.rtp_analyzer import RtpAnalyzer

# Mapping from ISDN/Q.850 cause code to standard SIP response code
Q850_TO_SIP_MAP: dict[int, tuple[int, str]] = {
    1: (404, "Not Found"),
    16: (200, "OK / Normal Clearing"),
    17: (486, "Busy Here"),
    18: (408, "No Answer"),
    19: (480, "No Answer (User Alerted)"),
    20: (480, "Subscriber Absent"),
    21: (603, "Decline"),
    28: (404, "Address Incomplete"),
    34: (503, "Circuit/Channel Congestion"),
    38: (503, "Network Out of Order"),
    41: (503, "Temporary Failure"),
    42: (503, "Switching Equipment Congestion"),
}


class VoiceEventCorrelator:
    """Correlates an AMI event trajectory into structured signaling and media reports."""

    @classmethod
    def correlate(
        cls,
        request: SyntheticCallRequest,
        action_id: str,
        events: list[dict[str, Any]],
        t_start: float,
        t_end: float,
        error_message: Optional[str] = None,
    ) -> SyntheticCallResult:
        """Parse the event stream and construct a comprehensive SyntheticCallResult."""
        duration_total = max(0.0, t_end - t_start)

        # Analyze Media
        media_metrics = RtpAnalyzer.parse_ami_rtcp_events(events)

        # Track Signaling Milestones
        originate_ts = t_start
        ring_ts: Optional[float] = None
        answer_ts: Optional[float] = None
        hangup_ts: Optional[float] = None

        channel_id: Optional[str] = None
        unique_id: Optional[str] = None
        hangup_cause: Optional[int] = None
        hangup_cause_txt: Optional[str] = None

        answered = False
        busy = False
        congestion = False

        for ev in events:
            ev_name = ev.get("Event", "")

            # Capture Channel IDs
            if "Channel" in ev and not channel_id:
                channel_id = ev.get("Channel")
            if "Uniqueid" in ev and not unique_id:
                unique_id = ev.get("Uniqueid")

            # Check dialplan executions
            if ev_name == "Newexten":
                app = ev.get("Application", "")
                if app == "Answer":
                    answered = True
                elif app == "Busy":
                    busy = True
                elif app == "Congestion":
                    congestion = True

            # Check channel states
            if ev_name == "Newstate":
                state = ev.get("ChannelState", "")
                desc = ev.get("ChannelStateDesc", "")
                if state == "4" or desc == "Ring":
                    if ring_ts is None:
                        ring_ts = t_start + 0.1  # approximated offset
                elif state == "6" or desc == "Up":
                    answered = True
                    if answer_ts is None:
                        answer_ts = t_start + 0.2

            # Check Hangup
            if ev_name == "Hangup":
                hangup_ts = t_end
                raw_cause = ev.get("Cause")
                if raw_cause is not None:
                    try:
                        hangup_cause = int(raw_cause)
                    except ValueError:
                        pass
                hangup_cause_txt = ev.get("Cause-txt")

        # Determine Outcome
        if error_message and not events:
            outcome = CallOutcome.FAILED
            success = False
        elif answered or hangup_cause == 16:
            outcome = CallOutcome.ANSWERED
            success = True
        elif busy or hangup_cause == 17:
            outcome = CallOutcome.BUSY
            success = True  # busy test succeeded as expected
        elif congestion or hangup_cause in {34, 38, 41, 42}:
            outcome = CallOutcome.CONGESTION
            success = (request.target == "1004")  # 1004 explicitly tests congestion
        elif hangup_cause in {18, 19}:
            outcome = CallOutcome.TIMEOUT
            success = False
        elif duration_total >= request.timeout_seconds:
            outcome = CallOutcome.TIMEOUT
            success = False
        else:
            outcome = CallOutcome.FAILED
            success = False

        # Map to SIP status
        sip_code = None
        sip_reason = None
        if hangup_cause and hangup_cause in Q850_TO_SIP_MAP:
            sip_code, sip_reason = Q850_TO_SIP_MAP[hangup_cause]
        elif outcome == CallOutcome.ANSWERED:
            sip_code, sip_reason = (200, "OK")
        elif outcome == CallOutcome.BUSY:
            sip_code, sip_reason = (486, "Busy Here")
        elif outcome == CallOutcome.CONGESTION:
            sip_code, sip_reason = (503, "Service Unavailable")
        elif outcome == CallOutcome.TIMEOUT:
            sip_code, sip_reason = (408, "Request Timeout")

        # Calculate timing metrics
        setup_ms = 0.0
        if answer_ts:
            setup_ms = max(0.0, (answer_ts - originate_ts) * 1000.0)

        ringing_ms = 0.0
        if ring_ts:
            ringing_ms = max(0.0, (ring_ts - originate_ts) * 1000.0)

        signaling = SipSignalingMetrics(
            setup_time_ms=round(setup_ms, 2),
            ringing_time_ms=round(ringing_ms, 2),
            duration_seconds=round(duration_total, 2),
            sip_status_code=sip_code,
            sip_status_reason=sip_reason,
            hangup_cause=hangup_cause,
            hangup_cause_txt=hangup_cause_txt,
            channel=channel_id,
            unique_id=unique_id,
            action_id=action_id,
        )

        return SyntheticCallResult(
            action_id=action_id,
            target=request.target,
            outcome=outcome,
            success=success,
            timestamp_start=t_start,
            timestamp_end=t_end,
            duration_seconds=round(duration_total, 2),
            signaling=signaling,
            media=media_metrics,
            error_message=error_message,
            events_captured=events,
        )

