"""Resource-conscious probe scheduler with jitter, timeouts, and duplicate execution guards."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from services.endpoint.core.logger import setup_agent_logger

logger = setup_agent_logger()


@dataclass
class ProbeTaskStats:
    """Runtime execution statistics for a scheduled probe task."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    skipped_duplicates: int = 0
    consecutive_failures: int = 0
    current_backoff_seconds: float = 0.0
    last_run_timestamp: Optional[float] = None
    last_duration_seconds: Optional[float] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "skipped_duplicates": self.skipped_duplicates,
            "consecutive_failures": self.consecutive_failures,
            "current_backoff_seconds": self.current_backoff_seconds,
            "last_run_timestamp": self.last_run_timestamp,
            "last_duration_seconds": self.last_duration_seconds,
            "last_error": self.last_error,
        }


@dataclass
class ScheduledProbe:
    """Registered probe definition in the scheduler."""
    probe_id: str
    name: str
    interval_seconds: float
    timeout_seconds: float
    handler: Callable[[], Awaitable[Any]]
    backoff_multiplier: float = 1.5
    max_backoff_seconds: float = 300.0
    stats: ProbeTaskStats = field(default_factory=ProbeTaskStats)


class ProbeScheduler:
    """Asyncio-based scheduler orchestrating diagnostic probe executions.

    Guarantees:
    1. Zero concurrent duplicate execution: A probe task will never run concurrently with itself.
    2. Randomized startup jitter: Staggers probe execution across fleet endpoints.
    3. Per-probe timeouts: Hard timeout prevents frozen network calls from hanging the agent.
    4. Failure backoff: Exponential delay prevents flooding degraded targets.
    5. Clean cancellation: Responds immediately to agent shutdown signals.
    """

    def __init__(self, max_concurrent_tasks: int = 5) -> None:
        self.max_concurrent_tasks = max_concurrent_tasks
        self._probes: Dict[str, ScheduledProbe] = {}
        self._running_probe_ids: Set[str] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._is_running = False
        self._loop_tasks: List[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()

    def register_probe(
        self,
        probe_id: str,
        name: str,
        interval_seconds: float,
        timeout_seconds: float,
        handler: Callable[[], Awaitable[Any]],
        backoff_multiplier: float = 1.5,
        max_backoff_seconds: float = 300.0,
    ) -> None:
        """Register a probe task with the scheduler."""
        if probe_id in self._probes:
            raise ValueError(f"Probe ID '{probe_id}' is already registered in the scheduler")

        self._probes[probe_id] = ScheduledProbe(
            probe_id=probe_id,
            name=name,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            handler=handler,
            backoff_multiplier=backoff_multiplier,
            max_backoff_seconds=max_backoff_seconds,
        )

    async def start(self, max_startup_jitter_seconds: float = 5.0) -> None:
        """Start the scheduler loops for all registered probes with randomized jitter."""
        if self._is_running:
            return

        self._is_running = True
        logger.info(f"Starting ProbeScheduler with {len(self._probes)} registered probes")

        for probe in self._probes.values():
            # Calculate initial randomized jitter
            jitter = random.uniform(0.0, max_startup_jitter_seconds) if max_startup_jitter_seconds > 0 else 0.0
            task = asyncio.create_task(self._run_probe_loop(probe, jitter))
            self._loop_tasks.append(task)

    async def stop(self) -> None:
        """Gracefully stop all scheduler loops and wait for running tasks to cancel."""
        if not self._is_running:
            return

        logger.info("Stopping ProbeScheduler...")
        self._is_running = False

        for task in self._loop_tasks:
            task.cancel()

        if self._loop_tasks:
            await asyncio.gather(*self._loop_tasks, return_exceptions=True)
            self._loop_tasks.clear()

        logger.info("ProbeScheduler stopped cleanly")

    async def execute_probe_once(self, probe_id: str) -> Any:
        """Directly trigger a single execution of a probe task (used for manual/test triggers)."""
        probe = self._probes.get(probe_id)
        if not probe:
            raise KeyError(f"Probe '{probe_id}' not found")
        return await self._dispatch_probe_run(probe)

    async def _run_probe_loop(self, probe: ScheduledProbe, initial_jitter: float) -> None:
        """Independent execution loop for a single probe task."""
        if initial_jitter > 0:
            logger.debug(f"Probe '{probe.probe_id}' waiting {initial_jitter:.2f}s initial jitter")
            try:
                await asyncio.sleep(initial_jitter)
            except asyncio.CancelledError:
                return

        while self._is_running:
            start_time = time.monotonic()
            await self._dispatch_probe_run(probe)

            # Determine sleep duration including backoff
            sleep_duration = probe.interval_seconds + probe.stats.current_backoff_seconds
            elapsed = time.monotonic() - start_time
            remaining_sleep = max(0.1, sleep_duration - elapsed)

            try:
                await asyncio.sleep(remaining_sleep)
            except asyncio.CancelledError:
                break

    async def _dispatch_probe_run(self, probe: ScheduledProbe) -> Any:
        """Execute a probe task with duplicate prevention, concurrency limits, and timeouts."""
        async with self._lock:
            if probe.probe_id in self._running_probe_ids:
                probe.stats.skipped_duplicates += 1
                logger.warning(
                    f"Probe '{probe.probe_id}' is already executing; skipping duplicate scheduled trigger"
                )
                return None
            self._running_probe_ids.add(probe.probe_id)

        probe.stats.total_runs += 1
        t_start = time.monotonic()

        try:
            async with self._semaphore:
                # Enforce per-probe hard timeout
                result = await asyncio.wait_for(
                    probe.handler(),
                    timeout=probe.timeout_seconds,
                )

            # Record success and reset backoff
            duration = time.monotonic() - t_start
            probe.stats.successful_runs += 1
            probe.stats.consecutive_failures = 0
            probe.stats.current_backoff_seconds = 0.0
            probe.stats.last_run_timestamp = time.time()
            probe.stats.last_duration_seconds = duration
            probe.stats.last_error = None
            return result

        except asyncio.TimeoutError:
            duration = time.monotonic() - t_start
            self._record_probe_failure(
                probe, duration, f"Probe timed out after {probe.timeout_seconds}s"
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            duration = time.monotonic() - t_start
            self._record_probe_failure(probe, duration, str(exc))
            return None
        finally:
            async with self._lock:
                self._running_probe_ids.discard(probe.probe_id)

    def _record_probe_failure(
        self, probe: ScheduledProbe, duration: float, error_message: str
    ) -> None:
        probe.stats.failed_runs += 1
        probe.stats.consecutive_failures += 1
        probe.stats.last_run_timestamp = time.time()
        probe.stats.last_duration_seconds = duration
        probe.stats.last_error = error_message

        # Exponential backoff calculation
        if probe.stats.current_backoff_seconds == 0.0:
            probe.stats.current_backoff_seconds = min(5.0, probe.max_backoff_seconds)
        else:
            probe.stats.current_backoff_seconds = min(
                probe.stats.current_backoff_seconds * probe.backoff_multiplier,
                probe.max_backoff_seconds,
            )

        logger.warning(
            f"Probe '{probe.probe_id}' failed: {error_message} (consecutive: {probe.stats.consecutive_failures}, backoff: {probe.stats.current_backoff_seconds:.1f}s)"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Return snapshot of scheduler and probe task execution statistics."""
        return {
            "is_running": self._is_running,
            "active_tasks_count": len(self._running_probe_ids),
            "probes": {
                p.probe_id: {
                    "name": p.name,
                    "interval_seconds": p.interval_seconds,
                    "timeout_seconds": p.timeout_seconds,
                    "stats": p.stats.to_dict(),
                }
                for p in self._probes.values()
            },
        }
