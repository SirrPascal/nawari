"""Integration test suite for Stage 7A Endpoint Agent Lifecycle & Platform Abstraction."""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.core.identity import IdentityManager, mask_agent_id
from services.endpoint.core.lifecycle import AgentStatus
from services.endpoint.models import ServiceProtocol, TelemetricEnvironment
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.runner import EndpointAgentRunner


def test_stage7a_e2e_agent_lifecycle_and_persistence():
    """Verify complete end-to-end agent initialization, probe execution, spooling, and restart."""
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                poll_interval_seconds=10,
                environment=TelemetricEnvironment.MOCK_SIMULATED,
                targets=[
                    TargetPolicy(
                        target_id="loopback-test",
                        target_name="Loopback Ping",
                        destination="127.0.0.1",
                        protocol=ServiceProtocol.ICMP,
                    )
                ],
            )

            # Step 1: Initialize runner
            runner1 = EndpointAgentRunner(config=config)
            agent_id1 = runner1.identity_mgr.agent_id
            assert agent_id1 is not None

            # Step 2: Execute single diagnostic cycle
            report = await runner1.run_once()
            assert report.metadata.agent_id == agent_id1
            assert report.metadata.environment == TelemetricEnvironment.MOCK_SIMULATED
            assert report.local_network.local_ip is not None
            assert len(report.service_probes) == 1
            assert report.service_probes[0].target_id == "loopback-test"
            assert report.service_probes[0].is_reachable is True

            # Step 3: Verify local disk spooling
            assert runner1.spooler.get_pending_count() == 1
            spooled_records = runner1.spooler.peek(limit=5)
            assert len(spooled_records) == 1
            assert spooled_records[0]["schema_version"] == "nawari.endpoint.telemetry.v1"
            assert spooled_records[0]["metadata"]["agent_id"] == agent_id1

            # Step 4: Simulate process restart with same state directory
            runner2 = EndpointAgentRunner(config=config)
            agent_id2 = runner2.identity_mgr.agent_id
            assert agent_id1 == agent_id2, "Agent ID must persist across restarts"
            assert runner2.identity_mgr.identity.re_registration_count == 0

            # Step 5: Test health diagnostics on restarted agent
            health = runner2.lifecycle.get_health()
            assert health["agent_id_masked"] == mask_agent_id(agent_id1)
            assert health["spool_pending_records"] == 1
            assert health["capabilities"]["supports_gateway_discovery"] is True

            # Step 6: Test re-registration
            new_id = runner2.identity_mgr.re_register(force=True)
            assert new_id.agent_id != agent_id1
            assert new_id.re_registration_count == 1

            # Verify persistent re-registration
            runner3 = EndpointAgentRunner(config=config)
            assert runner3.identity_mgr.agent_id == new_id.agent_id

    asyncio.run(_test())


def test_stage7a_scheduler_execution_and_clean_shutdown():
    """Verify continuous probe execution, stats collection, and clean termination."""
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                poll_interval_seconds=5,
                jitter_max_seconds=0.0,
                targets=[
                    TargetPolicy(
                        target_id="local-sig",
                        target_name="Local Loopback",
                        destination="127.0.0.1",
                        protocol=ServiceProtocol.ICMP,
                    )
                ],
            )

            runner = EndpointAgentRunner(config=config)
            agent_task = asyncio.create_task(runner.start())

            # Allow scheduler to run for a short duration
            await asyncio.sleep(0.3)

            # Check stats while running
            stats = runner.scheduler.get_stats()
            assert stats["is_running"] is True
            assert "local_network" in stats["probes"]

            # Graceful shutdown
            await runner.stop()
            await agent_task

            assert runner.lifecycle.status == AgentStatus.STOPPED
            assert runner.scheduler._is_running is False

    asyncio.run(_test())
