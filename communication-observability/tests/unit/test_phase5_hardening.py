"""Nawari Phase 5.1 Hardening Test Suite.

Validates the 7 Principal Engineering Hardening Requirements:
1. Complete Call Lifecycle Correlation (SIP Call-ID, Uniqueid, Linkedid, Channels, Timestamps, 7-Stage Checklist)
2. Simultaneous Call Concurrency Protection
3. Stale Lock Recovery after Abnormal Process Termination
4. Circuit Breaker Persistence Across Process Restarts
5. SIP Outcome and Q.850 Cause Mapping (200, 486, 503, 408, 404, 603)
6. Bidirectional Media Verification & One-Way Audio Diagnostics
7. ITU-T G.107 Mouth-to-Ear Estimated MOS & Missing-Data Invariants
"""

import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from services.voice.config import VoiceSettings
from services.voice.correlator import VoiceEventCorrelator
from services.voice.models import (
    CallOutcome,
    MediaVerificationLevel,
    SyntheticCallRequest,
)
from services.voice.rtp_analyzer import RtpAnalyzer
from services.voice.safety import (
    CallSafetyManager,
    CircuitBreakerError,
    SafetyViolationError,
)


@pytest.fixture
def isolated_safety_manager():
    """Create a CallSafetyManager in an isolated temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = VoiceSettings(
            state_dir=Path(tmpdir),
            allowed_targets=["1001", "1002", "1003", "1004", "0722000000"],
            emergency_blacklist={"911", "112", "999", "000", "100", "991"},
            max_duration_seconds=30.0,
            cooldown_seconds=0.5,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown_seconds=10.0,
        )
        yield CallSafetyManager(settings)


# ------------------------------------------------------------------------------
# Priority 1: Complete Call Lifecycle Correlation
# ------------------------------------------------------------------------------
def test_priority1_complete_call_lifecycle_correlation():
    """Verify correlation captures all identifiers, timestamps, and 7 lifecycle stages."""
    t_start = 1794076000.0
    t_end = 1794076004.5
    action_id = "nawari-audit-99"

    raw_events = [
        {
            "Event": "Newchannel",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "Uniqueid": "1794076000.1",
            "Linkedid": "1794076000.1",
            "CallerIDNum": "1000",
            "ActionID": action_id,
        },
        {
            "Event": "Newchannel",
            "Channel": "Local/1001@nawari-diagnostic-00000001;2",
            "Uniqueid": "1794076000.2",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "VarSet",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "Variable": "SIPCALLID",
            "Value": "kq-session-789xyz@10.2.156.131",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "DialBegin",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "DestChannel": "PJSIP/avaya-sbce-trunk-00000002",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "Newstate",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "ChannelState": "4",
            "ChannelStateDesc": "Ring",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "Newstate",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "ChannelState": "6",
            "ChannelStateDesc": "Up",
            "ConnectedLineNum": "1001",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "RTCPReceived",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "Jitter": "0.003",
            "FractionLost": "0",
            "RTT": "0.020",
            "PacketsSent": "150",
            "PacketsReceived": "149",
            "Linkedid": "1794076000.1",
        },
        {
            "Event": "Hangup",
            "Channel": "Local/1001@nawari-diagnostic-00000001;1",
            "Cause": "16",
            "Cause-txt": "Normal Clearing",
            "Linkedid": "1794076000.1",
        },
    ]

    req = SyntheticCallRequest(target="1001", timeout_seconds=10.0, caller_id="1000")
    res = VoiceEventCorrelator.correlate(
        request=req,
        action_id=action_id,
        events=raw_events,
        t_start=t_start,
        t_end=t_end,
    )

    sig = res.signaling
    assert res.outcome == CallOutcome.ANSWERED
    assert res.success
    assert sig.sip_status_code == 200
    assert sig.hangup_cause == 16

    # Full Identifiers
    assert sig.action_id == action_id
    assert sig.sip_call_id == "kq-session-789xyz@10.2.156.131"
    assert sig.unique_id == "1794076000.1"
    assert sig.linked_id == "1794076000.1"
    assert sig.channel == "Local/1001@nawari-diagnostic-00000001;1"
    assert sig.dest_channel == "PJSIP/avaya-sbce-trunk-00000002"
    assert sig.caller == "1000"
    assert sig.destination == "1001"

    # Latencies
    assert sig.setup_time_ms > 0
    assert sig.ringing_time_ms > 0
    assert sig.duration_seconds == 4.5

    # 7-Stage Lifecycle Verification Checklist
    lc = sig.lifecycle
    assert lc.signaling_established
    assert lc.channel_answered
    assert lc.rtp_tx_observed
    assert lc.rtp_rx_observed
    assert lc.rtcp_received
    assert lc.bidirectional_media
    assert lc.quality_calculated


# ------------------------------------------------------------------------------
# Priority 2: Simultaneous Call Concurrency Protection
# ------------------------------------------------------------------------------
def test_priority2_simultaneous_call_concurrency_lock(isolated_safety_manager):
    """Verify that multiple concurrent threads/processes cannot acquire the lock simultaneously."""
    lock_errors = []
    lock_acquired_count = 0
    lock_event = threading.Event()
    finish_event = threading.Event()

    def worker():
        nonlocal lock_acquired_count
        try:
            with isolated_safety_manager.concurrency_lock():
                lock_acquired_count += 1
                lock_event.set()
                finish_event.wait(timeout=2.0)
        except SafetyViolationError as e:
            lock_errors.append(str(e))

    t1 = threading.Thread(target=worker)
    t1.start()
    assert lock_event.wait(timeout=1.0), "Worker 1 did not acquire lock in time"

    # Second worker attempts while Worker 1 is still holding the lock
    with pytest.raises(SafetyViolationError) as exc_info:
        with isolated_safety_manager.concurrency_lock():
            pass
    assert "concurrency limit" in str(exc_info.value).lower()

    finish_event.set()
    t1.join()
    assert lock_acquired_count == 1


# ------------------------------------------------------------------------------
# Priority 3: Stale Lock Recovery after Process Termination
# ------------------------------------------------------------------------------
def test_priority3_lock_recovery_after_process_termination(isolated_safety_manager):
    """Verify that a lock held by a dead process PID is detected and automatically recovered."""
    lock_path = isolated_safety_manager.settings.lock_file_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a non-existent PID (e.g. 9999999) that is guaranteed to not be running
    dead_pid = 9999999
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"{dead_pid}:{time.time() - 100.0}\n")

    # Manager should detect dead PID and acquire lock cleanly
    with isolated_safety_manager.concurrency_lock():
        # Verify current PID is now written
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        assert str(os.getpid()) in content


# ------------------------------------------------------------------------------
# Priority 4: Circuit Breaker Persistence Across Restarts
# ------------------------------------------------------------------------------
def test_priority4_circuit_breaker_persistence_across_restarts():
    """Verify circuit-breaker state survives process restarts via disk persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        settings = VoiceSettings(
            state_dir=state_dir,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown_seconds=30.0,
        )

        # Instance 1: Trip the breaker
        mgr1 = CallSafetyManager(settings)
        mgr1.record_call_completion(success=False)
        mgr1.record_call_completion(success=False)
        mgr1.record_call_completion(success=False)

        with pytest.raises(CircuitBreakerError):
            mgr1.check_circuit_breaker()

        # Simulate process termination by destroying Instance 1
        del mgr1

        # Instance 2 (new process start): Verify circuit breaker remains TRIPPED
        mgr2 = CallSafetyManager(settings)
        with pytest.raises(CircuitBreakerError) as exc_info:
            mgr2.check_circuit_breaker()
        assert "circuit breaker tripped" in str(exc_info.value).lower()

        # Manual reset on Instance 2
        mgr2.reset_circuit_breaker()
        mgr2.check_circuit_breaker()  # Should not raise


