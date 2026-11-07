"""Unit tests for Stage 7F: Cross-Domain Service Assurance & Automated Root-Cause Hierarchy."""

import time
import pytest

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
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import (
    CanonicalVoiceEvent,
    DataCompleteness,
    EndpointIdentifiers,
    MediaTelemetry,
    MilestoneTimestamps,
    SignalingTelemetry,
)


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


def make_endpoint_report(
    hostname: str = "endpoint-01",
    gateway_rtt_ms: float = 4.2,
    gateway_loss_pct: float = 0.0,
    gateway_is_reachable: bool = True,
    is_wifi: bool = False,
    wifi_quality: float = 85.0,
    wifi_rssi: int = -55,
    dns_status: DnsResolutionStatus = DnsResolutionStatus.NOERROR,
    dns_latency_ms: float = 12.0,
    service_reachable: bool = True,
    tcp_ms: float = 15.0,
    tls_ms: float = 45.0,
    http_status: int = 200,
    http_ttfb_ms: float = 85.0,
    hops: list[HopTelemetry] = None,
) -> EndpointTelemetryReport:
    """Helper to synthesize structured endpoint telemetry reports."""
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
            make_hop(1, ip_address="192.168.1.1", rtt_avg_ms=2.1),
            make_hop(2, ip_address="10.0.0.1", rtt_avg_ms=8.5),
            make_hop(3, ip_address="10.50.1.10", rtt_avg_ms=14.2),
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
                resolution_time_ms=dns_latency_ms,
                status=dns_status,
                resolved_ips=["10.50.1.10"],
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
                tcp_connect_time_ms=tcp_ms,
                tls_handshake_time_ms=tls_ms,
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
                end_to_end_rtt_ms=hops[-1].rtt_avg_ms if hops else 15.0,
                end_to_end_loss_pct=hops[-1].loss_pct if hops else 0.0,
                path_hash="abc123hash",
                has_route_changed=False,
                hops=hops,
            )
        ],
    )


def make_voice_call_event(
    outcome: CallOutcome = CallOutcome.ANSWERED,
    sip_code: int = 200,
    verification: MediaVerificationLevel = MediaVerificationLevel.BIDIRECTIONAL,
    mos: float = 4.3,
) -> CanonicalVoiceEvent:
    now = time.time()
    return CanonicalVoiceEvent(
        collection_timestamp=now,
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=now - 5.0, hungup=now),
        signaling=SignalingTelemetry(
            outcome=outcome,
            setup_time_ms=140.0,
            duration_seconds=5.0,
            sip_status_code=sip_code,
        ),
        media=MediaTelemetry(
            verification_level=verification,
            estimated_mos=mos,
            jitter_ms=2.5,
            loss_pct=0.0,
            rtt_ms=14.0,
            estimated_one_way_delay_ms=20.0,
            data_completeness=DataCompleteness.COMPLETE,
        ),
    )


def test_scenario_1_local_endpoint_problem():
    """Scenario 1: Isolated high latency and poor Wi-Fi on one endpoint while peers are healthy."""
    impaired_endpoint = make_endpoint_report(
        hostname="kiosk-terminal-04",
        gateway_rtt_ms=78.5,
        gateway_loss_pct=25.0,
        is_wifi=True,
        wifi_quality=24.0,
        wifi_rssi=-84,
    )
    peer_endpoint_1 = make_endpoint_report(hostname="checkin-agent-01", gateway_rtt_ms=3.1, is_wifi=False)
    peer_endpoint_2 = make_endpoint_report(hostname="checkin-agent-02", gateway_rtt_ms=2.8, is_wifi=False)

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(
        endpoint_reports=[impaired_endpoint, peer_endpoint_1, peer_endpoint_2]
    )

    assert report.health_state in (ServiceHealthState.DEGRADED, ServiceHealthState.CRITICAL)
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.root_cause_domain == RootCauseDomain.LOCAL_ENDPOINT
    assert "kiosk-terminal-04" in primary.title
    assert any(e.domain == EvidenceDomain.ENDPOINT for e in primary.evidence)
    assert any("Wi-Fi" in r or "cabling" in r for r in primary.remediation_recommendations)


def test_scenario_2_dns_infrastructure_problem():
    """Scenario 2: Multiple endpoints fail DNS queries (NXDOMAIN/SERVFAIL) while IP transport succeeds."""
    ep1 = make_endpoint_report(
        hostname="ops-workstation-01",
        dns_status=DnsResolutionStatus.SERVFAIL,
        gateway_is_reachable=True,
    )
    ep2 = make_endpoint_report(
        hostname="ops-workstation-02",
        dns_status=DnsResolutionStatus.SERVFAIL,
        gateway_is_reachable=True,
    )

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(endpoint_reports=[ep1, ep2])

    assert report.health_state in (ServiceHealthState.DEGRADED, ServiceHealthState.CRITICAL)
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.root_cause_domain == RootCauseDomain.DNS_INFRASTRUCTURE
    assert "DNS" in primary.title
    assert any(e.domain == EvidenceDomain.DNS for e in primary.evidence)
    assert any("resolver" in r.lower() or "dns" in r.lower() for r in primary.remediation_recommendations)


