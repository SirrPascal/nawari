"""Integration test suite for Stage 7D: Ingestion Gateway & Zabbix Integration.

Validates:
1. Live Ingestion Gateway communication with live nawari-zabbix-server (port 10051).
2. Live EndpointAgentRunner with TelemetryUploader delivering report to Gateway.
3. Spooler auto-drain on successful delivery.
4. Offline spool accumulation and replay recovery when Gateway becomes reachable.
"""

import asyncio
import json
import tempfile
import urllib.request
from pathlib import Path

import pytest

from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.core.uploader import TelemetryUploader
from services.endpoint.models import ServiceProtocol, TelemetricEnvironment
from services.endpoint.runner import EndpointAgentRunner
from services.gateway.config import GatewayConfig
from services.gateway.server import IngestionGatewayServer
from services.voice.zabbix_sender import ZabbixSender


def test_stage7d_live_gateway_with_live_zabbix_trapper():
    """Verify Ingestion Gateway receives telemetry and dispatches to live Zabbix server (port 10051)."""
    # Point to live local nawari-zabbix-server container
    config = GatewayConfig(
        host="127.0.0.1",
        port=18448,
        zabbix_server_host="127.0.0.1",
        zabbix_server_port=10051,
        auth_token="integration-test-token",
        require_auth=True,
    )
    server = IngestionGatewayServer(config=config)

    try:
        server.start()
        assert server.is_running is True

        # Generate live runner report
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                hostname="kq-mon01",
                targets=[
                    TargetPolicy(
                        target_id="asterisk-sip",
                        target_name="Asterisk SIP TLS",
                        destination="127.0.0.1",
                        port=5061,
                        protocol=ServiceProtocol.TCP,
                    )
                ],
            )
            runner = EndpointAgentRunner(config=agent_config)

            async def _run():
                return await runner.run_once()

            report = asyncio.run(_run())

            # Post report to Gateway
            req = urllib.request.Request(
                "http://127.0.0.1:18448/api/v1/telemetry",
                data=json.dumps(report.to_dict()).encode("utf-8"),
                headers={
                    "Authorization": "Bearer integration-test-token",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=5.0) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "ACCEPTED"
                assert data["hostname"] == "kq-mon01"
                assert data["metrics_dispatched"] > 5
                assert data["zabbix_dispatched"] is True
    finally:
        server.stop()


def test_stage7d_live_runner_with_uploader_and_gateway():
    """Verify EndpointAgentRunner automatically uploads to Gateway and clears spool on success."""
    gateway_config = GatewayConfig(
        host="127.0.0.1",
        port=18449,
        zabbix_server_host="127.0.0.1",
        zabbix_server_port=10051,
        auth_token="auto-upload-token",
        require_auth=True,
    )
    server = IngestionGatewayServer(config=gateway_config)

    try:
        server.start()

        with tempfile.TemporaryDirectory() as tmpdir:
            agent_config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                gateway_url="http://127.0.0.1:18449",
                api_token="auto-upload-token",
                targets=[
                    TargetPolicy(
                        target_id="loopback-target",
                        target_name="Loopback",
                        destination="127.0.0.1",
                        protocol=ServiceProtocol.ICMP,
                    )
                ],
            )

            runner = EndpointAgentRunner(config=agent_config, enable_uploader=True)

            async def _run():
                return await runner.run_once()

            report = asyncio.run(_run())

            # Gateway ingested report
            stats = server.get_stats()
            assert stats["total_ingested_reports"] >= 1

            # Spooler must have 0 pending because it was successfully uploaded and dequeued
            assert runner.spooler.get_pending_count() == 0
    finally:
        server.stop()


def test_stage7d_live_spool_backlog_and_replay_on_recovery():
    """Verify spooler retains records when Gateway is offline, and replays all on recovery."""
    offline_port = 18450

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_config = AgentConfig(
            state_dir=tmpdir,
            spool_dir=f"{tmpdir}/spool",
            gateway_url=f"http://127.0.0.1:{offline_port}",
            api_token="recovery-token",
            targets=[
                TargetPolicy(
                    target_id="loopback-target",
                    target_name="Loopback",
                    destination="127.0.0.1",
                    protocol=ServiceProtocol.ICMP,
                )
            ],
        )

        runner = EndpointAgentRunner(config=agent_config, enable_uploader=True)

        async def _run_twice():
            await runner.run_once()
            await runner.run_once()

        asyncio.run(_run_twice())

        # Gateway is offline: spooler must accumulate 2 pending records on disk
        assert runner.spooler.get_pending_count() == 2

        # Now start Gateway on offline_port
        gateway_config = GatewayConfig(
            host="127.0.0.1",
            port=offline_port,
            zabbix_server_host="127.0.0.1",
            zabbix_server_port=10051,
            auth_token="recovery-token",
            require_auth=True,
        )
        server = IngestionGatewayServer(config=gateway_config)

        try:
            server.start()

            # Trigger spool replay
            replayed = runner.uploader.replay_spooled(batch_size=10)
            assert replayed == 2

            # Spooler pending count must now be 0!
            assert runner.spooler.get_pending_count() == 0

            # Gateway must have recorded ingestion of both replayed reports
            stats = server.get_stats()
            assert stats["total_ingested_reports"] == 2
        finally:
            server.stop()