# ------------------------------------------------------------------------------
# Priority 5: SIP Outcomes and Q.850 Cause Mapping
# ------------------------------------------------------------------------------
def test_priority5_sip_outcomes_mapping():
    """Verify correct outcome classification and SIP response mapping across call scenarios."""
    scenarios = [
        # (Cause, App, Expected Outcome, Expected SIP Code)
        (16, "Answer", CallOutcome.ANSWERED, 200),
        (17, "Busy", CallOutcome.BUSY, 486),
        (34, "Congestion", CallOutcome.CONGESTION, 503),
        (18, None, CallOutcome.TIMEOUT, 408),
        (1, None, CallOutcome.FAILED, 404),
        (21, None, CallOutcome.FAILED, 603),
    ]

    for cause, app, expected_outcome, expected_sip in scenarios:
        events = [{"Event": "Newchannel", "Channel": "Local/test;1"}]
        if app:
            events.append({"Event": "Newexten", "Application": app})
        if cause:
            events.append({"Event": "Hangup", "Cause": str(cause), "Cause-txt": "Test"})

        res = VoiceEventCorrelator.correlate(
            request=SyntheticCallRequest(target="1001", timeout_seconds=5.0),
            action_id="test-scenario",
            events=events,
            t_start=100.0,
            t_end=102.0,
        )

        assert res.outcome == expected_outcome, f"Failed for cause {cause}: got {res.outcome}"
        assert res.signaling.sip_status_code == expected_sip, f"Failed for cause {cause}: got {res.signaling.sip_status_code}"