def test_scenario_3_network_infrastructure_problem():
    """Scenario 3: Transit WAN hop packet loss coincides with active Zabbix router interface alarm."""
    degraded_hops = [
        make_hop(1, ip_address="192.168.1.1", rtt_avg_ms=2.0, loss_pct=0.0),
        make_hop(2, ip_address="172.16.50.1", rtt_avg_ms=45.0, loss_pct=30.0),
        make_hop(3, ip_address="10.50.1.10", rtt_avg_ms=52.0, loss_pct=30.0),
    ]
    ep = make_endpoint_report(hostname="hq-finance-01", hops=degraded_hops)

    active_problems = [
        {"eventid": "301", "name": "Interface ge-0/0/2 link down on core-router-01", "severity": "4"}
    ]

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(
        endpoint_reports=[ep],
        active_problems=active_problems,
    )

    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.root_cause_domain == RootCauseDomain.NETWORK_TRANSIT_PATH
    assert "Network Infrastructure" in primary.title or "Transit" in primary.title
    assert any(e.domain == EvidenceDomain.PATH for e in primary.evidence)
    assert any(e.domain == EvidenceDomain.NETWORK for e in primary.evidence)


def test_scenario_4_avaya_signaling_problem():
    """Scenario 4: Perimeter TCP port 5061 is reachable, but synthetic call fails with SIP 503."""
    ep = make_endpoint_report(hostname="telephony-tester-01", service_reachable=True, tcp_ms=12.0)
    voice_event = make_voice_call_event(outcome=CallOutcome.CONGESTION, sip_code=503)

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(voice_event=voice_event, endpoint_reports=[ep])

    assert report.health_state == ServiceHealthState.CRITICAL
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.root_cause_domain == RootCauseDomain.VOICE_SIGNALING
    assert "Signaling Outage" in primary.title or "SIP 503" in primary.title
    assert any(e.domain == EvidenceDomain.SIGNALING for e in primary.evidence)
    assert any(e.domain == EvidenceDomain.SERVICE for e in primary.evidence)
    assert any("Session Manager" in r or "ACM" in r for r in primary.remediation_recommendations)


def test_scenario_5_voice_media_problem():
    """Scenario 5: SIP call answered (200 OK), but media is strictly one-way (firewall RTP drop)."""
    voice_event = make_voice_call_event(
        outcome=CallOutcome.ANSWERED,
        sip_code=200,
        verification=MediaVerificationLevel.TRANSMIT_ONLY,
    )

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(voice_event=voice_event)

    assert report.health_state == ServiceHealthState.CRITICAL
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.FIREWALL_NAT_ASYMMETRY
    assert "One-Way Audio" in primary.title
    assert any(e.domain == EvidenceDomain.MEDIA for e in primary.evidence)


def test_scenario_6_application_service_problem():
    """Scenario 6: DNS, TCP, and TLS succeed (<100ms), but HTTP service returns HTTP 500."""
    ep = make_endpoint_report(
        hostname="dispatch-console-01",
        dns_status=DnsResolutionStatus.NOERROR,
        dns_latency_ms=10.0,
        tcp_ms=14.0,
        tls_ms=35.0,
        http_status=500,
        http_ttfb_ms=45.0,
    )

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(endpoint_reports=[ep])

    assert report.health_state in (ServiceHealthState.DEGRADED, ServiceHealthState.CRITICAL)
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.root_cause_domain == RootCauseDomain.APPLICATION_SERVICE
    assert "Application Backend Failure" in primary.title
    assert any(e.domain == EvidenceDomain.SERVICE for e in primary.evidence)
    assert any("server logs" in r.lower() or "database" in r.lower() for r in primary.remediation_recommendations)


def test_healthy_fleet_scenario():
    """Scenario 7: Clean normal fleet execution with healthy gateway, DNS, and services."""
    ep1 = make_endpoint_report(hostname="desk-01")
    ep2 = make_endpoint_report(hostname="desk-02")
    voice_event = make_voice_call_event(outcome=CallOutcome.ANSWERED, mos=4.38)

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(voice_event=voice_event, endpoint_reports=[ep1, ep2])

    assert report.health_state == ServiceHealthState.HEALTHY
    assert report.health_score >= 90.0
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.HEALTHY
    assert primary.root_cause_domain == RootCauseDomain.HEALTHY
