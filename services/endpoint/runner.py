"""Endpoint Agent runtime coordinator and execution engine (Stage 7B Baseline)."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from typing import Any, Dict, List, Optional

from services.endpoint.collectors.local_network import LocalNetworkCollector
from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.core.circuit_breaker import CircuitBreaker
from services.endpoint.core.identity import IdentityManager
from services.endpoint.core.lifecycle import AgentLifecycleManager, AgentStatus
from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.core.scheduler import ProbeScheduler
from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.models import (
    AgentMetadata,
    DnsProbeTelemetry,
    EndpointTelemetryReport,
    LocalNetworkTelemetry,
    PathTelemetry,
    ServiceConnectivityTelemetry,
    ServiceProtocol,
    TelemetricEnvironment,
)
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.os_platform.base import PlatformAdapter
from services.endpoint.path import ParisTraceroute
from services.endpoint.probes.dns import DnsProbe
from services.endpoint.probes.http import HttpProbe, HttpStatusOutcome
from services.endpoint.probes.tcp import TcpConnectStatus, TcpProbe
from services.endpoint.probes.tls import TlsHandshakeStatus, TlsProbe

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

        # Stage 7B Probing Engines
        self.dns_probe = DnsProbe(timeout_seconds=3.0)
        self.tcp_probe = TcpProbe(default_timeout_seconds=3.0)
        self.tls_probe = TlsProbe(verify_certificates=True, default_timeout_seconds=3.0)
        self.http_probe = HttpProbe(default_timeout_seconds=5.0)

        # Stage 7C Path Analysis Engine
        self.traceroute = ParisTraceroute(adapter=self.adapter, default_max_hops=15, default_timeout_seconds=1.0)

        self._shutdown_event = asyncio.Event()

        # Register probe tasks
        self._register_default_probes()

    def _register_default_probes(self) -> None:
        """Register Stage 7A and 7B diagnostic probe tasks."""
        # 1. Local Network probe task
        self.scheduler.register_probe(
            probe_id="local_network",
            name="Local Gateway and Interface Diagnostic",
            interval_seconds=float(self.config.poll_interval_seconds),
            timeout_seconds=5.0,
            handler=self._probe_local_network,
        )

        # 2. Service connectivity probe tasks for configured targets
        for target in self.config.targets:
            if not self.config.validate_target_allowed(target):
                logger.warning(f"Target '{target.target_id}' violates security whitelist policy; skipping registration")
                continue

            self.scheduler.register_probe(
                probe_id=f"service_{target.target_id}",
                name=f"Reachability probe to {target.target_name}",
                interval_seconds=float(self.config.poll_interval_seconds),
                timeout_seconds=target.timeout_seconds + 1.0,
                handler=lambda t=target: self._probe_service(t),
            )

    async def _probe_local_network(self) -> LocalNetworkTelemetry:
        """Probe handler for local edge network diagnostics."""
        if not self.circuit_breaker.can_execute():
            logger.warning("Skipping local network probe due to active circuit breaker")
            return self.local_net_collector.collect()

        self.lifecycle.set_status(AgentStatus.PROBING)
        try:
            telemetry = self.local_net_collector.collect()
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

    async def _probe_service(self, target: TargetPolicy) -> ServiceConnectivityTelemetry:
        """Execute protocol-specific reachability and handshake probing (Stage 7B)."""
        destination = target.destination
        port = target.port
        timeout = target.timeout_seconds

        # Protocol dispatch
        if target.protocol == ServiceProtocol.TCP:
            # TCP 3-way handshake measurement
            res = await self.tcp_probe.probe(destination, port or 80, timeout_seconds=timeout)
            return ServiceConnectivityTelemetry(
                target_id=target.target_id,
                target_name=target.target_name,
                destination_ip=destination,
                destination_port=port,
                protocol=ServiceProtocol.TCP,
                is_reachable=res.is_reachable,
                tcp_connect_time_ms=res.connect_time_ms,
                tcp_status=res.status.value,
                error_message=res.error_message,
            )

        elif target.protocol == ServiceProtocol.TLS:
            # TLS handshake measurement
            res = await self.tls_probe.probe(destination, port or 5061, timeout_seconds=timeout)
            return ServiceConnectivityTelemetry(
                target_id=target.target_id,
                target_name=target.target_name,
                destination_ip=destination,
                destination_port=port or 5061,
                protocol=ServiceProtocol.TLS,
                is_reachable=res.is_valid,
                tls_handshake_time_ms=res.handshake_time_ms,
                tls_version=res.tls_version,
                tls_cipher=res.cipher_suite,
                tls_cert_valid=res.is_valid,
                tls_cert_days_remaining=res.cert_days_remaining,
                error_message=res.error_message,
            )

        elif target.protocol in (ServiceProtocol.HTTP, ServiceProtocol.HTTPS):
            # Decomposed HTTP(S) measurement
            scheme = "https" if target.protocol == ServiceProtocol.HTTPS else "http"
            default_port = 443 if scheme == "https" else 80
            url = f"{scheme}://{destination}:{port or default_port}/"
            res = await self.http_probe.probe(url, timeout_seconds=timeout)
            return ServiceConnectivityTelemetry(
                target_id=target.target_id,
                target_name=target.target_name,
                destination_ip=destination,
                destination_port=port or default_port,
                protocol=target.protocol,
                is_reachable=res.is_success,
                dns_lookup_time_ms=res.dns_time_ms,
                tcp_connect_time_ms=res.tcp_time_ms,
                tls_handshake_time_ms=res.tls_time_ms,
                http_status_code=res.status_code,
                http_ttfb_ms=res.ttfb_ms,
                http_total_time_ms=res.total_time_ms,
                http_response_size_bytes=res.response_size_bytes,
                error_message=res.error_message,
            )

        else:
            # Default / ICMP ping
            is_reachable, rtt, loss = self.adapter.ping(destination, count=2, timeout_seconds=timeout)
            return ServiceConnectivityTelemetry(
                target_id=target.target_id,
                target_name=target.target_name,
                destination_ip=destination,
                destination_port=port,
                protocol=ServiceProtocol.ICMP,
                is_reachable=is_reachable,
                icmp_rtt_ms=rtt,
                icmp_loss_pct=loss,
            )

    async def run_once(self) -> EndpointTelemetryReport:
        """Execute a complete diagnostic cycle across DNS, local network, and service probes."""
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

        # 1. Execute DNS probes for configured DNS resolvers or target hostnames
        dns_probes: List[DnsProbeTelemetry] = []
        # Probe local resolution of localhost and configured targets if hostname
        test_domains = ["localhost"]
        for t in self.config.targets:
            if not t.destination.replace(".", "").isdigit():
                test_domains.append(t.destination)

        for domain in set(test_domains):
            try:
                dp = await self.dns_probe.probe(query_name=domain, record_type="A")
                dns_probes.append(dp)
            except Exception as exc:
                logger.warning(f"Error in DNS probe for {domain}: {exc}")

        # 2. Execute Service Probes
        service_probes: List[ServiceConnectivityTelemetry] = []
        for target in self.config.targets:
            if self.config.validate_target_allowed(target):
                sp = await self._probe_service(target)
                service_probes.append(sp)

        # 3. Execute Path Traces for Allowed Targets
        path_traces: List[PathTelemetry] = []
        for target in self.config.targets:
            if self.config.validate_target_allowed(target):
                try:
                    pt = await self.traceroute.trace(
                        target_id=target.target_id,
                        destination_ip=target.destination,
                        target_port=target.port,
                        protocol=target.protocol.value,
                        max_hops=10,
                        timeout_seconds=1.0,
                    )
                    path_traces.append(pt)
                except Exception as exc:
                    logger.warning(f"Error executing path trace to {target.target_id}: {exc}")

        report = EndpointTelemetryReport(
            metadata=metadata,
            local_network=local_net,
            dns_probes=dns_probes,
            service_probes=service_probes,
            path_traces=path_traces,
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
