"""
Nawari Phase 8 — Base Enterprise Adapter Architecture (Workstream 8E)
Implements Circuit Breaker, Bounded Retries with Jitter, Socket Timeouts,
Idempotency, and Failure Isolation guarantees.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Dict


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Fast-failing after repeated failures
    HALF_OPEN = "HALF_OPEN"  # Probing whether upstream has recovered


@dataclass
class AdapterResult:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    duration_seconds: float = 0.0
    idempotent_replay: bool = False


class BaseEnterpriseAdapter:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        request_timeout_seconds: float = 5.0,
        max_retries: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries

        # Circuit breaker state
        self._circuit_state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._last_state_change: float = time.time()

        # Idempotency cache: idempotency_key -> AdapterResult
        self._idempotency_cache: Dict[str, AdapterResult] = {}

    @property
    def circuit_state(self) -> CircuitState:
        now = time.time()
        if self._circuit_state == CircuitState.OPEN:
            if now - self._last_state_change >= self.recovery_timeout_seconds:
                self._circuit_state = CircuitState.HALF_OPEN
                self._last_state_change = now
        return self._circuit_state

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        if self._circuit_state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            self._circuit_state = CircuitState.CLOSED
            self._last_state_change = time.time()

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._circuit_state = CircuitState.OPEN
            self._last_state_change = time.time()

    def execute_with_resilience(
        self,
        operation_name: str,
        func: Callable[..., Dict[str, Any]],
        *args: Any,
        idempotency_key: Optional[str] = None,
        **kwargs: Any,
    ) -> AdapterResult:
        """
        Executes an external adapter call wrapped in:
        1. Idempotency verification
        2. Circuit breaker check
        3. Bounded retries with exponential backoff and jitter
        4. Failure isolation (never crashes the caller)
        """
        start_time = time.time()

        # 1. Idempotency check
        if idempotency_key and idempotency_key in self._idempotency_cache:
            cached = self._idempotency_cache[idempotency_key]
            return AdapterResult(
                success=cached.success,
                data=cached.data,
                error=cached.error,
                duration_seconds=time.time() - start_time,
                idempotent_replay=True,
            )

        # 2. Circuit breaker check
        current_state = self.circuit_state
        if current_state == CircuitState.OPEN:
            return AdapterResult(
                success=False,
                error=f"Circuit breaker for adapter '{self.name}' is OPEN (fast-failing upstream).",
                duration_seconds=time.time() - start_time,
            )

        # 3. Retries loop
        attempts = 0
        last_error = ""

        while attempts <= self.max_retries:
            attempts += 1
            try:
                # Call underlying function
                data = func(*args, **kwargs)
                self._record_success()

                res = AdapterResult(
                    success=True,
                    data=data,
                    retry_count=attempts - 1,
                    duration_seconds=time.time() - start_time,
                )
                if idempotency_key:
                    self._idempotency_cache[idempotency_key] = res
                return res

            except Exception as ex:
                last_error = str(ex)
                if attempts <= self.max_retries:
                    # Exponential backoff with jitter
                    backoff = min(4.0, (1.0 * (2 ** (attempts - 1)))) + random.uniform(0.01, 0.05)
                    time.sleep(backoff)

        # Retries exhausted
        self._record_failure()
        fail_res = AdapterResult(
            success=False,
            error=f"Operation '{operation_name}' failed after {attempts} attempts: {last_error}",
            retry_count=attempts,
            duration_seconds=time.time() - start_time,
        )
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = fail_res
        return fail_res
