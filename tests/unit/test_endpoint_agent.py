"""Comprehensive unit test suite for Stage 7A: Endpoint Agent Core & Platform Abstraction."""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.endpoint.collectors.local_network import LocalNetworkCollector
from services.endpoint.config import AgentConfig, ConfigurationError, TargetPolicy
from services.endpoint.core.circuit_breaker import CircuitBreaker
from services.endpoint.core.identity import (
    EndpointIdentity,
    IdentityCorruptError,
    IdentityManager,
    mask_agent_id,
)
from services.endpoint.core.lifecycle import AgentLifecycleManager, AgentStatus
from services.endpoint.core.logger import SanitizingFormatter, setup_agent_logger
from services.endpoint.core.scheduler import ProbeScheduler, ScheduledProbe
from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.models import (
    AgentMetadata,
    EndpointTelemetryReport,
    HopResponseStatus,
    HopTelemetry,
    InterfaceState,
    InterfaceType,
    LocalNetworkTelemetry,
    ServiceProtocol,
    TelemetricEnvironment,
    WifiMetrics,
)
from services.endpoint.os_platform.base import PlatformAdapter, PlatformCapabilities
from services.endpoint.runner import EndpointAgentRunner


# =====================================================================
# 1. Identity Tests
# =====================================================================

def test_identity_persistence_and_restart():
    """Verify that agent identity is generated once and survives restarts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = str(Path(tmpdir) / "agent_id.json")
        mgr1 = IdentityManager(state_path=state_file)
        id1 = mgr1.agent_id

        # Verify UUIDv4 format
        parsed_uuid = uuid.UUID(id1, version=4)
        assert str(parsed_uuid) == id1

        # Second instance simulating process restart
        mgr2 = IdentityManager(state_path=state_file)
        id2 = mgr2.agent_id
        assert id1 == id2
        assert mgr2.identity.re_registration_count == 0


def test_identity_corrupted_file_recovery():
    """Verify that corrupt identity file halts with IdentityCorruptError and requires explicit recovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "agent_id.json"
        
        # Write corrupted JSON
        state_file.write_text("{malformed: json", encoding="utf-8")

        mgr = IdentityManager(state_path=str(state_file))
        
        # Must raise IdentityCorruptError rather than silently generating new identity
        with pytest.raises(IdentityCorruptError, match="Automatic identity re-generation is disabled"):
            _ = mgr.agent_id

        # Verify backup of corrupted file was created for forensics
        corrupt_backups = list(Path(tmpdir).glob("*.corrupt.*"))
        assert len(corrupt_backups) == 1

        # Explicit operator re-registration with force=True succeeds
        new_identity = mgr.re_register(force=True)
        assert uuid.UUID(new_identity.agent_id, version=4)
        assert new_identity.re_registration_count == 1
        assert mgr.agent_id == new_identity.agent_id


def test_identity_masking():
    """Verify agent ID masking in logs."""
    raw_uuid = "e4b3c2a1-0000-4000-8000-123456789abc"
    masked = mask_agent_id(raw_uuid)
    assert masked == "e4b3****-****-****-****-****9abc"
    assert mask_agent_id("") == "********"


