"""Unit test suite for Stage 7D: Ingestion Gateway & Zabbix Integration.

Validates:
1. Zabbix metric translation and unit normalization (seconds for latencies).
2. Invariant 1: CoPP Guard in Zabbix metrics (omission of RTT for TIMEOUT_COPP).
3. Invariant 2: Wi-Fi metric isolation (omission when interface != WIFI).
4. Invariant 3: Authoritative provenance & anti-spoofing rejection of PHYSICAL_PRODUCTION.
5. Gateway authentication guard (Bearer token validation).
6. Gateway payload size limiting (413 Payload Too Large).
7. Spool replay endpoint execution and count tracking.
"""

import json
import time
from unittest.mock import MagicMock

import pytest

from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.core.uploader import TelemetryUploader
from services.endpoint.models import (
    AgentMetadata,
    DnsProbeTelemetry,
    DnsResolutionStatus,
    EndpointTelemetryReport,
    HopResponseStatus,
    HopTelemetry,
    InterfaceState,
    InterfaceType,
    LocalNetworkTelemetry,
    PathTelemetry,
    ServiceConnectivityTelemetry,
    ServiceProtocol,
    TelemetricEnvironment,
    WifiMetrics,
)
from services.gateway.config import GatewayConfig
from services.gateway.server import IngestionGatewayServer
from services.gateway.zabbix_mapper import ZabbixEndpointMapper
from services.voice.zabbix_sender import ZabbixSender


# =====================================================================
# Fixtures & Helper Builders
# =====================================================================

def build_sample_report(
    interface_type: InterfaceType = InterfaceType.ETHERNET,
    include_wifi: bool = False,
    environment: TelemetricEnvironment = TelemetricEnvironment.MOCK_SIMULATED,
    include_copp_hop: bool = False,
) -> EndpointTelemetryReport:
    """Helper to build a deterministic sample EndpointTelemetryReport."""
    meta = AgentMetadata(
        agent_id="test-agent-123",
        hostname="kq-laptop-01",
        os_name="Darwin",
        os_version="15.0.0",
        agent_version="1.0.0",
        timestamp_ns=1700000000000000000,
        environment=environment,
    )

    wifi = (
        WifiMetrics(ssid="KQ-Corp", bssid="00:11:22:33:44:55", rssi_dbm=-65, signal_quality_pct=85.0)
        if include_wifi
        else None
    )

    local_net = LocalNetworkTelemetry(
        default_gateway_ip="192.168.1.1",
        default_gateway_mac="00:aa:bb:cc:dd:ee",
        gateway_is_reachable=True,
        gateway_rtt_ms=2.5,
        gateway_loss_pct=0.0,
        interface_name="en0",
        interface_type=interface_type,
        interface_state=InterfaceState.UP,
        local_ip="192.168.1.50",
        subnet_cidr=24,
        dhcp_enabled=True,
        configured_dns_servers=["192.168.1.1"],
        wifi=wifi,
    )

    dns_probes = [
        DnsProbeTelemetry(
            query_name="sbce.kq.internal",
            record_type="A",
            resolver_ip="192.168.1.1",
            status=DnsResolutionStatus.NOERROR,
            resolution_time_ms=1.2,
            resolved_ips=["10.0.0.1"],
        )
    ]

    service_probes = [
        ServiceConnectivityTelemetry(
            target_id="sbce-sip",
            target_name="Avaya SBCE SIP",
            destination_ip="10.0.0.1",
            destination_port=5061,
            protocol=ServiceProtocol.TCP,
            is_reachable=True,
            tcp_connect_time_ms=5.4,
        )
    ]

    hops = [
        HopTelemetry(
            hop_index=1,
            ip_address="192.168.1.1",
            rdns_hostname=None,
            asn=None,
            as_org=None,
            rtt_min_ms=1.0,
            rtt_avg_ms=1.2,
            rtt_max_ms=1.4,
            rtt_stddev_ms=0.1,
            loss_pct=0.0,
            status=HopResponseStatus.RESPONSIVE,
        )
    ]

    if include_copp_hop:
        hops.append(
            HopTelemetry(
                hop_index=2,
                ip_address=None,
                rdns_hostname=None,
                asn=None,
                as_org=None,
                rtt_min_ms=None,
                rtt_avg_ms=None,
                rtt_max_ms=None,
                rtt_stddev_ms=None,
                loss_pct=100.0,
                status=HopResponseStatus.TIMEOUT_COPP,
            )
        )
    hops.append(
        HopTelemetry(
            hop_index=3 if include_copp_hop else 2,
            ip_address="10.0.0.1",
            rdns_hostname=None,
            asn=None,
            as_org=None,
            rtt_min_ms=10.0,
            rtt_avg_ms=10.5,
            rtt_max_ms=11.0,
            rtt_stddev_ms=0.3,
            loss_pct=0.0,
            status=HopResponseStatus.RESPONSIVE,
        )
    )

    path_traces = [
        PathTelemetry(
            target_id="sbce-sip",
            target_ip="10.0.0.1",
            protocol="UDP",
            total_hops=len(hops),
            end_to_end_rtt_ms=10.5,
            end_to_end_loss_pct=0.0,
            path_hash="a1b2c3d4e5",
            has_route_changed=False,
            hops=hops,
        )
    ]

    return EndpointTelemetryReport(
        metadata=meta,
        local_network=local_net,
        dns_probes=dns_probes,
        service_probes=service_probes,
        path_traces=path_traces,
    )


