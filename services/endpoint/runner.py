"""Endpoint Agent runtime coordinator and execution engine."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from typing import Any, Dict, Optional

from services.endpoint.collectors.local_network import LocalNetworkCollector
from services.endpoint.config import AgentConfig
from services.endpoint.core.circuit_breaker import CircuitBreaker
from services.endpoint.core.identity import IdentityManager
from services.endpoint.core.lifecycle import AgentLifecycleManager, AgentStatus
from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.core.scheduler import ProbeScheduler
from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.models import (
    AgentMetadata,
    EndpointTelemetryReport,
    LocalNetworkTelemetry,
    ServiceConnectivityTelemetry,
    ServiceProtocol,
    TelemetricEnvironment,
)
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.os_platform.base import PlatformAdapter

logger = setup_agent_logger()


class EndpointAgentRunner:
    """Coordinates lifecycle, scheduled diagnostics, and local spooling."""

    def __init__(
        self,
        config: AgentConfig,
        platform_adapter: Optional[PlatformAdapter] = None,
        identity_manager: Optional[IdentityManager] = None,
    ) -> None:
        self.config = config
        self.adapter = platform_adapter or get_platform_adapter()
        self.identity_mgr = identity_manager or IdentityManager(state_path=f"{config.state_dir}/agent_identity.json")
        self.spooler = DiskSpooler(spool_dir=config.spool_dir, max_records=config.max_spool_records)
        self.circuit_breaker = CircuitBreaker(max_cpu_pct=config.circuit_breaker_max_cpu_pct)
        self.scheduler = ProbeScheduler(max_concurrent_tasks=5)
        self.lifecycle = AgentLifecycleManager(
            identity_mgr=self.identity_mgr,
            platform_adapter=self.adapter,
            scheduler=self.scheduler,
            spooler=self.spooler,
        )
        self.local_net_collector = LocalNetworkCollector(self.adapter)
        self._shutdown_event = asyncio.Event()

        # Register probe tasks
        self._register_default_probes()

    def _register_default_probes(self) -> None:
        """Register Stage 7A diagnostic probe tasks."""
        # 1. Local Network probe task
        self.scheduler.register_probe(
            probe_id="local_network",
            name="Local Gateway and Interface Diagnostic",
            interval_seconds=float(self.config.poll_interval_seconds),
            timeout_seconds=5.0,
            handler=self._probe_local_network,
        )

        # 2. Local mock service reachability task
        for target in self.config.targets:
            if not self.config.validate_target_allowed(target):
                logger.warning(f"Target '{target.target_id}' violates security whitelist policy; skipping registration")
                continue

            self.scheduler.register_probe(
                probe_id=f"service_{target.target_id}",
                name=f"Reachability probe to {target.target_name}",
                interval_seconds=float(self.config.poll_interval_seconds),
                timeout_seconds=target.timeout_seconds,
                handler=lambda t=target: self._probe_service_mock(t),
            )

    async def _probe_local_network(self) -> LocalNetworkTelemetry:
        """Probe handler for local edge network diagnostics."""
        if not self.circuit_breaker.can_execute():
            logger.warning("Skipping local network probe due to active circuit breaker")
            return self.local_net_collector.collect()

        self.lifecycle.set_status(AgentStatus.PROBING)
        try:
            telemetry = self.local_net_collector.collect()
            # Spool to local disk
            metadata = AgentMetadata(
                agent_id=self.identity_mgr.agent_id,
                hostname=self.config.hostname,
                os_name=self.adapter.get_capabilities().os_name,
                os_version=self.adapter.get_capabilities().os_version,
                agent_version="1.0.0",
                timestamp_ns=time.time_ns(),
                environment=self.config.environment,
            )
            report = EndpointTelemetryReport(
                metadata=metadata,
                local_network=telemetry,
            )
            self.spooler.spool(report.to_dict())
            return telemetry
        finally:
            self.lifecycle.set_status(AgentStatus.IDLE)

    async def _probe_service_mock(self, target: Any) -> ServiceConnectivityTelemetry:
        """Controlled local service reachability probe handler for Stage 7A testing."""
        is_reachable, rtt, loss = self.adapter.ping(target.destination, count=1, timeout_seconds=1.0)
        return ServiceConnectivityTelemetry(
            target_id=target.target_id,
            target_name=target.target_name,
            destination_ip=target.destination,
            destination_port=target.port,
            protocol=target.protocol,
            is_reachable=is_reachable,
            icmp_rtt_ms=rtt,
            icmp_loss_pct=loss,
        )

    async def run_once(self) -> EndpointTelemetryReport:
        """Execute a single diagnostic cycle and return the canonical telemetry report."""
        metadata = AgentMetadata(
            agent_id=self.identity_mgr.agent_id,
            hostname=self.config.hostname,
            os_name=self.adapter.get_capabilities().os_name,
            os_version=self.adapter.get_capabilities().os_version,
            agent_version="1.0.0",
            timestamp_ns=time.time_ns(),
            environment=self.config.environment,
        )

        local_net = self.local_net_collector.collect()
        service_probes = []
        for target in self.config.targets:
            if self.config.validate_target_allowed(target):
                sp = await self._probe_service_mock(target)
                service_probes.append(sp)

        report = EndpointTelemetryReport(
            metadata=metadata,
            local_network=local_net,
            service_probes=service_probes,
        )

        self.spooler.spool(report.to_dict())
        return report

    async def start(self) -> None:
        """Start the continuous agent probe loop with signal handling."""
        self.lifecycle.set_status(AgentStatus.IDLE)
        logger.info(
            f"Nawari Endpoint Agent started (OS: {self.adapter.get_capabilities().os_name}, "
            f"Poll Interval: {self.config.poll_interval_seconds}s)"
        )

        # Setup OS signal handlers if in main thread
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._handle_signal)
        except (NotImplementedError, RuntimeError):
            pass

        await self.scheduler.start(max_startup_jitter_seconds=self.config.jitter_max_seconds)
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    def _handle_signal(self) -> None:
        logger.info("Termination signal received; initiating graceful shutdown")
        self.lifecycle.trigger_shutdown()
        self._shutdown_event.set()

    async def stop(self) -> None:
        """Cleanly terminate all scheduler loops and lifecycle resources."""
        self._shutdown_event.set()
        self.lifecycle.set_status(AgentStatus.STOPPING)
        await self.scheduler.stop()
        self.lifecycle.set_status(AgentStatus.STOPPED)
        logger.info("Nawari Endpoint Agent terminated cleanly")