def test_identity_re_registration():
    """Verify explicit re-registration creates a new identity with incremented counter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = str(Path(tmpdir) / "agent_id.json")
        mgr = IdentityManager(state_path=state_file)
        id1 = mgr.agent_id

        new_identity = mgr.re_register(force=True)
        assert new_identity.agent_id != id1
        assert new_identity.re_registration_count == 1

        # Restart check
        mgr_restart = IdentityManager(state_path=state_file)
        assert mgr_restart.agent_id == new_identity.agent_id
        assert mgr_restart.identity.re_registration_count == 1


# =====================================================================
# 2. Configuration & Zero-RCE Security Tests
# =====================================================================

def test_target_policy_valid():
    """Verify valid target policy creation."""
    target = TargetPolicy(
        target_id="sbce-sig-01",
        target_name="Avaya SBCE",
        destination="10.250.1.10",
        port=5061,
        protocol=ServiceProtocol.TCP,
        timeout_seconds=2.5,
    )
    assert target.destination == "10.250.1.10"
    assert target.port == 5061


def test_target_policy_rejects_shell_metacharacters():
    """Zero-RCE: Reject targets containing shell metacharacters."""
    dangerous_targets = [
        "10.0.0.1; rm -rf /",
        "sbce.local | cat /etc/passwd",
        "sbce`whoami`.kq.internal",
        "10.0.0.1 && echo hacked",
        "sbce$(reboot)",
        "destination\nnewline",
    ]
    for dt in dangerous_targets:
        with pytest.raises(ConfigurationError, match="forbidden shell metacharacters"):
            TargetPolicy(
                target_id="test-probe",
                target_name="Test",
                destination=dt,
            )


def test_config_whitelist_validation():
    """Verify destination whitelist enforcement."""
    config = AgentConfig(
        allowed_domains=["*.kq.internal", "localhost"],
        allowed_subnets=["10.0.0.0/8", "127.0.0.0/8"],
    )

    allowed_target_ip = TargetPolicy(target_id="t1", target_name="T1", destination="10.200.1.5")
    allowed_target_dns = TargetPolicy(target_id="t2", target_name="T2", destination="sbce.kq.internal")
    forbidden_target_ip = TargetPolicy(target_id="t3", target_name="T3", destination="8.8.8.8")
    forbidden_target_dns = TargetPolicy(target_id="t4", target_name="T4", destination="evil.com")

    assert config.validate_target_allowed(allowed_target_ip) is True
    assert config.validate_target_allowed(allowed_target_dns) is True
    assert config.validate_target_allowed(forbidden_target_ip) is False
    assert config.validate_target_allowed(forbidden_target_dns) is False


def test_config_numeric_bounds():
    """Verify strict validation of polling intervals and limits."""
    with pytest.raises(ConfigurationError, match="poll_interval_seconds out of range"):
        AgentConfig(poll_interval_seconds=1)  # Below 5s min

    with pytest.raises(ConfigurationError, match="jitter_max_seconds out of range"):
        AgentConfig(jitter_max_seconds=120.0)  # Exceeds 60s max


# =====================================================================
# 3. Structured Logging & Token Sanitization Tests
# =====================================================================

def test_logging_sanitizer():
    """Verify log formatter automatically redacts tokens and masks UUIDs."""
    formatter = SanitizingFormatter(json_output=False)
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Connecting with api_token=secret_xyz123 and agent e4b3c2a1-0000-4000-8000-123456789abc",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "secret_xyz123" not in formatted
    assert "api_token=***REDACTED***" in formatted
    assert "e4b3****-****-****-****-****9abc" in formatted


# =====================================================================
# 4. Probe Scheduler Tests
# =====================================================================

def test_scheduler_duplicate_execution_prevention():
    """Verify the scheduler prevents simultaneous duplicate execution of the same probe."""
    async def _test():
        scheduler = ProbeScheduler(max_concurrent_tasks=2)
        execution_count = 0
        gate_event = asyncio.Event()

        async def slow_probe():
            nonlocal execution_count
            execution_count += 1
            await gate_event.wait()
            return "done"

        scheduler.register_probe(
            probe_id="p1",
            name="Slow Probe",
            interval_seconds=0.1,
            timeout_seconds=5.0,
            handler=slow_probe,
        )

        # Launch task 1
        t1 = asyncio.create_task(scheduler._dispatch_probe_run(scheduler._probes["p1"]))
        await asyncio.sleep(0.01)

        # Attempt concurrent launch of same probe task
        t2 = asyncio.create_task(scheduler._dispatch_probe_run(scheduler._probes["p1"]))
        res2 = await t2

        # Second launch must be skipped
        assert res2 is None
        assert scheduler._probes["p1"].stats.skipped_duplicates == 1
        assert execution_count == 1

        # Release first task
        gate_event.set()
        res1 = await t1
        assert res1 == "done"
        assert scheduler._probes["p1"].stats.successful_runs == 1

    asyncio.run(_test())


def test_scheduler_timeout_and_backoff():
    """Verify hard timeout terminates hanging tasks and triggers exponential backoff."""
    async def _test():
        scheduler = ProbeScheduler()

        async def hanging_probe():
            await asyncio.sleep(10.0)

        scheduler.register_probe(
            probe_id="hang",
            name="Hanging Probe",
            interval_seconds=1.0,
            timeout_seconds=0.05,
            handler=hanging_probe,
            backoff_multiplier=2.0,
        )

        res = await scheduler._dispatch_probe_run(scheduler._probes["hang"])
        assert res is None
        probe = scheduler._probes["hang"]
        assert probe.stats.failed_runs == 1
        assert probe.stats.consecutive_failures == 1
        assert probe.stats.current_backoff_seconds == 5.0
        assert "timed out" in (probe.stats.last_error or "")

    asyncio.run(_test())


def test_scheduler_lifecycle_and_cancellation():
    """Verify scheduler startup, loop execution, and graceful cancellation."""
    async def _test():
        scheduler = ProbeScheduler()
        counter = 0

        async def quick_probe():
            nonlocal counter
            counter += 1

        scheduler.register_probe(
            probe_id="fast",
            name="Fast Probe",
            interval_seconds=0.05,
            timeout_seconds=1.0,
            handler=quick_probe,
        )

        await scheduler.start(max_startup_jitter_seconds=0.0)
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert counter >= 2
        assert scheduler._is_running is False

    asyncio.run(_test())


# =====================================================================
# 5. Local Network Collector & Invariants Tests
# =====================================================================

def test_local_network_collector_invariants():
    """Verify collector enforces telemetry invariants."""
    mock_adapter = MagicMock(spec=PlatformAdapter)
    mock_adapter.get_default_gateway.return_value = ("192.168.1.1", "00:11:22:33:44:55", "eth0")
    mock_adapter.get_interface_details.return_value = {
        "local_ip": "192.168.1.100",
        "subnet_cidr": 24,
        "state": InterfaceState.UP,
        "type": InterfaceType.ETHERNET,
        "dhcp_enabled": True,
    }
    mock_adapter.get_wifi_metrics.return_value = None
    mock_adapter.get_configured_dns_servers.return_value = ["1.1.1.1"]
    mock_adapter.ping.return_value = (True, 2.5, 0.0)

    collector = LocalNetworkCollector(mock_adapter)
    telemetry = collector.collect()

    assert telemetry.default_gateway_ip == "192.168.1.1"
    assert telemetry.gateway_is_reachable is True
    assert telemetry.gateway_rtt_ms == 2.5
    assert telemetry.gateway_loss_pct == 0.0
    assert telemetry.interface_type == InterfaceType.ETHERNET
    assert telemetry.wifi is None  # Invariant 2: None for Ethernet


def test_wifi_isolation_invariant():
    """Verify ValueError is raised if Wi-Fi metrics are attached to Ethernet."""
    with pytest.raises(ValueError, match="Wi-Fi metrics must be None"):
        LocalNetworkTelemetry(
            default_gateway_ip="10.0.0.1",
            default_gateway_mac=None,
            gateway_is_reachable=True,
            gateway_rtt_ms=1.0,
            gateway_loss_pct=0.0,
            interface_name="eth0",
            interface_type=InterfaceType.ETHERNET,
            interface_state=InterfaceState.UP,
            local_ip="10.0.0.50",
            subnet_cidr=24,
            dhcp_enabled=True,
            wifi=WifiMetrics(ssid="Corporate_HQ", rssi_dbm=-65),
        )


# =====================================================================
# 6. Disk Spooler Tests
# =====================================================================

def test_disk_spooler_operations():
    """Verify bounded spooling, peek, purge, and corruption resistance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spooler = DiskSpooler(spool_dir=tmpdir, max_records=5)

        # Spool 3 records
        for i in range(3):
            spooler.spool({"record_id": i, "val": i * 10})

        assert spooler.get_pending_count() == 3

        # Peek
        records = spooler.peek(limit=2)
        assert len(records) == 2
        assert records[0]["record_id"] == 0
        assert records[1]["record_id"] == 1

        # Purge oldest 2
        purged = spooler.purge(2)
        assert purged == 2
        assert spooler.get_pending_count() == 1

        remaining = spooler.peek(limit=10)
        assert len(remaining) == 1
        assert remaining[0]["record_id"] == 2


