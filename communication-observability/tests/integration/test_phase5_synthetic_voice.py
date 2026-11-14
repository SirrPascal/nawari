"""Phase 5 Integration Acceptance Tests: Voice Observability, SIP Health, and Synthetic Calls.

Validates:
1. Asterisk 22 container health and PJSIP endpoint configuration.
2. AMI TCP connectivity, authentication, and command dispatch.
3. Controlled synthetic call execution across diagnostic loopbacks (1001-1004).
4. Pre-call safety gate (emergency number and allowlist rejection).
5. Accurate SIP status mapping and timing telemetry.
6. Media quality invariant: missing RTCP reports UNKNOWN (never fabricated).
"""

import subprocess
import time

import pytest

from services.voice.ami_client import AmiClient
from services.voice.config import get_voice_settings
from services.voice.models import CallOutcome, SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner


@pytest.fixture(scope="module")
def voice_settings():
    return get_voice_settings()


@pytest.fixture(scope="module")
def voice_runner(voice_settings):
    # Reset any tripped circuit breaker before running integration tests
    runner = SyntheticCallRunner(voice_settings)
    runner.safety.reset_circuit_breaker()
    return runner


def test_01_asterisk_container_healthy():
    """Verify nawari-asterisk container is running and Asterisk core responds."""
    cmd = ["docker", "exec", "nawari-asterisk", "asterisk", "-rx", "core show version"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "Asterisk 22" in res.stdout, f"Unexpected Asterisk version output: {res.stdout}"


def test_02_ami_authentication_and_ping(voice_settings):
    """Verify AMI socket connection, authentication, and Ping response."""
    with AmiClient(
        host=voice_settings.ami_host,
        port=voice_settings.ami_port,
        username=voice_settings.ami_user,
        secret=voice_settings.ami_secret,
        timeout=5.0,
    ) as ami:
        ping_resp = ami.ping()
        assert ping_resp.get("Response") == "Success", f"Ping failed: {ping_resp}"


def test_03_diagnostic_pjsip_endpoints_configured():
    """Verify PJSIP endpoints are loaded in Asterisk."""
    cmd = ["docker", "exec", "nawari-asterisk", "asterisk", "-rx", "pjsip show endpoints"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = res.stdout
    for ep in ["1001", "1002", "1003", "1004", "avaya-sbce-trunk"]:
        assert ep in out, f"Expected endpoint '{ep}' not found in pjsip show endpoints"


def test_04_synthetic_call_echo_1001(voice_runner, voice_settings):
    """Execute synthetic call to loopback 1001 (Echo)."""
    time.sleep(voice_settings.cooldown_seconds + 0.5)
    req = SyntheticCallRequest(target="1001", timeout_seconds=10.0)
    res = voice_runner.execute_call(req)

    assert res.success, f"Echo call failed: {res.error_message}"
    assert res.outcome == CallOutcome.ANSWERED
    assert res.signaling.sip_status_code == 200
    assert res.signaling.hangup_cause in {0, 16}  # Normal clearing or channel teardown



def test_05_synthetic_call_fast_answer_1002(voice_runner, voice_settings):
    """Execute synthetic call to loopback 1002 (Fast Answer & Disconnect)."""
    time.sleep(voice_settings.cooldown_seconds + 0.5)
    req = SyntheticCallRequest(target="1002", timeout_seconds=10.0)
    res = voice_runner.execute_call(req)

    assert res.success, f"Fast answer call failed: {res.error_message}"
    assert res.outcome == CallOutcome.ANSWERED
    assert res.signaling.sip_status_code == 200
    assert res.duration_seconds >= 2.5, f"Expected duration ~3s, got {res.duration_seconds}s"


def test_06_synthetic_call_busy_simulation_1003(voice_runner, voice_settings):
    """Execute synthetic call to busy simulation loopback 1003."""
    time.sleep(voice_settings.cooldown_seconds + 0.5)
    req = SyntheticCallRequest(target="1003", timeout_seconds=10.0)
    res = voice_runner.execute_call(req)

    assert res.outcome == CallOutcome.BUSY
    assert res.signaling.sip_status_code == 486
    assert res.signaling.hangup_cause in {0, 17}


def test_07_synthetic_call_congestion_simulation_1004(voice_runner, voice_settings):
    """Execute synthetic call to congestion simulation loopback 1004."""
    time.sleep(voice_settings.cooldown_seconds + 0.5)
    req = SyntheticCallRequest(target="1004", timeout_seconds=10.0)
    res = voice_runner.execute_call(req)

    assert res.outcome == CallOutcome.CONGESTION
    assert res.signaling.sip_status_code == 503
    assert res.signaling.hangup_cause in {0, 34}



def test_08_safety_gate_rejects_emergency_and_unallowlisted(voice_runner):
    """Verify safety manager blocks 911 and unallowlisted numbers."""
    # Emergency number
    res_emerg = voice_runner.execute_call(SyntheticCallRequest(target="911"))
    assert res_emerg.outcome == CallOutcome.SAFETY_BLOCKED
    assert not res_emerg.success
    assert "emergency" in (res_emerg.error_message or "").lower()

    # Unauthorized destination
    res_unauth = voice_runner.execute_call(SyntheticCallRequest(target="+19998887777"))
    assert res_unauth.outcome == CallOutcome.SAFETY_BLOCKED
    assert not res_unauth.success
    assert "allowlist" in (res_unauth.error_message or "").lower()


def test_09_dry_run_execution(voice_runner):
    """Verify dry-run mode returns safe simulated result without placing calls."""
    req = SyntheticCallRequest(target="1001", dry_run=True)
    res = voice_runner.execute_call(req)

    assert res.success
    assert res.outcome == CallOutcome.DRY_RUN
    assert res.signaling.sip_status_code == 200
    assert not res.media.is_valid


def test_10_missing_rtcp_reports_unknown(voice_runner, voice_settings):
    """CRITICAL DIRECTIVE: Verify missing RTCP telemetry reports UNKNOWN, never healthy."""
    time.sleep(voice_settings.cooldown_seconds + 0.5)
    req = SyntheticCallRequest(target="1001", timeout_seconds=5.0)
    res = voice_runner.execute_call(req)

    # In local loopback without RTCP session, media quality must remain invalid
    assert not res.media.is_valid
    assert res.media.mos_score is None
    assert res.media.r_factor is None

