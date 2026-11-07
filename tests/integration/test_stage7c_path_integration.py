"""Integration test suite for Stage 7C: Network Path Discovery and Analysis.

Validates:
1. Live unprivileged platform adapter path tracing.
2. ParisTraceroute live execution against local targets (127.0.0.1 / containers).
3. Complete EndpointAgentRunner cycle including path_traces in spooled report.
4. Sequential route stability and route hash consistency.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from services.endpoint.config import AgentConfig, TargetPolicy
from services.endpoint.models import HopResponseStatus, ServiceProtocol, TelemetricEnvironment
from services.endpoint.os_platform import get_platform_adapter
from services.endpoint.path.traceroute import ParisTraceroute
from services.endpoint.runner import EndpointAgentRunner


def test_stage7c_live_darwin_adapter_path_trace():
    """Verify live platform adapter trace_path returns structured hop records."""
    adapter = get_platform_adapter()
    raw_hops = adapter.trace_path("127.0.0.1", max_hops=3, timeout_seconds=1.0)

    assert len(raw_hops) >= 1
    hop1 = raw_hops[0]
    assert hop1["hop_index"] == 1
    assert hop1["ip_address"] == "127.0.0.1"
    assert hop1["probes_received"] > 0
    assert len(hop1["rtts_ms"]) > 0


def test_stage7c_live_paris_traceroute():
    """Verify live ParisTraceroute execution and PathTelemetry analysis."""
    async def _test():
        tracer = ParisTraceroute(default_max_hops=3, default_timeout_seconds=1.0)
        res = await tracer.trace(target_id="loopback-test", destination_ip="127.0.0.1")

        assert res.target_id == "loopback-test"
        assert res.target_ip == "127.0.0.1"
        assert res.total_hops >= 1
        assert res.end_to_end_loss_pct == 0.0
        assert res.end_to_end_rtt_ms is not None
        assert len(res.path_hash) == 64  # Valid SHA-256 hex string
        assert res.has_route_changed is False
        assert len(res.hops) >= 1
        assert res.hops[0].status == HopResponseStatus.RESPONSIVE

    asyncio.run(_test())


def test_stage7c_live_runner_end_to_end_with_path_traces():
    """Verify EndpointAgentRunner executes path traces and persists them to local spooler."""
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
                        target_name="Zabbix Web UI",
                        destination="127.0.0.1",
                        port=8088,
                        protocol=ServiceProtocol.HTTP,
                    ),
                ],
            )

            runner = EndpointAgentRunner(config=config)
            report = await runner.run_once()

            # Metadata and previous probes
            assert report.metadata.environment == TelemetricEnvironment.MOCK_SIMULATED
            assert len(report.service_probes) == 2

            # Stage 7C Path Traces
            assert len(report.path_traces) == 2
            p_sip = next(p for p in report.path_traces if p.target_id == "asterisk-sip")
            p_web = next(p for p in report.path_traces if p.target_id == "zabbix-web")

            assert p_sip.target_ip == "127.0.0.1"
            assert p_sip.total_hops >= 1
            assert p_sip.end_to_end_rtt_ms is not None
            assert p_sip.path_hash is not None

            assert p_web.target_ip == "127.0.0.1"
            assert p_web.total_hops >= 1
            assert p_web.end_to_end_rtt_ms is not None

            # Spooled telemetry validation
            assert runner.spooler.get_pending_count() == 1
            spooled = runner.spooler.peek(limit=1)[0]
            assert "path_traces" in spooled
            assert len(spooled["path_traces"]) == 2
            assert spooled["path_traces"][0]["path_hash"] == p_sip.path_hash

    asyncio.run(_test())


def test_stage7c_route_stability_across_sequential_runs():
    """Verify route hash remains stable and has_route_changed is False when path is consistent."""
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                state_dir=tmpdir,
                spool_dir=f"{tmpdir}/spool",
                targets=[
                    TargetPolicy(
                        target_id="test-target",
                        target_name="Test Target",
                        destination="127.0.0.1",
                        protocol=ServiceProtocol.ICMP,
                    )
                ],
            )
            runner = EndpointAgentRunner(config=config)

            # Cycle 1
            report1 = await runner.run_once()
            assert len(report1.path_traces) == 1
            trace1 = report1.path_traces[0]
            assert trace1.has_route_changed is False

            # Cycle 2 (same route)
            report2 = await runner.run_once()
            assert len(report2.path_traces) == 1
            trace2 = report2.path_traces[0]
            assert trace2.has_route_changed is False
            assert trace2.path_hash == trace1.path_hash

    asyncio.run(_test())

