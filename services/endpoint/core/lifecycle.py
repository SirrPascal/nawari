"""Agent lifecycle, state management, and health telemetry."""

from __future__ import annotations

import os
import signal
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

from services.endpoint.core.identity import IdentityManager, mask_agent_id
from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.core.scheduler import ProbeScheduler
from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.os_platform.base import PlatformAdapter

logger = setup_agent_logger()


class AgentStatus(str, Enum):
    """Operational state of the endpoint agent."""
    INITIALIZING = "INITIALIZING"
    IDLE = "IDLE"
    PROBING = "PROBING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class AgentLifecycleManager:
    """Coordinates startup, health reporting, signal trapping, and clean termination."""

    def __init__(
        self,
        identity_mgr: IdentityManager,
        platform_adapter: PlatformAdapter,
        scheduler: ProbeScheduler,
        spooler: DiskSpooler,
    ) -> None:
        self.identity_mgr = identity_mgr
        self.platform_adapter = platform_adapter
        self.scheduler = scheduler
        self.spooler = spooler
        self.status = AgentStatus.INITIALIZING
        self.start_time = time.time()
        self._shutdown_callbacks: list[Callable[[], None]] = []

    def set_status(self, new_status: AgentStatus) -> None:
        if self.status != new_status:
            logger.info(f"Agent state transition: {self.status.value} -> {new_status.value}")
            self.status = new_status

    def get_health(self) -> Dict[str, Any]:
        """Generate a complete diagnostic snapshot of the agent's runtime health."""
        uptime = time.time() - self.start_time

        # Measure memory RSS and CPU if psutil or resource is available
        rss_bytes = 0
        try:
            import resource
            # ru_maxrss is in KB on Linux, bytes on macOS
            max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if os.uname().sysname == "Darwin":
                rss_bytes = max_rss
            else:
                rss_bytes = max_rss * 1024
        except Exception:
            pass

        return {
            "status": self.status.value,
            "uptime_seconds": round(uptime, 2),
            "agent_id_masked": mask_agent_id(self.identity_mgr.agent_id),
            "hostname": self.identity_mgr.identity.hostname,
            "memory_rss_mb": round(rss_bytes / (1024 * 1024), 2),
            "capabilities": self.platform_adapter.get_capabilities().to_dict(),
            "spool_pending_records": self.spooler.get_pending_count(),
            "scheduler_stats": self.scheduler.get_stats(),
        }

    def register_shutdown_callback(self, cb: Callable[[], None]) -> None:
        self._shutdown_callbacks.append(cb)

    def trigger_shutdown(self) -> None:
        """Execute registered shutdown callbacks and set status to STOPPING."""
        if self.status in (AgentStatus.STOPPING, AgentStatus.STOPPED):
            return
        self.set_status(AgentStatus.STOPPING)
        for cb in self._shutdown_callbacks:
            try:
                cb()
            except Exception as exc:
                logger.warning(f"Error in shutdown callback: {exc}")
        self.set_status(AgentStatus.STOPPED)
