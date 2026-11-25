"""Safety controls, concurrency guards, and circuit breaker for voice testing."""

import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Generator, Optional

from services.voice.config import VoiceSettings, get_voice_settings
from services.voice.models import SyntheticCallRequest


class SafetyViolationError(Exception):
    """Raised when a synthetic call violates pre-call safety constraints."""


class CircuitBreakerError(Exception):
    """Raised when consecutive call failures trip the circuit breaker."""


@dataclass
class CircuitBreakerState:
    """State of the consecutive failure circuit breaker."""

    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    is_tripped: bool = False
    total_calls: int = 0
    last_call_time: float = 0.0

    @classmethod
    def load(cls, path: Path) -> "CircuitBreakerState":
        if not path.exists():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return cls(
                    consecutive_failures=int(data.get("consecutive_failures", 0)),
                    last_failure_time=float(data.get("last_failure_time", 0.0)),
                    is_tripped=bool(data.get("is_tripped", False)),
                    total_calls=int(data.get("total_calls", 0)),
                    last_call_time=float(data.get("last_call_time", 0.0)),
                )
        except Exception:
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        tmp.replace(path)


class CallSafetyManager:
    """Enforces pre-call safety validation, concurrency limits, and circuit breaking."""

    def __init__(self, settings: Optional[VoiceSettings] = None):
        self.settings = settings or get_voice_settings()
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)

    def validate_request(self, request: SyntheticCallRequest) -> None:
        """Validate all pre-call safety constraints against the request."""
        target = request.target.strip()
        if not target:
            raise SafetyViolationError("Target phone number or extension cannot be empty")

        # 1. Emergency Blacklist Verification
        self._check_emergency_blacklist(target)

        # 2. Destination Allowlist Verification
        self._check_allowlist(target)

        # 3. Call Duration & Timeout Verification
        if request.timeout_seconds <= 0:
            raise SafetyViolationError(
                f"Timeout {request.timeout_seconds}s must be greater than 0"
            )
        if request.timeout_seconds > self.settings.max_duration_seconds:
            raise SafetyViolationError(
                f"Requested timeout {request.timeout_seconds}s exceeds hard limit "
                f"of {self.settings.max_duration_seconds}s"
            )

        # Dry run bypasses live trunk checks, circuit breaker lock, and cooldown!
        if request.dry_run:
            return

        # 4. Dry-Run / Live Gating for Non-Diagnostic Extensions
        is_diagnostic = target in {"1001", "1002", "1003", "1004"}
        if not is_diagnostic:
            if not request.live or not request.confirm_live_call:
                raise SafetyViolationError(
                    f"Outbound trunk call to '{target}' requires explicit live confirmation: "
                    f"pass live=True and confirm_live_call=True (CLI: --live --confirm-live-call)"
                )
            # Staged validation: require Stage 1 (OPTIONS) reachability
            self.validate_staged_prerequisites(request)

        # 5. Circuit Breaker Check
        self.check_circuit_breaker()

        # 6. Cooldown Verification
        self._check_cooldown()


    def _check_emergency_blacklist(self, target: str) -> None:
        """Reject emergency numbers unconditionally."""
        # Normalize digits
        clean_num = re.sub(r"[^\d]", "", target)

        for emergency in self.settings.emergency_blacklist:
            # Exact match
            if clean_num == emergency:
                raise SafetyViolationError(
                    f"Target '{target}' matches emergency number '{emergency}'. "
                    f"Call unconditionally blocked for safety."
                )
            # Prefix matches e.g. 9911, 0911
            if len(clean_num) > len(emergency) and clean_num.endswith(emergency):
                prefix = clean_num[: -len(emergency)]
                if prefix in {"9", "0", "99", "00"}:
                    raise SafetyViolationError(
                        f"Target '{target}' matches emergency number '{emergency}' with escape prefix '{prefix}'. "
                        f"Call unconditionally blocked for safety."
                    )

    def _check_allowlist(self, target: str) -> None:
        """Ensure destination is explicitly authorized."""
        allowed = set(self.settings.allowed_targets)
        # Always allow internal diagnostic extensions
        allowed.update({"1001", "1002", "1003", "1004"})

        if target not in allowed:
            raise SafetyViolationError(
                f"Destination '{target}' is not in the approved voice destination allowlist: {sorted(allowed)}"
            )

    def _check_cooldown(self) -> None:
        """Ensure minimum cooldown between successive calls."""
        state = CircuitBreakerState.load(self.settings.circuit_breaker_state_path)
        if state.last_call_time > 0:
            elapsed = time.time() - state.last_call_time
            if elapsed < self.settings.cooldown_seconds:
                remaining = self.settings.cooldown_seconds - elapsed
                raise SafetyViolationError(
                    f"Voice test cooldown active: please wait {remaining:.1f}s before next call"
                )

    def check_circuit_breaker(self) -> None:
        """Check if circuit breaker is tripped due to consecutive failures."""
        state = CircuitBreakerState.load(self.settings.circuit_breaker_state_path)
        if state.is_tripped:
            elapsed = time.time() - state.last_failure_time
            if elapsed < self.settings.circuit_breaker_cooldown_seconds:
                remaining = self.settings.circuit_breaker_cooldown_seconds - elapsed
                raise CircuitBreakerError(
                    f"Circuit breaker TRIPPED after {state.consecutive_failures} consecutive failures. "
                    f"Cooldown active for {remaining:.1f}s (or use reset_circuit_breaker)"
                )
            # Auto-reset after cooldown
            state.is_tripped = False
            state.consecutive_failures = 0
            state.save(self.settings.circuit_breaker_state_path)

    def record_call_completion(self, success: bool) -> None:
        """Update circuit breaker and cooldown state upon call completion."""
        state = CircuitBreakerState.load(self.settings.circuit_breaker_state_path)
        state.total_calls += 1
        state.last_call_time = time.time()

        if success:
            state.consecutive_failures = 0
            state.is_tripped = False
        else:
            state.consecutive_failures += 1
            state.last_failure_time = time.time()
            if state.consecutive_failures >= self.settings.circuit_breaker_threshold:
                state.is_tripped = True

        state.save(self.settings.circuit_breaker_state_path)

    def record_options_status(
        self,
        target_peer: str,
        is_reachable: bool,
        rtt_ms: float = 0.0,
        status_code: int = 200,
        status_reason: str = "OK",
    ) -> None:
        """Persist latest SIP OPTIONS qualification result for staged gating."""
        path = self.settings.options_state_path
        data = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[target_peer] = {
            "target_peer": target_peer,
            "is_reachable": is_reachable,
            "rtt_ms": rtt_ms,
            "status_code": status_code,
            "status_reason": status_reason,
            "timestamp": time.time(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)

    def get_last_options_status(self, target_peer: str) -> Optional[dict]:
        """Retrieve latest SIP OPTIONS qualification state for a peer."""
        path = self.settings.options_state_path
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(target_peer)
        except Exception:
            return None

    def validate_staged_prerequisites(self, request: SyntheticCallRequest) -> None:
        """Verify that Stage 1 (SIP OPTIONS) has passed before permitting Stage 2 test calls."""
        target_peer = request.target_entity or "avaya-sbce-primary"
        status = self.get_last_options_status(target_peer)
        if not status:
            raise SafetyViolationError(
                f"Stage 2 test call blocked: No Stage 1 SIP OPTIONS verification on record for '{target_peer}'. "
                f"Run 'nawari-voice options --peer {target_peer}' first."
            )
        if not status.get("is_reachable"):
            code = status.get("status_code", 0)
            reason = status.get("status_reason", "Unreachable")
            raise SafetyViolationError(
                f"Stage 2 test call blocked: Stage 1 SIP OPTIONS to '{target_peer}' failed "
                f"(Status: {code} {reason}). Signaling reachability must be verified first."
            )
        elapsed = time.time() - status.get("timestamp", 0.0)
        if elapsed > self.settings.stage_prerequisite_window_seconds:
            raise SafetyViolationError(
                f"Stage 2 test call blocked: Stage 1 SIP OPTIONS qualification for '{target_peer}' "
                f"expired ({elapsed:.1f}s ago > {self.settings.stage_prerequisite_window_seconds}s limit). "
                f"Refresh SIP OPTIONS qualification first."
            )


    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker state."""
        state = CircuitBreakerState.load(self.settings.circuit_breaker_state_path)
        state.consecutive_failures = 0
        state.is_tripped = False
        state.save(self.settings.circuit_breaker_state_path)

    @contextmanager
    def concurrency_lock(self) -> Generator[None, None, None]:
        """Acquire non-blocking system-wide concurrency lock with automatic stale lock recovery."""
        lock_path = self.settings.lock_file_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        acquired = False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                # Check for dead PID / stale lock
                stale_recovered = False
                try:
                    with open(str(lock_path), "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if ":" in content:
                        pid_str, ts_str = content.split(":", 1)
                        holder_pid = int(pid_str)
                        holder_ts = float(ts_str)
                        # Check if process is still alive
                        try:
                            os.kill(holder_pid, 0)
                        except (ProcessLookupError, OSError):
                            # Process died! Auto-recover lock
                            stale_recovered = True
                        else:
                            # If process has exceeded 2x max duration, flag anomaly
                            if time.time() - holder_ts > (self.settings.max_duration_seconds * 2):
                                stale_recovered = True
                except Exception:
                    pass

                if stale_recovered:
                    # Stale lock holder is dead; try acquiring again
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except (BlockingIOError, OSError):
                        raise SafetyViolationError(
                            "Another synthetic call is currently executing. Concurrency limit is strictly 1."
                        )
                else:
                    raise SafetyViolationError(
                        "Another synthetic call is currently executing. Concurrency limit is strictly 1."
                    )

            # Record holder PID and timestamp
            if acquired:
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                payload = f"{os.getpid()}:{time.time()}\n".encode("utf-8")
                os.write(fd, payload)

            yield
        finally:
            if acquired:
                try:
                    os.ftruncate(fd, 0)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass


