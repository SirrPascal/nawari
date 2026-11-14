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
from services.endpoint.delivery import RECEIPT_VERSION, REJECTED, RETRY, TARGET_ACCEPTED, record_id
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
from services.voice.zabbix_sender import ZabbixSender, ZabbixSenderResponse


def accepted_sender_response(metrics):
    return ZabbixSenderResponse("success", "", processed=len(metrics), failed=0, total=len(metrics))


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


@pytest.mark.parametrize("configured_token", ["fixture-token", None, ""])
def test_gateway_auth_guard(configured_token):
    """Require a configured token and reject missing or invalid credentials."""
    import urllib.error
    import urllib.request

    config = GatewayConfig(host="127.0.0.1", port=18444, auth_token=configured_token, require_auth=True)
    sender = MagicMock(spec=ZabbixSender)
    sender.send.side_effect = accepted_sender_response
    server = IngestionGatewayServer(config=config, zabbix_sender=sender)

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

        req_wrong = urllib.request.Request(
            "http://127.0.0.1:18444/api/v1/telemetry",
            data=json.dumps(report.to_dict()).encode("utf-8"),
            headers={"Authorization": "Bearer wrong-token"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_wrong, timeout=2.0)
        assert exc_info.value.code == 401

        # 2. A matching header works only when an expected token is configured.
        req_auth = urllib.request.Request(
            "http://127.0.0.1:18444/api/v1/telemetry",
            data=json.dumps(report.to_dict()).encode("utf-8"),
            headers={"Authorization": "Bearer fixture-token", "Content-Type": "application/json"},
            method="POST",
        )
        if not configured_token:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req_auth, timeout=2.0)
            assert exc_info.value.code == 401
            return
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
    mock_sender.send.side_effect = accepted_sender_response
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


@pytest.fixture
def delivery_lab(tmp_path):
    from contextlib import ExitStack

    sender = MagicMock(spec=ZabbixSender)
    sender.send.side_effect = accepted_sender_response
    spool = DiskSpooler(str(tmp_path / "spool"))

    with ExitStack() as cleanup:
        def start(**options):
            server = IngestionGatewayServer(GatewayConfig(port=0, require_auth=False, **options), sender)
            server.start()
            cleanup.callback(server.stop)
            url = f"http://127.0.0.1:{server._httpd.server_port}"
            return server, TelemetryUploader(url, spooler=spool)

        yield start, spool, sender


def wire_reports():
    for timestamp in (1_700_000_000, 1_700_000_002, 1_700_000_001):
        report = build_sample_report().to_dict()
        report["metadata"]["timestamp_ns"] = timestamp * 10**9
        yield report