# =====================================================================
# 1. Zabbix Metric Mapper Unit Tests
# =====================================================================

def test_zabbix_metric_mapping_static_items():
    """Verify static metadata and gateway latency conversion to seconds."""
    report = build_sample_report()
    metrics = ZabbixEndpointMapper.map_report_to_metrics(
        report=report,
        authoritative_environment=TelemetricEnvironment.MOCK_SIMULATED,
    )

    metric_dict = {m.key: m.value for m in metrics}

    # Host assignment
    assert all(m.host == "kq-laptop-01" for m in metrics)

    # Info & Environment
    assert "endpoint.info" in metric_dict
    assert metric_dict["endpoint.environment"] == 0

    # Gateway RTT normalized from 2.5ms to 0.0025s
    assert metric_dict["endpoint.network.gateway.rtt"] == 0.0025
    assert metric_dict["endpoint.network.gateway.loss"] == 0.0
    assert metric_dict["endpoint.network.interface.type"] == 0  # Ethernet


def test_zabbix_metric_mapping_wifi_isolation_invariant():
    """Invariant 2: Wi-Fi metrics strictly omitted if interface != WIFI."""
    # 1. Ethernet interface: must NOT contain wifi metrics
    eth_report = build_sample_report(interface_type=InterfaceType.ETHERNET, include_wifi=False)
    eth_metrics = ZabbixEndpointMapper.map_report_to_metrics(eth_report, TelemetricEnvironment.MOCK_SIMULATED)
    eth_keys = [m.key for m in eth_metrics]
    assert "endpoint.network.wifi.rssi" not in eth_keys
    assert "endpoint.network.wifi.quality" not in eth_keys

    # 2. Wi-Fi interface: must contain wifi metrics
    wifi_report = build_sample_report(interface_type=InterfaceType.WIFI, include_wifi=True)
    wifi_metrics = ZabbixEndpointMapper.map_report_to_metrics(wifi_report, TelemetricEnvironment.MOCK_SIMULATED)
    wifi_dict = {m.key: m.value for m in wifi_metrics}
    assert wifi_dict["endpoint.network.interface.type"] == 1
    assert wifi_dict["endpoint.network.wifi.rssi"] == -65.0
    assert wifi_dict["endpoint.network.wifi.quality"] == 85.0


def test_zabbix_metric_mapping_copp_guard_invariant():
    """Invariant 1: TIMEOUT_COPP hops omit RTT metrics and report status 1."""
    report = build_sample_report(include_copp_hop=True)
    metrics = ZabbixEndpointMapper.map_report_to_metrics(report, TelemetricEnvironment.MOCK_SIMULATED)
    metric_dict = {m.key: m.value for m in metrics}

    # Hop 2 was CoPP:
    # 1. nawari.path.hop.rtt[sbce-sip,2] MUST BE OMITTED
    assert "nawari.path.hop.rtt[sbce-sip,2]" not in metric_dict
    # 2. Status must be 1 (TIMEOUT_COPP)
    assert metric_dict["nawari.path.hop.status[sbce-sip,2]"] == 1
    assert metric_dict["nawari.path.hop.loss[sbce-sip,2]"] == 100.0

    # Hop 1 and 3 are responsive: RTT present in seconds
    assert metric_dict["nawari.path.hop.rtt[sbce-sip,1]"] == 0.0012
    assert metric_dict["nawari.path.hop.status[sbce-sip,1]"] == 0


