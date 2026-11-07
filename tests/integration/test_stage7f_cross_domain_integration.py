"""Integration test suite for Stage 7F: Cross-Domain Service Assurance & Automated Root-Cause Hierarchy."""

import time
import pytest
from typing import Any

from services.api.client import ZabbixClient
from services.api.config import get_settings
from services.assurance.cli import format_assurance_report
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import (
    EvidenceDomain,
    HypothesisStatus,
    RootCauseDomain,
    ServiceHealthState,
)
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
from services.voice.models import CallOutcome, MediaVerificationLevel, SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner
from services.voice.telemetry_schema import (
    CanonicalVoiceEvent,
    DataCompleteness,
    EndpointIdentifiers,
    MediaTelemetry,
    MilestoneTimestamps,
    SignalingTelemetry,
)


@pytest.fixture(scope="module")
def zabbix_client() -> ZabbixClient:
    """Provide an authenticated Zabbix JSON-RPC API client."""
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)
    client.connect()
    return client


def make_hop(
    hop_index: int,
    ip_address: str = "192.168.1.1",
    rtt_avg_ms: float = 2.0,
    loss_pct: float = 0.0,
    status: HopResponseStatus = HopResponseStatus.RESPONSIVE,
) -> HopTelemetry:
    return HopTelemetry(
        hop_index=hop_index,
        ip_address=ip_address,
        rdns_hostname=f"hop{hop_index}.gw",
        asn=64512,
        as_org="Kenya Airways Intranet",
        rtt_min_ms=rtt_avg_ms,
        rtt_avg_ms=rtt_avg_ms,
        rtt_max_ms=rtt_avg_ms,
        rtt_stddev_ms=0.5 if rtt_avg_ms is not None else None,
        loss_pct=loss_pct,
        status=status,
    )


def make_test_endpoint(
    hostname: str,
    gateway_rtt_ms: float = 4.0,
    gateway_loss_pct: float = 0.0,
    gateway_is_reachable: bool = True,
    is_wifi: bool = False,
    wifi_quality: float = 85.0,
    wifi_rssi: int = -55,
    dns_status: DnsResolutionStatus = DnsResolutionStatus.NOERROR,
    service_reachable: bool = True,
    http_status: int = 200,
    http_ttfb_ms: float = 80.0,
    hops: list[HopTelemetry] = None,
) -> EndpointTelemetryReport:
    now_ns = int(time.time() * 1_000_000_000)
    wifi_obj = (
        WifiMetrics(
            ssid="KQ-Corporate-WPA3",
            bssid="00:11:22:33:44:55",
            rssi_dbm=wifi_rssi,
            signal_quality_pct=wifi_quality,
        )
        if is_wifi
        else None
    )

    if hops is None:
        hops = [
            make_hop(1, ip_address="192.168.1.1", rtt_avg_ms=2.0),
            make_hop(2, ip_address="10.0.0.1", rtt_avg_ms=6.0),
            make_hop(3, ip_address="10.50.1.10", rtt_avg_ms=12.0),
        ]

    return EndpointTelemetryReport(
        metadata=AgentMetadata(
            agent_id=f"agent-{hostname}",
            hostname=hostname,
            os_name="Darwin",
            os_version="14.5",
            agent_version="7.0.0",
            environment=TelemetricEnvironment.MOCK_SIMULATED,
            timestamp_ns=now_ns,
        ),
        local_network=LocalNetworkTelemetry(
            default_gateway_ip="192.168.1.1",
            default_gateway_mac="00:11:22:33:44:01",
            gateway_is_reachable=gateway_is_reachable,
            gateway_rtt_ms=gateway_rtt_ms if gateway_is_reachable else None,
            gateway_loss_pct=100.0 if not gateway_is_reachable else gateway_loss_pct,
            interface_name="en0",
            interface_type=InterfaceType.WIFI if is_wifi else InterfaceType.ETHERNET,
            interface_state=InterfaceState.UP,
            local_ip="192.168.1.100",
            subnet_cidr=24,
            dhcp_enabled=True,
            configured_dns_servers=["192.168.1.1"],
            wifi=wifi_obj,
        ),
        dns_probes=[
            DnsProbeTelemetry(
                query_name="pbx.kq.internal",
                record_type="A",
                resolver_ip="192.168.1.1",
                resolution_time_ms=15.0,
                status=dns_status,
                resolved_ips=["10.50.1.10"] if dns_status == DnsResolutionStatus.NOERROR else [],
            )
        ],
        service_probes=[
            ServiceConnectivityTelemetry(
                target_id="avaya-sbce",
                target_name="Avaya SBCE Edge SIP",
                destination_ip="10.50.1.10",
                destination_port=5061,
                protocol=ServiceProtocol.TCP,
                is_reachable=service_reachable,
                tcp_connect_time_ms=15.0,
                tls_handshake_time_ms=45.0,
                http_status_code=http_status,
                http_ttfb_ms=http_ttfb_ms,
                http_total_time_ms=http_ttfb_ms + 10.0,
            )
        ],
        path_traces=[
            PathTelemetry(
                target_id="avaya-sbce",
                target_ip="10.50.1.10",
                protocol="udp",
                total_hops=len(hops),
                end_to_end_rtt_ms=hops[-1].rtt_avg_ms if hops else 12.0,
                end_to_end_loss_pct=hops[-1].loss_pct if hops else 0.0,
                path_hash="sha256hash",
                has_route_changed=False,
                hops=hops,
            )
        ],
    )