def test_disk_spooler_corruption_handling():
    """Verify spool reader skips corrupt lines without failing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spooler = DiskSpooler(spool_dir=tmpdir, max_records=10)
        spool_file = Path(tmpdir) / "telemetry_spool.jsonl"

        # Write mixed valid and corrupt records
        with open(spool_file, "w") as f:
            f.write(json.dumps({"id": 1}) + "\n")
            f.write("corrupt_non_json_line\n")
            f.write(json.dumps({"id": 2}) + "\n")

        records = spooler.peek(limit=10)
        assert len(records) == 2
        assert records[0]["id"] == 1
        assert records[1]["id"] == 2


# =====================================================================
# 7. Circuit Breaker Tests
# =====================================================================

def test_circuit_breaker_trip_and_cooldown():
    """Verify circuit breaker trips and respects cooldown."""
    cb = CircuitBreaker(max_cpu_pct=25.0, cooldown_seconds=0.1)
    assert cb.can_execute() is True

    # Manually trip
    cb.trip("CPU overload test")
    assert cb.can_execute() is False

    # Wait for cooldown
    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.is_tripped is False


# =====================================================================
# 8. Agent Lifecycle & Runner Tests
# =====================================================================

def test_agent_runner_run_once():
    """Verify single diagnostic cycle produces valid canonical report."""
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                poll_interval_seconds=30,
                targets=[
                    TargetPolicy(
                        target_id="mock-gw",
                        target_name="Mock Gateway",
                        destination="127.0.0.1",
                        port=80,
                        protocol=ServiceProtocol.ICMP,
                    )
                ],
            )

            mock_adapter = MagicMock(spec=PlatformAdapter)
            mock_adapter.get_capabilities.return_value = PlatformCapabilities(
                os_name="TestOS",
                os_version="1.0",
                architecture="x86_64",
                supports_raw_icmp=False,
                supports_unprivileged_icmp=True,
                supports_wifi_diagnostics=False,
                supports_gateway_discovery=True,
                supports_dns_discovery=True,
            )
            mock_adapter.get_default_gateway.return_value = ("127.0.0.1", None, "lo0")
            mock_adapter.get_interface_details.return_value = {
                "local_ip": "127.0.0.1",
                "subnet_cidr": 8,
                "state": InterfaceState.UP,
                "type": InterfaceType.LOOPBACK,
                "dhcp_enabled": False,
            }
            mock_adapter.get_wifi_metrics.return_value = None
            mock_adapter.get_configured_dns_servers.return_value = ["127.0.0.1"]
            mock_adapter.ping.return_value = (True, 0.2, 0.0)

            runner = EndpointAgentRunner(config=config, platform_adapter=mock_adapter)
            report = await runner.run_once()

            assert report.metadata.environment == TelemetricEnvironment.MOCK_SIMULATED
            assert report.local_network.gateway_is_reachable is True
            assert len(report.service_probes) == 1
            assert report.service_probes[0].is_reachable is True

            # Verify spooled
            assert runner.spooler.get_pending_count() == 1

            # Check health diagnostics
            health = runner.lifecycle.get_health()
            assert health["status"] == AgentStatus.INITIALIZING.value
            assert "capabilities" in health
            assert health["spool_pending_records"] == 1

    asyncio.run(_test())
