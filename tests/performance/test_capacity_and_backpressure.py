"""
Nawari Phase 8 — Performance, Scalability & Capacity Engineering Tests (Workstream 8F)
Validates queue backpressure under burst loads, memory budget limits, and local spool safety.
"""

import json
import os
import subprocess
import urllib.request
import urllib.error
from unittest.mock import MagicMock
import pytest

from services.endpoint.models import TelemetricEnvironment
from services.gateway.config import GatewayConfig
from services.gateway.server import IngestionGatewayServer
from services.voice.zabbix_sender import ZabbixSender
from tests.unit.test_stage7d_gateway import build_sample_report


def test_01_gateway_queue_backpressure_http_429():
    """Verify that when the gateway is congested, it rejects requests with HTTP 429 and Retry-After."""
    mock_sender = MagicMock(spec=ZabbixSender)
    config = GatewayConfig(
        host="127.0.0.1",
        port=8455,
        environment=TelemetricEnvironment.MOCK_SIMULATED,
        require_auth=False,
        max_queue_depth=10,
        backpressure_threshold=0.5,  # Congests at >= 5 items
        retry_after_seconds=30,
    )
    server = IngestionGatewayServer(config=config, zabbix_sender=mock_sender)
    server.start()

    try:
        report = build_sample_report()
        payload = json.dumps(report.to_dict()).encode("utf-8")

        # 1. Normal ingestion works
        req = urllib.request.Request(
            "http://127.0.0.1:8455/api/v1/telemetry",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

        # 2. Simulate artificial queue congestion
        for _ in range(6):
            server.increment_queue_depth()

        assert server.is_congested() is True

        # 3. Next request must fail with HTTP 429 and Retry-After: 30
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)

        err = exc_info.value
        assert err.code == 429
        assert err.headers.get("Retry-After") == "30"
        err_body = json.loads(err.read().decode("utf-8"))
        assert "backpressured" in err_body["error"]

        # 4. Drain queue -> Gateway recovers
        for _ in range(6):
            server.decrement_queue_depth()

        assert server.is_congested() is False
        with urllib.request.urlopen(req) as resp2:
            assert resp2.status == 200

    finally:
        server.stop()


def test_02_production_memory_budget_under_2_2_gib():
    """Verify that all container memory limits in compose.prod.yaml sum to <= 2.2 GiB (2,250 MiB)."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    res = subprocess.run(
        [
            "docker", "compose",
            "--env-file", os.path.join(project_root, ".env"),
            "-f", os.path.join(project_root, "docker", "compose.yaml"),
            "-f", os.path.join(project_root, "docker", "compose.prod.yaml"),
            "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert res.returncode == 0, f"docker compose config failed: {res.stderr}"
    compose_cfg = json.loads(res.stdout)

    total_mem_limit_bytes = 0
    services = compose_cfg.get("services", {})
    assert len(services) >= 5, "At least 5 services expected in production compose stack"

    for svc_name, svc_data in services.items():
        deploy = svc_data.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        mem = limits.get("memory")
        if mem:
            mem_bytes = int(mem)
            total_mem_limit_bytes += mem_bytes

    total_mem_mib = total_mem_limit_bytes / (1024 * 1024)
    # Hardware budget: 2.2 GiB = 2252.8 MiB
    max_budget_mib = 2252.8
    assert total_mem_mib <= max_budget_mib, (
        f"Total production memory limit {total_mem_mib:.1f} MiB exceeds hardware budget {max_budget_mib:.1f} MiB"
    )
