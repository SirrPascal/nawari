"""tests/unit/test_hub_daemon.py
==============================
Unit tests for Nawari Central Hub Application Daemon.
"""

import json
import time
import urllib.request
import pytest

from services.hub_daemon import HubDaemon, parse_environment
from services.endpoint.models import TelemetricEnvironment


def test_parse_environment():
    assert parse_environment("production") == TelemetricEnvironment.PHYSICAL_PRODUCTION
    assert parse_environment("PRODUCTION") == TelemetricEnvironment.PHYSICAL_PRODUCTION
    assert parse_environment("staging") == TelemetricEnvironment.MOCK_SIMULATED
    assert parse_environment("simulation") == TelemetricEnvironment.MOCK_SIMULATED
    assert parse_environment("unknown") == TelemetricEnvironment.MOCK_SIMULATED


def test_hub_daemon_lifecycle():
    daemon = HubDaemon(
        host="127.0.0.1",
        port=8499,
        env_name="staging",
        profile="staging",
        zabbix_host="127.0.0.1",
        zabbix_port=10051,
        require_auth=False,
    )
    daemon.start()

    try:
        # Give server time to bind
        time.sleep(0.1)

        # 1. Health check via /health
        req1 = urllib.request.Request("http://127.0.0.1:8499/health")
        with urllib.request.urlopen(req1, timeout=2.0) as resp1:
            assert resp1.status == 200
            data1 = json.loads(resp1.read().decode())
            assert data1["status"] == "HEALTHY"

        # 2. Health check via /api/v1/health
        req2 = urllib.request.Request("http://127.0.0.1:8499/api/v1/health")
        with urllib.request.urlopen(req2, timeout=2.0) as resp2:
            assert resp2.status == 200
            data2 = json.loads(resp2.read().decode())
            assert data2["status"] == "HEALTHY"
            assert data2["environment"] == "MOCK_SIMULATED"
    finally:
        daemon.stop()
