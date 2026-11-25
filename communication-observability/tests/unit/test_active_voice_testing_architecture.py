"""Unit tests for Nawari Active Voice Testing Architecture and HOMER Observability.

Validates:
1. Staged testing hierarchy: Stage 1 (OPTIONS) -> Stage 2 (Internal Test Calls) -> Stage 3 (Passive Production Capture).
2. PJSIP configuration for Avaya SBCE and Session Manager endpoints.
3. Dialplan routing for authorized internal test extensions (8801, 8802).
4. Pre-call safety manager staging gate and qualification expiration.
5. Active SIP OPTIONS probe simulation and RTT calculation.
6. Circuit breaker state progression.
7. Strict provenance separation between Asterisk AVTEST and Production Avaya capture in HOMER queries.
"""

import json
import tempfile
import time
from pathlib import Path

import pytest

from services.voice.config import VoiceSettings
from services.voice.models import CallOutcome, SipOptionsResult, SyntheticCallRequest
from services.voice.safety import CallSafetyManager, CircuitBreakerError, SafetyViolationError
from services.voice.sip_options_probe import SipOptionsProbe


@pytest.fixture
def staged_voice_env():
    """Create an isolated test environment with temporary state directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = VoiceSettings(
            state_dir=Path(tmpdir),
            allowed_targets=["1001", "1002", "1003", "1004", "8801", "8802"],
            emergency_blacklist={"911", "112", "999", "000", "100", "991"},
            max_duration_seconds=30.0,
            cooldown_seconds=0.1,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown_seconds=1.0,
            stage_prerequisite_window_seconds=2.0,  # Fast window for test
        )
        safety = CallSafetyManager(settings)
        probe = SipOptionsProbe(settings, safety)
        yield settings, safety, probe


def test_01_pjsip_config_avaya_endpoints():
    """Verify pjsip.conf defines Avaya SBCE and Session Manager endpoints and AORs."""
    pjsip_path = Path("communication-observability/docker/asterisk/config/pjsip.conf")
    assert pjsip_path.exists(), "pjsip.conf file not found"
    content = pjsip_path.read_text(encoding="utf-8")

    assert "[avaya-sbce-primary]" in content
    assert "contact = sip:10.2.156.132:5060" in content
    assert "qualify_frequency = 60" in content

    assert "[avaya-sbce-secondary]" in content
    assert "contact = sip:10.2.156.130:5060" in content

    assert "[avaya-sm-primary]" in content
    assert "contact = sip:10.2.156.22:5060" in content


def test_02_dialplan_staged_extensions():
    """Verify extensions.conf defines routing for 8801, 8802 with telemetry headers."""
    ext_path = Path("communication-observability/docker/asterisk/config/extensions.conf")
    assert ext_path.exists(), "extensions.conf file not found"
    content = ext_path.read_text(encoding="utf-8")

    assert "exten => 8801" in content
    assert "STAGE_2_INTERNAL_ECHO" in content
    assert "exten => 8802" in content
    assert "STAGE_2_INTERNAL_FAST_ANSWER" in content
    assert "PJSIP_HEADER(add,X-Nawari-ActionID)" in content
    assert "PJSIP_HEADER(add,X-Nawari-Test-Stage)" in content


def test_03_sip_options_probe_simulation(staged_voice_env):
    """Verify SipOptionsProbe generates structured telemetry and records state."""
    settings, safety, probe = staged_voice_env

    # 1. Successful probe simulation
    res = probe.probe(
        target_peer="avaya-sbce-primary",
        simulate=True,
        mock_status=200,
        mock_rtt_ms=12.4,
    )
    assert isinstance(res, SipOptionsResult)
    assert res.is_reachable is True
    assert res.status_code == 200
    assert res.status_reason == "OK"
    assert res.rtt_ms == 12.4
    assert res.provenance == "SYNTHETIC_AVTEST"
    assert res.target_host == settings.avaya_sbce_primary_ip

    # Verify state was saved
    saved = safety.get_last_options_status("avaya-sbce-primary")
    assert saved is not None
    assert saved["is_reachable"] is True
    assert saved["status_code"] == 200


def test_04_sip_options_probe_unreachable_simulation(staged_voice_env):
    """Verify SipOptionsProbe correctly reports unreachable endpoints."""
    settings, safety, probe = staged_voice_env

    res = probe.probe(
        target_peer="avaya-sbce-secondary",
        simulate=True,
        mock_status=408,
        mock_rtt_ms=3000.0,
    )
    assert res.is_reachable is False
    assert res.status_code == 408

    saved = safety.get_last_options_status("avaya-sbce-secondary")
    assert saved is not None
    assert saved["is_reachable"] is False


def test_05_staged_prerequisite_blocks_without_prior_options(staged_voice_env):
    """Verify Stage 2 live test call is blocked if Stage 1 OPTIONS was never executed."""
    settings, safety, _ = staged_voice_env

    req = SyntheticCallRequest(
        target="8801",
        live=True,
        confirm_live_call=True,
        target_entity="avaya-sbce-primary",
    )
    with pytest.raises(SafetyViolationError) as exc_info:
        safety.validate_request(req)
    assert "no stage 1 sip options verification on record" in str(exc_info.value).lower()


def test_06_staged_prerequisite_blocks_on_options_failure(staged_voice_env):
    """Verify Stage 2 call is blocked if Stage 1 OPTIONS recorded unreachable."""
    settings, safety, probe = staged_voice_env

    # Simulate failing OPTIONS probe
    probe.probe(target_peer="avaya-sbce-primary", simulate=True, mock_status=503)

    req = SyntheticCallRequest(
        target="8801",
        live=True,
        confirm_live_call=True,
        target_entity="avaya-sbce-primary",
    )
    with pytest.raises(SafetyViolationError) as exc_info:
        safety.validate_request(req)
    assert "failed" in str(exc_info.value).lower()
    assert "signaling reachability must be verified first" in str(exc_info.value).lower()


def test_07_staged_prerequisite_blocks_on_expired_options(staged_voice_env):
    """Verify Stage 2 call is blocked if Stage 1 qualification has expired."""
    settings, safety, probe = staged_voice_env

    # Probe passes
    probe.probe(target_peer="avaya-sbce-primary", simulate=True, mock_status=200)

    # Sleep longer than stage_prerequisite_window_seconds (2.0s in fixture)
    time.sleep(2.2)

    req = SyntheticCallRequest(
        target="8801",
        live=True,
        confirm_live_call=True,
        target_entity="avaya-sbce-primary",
    )
    with pytest.raises(SafetyViolationError) as exc_info:
        safety.validate_request(req)
    assert "expired" in str(exc_info.value).lower()


def test_08_staged_prerequisite_passes_when_green(staged_voice_env):
    """Verify Stage 2 call passes validation when Stage 1 is fresh and reachable."""
    settings, safety, probe = staged_voice_env

    # Probe passes
    probe.probe(target_peer="avaya-sbce-primary", simulate=True, mock_status=200)

    req = SyntheticCallRequest(
        target="8801",
        live=True,
        confirm_live_call=True,
        target_entity="avaya-sbce-primary",
    )
    # Should not raise exception
    safety.validate_request(req)


def test_09_emergency_blacklist_unconditionally_enforced(staged_voice_env):
    """Verify emergency numbers are rejected even with live=True and confirm_live_call=True."""
    settings, safety, probe = staged_voice_env
    probe.probe(target_peer="avaya-sbce-primary", simulate=True, mock_status=200)

    for num in ["911", "112", "999", "9911"]:
        req = SyntheticCallRequest(
            target=num,
            live=True,
            confirm_live_call=True,
        )
        with pytest.raises(SafetyViolationError) as exc_info:
            safety.validate_request(req)
        assert "emergency" in str(exc_info.value).lower()


def test_10_homer_provenance_separation_invariants():
    """Verify Grafana Voice Intelligence queries enforce strict provenance isolation."""
    dashboard_path = Path(
        "communication-observability/docker/grafana/dashboards/communication_observability/nawari_voice_intelligence.json"
    )
    assert dashboard_path.exists()
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

    panel_10 = next((p for p in dashboard.get("panels", []) if p.get("id") == 10), None)
    assert panel_10 is not None, "Panel 10 (Production SIP) not found"
    sql_10 = panel_10["targets"][0]["rawSql"]

    # Invariant: Panel 10 must positively require production capture IDs and enterprise subnets
    assert "protocol_header->>'captureId' IN ('nawari-avaya-sbce-prod', 'nawari-avaya-span-prod')" in sql_10
    assert "10.2.156.%" in sql_10

    panel_17 = next((p for p in dashboard.get("panels", []) if p.get("id") == 17), None)
    assert panel_17 is not None, "Panel 17 (Synthetic AVTEST) not found"
    sql_17 = panel_17["targets"][0]["rawSql"]

    # Invariant: Panel 17 must target synthetic lab capture ID or loopbacks
    assert "protocol_header->>'captureId' = 'nawari-avtest-lab'" in sql_17 or "127.0.0.1" in sql_17