def test_partial_replay_removes_only_accepted_ids(delivery_lab):
    start, spool, sender = delivery_lab
    _, uploader = start()
    first, failed, last = wire_reports()
    rejected = {"schema_version": "unknown"}
    for report in (first, failed, rejected, last):
        assert spool.spool(report)
    with spool.spool_file.open("a", encoding="utf-8") as file:
        file.write("corrupt record\n")

    def downstream(metrics):
        if metrics[0].clock == failed["metadata"]["timestamp_ns"] // 10**9:
            return ZabbixSenderResponse("success", "", len(metrics) - 1, 1, len(metrics))
        return accepted_sender_response(metrics)

    sender.send.side_effect = downstream
    assert uploader.replay_spooled() == 2
    assert spool.peek() == [failed, rejected]
    assert spool.spool_file.read_text().endswith("corrupt record\n")
    sent_clocks = [call.args[0][0].clock for call in sender.send.call_args_list]
    assert sent_clocks == [item["metadata"]["timestamp_ns"] // 10**9 for item in (first, failed, last)]


def test_lost_response_replays_by_id_after_gateway_restart(delivery_lab, tmp_path, monkeypatch):
    start, spool, sender = delivery_lab
    path = str(tmp_path / "receipts.sqlite3")
    first, _, _ = wire_reports()
    assert spool.spool(first)
    server, uploader = start(receipt_db_path=path)
    request = uploader._send

    def lose_response(*args):
        body = request(*args)
        assert body["receipts"] == {record_id(first): TARGET_ACCEPTED}
        return {}

    monkeypatch.setattr(uploader, "_send", lose_response)
    assert uploader.replay_spooled() == 0
    assert spool.peek() == [first]
    server.stop()
    _, restarted_uploader = start(receipt_db_path=path)
    assert restarted_uploader.replay_spooled() == 1
    assert spool.get_pending_count() == 0
    assert sender.send.call_count == 1


def test_replay_has_explicit_failures_and_legacy_partial_is_non_success(delivery_lab):
    import urllib.error
    import urllib.request

    start, spool, sender = delivery_lab
    _, uploader = start()
    first, failed, _ = wire_reports()
    rejected = {"schema_version": "unknown"}

    def forward(metrics):
        if metrics[0].clock == failed["metadata"]["timestamp_ns"] // 10**9:
            raise TimeoutError
        return accepted_sender_response(metrics)

    sender.send.side_effect = forward
    for item in (first, failed, rejected):
        assert spool.spool(item)
    body = uploader._send("/api/v1/telemetry/replay", {
        "receipt_version": RECEIPT_VERSION,
        "reports": spool.peek(),
    }, 2)
    assert body["receipts"] == {
        record_id(first): TARGET_ACCEPTED, record_id(failed): RETRY, record_id(rejected): REJECTED,
    }
    legacy = uploader._build_request("/api/v1/telemetry/replay", {"reports": spool.peek()})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(legacy, timeout=2)
    assert error.value.code == 503
    assert spool.peek() == [first, failed, rejected]


@pytest.mark.parametrize("status", [429, 503])
def test_agent_retains_records_after_http_failure(delivery_lab, status):
    start, spool, sender = delivery_lab
    server, uploader = start(max_queue_depth=2)
    first, _, _ = wire_reports()
    assert spool.spool(first)
    if status == 429:
        server.increment_queue_depth()
        assert server.is_congested()
    else:
        sender.send.side_effect = OSError("mock backend unavailable")
    if status == 429:
        assert uploader.replay_spooled() == 0
    else:
        report = EndpointTelemetryReport.from_dict(first)
        assert uploader.upload_report(report) is False
    assert spool.peek() == [first]


def test_old_count_only_gateway_cannot_clear_new_agent_spool(delivery_lab, monkeypatch):
    start, spool, _ = delivery_lab
    _, uploader = start()
    first, _, _ = wire_reports()
    assert spool.spool(first)
    monkeypatch.setattr(uploader, "_send", lambda *_: {"status": "ACCEPTED", "replayed_count": 1})
    assert uploader.replay_spooled() == 0
    assert spool.peek() == [first]


def test_replay_retains_source_timestamp_and_rejects_future_and_unlisted_agent(delivery_lab):
    start, spool, sender = delivery_lab
    _, uploader = start(enforce_replay_guard=True)
    first, future, version = wire_reports()
    future["metadata"]["timestamp_ns"] = time.time_ns() + 600 * 10**9
    version["metadata"]["agent_version"] = "unsupported"
    for report in (first, future, version):
        assert spool.spool(report)
    assert uploader.upload_report(EndpointTelemetryReport.from_dict(first)) is False
    assert uploader.replay_spooled() == 1
    assert spool.peek() == [future, version]
    assert sender.send.call_args.args[0][0].clock == first["metadata"]["timestamp_ns"] // 10**9


def test_incomplete_sender_counts_do_not_confirm_delivery(delivery_lab):
    start, spool, sender = delivery_lab
    _, uploader = start()
    first, _, _ = wire_reports()
    assert spool.spool(first)

    def incomplete(metrics):
        return ZabbixSenderResponse.parse(json.dumps({
            "response": "success",
            "info": f"processed: {len(metrics)}; total: {len(metrics)}",
        }))

    sender.send.side_effect = incomplete
    assert uploader.replay_spooled() == 0
    assert spool.peek() == [first]


def test_duplicate_in_flight_is_retried_without_a_second_send(delivery_lab):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    start, _, sender = delivery_lab
    _, uploader = start()
    first, _, _ = wire_reports()
    payload = {"receipt_version": RECEIPT_VERSION, "reports": [first]}
    identifier = record_id(first)
    entered, release = Event(), Event()

    def paused_sender(metrics):
        entered.set()
        assert release.wait(timeout=5)
        return accepted_sender_response(metrics)

    sender.send.side_effect = paused_sender
    with ThreadPoolExecutor() as pool:
        original = pool.submit(uploader._send, "/api/v1/telemetry/replay", payload, 5)
        try:
            assert entered.wait(timeout=3)
            duplicate = uploader._send("/api/v1/telemetry/replay", payload, 2)
            assert duplicate["receipts"] == {identifier: RETRY}
        finally:
            release.set()
        assert original.result(timeout=3)["receipts"] == {identifier: TARGET_ACCEPTED}
    assert sender.send.call_count == 1