def test_01_live_zabbix_correlation_with_endpoint_fleet(zabbix_client: ZabbixClient):
    """Verify CrossDomainCorrelator with live Zabbix API and endpoint reports."""
    ep1 = make_test_endpoint("agent-terminal-01")
    ep2 = make_test_endpoint("agent-terminal-02")

    correlator = CrossDomainCorrelator(zabbix_client=zabbix_client)
    report = correlator.correlate(endpoint_reports=[ep1, ep2])

    assert report is not None
    assert report.health_state == ServiceHealthState.HEALTHY
    assert report.health_score >= 90.0
    assert report.endpoint_summary.get("total_endpoints") == 2
    assert report.endpoint_summary.get("degraded_endpoints") == 0

    # Format report string via CLI helper
    report_text = format_assurance_report(report.to_dict())
    assert "NAWARI VOICE SERVICE ASSURANCE AUDIT REPORT" in report_text
    assert "Endpoints: Total=2 | Degraded=0" in report_text


def test_02_six_failure_scenarios_calibration(zabbix_client: ZabbixClient):
    """Verify strict calibration of CONFIRMED vs PROBABLE across the 6 failure scenarios."""
    correlator = CrossDomainCorrelator(zabbix_client=zabbix_client)

    # 1. Local Endpoint Problem
    impaired = make_test_endpoint("kiosk-01", gateway_loss_pct=30.0, is_wifi=True, wifi_quality=20.0, wifi_rssi=-88)
    healthy_peer = make_test_endpoint("kiosk-02")
    r1 = correlator.correlate(endpoint_reports=[impaired, healthy_peer], active_problems=[])
    assert r1.primary_hypothesis.status == HypothesisStatus.CONFIRMED
    assert r1.primary_hypothesis.root_cause_domain == RootCauseDomain.LOCAL_ENDPOINT

    # 2. DNS Problem
    dns_fail_1 = make_test_endpoint("desk-01", dns_status=DnsResolutionStatus.SERVFAIL)
    dns_fail_2 = make_test_endpoint("desk-02", dns_status=DnsResolutionStatus.SERVFAIL)
    r2 = correlator.correlate(endpoint_reports=[dns_fail_1, dns_fail_2], active_problems=[])
    assert r2.primary_hypothesis.status == HypothesisStatus.CONFIRMED
    assert r2.primary_hypothesis.root_cause_domain == RootCauseDomain.DNS_INFRASTRUCTURE

    # 3. Network Infrastructure Problem
    degraded_hops = [
        make_hop(1, rtt_avg_ms=2.0),
        make_hop(2, ip_address="172.16.1.1", rtt_avg_ms=60.0, loss_pct=25.0),
        make_hop(3, ip_address="10.50.1.10", rtt_avg_ms=65.0, loss_pct=25.0),
    ]
    path_ep = make_test_endpoint("desk-03", hops=degraded_hops)
    zabbix_prob = [{"eventid": "999", "name": "Interface ge-0-0-1 link down", "severity": "4"}]
    r3 = correlator.correlate(endpoint_reports=[path_ep], active_problems=zabbix_prob)
    assert r3.primary_hypothesis.status == HypothesisStatus.CONFIRMED
    assert r3.primary_hypothesis.root_cause_domain == RootCauseDomain.NETWORK_TRANSIT_PATH

    # 4. Avaya Signaling Problem
    voice_sig_fail = CanonicalVoiceEvent(
        collection_timestamp=time.time(),
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=time.time() - 3.0, hungup=time.time()),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.CONGESTION,
            sip_status_code=503,
            setup_time_ms=150.0,
            duration_seconds=3.0,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.NO_MEDIA,
            data_completeness=DataCompleteness.PARTIAL_SIGNALING_ONLY,
        ),
    )
    sig_ep = make_test_endpoint("desk-04", service_reachable=True)
    r4 = correlator.correlate(voice_event=voice_sig_fail, endpoint_reports=[sig_ep], active_problems=[])
    assert r4.primary_hypothesis.status == HypothesisStatus.CONFIRMED
    assert r4.primary_hypothesis.root_cause_domain == RootCauseDomain.VOICE_SIGNALING

    # 5. Voice Media Problem
    voice_one_way = CanonicalVoiceEvent(
        collection_timestamp=time.time(),
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=time.time() - 5.0, hungup=time.time()),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            sip_status_code=200,
            setup_time_ms=120.0,
            duration_seconds=5.0,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.TRANSMIT_ONLY,
            data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA,
        ),
    )
    r5 = correlator.correlate(voice_event=voice_one_way, active_problems=[])
    assert r5.primary_hypothesis.status == HypothesisStatus.PROBABLE
    assert r5.primary_hypothesis.root_cause_domain == RootCauseDomain.FIREWALL_NAT_ASYMMETRY

    # 6. Application Problem
    app_ep = make_test_endpoint("desk-05", http_status=502)
    r6 = correlator.correlate(endpoint_reports=[app_ep], active_problems=[])
    assert r6.primary_hypothesis.status == HypothesisStatus.CONFIRMED
    assert r6.primary_hypothesis.root_cause_domain == RootCauseDomain.APPLICATION_SERVICE


def test_03_end_to_end_voice_and_endpoint_loop(zabbix_client: ZabbixClient):
    """Execute live synthetic call against Asterisk and correlate with endpoint telemetry."""
    runner = SyntheticCallRunner()
    req = SyntheticCallRequest(target="1001", timeout_seconds=10.0, dry_run=False)

    call_result = runner.execute_call(req)
    assert call_result is not None
    voice_event = CanonicalVoiceEvent.from_call_result(call_result, device_id="nawari-voice-probe-01")

    # Fleet of endpoints observing edge connectivity
    endpoints = [
        make_test_endpoint("nawari-endpoint-probe-01"),
        make_test_endpoint("nawari-endpoint-probe-02"),
    ]

    correlator = CrossDomainCorrelator(zabbix_client=zabbix_client)
    report = correlator.correlate(voice_event=voice_event, endpoint_reports=endpoints)

    assert report is not None
    assert report.report_id.startswith("sar-")
    assert report.service_id == voice_event.service_id
    assert len(report.hypotheses) >= 1
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.confidence > 0.0

    # Ensure report converts cleanly to JSON
    json_out = report.to_json(indent=2)
    assert "report_id" in json_out
    assert "endpoint_summary" in json_out
    assert "path_summary" in json_out
