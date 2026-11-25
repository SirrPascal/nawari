"""Unit tests for Nawari Voice Pre-Call Safety Framework and Circuit Breaker."""

import tempfile
import time
from pathlib import Path

import pytest

from services.voice.config import VoiceSettings
from services.voice.models import SyntheticCallRequest
from services.voice.safety import (
    CallSafetyManager,
    CircuitBreakerError,
    CircuitBreakerState,
    SafetyViolationError,
)


@pytest.fixture
def temp_safety_manager():
    """Create a CallSafetyManager in an isolated temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = VoiceSettings(
            state_dir=Path(tmpdir),
            allowed_targets=["1001", "1002", "1003", "1004", "0722000000"],
            emergency_blacklist={"911", "112", "999", "000", "100", "991"},
            max_duration_seconds=30.0,
            cooldown_seconds=1.0,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown_seconds=5.0,
        )
        yield CallSafetyManager(settings)


def test_emergency_numbers_strictly_blocked(temp_safety_manager):
    """Verify that all emergency numbers are unconditionally rejected."""
    for emerg in ["911", "112", "999", "000", "100", "991", "9911", "0911"]:
        req = SyntheticCallRequest(target=emerg)
        with pytest.raises(SafetyViolationError) as exc_info:
            temp_safety_manager.validate_request(req)
        assert "emergency" in str(exc_info.value).lower()


def test_destination_allowlist_enforcement(temp_safety_manager):
    """Verify that non-allowlisted numbers are rejected."""
    # Allowlisted
    temp_safety_manager.validate_request(
        SyntheticCallRequest(target="1001")
    )
    # Record green Stage 1 OPTIONS status to satisfy staging prerequisite for live call
    temp_safety_manager.record_options_status("avaya-sbce-primary", is_reachable=True)
    temp_safety_manager.validate_request(
        SyntheticCallRequest(target="0722000000", live=True, confirm_live_call=True)
    )

    # Unauthorized
    req = SyntheticCallRequest(target="12345678")
    with pytest.raises(SafetyViolationError) as exc_info:
        temp_safety_manager.validate_request(req)
    assert "allowlist" in str(exc_info.value).lower()


def test_timeout_and_duration_limits(temp_safety_manager):
    """Verify that excessive or negative timeouts are rejected."""
    # Exceeds max duration
    req_too_long = SyntheticCallRequest(target="1001", timeout_seconds=45.0)
    with pytest.raises(SafetyViolationError) as exc_info:
        temp_safety_manager.validate_request(req_too_long)
    assert "exceeds hard limit" in str(exc_info.value).lower()

    # Zero or negative timeout
    req_zero = SyntheticCallRequest(target="1001", timeout_seconds=0.0)
    with pytest.raises(SafetyViolationError) as exc_info:
        temp_safety_manager.validate_request(req_zero)
    assert "greater than 0" in str(exc_info.value).lower()


def test_outbound_trunk_requires_live_confirmation(temp_safety_manager):
    """Verify that external destinations require explicit live confirmation."""
    req_unconfirmed = SyntheticCallRequest(target="0722000000", live=False)
    with pytest.raises(SafetyViolationError) as exc_info:
        temp_safety_manager.validate_request(req_unconfirmed)
    assert "live confirmation" in str(exc_info.value).lower()

    # Dry run is allowed without live confirmation
    req_dry_run = SyntheticCallRequest(target="0722000000", dry_run=True)
    temp_safety_manager.validate_request(req_dry_run)


def test_call_cooldown_enforcement(temp_safety_manager):
    """Verify that successive calls within cooldown window are rejected."""
    req = SyntheticCallRequest(target="1001")
    temp_safety_manager.validate_request(req)
    temp_safety_manager.record_call_completion(success=True)

    # Immediate second call should be blocked by cooldown
    with pytest.raises(SafetyViolationError) as exc_info:
        temp_safety_manager.validate_request(req)
    assert "cooldown active" in str(exc_info.value).lower()

    # Wait for cooldown to expire
    time.sleep(1.1)
    temp_safety_manager.validate_request(req)


def test_circuit_breaker_trips_after_consecutive_failures(temp_safety_manager):
    """Verify circuit breaker trips at threshold (3 failures) and rejects subsequent calls."""
    req = SyntheticCallRequest(target="1001")

    # Record 2 failures - breaker should NOT be tripped yet
    temp_safety_manager.record_call_completion(success=False)
    time.sleep(1.1)
    temp_safety_manager.record_call_completion(success=False)
    time.sleep(1.1)
    temp_safety_manager.check_circuit_breaker()

    # Record 3rd failure - breaker trips!
    temp_safety_manager.record_call_completion(success=False)
    time.sleep(1.1)

    with pytest.raises(CircuitBreakerError) as exc_info:
        temp_safety_manager.validate_request(req)
    assert "circuit breaker tripped" in str(exc_info.value).lower()

    # Reset circuit breaker
    temp_safety_manager.reset_circuit_breaker()
    temp_safety_manager.validate_request(req)


def test_concurrency_lock(temp_safety_manager):
    """Verify that multiple concurrent calls cannot acquire the lock simultaneously."""
    with temp_safety_manager.concurrency_lock():
        with pytest.raises(SafetyViolationError) as exc_info:
            with temp_safety_manager.concurrency_lock():
                pass
        assert "concurrency limit" in str(exc_info.value).lower()

