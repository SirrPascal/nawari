"""Integration test suite for Stage 7B: Endpoint Connectivity, DNS, and Service Probing.

Validates decomposed probing against live local Docker containers:
- nawari-asterisk (Port 5061 TCP/TLS)
- nawari-zabbix-web (Port 8088 HTTP)
- nawari-postgres (Port 5433 TCP)
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.models import DnsResolutionStatus, ServiceProtocol, TelemetricEnvironment
from services.endpoint.probes.dns import DnsProbe
from services.endpoint.probes.http import HttpProbe, HttpStatusOutcome
from services.endpoint.probes.tcp import TcpConnectStatus, TcpProbe
from services.endpoint.probes.tls import TlsHandshakeStatus, TlsProbe
from services.endpoint.runner import EndpointAgentRunner


def test_stage7b_live_dns_resolution():
    """Verify live DNS resolution of localhost and external domains."""
    async def _test():
        probe = DnsProbe(timeout_seconds=3.0)
        res = await probe.probe("localhost", record_type="A")
        assert res.status in (DnsResolutionStatus.NOERROR, DnsResolutionStatus.SUCCESS)
        assert "127.0.0.1" in res.resolved_ips
        assert res.resolution_time_ms > 0.0

    asyncio.run(_test())


def test_stage7b_live_tcp_probing_across_containers():
    """Verify TCP 3-way handshake probing against Asterisk (5061), Zabbix (8088), and Postgres (5433)."""
    async def _test():
        tcp_probe = TcpProbe(default_timeout_seconds=2.0)

        # 1. Asterisk SIP TLS port 5061
        res_asterisk = await tcp_probe.probe("127.0.0.1", 5061)
        assert res_asterisk.status == TcpConnectStatus.SUCCESS
        assert res_asterisk.is_reachable is True
        assert res_asterisk.connect_time_ms is not None
        assert res_asterisk.connect_time_ms < 100.0  # Fast local loopback

        # 2. Zabbix Web HTTP port 8088
        res_zabbix = await tcp_probe.probe("127.0.0.1", 8088)
        assert res_zabbix.status == TcpConnectStatus.SUCCESS
        assert res_zabbix.is_reachable is True
        assert res_zabbix.connect_time_ms is not None

        # 3. PostgreSQL port 5433
        res_pg = await tcp_probe.probe("127.0.0.1", 5433)
        assert res_pg.status == TcpConnectStatus.SUCCESS
        assert res_pg.is_reachable is True
        assert res_pg.connect_time_ms is not None

        # 4. Closed port verification (must return CONNECTION_REFUSED, not hang)
        res_closed = await tcp_probe.probe("127.0.0.1", 59998)
        assert res_closed.status == TcpConnectStatus.CONNECTION_REFUSED
        assert res_closed.is_reachable is False

    asyncio.run(_test())


def test_stage7b_live_decomposed_http_probe():
    """Verify decomposed timing metrics against Zabbix Web UI container."""
    async def _test():
        http_probe = HttpProbe(default_timeout_seconds=5.0)
        res = await http_probe.probe("http://127.0.0.1:8088/")

        assert res.status_outcome == HttpStatusOutcome.SUCCESS
        assert res.is_success is True
        assert res.status_code == 200

        # Decomposed timing checks
        assert res.dns_time_ms is not None
        assert res.tcp_time_ms is not None
        assert res.ttfb_ms is not None
        assert res.total_time_ms is not None
        assert res.total_time_ms >= res.ttfb_ms
        assert res.response_size_bytes is not None
        assert res.response_size_bytes > 500  # HTML page returned

    asyncio.run(_test())


def test_stage7b_layer_independence_verification():
    """Verify transport success is distinguished from application status."""
    async def _test():
        http_probe = HttpProbe(default_timeout_seconds=3.0)
        # 404 endpoint: transport (TCP) succeeds, but application returns 404
        res = await http_probe.probe("http://127.0.0.1:8088/definitely-missing-404-check")
        assert res.status_outcome == HttpStatusOutcome.CLIENT_ERROR_4XX
        assert res.is_success is False
        assert res.status_code == 404
        # Transport metrics were measured and healthy
        assert res.tcp_time_ms is not None
        assert res.ttfb_ms is not None

    asyncio.run(_test())


def test_stage7b_end_to_end_agent_runner_with_probes():
    """Verify EndpointAgentRunner executes Stage 7B probes and produces validated report."""
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                poll_interval_seconds=15,
                targets=[
                    TargetPolicy(
                        target_id="asterisk-sip",
                        target_name="Asterisk SIP TLS",
                        destination="127.0.0.1",
                        port=5061,
                        protocol=ServiceProtocol.TCP,
                    ),
                    TargetPolicy(
                        target_id="zabbix-web",
                        target_name="Zabbix Web",
                        destination="127.0.0.1",
                        port=8088,
                        protocol=ServiceProtocol.HTTP,
                    ),
                ],
            )

            runner = EndpointAgentRunner(config=config)
            report = await runner.run_once()

            # Metadata
            assert report.metadata.environment == TelemetricEnvironment.MOCK_SIMULATED

            # DNS probe validation
            assert len(report.dns_probes) >= 1
            dns_res = report.dns_probes[0]
            assert dns_res.status in (DnsResolutionStatus.NOERROR, DnsResolutionStatus.SUCCESS)

            # Service probes validation
            assert len(report.service_probes) == 2
            p_sip = next(p for p in report.service_probes if p.target_id == "asterisk-sip")
            p_web = next(p for p in report.service_probes if p.target_id == "zabbix-web")

            # SIP TCP probe: transport healthy
            assert p_sip.is_reachable is True
            assert p_sip.tcp_connect_time_ms is not None
            assert p_sip.tcp_status == "SUCCESS"

            # Web HTTP probe: decomposed timing present
            assert p_web.is_reachable is True
            assert p_web.http_status_code == 200
            assert p_web.http_ttfb_ms is not None

            # Local spool validation
            assert runner.spooler.get_pending_count() == 1
            spooled = runner.spooler.peek(limit=1)[0]
            assert spooled["schema_version"] == "nawari.endpoint.telemetry.v1"
            assert len(spooled["service_probes"]) == 2

    asyncio.run(_test())
