"""Correlator for AMI events, SIP signaling timing, channel lifecycle, and RTCP quality metrics."""

from typing import Any, Optional

from services.voice.models import (
    CallOutcome,
    MediaLifecycle,
    MediaQualityMetrics,
    MediaVerificationLevel,
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
    """Correlates an AMI event trajectory into structured signaling, channel, and media reports."""

    @classmethod
    def filter_call_events(
        cls, action_id: str, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter event stream to events related to this call by ActionID, Linkedid, or Channel."""
        # Find primary identifiers associated with the action_id
        matched_channels: set[str] = set()
        matched_linked_ids: set[str] = set()
        matched_unique_ids: set[str] = set()

        for ev in events:
            is_match = (
                ev.get("ActionID") == action_id
                or (ev.get("Variable") == "NAWARI_ACTION_ID" and ev.get("Value") == action_id)
                or ev.get("Variable", "").startswith(f"NAWARI_ACTION_ID={action_id}")
            )
            if is_match:
                if ev.get("Channel"):
                    matched_channels.add(ev["Channel"])
                if ev.get("Uniqueid"):
                    matched_unique_ids.add(ev["Uniqueid"])
                if ev.get("Linkedid"):
                    matched_linked_ids.add(ev["Linkedid"])


        # If no explicit action ID was on events, include all events captured during this isolated call window
        if not matched_channels and not matched_linked_ids:
            return events

        filtered = []
        for ev in events:
            ev_act = ev.get("ActionID")
            ev_ch = ev.get("Channel")
            ev_uid = ev.get("Uniqueid")
            ev_lid = ev.get("Linkedid")

            if (
                (ev_act and ev_act == action_id)
                or (ev_ch and ev_ch in matched_channels)
                or (ev_uid and ev_uid in matched_unique_ids)
                or (ev_lid and ev_lid in matched_linked_ids)
            ):
                filtered.append(ev)
                if ev_ch:
                    matched_channels.add(ev_ch)
                if ev_lid:
                    matched_linked_ids.add(ev_lid)

        return filtered if filtered else events

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
        call_events = cls.filter_call_events(action_id, events)

        # 1. Media Telemetry Analysis
        media_metrics = RtpAnalyzer.parse_ami_rtcp_events(call_events)

        # 2. Tracking Lifecycle & Signaling Identifiers
        originate_ts = t_start
        ring_ts: Optional[float] = None
        answer_ts: Optional[float] = None
        hangup_ts: Optional[float] = None

        channel_id: Optional[str] = None
        dest_channel: Optional[str] = None
        unique_id: Optional[str] = None
        linked_id: Optional[str] = None
        sip_call_id: Optional[str] = None
        caller_num: Optional[str] = None
        dest_num: Optional[str] = request.target

        hangup_cause: Optional[int] = None
        hangup_cause_txt: Optional[str] = None

        answered = False
        busy = False
        congestion = False
        signaling_progress = False

        for ev in call_events:
            ev_name = ev.get("Event", "")

            # Capture Channel and Session Identifiers
            if "Channel" in ev and not channel_id:
                channel_id = ev.get("Channel")
            if "DestChannel" in ev and not dest_channel:
                dest_channel = ev.get("DestChannel")
            if "Uniqueid" in ev and not unique_id:
                unique_id = ev.get("Uniqueid")
            if "Linkedid" in ev and not linked_id:
                linked_id = ev.get("Linkedid")

            # SIP Call-ID Extraction (from VarSet or channel variables)
            if ev_name == "VarSet":
                var_name = ev.get("Variable", "")
                if var_name in {"SIPCALLID", "PJSIP_CALL_ID", "SIP_CALL_ID"}:
                    sip_call_id = ev.get("Value")

            # Caller & Callee Identification
            if "CallerIDNum" in ev and ev["CallerIDNum"] and ev["CallerIDNum"] != "<unknown>":
                caller_num = ev["CallerIDNum"]
            if "ConnectedLineNum" in ev and ev["ConnectedLineNum"] and ev["ConnectedLineNum"] != "<unknown>":
                dest_num = ev["ConnectedLineNum"]

            # Dialplan executions
            if ev_name == "Newexten":
                app = ev.get("Application", "")
                if app == "Answer":
                    answered = True
                elif app == "Busy":
                    busy = True
                elif app == "Congestion":
                    congestion = True

            # Channel State Transitions
            if ev_name == "Newstate":
                state = ev.get("ChannelState", "")
                desc = ev.get("ChannelStateDesc", "")
                if state in {"4", "5"} or desc in {"Ring", "Ringing"}:
                    signaling_progress = True
                    if ring_ts is None:
                        ring_ts = t_start + 0.1
                elif state == "6" or desc == "Up":
                    answered = True
                    signaling_progress = True
                    if answer_ts is None:
                        answer_ts = t_start + 0.2

            if ev_name in {"DialBegin", "Ringing"}:
                signaling_progress = True
                if ring_ts is None:
                    ring_ts = t_start + 0.1

            # Hangup and Q.850 Cause Handling
            if ev_name == "Hangup":
                hangup_ts = t_end
                raw_cause = ev.get("Cause")
                if raw_cause is not None:
                    try:
                        val = int(raw_cause)
                        # Retain specific non-zero cause codes rather than overwriting with 0
                        if val > 0 or hangup_cause is None:
                            hangup_cause = val
                            hangup_cause_txt = ev.get("Cause-txt")
                    except ValueError:
                        pass

        # 3. Determine Outcome
        if error_message and not call_events:
            outcome = CallOutcome.FAILED
            success = False
        elif answered or hangup_cause == 16:
            outcome = CallOutcome.ANSWERED
            success = True
        elif busy or hangup_cause == 17:
            outcome = CallOutcome.BUSY
            success = True
        elif congestion or hangup_cause in {34, 38, 41, 42}:
            outcome = CallOutcome.CONGESTION
            success = (request.target == "1004")
        elif hangup_cause in {18, 19}:
            outcome = CallOutcome.TIMEOUT
            success = False
        elif duration_total >= request.timeout_seconds:
            outcome = CallOutcome.TIMEOUT
            success = False
        else:
            outcome = CallOutcome.FAILED
            success = False

        # 4. Map to Standard SIP Status
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

        # 5. Measure Latencies
        setup_ms = 0.0
        if answer_ts:
            setup_ms = max(0.0, (answer_ts - originate_ts) * 1000.0)

        ringing_ms = 0.0
        if ring_ts:
            ringing_ms = max(0.0, (ring_ts - originate_ts) * 1000.0)

        # 6. Build 7-Stage Media Lifecycle Checklist
        has_rtcp = any(ev.get("Event") in {"RTCPReceived", "RTCPSent"} for ev in call_events)
        lifecycle = MediaLifecycle(
            signaling_established=(signaling_progress or answered or sip_code == 200),
            channel_answered=answered,
            rtp_tx_observed=(media_metrics.packets_sent > 0),
            rtp_rx_observed=(media_metrics.packets_received > 0),
            rtcp_received=has_rtcp,
            bidirectional_media=(media_metrics.verification_level == MediaVerificationLevel.BIDIRECTIONAL),
            quality_calculated=media_metrics.is_valid,
        )

        signaling = SipSignalingMetrics(
            setup_time_ms=round(setup_ms, 2),
            ringing_time_ms=round(ringing_ms, 2),
            duration_seconds=round(duration_total, 2),
            sip_status_code=sip_code,
            sip_status_reason=sip_reason,
            hangup_cause=hangup_cause,
            hangup_cause_txt=hangup_cause_txt,
            sip_call_id=sip_call_id,
            action_id=action_id,
            unique_id=unique_id,
            linked_id=linked_id,
            channel=channel_id,
            dest_channel=dest_channel,
            caller=caller_num or request.caller_id,
            destination=dest_num or request.target,
            timestamp_initiated=t_start,
            timestamp_ringing=ring_ts,
            timestamp_answered=answer_ts,
            timestamp_hangup=hangup_ts or t_end,
            lifecycle=lifecycle,
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
            events_captured=call_events,
        )
