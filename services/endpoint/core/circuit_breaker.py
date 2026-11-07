"""Resource-conscious circuit breaker protecting endpoint CPU and battery."""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

from services.endpoint.core.logger import setup_agent_logger

logger = setup_agent_logger()


class CircuitBreaker:
    """Monitors endpoint resource consumption and trips if thresholds are exceeded."""

    def __init__(
        self,
        max_cpu_pct: float = 25.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.max_cpu_pct = max_cpu_pct
        self.cooldown_seconds = cooldown_seconds
        self.is_tripped = False
        self.tripped_reason: Optional[str] = None
        self.tripped_at: Optional[float] = None
        self._last_cpu_times: Optional[os.times_result] = None
        self._last_check_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Return True if safe to execute probe, or False if circuit breaker is active."""
        if self.is_tripped:
            elapsed = time.monotonic() - (self.tripped_at or 0.0)
            if elapsed < self.cooldown_seconds:
                return False
            # Cooldown expired: attempt reset
            logger.info("Circuit breaker cooldown expired; resetting to CLOSED")
            self.is_tripped = False
            self.tripped_reason = None
            self.tripped_at = None

        # Check process CPU utilization
        cpu_pct = self._estimate_process_cpu()
        if cpu_pct is not None and cpu_pct > self.max_cpu_pct:
            self.trip(f"Process CPU usage ({cpu_pct:.1f}%) exceeded threshold ({self.max_cpu_pct}%)")
            return False

        return True

    def trip(self, reason: str) -> None:
        """Manually or automatically trip the breaker into OPEN state."""
        self.is_tripped = True
        self.tripped_reason = reason
        self.tripped_at = time.monotonic()
        logger.warning(f"Circuit breaker TRIPPED: {reason}. Throttling probes for {self.cooldown_seconds}s.")

    def reset(self) -> None:
        """Reset the breaker to closed state."""
        self.is_tripped = False
        self.tripped_reason = None
        self.tripped_at = None

    def _estimate_process_cpu(self) -> Optional[float]:
        try:
            current_times = os.times()
            now = time.monotonic()
            if self._last_cpu_times is not None and self._last_check_time is not None:
                delta_proc = (current_times.user - self._last_cpu_times.user) + (
                    current_times.system - self._last_cpu_times.system
                )
                delta_wall = now - self._last_check_time
                if delta_wall > 0.1:
                    cpu_pct = (delta_proc / delta_wall) * 100.0
                    self._last_cpu_times = current_times
                    self._last_check_time = now
                    return min(100.0, max(0.0, cpu_pct))

            self._last_cpu_times = current_times
            self._last_check_time = now
            return None
        except Exception:
            return None

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_tripped": self.is_tripped,
            "tripped_reason": self.tripped_reason,
            "tripped_at": self.tripped_at,
            "max_cpu_pct": self.max_cpu_pct,
            "cooldown_seconds": self.cooldown_seconds,
        }