# =====================================================================
# 2. Gateway Server & Security Invariant Tests
# =====================================================================

def test_gateway_server_lifecycle():
    """Verify IngestionGatewayServer starts, serves GET /api/v1/health, and shuts down."""
    import urllib.request

    config = GatewayConfig(host="127.0.0.1", port=18443, require_auth=False)
    server = IngestionGatewayServer(config=config, zabbix_sender=MagicMock(spec=ZabbixSender))

    try:
        server.start()
        assert server.is_running is True

        req = urllib.request.Request("http://127.0.0.1:18443/api/v1/health")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "HEALTHY"
            assert data["environment"] == "MOCK_SIMULATED"
    finally:
        server.stop()
        assert server.is_running is False


def test_gateway_auth_guard():
    """Verify missing or invalid Bearer token returns HTTP 401."""
    import urllib.error
    import urllib.request

    config = GatewayConfig(host="127.0.0.1", port=18444, auth_token="super-secret", require_auth=True)
    server = IngestionGatewayServer(config=config, zabbix_sender=MagicMock(spec=ZabbixSender))

    try:
        server.start()

        # 1. No auth header -> 401
        report = build_sample_report()
        req_no_auth = urllib.request.Request(
            "http://127.0.0.1:18444/api/v1/telemetry",
            data=json.dumps(report.to_dict()).encode("utf-8"),
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_no_auth, timeout=2.0)
        assert exc_info.value.code == 401

        # 2. Correct auth header -> 200
        req_auth = urllib.request.Request(
            "http://127.0.0.1:18444/api/v1/telemetry",
            data=json.dumps(report.to_dict()).encode("utf-8"),
            headers={"Authorization": "Bearer super-secret", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_auth, timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ACCEPTED"
    finally:
        server.stop()


def test_gateway_anti_spoofing_provenance_guard():
    """Invariant 3: Simulated collector rejects client claiming PHYSICAL_PRODUCTION."""
    import urllib.error
    import urllib.request

    config = GatewayConfig(
        host="127.0.0.1",
        port=18445,
        environment=TelemetricEnvironment.MOCK_SIMULATED,
        require_auth=False,
    )
    server = IngestionGatewayServer(config=config, zabbix_sender=MagicMock(spec=ZabbixSender))

    try:
        server.start()

        # Agent falsely claims PHYSICAL_PRODUCTION
        spoofed_report = build_sample_report(environment=TelemetricEnvironment.PHYSICAL_PRODUCTION)
        req = urllib.request.Request(
            "http://127.0.0.1:18445/api/v1/telemetry",
            data=json.dumps(spoofed_report.to_dict()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=2.0)

        # Anti-spoofing guard must reject with 403 Forbidden
        assert exc_info.value.code == 403
        resp_body = json.loads(exc_info.value.read().decode("utf-8"))
        assert "Anti-spoofing guard" in resp_body["error"]
    finally:
        server.stop()


def test_gateway_payload_size_limit():
    """Verify oversized payloads are rejected with HTTP 413."""
    import urllib.error
    import urllib.request

    config = GatewayConfig(host="127.0.0.1", port=18446, max_payload_bytes=500, require_auth=False)
    server = IngestionGatewayServer(config=config, zabbix_sender=MagicMock(spec=ZabbixSender))

    try:
        server.start()

        report = build_sample_report()
        req = urllib.request.Request(
            "http://127.0.0.1:18446/api/v1/telemetry",
            data=json.dumps(report.to_dict()).encode("utf-8"),  # Over 500 bytes
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=2.0)

        assert exc_info.value.code == 413
    finally:
        server.stop()


def test_gateway_replay_endpoint():
    """Verify POST /api/v1/telemetry/replay processes batch of reports."""
    import urllib.request

    mock_sender = MagicMock(spec=ZabbixSender)
    config = GatewayConfig(host="127.0.0.1", port=18447, require_auth=False)
    server = IngestionGatewayServer(config=config, zabbix_sender=mock_sender)

    try:
        server.start()

        r1 = build_sample_report()
        r2 = build_sample_report()
        batch_payload = {"reports": [r1.to_dict(), r2.to_dict()]}

        req = urllib.request.Request(
            "http://127.0.0.1:18447/api/v1/telemetry/replay",
            data=json.dumps(batch_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ACCEPTED"
            assert data["replayed_count"] == 2
            assert mock_sender.send.called
    finally:
        server.stop()
