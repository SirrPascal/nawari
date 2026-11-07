"""Benchmark script measuring empirical runtime resource utilization for the Nawari Endpoint Agent."""

from __future__ import annotations

import asyncio
import os
import resource
import sys
import tempfile
import threading
import time
from typing import Any, Dict

from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.models import ServiceProtocol
from services.endpoint.runner import EndpointAgentRunner


def get_current_rss_mb() -> float:
    """Return current process RSS in Megabytes."""
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    max_rss = rusage.ru_maxrss
    if sys.platform == "darwin":
        return max_rss / (1024 * 1024)
    else:
        return max_rss / 1024


def benchmark_startup_time() -> Dict[str, Any]:
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(
            state_dir=tmpdir,
            spool_dir=f"{tmpdir}/spool",
            targets=[TargetPolicy("t1", "T1", "127.0.0.1", protocol=ServiceProtocol.ICMP)],
        )
        runner = EndpointAgentRunner(config=config)
        t_init = time.monotonic() - t0
        rss_init = get_current_rss_mb()
        return {
            "initialization_time_ms": round(t_init * 1000, 2),
            "idle_rss_mb": round(rss_init, 2),
            "thread_count": threading.active_count(),
        }


async def benchmark_active_workload() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(
            state_dir=tmpdir,
            spool_dir=f"{tmpdir}/spool",
            targets=[
                TargetPolicy("t1", "T1", "127.0.0.1", protocol=ServiceProtocol.ICMP),
                TargetPolicy("t2", "T2", "127.0.0.1", protocol=ServiceProtocol.ICMP),
            ],
        )
        runner = EndpointAgentRunner(config=config)

        # Baseline CPU times
        t_wall_start = time.monotonic()
        t_cpu_start = os.times()

        # Run 5 consecutive diagnostic cycles
        for _ in range(5):
            await runner.run_once()

        t_wall_end = time.monotonic()
        t_cpu_end = os.times()

        delta_proc = (t_cpu_end.user - t_cpu_start.user) + (t_cpu_end.system - t_cpu_start.system)
        delta_wall = t_wall_end - t_wall_start
        cpu_pct = (delta_proc / delta_wall) * 100.0 if delta_wall > 0 else 0.0

        return {
            "five_cycles_duration_seconds": round(delta_wall, 2),
            "active_rss_mb": round(get_current_rss_mb(), 2),
            "average_cpu_pct": round(cpu_pct, 2),
            "spool_count": runner.spooler.get_pending_count(),
        }


def benchmark_logging_overhead() -> Dict[str, Any]:
    logger = setup_agent_logger("bench.logger")
    t0 = time.monotonic()
    for i in range(1000):
        logger.info(f"Test record #{i} with token=secret123 and agent=e4b3c2a1-0000-4000-8000-123456789abc")
    duration = time.monotonic() - t0
    return {
        "thousand_log_lines_ms": round(duration * 1000, 2),
        "microseconds_per_log_line": round((duration / 1000) * 1e6, 2),
    }


def main() -> None:
    print("======================================================================")
    print("NAWARI ENDPOINT AGENT EMPIRICAL RESOURCE BENCHMARK (STAGE 7A)")
    print("======================================================================")
    
    startup_metrics = benchmark_startup_time()
    print(f"Startup & Init Latency : {startup_metrics['initialization_time_ms']} ms")
    print(f"Baseline Idle RSS      : {startup_metrics['idle_rss_mb']} MiB")
    print(f"Baseline Thread Count  : {startup_metrics['thread_count']} threads")

    active_metrics = asyncio.run(benchmark_active_workload())
    print(f"Active Probing RSS     : {active_metrics['active_rss_mb']} MiB")
    print(f"Active CPU Usage       : {active_metrics['average_cpu_pct']}% of 1 core")
    print(f"5 Probe Cycles Duration: {active_metrics['five_cycles_duration_seconds']} s")
    print(f"Spooled Records        : {active_metrics['spool_count']} records")

    log_metrics = benchmark_logging_overhead()
    print(f"Logging Overhead (1000): {log_metrics['thousand_log_lines_ms']} ms ({log_metrics['microseconds_per_log_line']} µs/line)")
    print("======================================================================")


if __name__ == "__main__":
    main()