# ------------------------------------------------------------------------------
# Priority 6: Bidirectional Media Verification & One-Way Audio Diagnostics
# ------------------------------------------------------------------------------
def test_priority6_bidirectional_media_verification():
    """Verify classification of bidirectional media and detection of one-way audio."""
    # 1. Full Bidirectional Media
    m_bidi = RtpAnalyzer.from_metrics(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=30.0, packets_sent=500, packets_received=498
    )
    assert m_bidi.verification_level == MediaVerificationLevel.BIDIRECTIONAL
    assert m_bidi.is_valid
    assert m_bidi.estimated_mos is not None and m_bidi.estimated_mos >= 4.0

    # 2. Transmit Only (One-Way Audio: Remote party cannot be heard)
    m_tx = RtpAnalyzer.from_metrics(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=30.0, packets_sent=500, packets_received=0
    )
    assert m_tx.verification_level == MediaVerificationLevel.TRANSMIT_ONLY

    # 3. Receive Only (One-Way Audio: Local mic muted / not transmitting)
    m_rx = RtpAnalyzer.from_metrics(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=30.0, packets_sent=0, packets_received=500
    )
    assert m_rx.verification_level == MediaVerificationLevel.RECEIVE_ONLY

    # 4. No Media (Both Tx and Rx = 0)
    m_none = RtpAnalyzer.from_metrics(
        jitter_ms=5.0, loss_pct=0.0, rtt_ms=30.0, packets_sent=0, packets_received=0
    )
    assert m_none.verification_level == MediaVerificationLevel.NO_MEDIA

    # 5. Unverified (Signaling only, packets None)
    m_unver = RtpAnalyzer.from_metrics(jitter_ms=None, loss_pct=None)
    assert m_unver.verification_level == MediaVerificationLevel.NO_MEDIA
    assert not m_unver.is_valid


# ------------------------------------------------------------------------------
# Priority 7: ITU-T G.107 Mouth-to-Ear Estimated MOS & Invariants
# ------------------------------------------------------------------------------
def test_priority7_mouth_to_ear_estimated_mos_and_invariants():
    """Verify mouth-to-ear delay calculation, codec models, and missing RTCP invariant."""
    # Mouth-to-ear delay calculation
    # RTT = 40ms -> half_rtt = 20ms. Jitter = 5ms -> 2*jitter = 10ms. Packetization = 20ms.
    # Total d = 20 + 10 + 20 = 50ms (well within 100ms conversational limit)
    delay_ms = RtpAnalyzer.calculate_mouth_to_ear_delay(rtt_ms=40.0, jitter_ms=5.0)
    assert delay_ms == 50.0

    # High RTT mouth-to-ear delay
    # RTT = 240ms -> half = 120ms. Jitter = 20ms -> 40ms. Packetization = 20ms -> d = 180ms (> 177.3ms)
    r_factor, mos, d_calc = RtpAnalyzer.calculate_estimated_mos(
        jitter_ms=20.0, loss_pct=1.0, rtt_ms=240.0, codec="G.711u"
    )
    assert d_calc == 180.0
    assert r_factor < 85.0
    assert 3.5 <= mos <= 4.2

    # Codec Comparison: G.711 vs G.729A under identical network conditions
    r_g711, mos_g711, _ = RtpAnalyzer.calculate_estimated_mos(jitter_ms=5.0, loss_pct=0.0, rtt_ms=20.0, codec="G.711u")
    r_g729, mos_g729, _ = RtpAnalyzer.calculate_estimated_mos(jitter_ms=5.0, loss_pct=0.0, rtt_ms=20.0, codec="G.729A")
    assert r_g711 > r_g729, "G.711 uncompressed should have higher R-factor than G.729 compressed"
    assert mos_g711 > mos_g729

    # CRITICAL INVARIANT: Missing RTCP returns UNKNOWN
    m_missing = RtpAnalyzer.from_metrics(jitter_ms=None, loss_pct=None)
    assert not m_missing.is_valid
    assert m_missing.estimated_mos is None
    assert m_missing.mos_score is None
    assert m_missing.r_factor is None

