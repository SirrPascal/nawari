"""
tests/unit/test_end_user_network_experience.py

Automated test suite for Nawari End-User Network Experience Monitoring (EU-NEM).
Verifies:
1. Corporate Network Presence Detection (Confirmed, Degraded, Off-Net).
2. Lifecycle State Classification (Shutdown, Sleep, Network Failure, Degraded, Unclassified).
3. Multi-Endpoint Correlation and Diagnostic Hypotheses (DNS outage, AP RF issue, Isolated laptop).
4. Live Zabbix API Provisioning (Template, Active Checks items, Dual-expression triggers, Pilot hosts).
"""

import time
import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
from services.endpoint.experience.correlation_engine import EndUserExperienceService
from services.endpoint.experience.lifecycle_classifier import EndpointLifecycleClassifier
from services.endpoint.experience.models import (
    CorporatePresenceState,
    DiagnosticHypothesis,
    EndpointLifecycleEvent,
    EndpointLifecycleState,
    EndpointTelemetrySnapshot,
    NetworkDiagnostics,
)
from services.endpoint.experience.presence_detector import CorporatePresenceDetector


def test_01_presence_detector_corporate_confirmed():
    """Verify on-premises laptop with corporate network attributes is CORPORATE_CONFIRMED."""
    detector = CorporatePresenceDetector()
    net = NetworkDiagnostics(
        adapter_name="Wi-Fi",
        adapter_type="WIFI",
        gateway_ip="10.2.1.1",
        gateway_reachable=True,
        gateway_rtt_ms=4.5,
        gateway_loss_pct=0.0,
        dns_server_ip="10.2.1.10",
        dns_domain="corp.kenya-airways.com",
        dns_success=True,
        dns_latency_ms=12.0,
        internal_services_ok=True,
        wifi_ssid="KQ-Corporate",
        wifi_bssid="00:11:22:33:44:55",
        wifi_signal_pct=85.0,
    )
    state, conf = detector.evaluate(net)
    assert state == CorporatePresenceState.CORPORATE_CONFIRMED
    assert conf >= 0.8


def test_02_presence_detector_corporate_degraded():
    """Verify laptop on corporate gateway is CORPORATE_DEGRADED when DNS fails (not marked off-net)."""
    detector = CorporatePresenceDetector()
    net = NetworkDiagnostics(
        adapter_name="Wi-Fi",
        adapter_type="WIFI",
        gateway_ip="10.2.1.1",
        gateway_reachable=True,
        gateway_rtt_ms=5.0,
        gateway_loss_pct=0.0,
        dns_server_ip="10.2.1.10",
        dns_domain="corp.kenya-airways.com",
        dns_success=False,  # DNS Outage
        dns_latency_ms=0.0,
        internal_services_ok=False,
        wifi_ssid="KQ-Corporate",
    )
    state, conf = detector.evaluate(net)
    assert state == CorporatePresenceState.CORPORATE_DEGRADED
    assert conf > 0.0


def test_03_presence_detector_off_net_remote():
    """Verify home/remote laptop on public IP with zero corporate markers is OFF_NET_REMOTE."""
    detector = CorporatePresenceDetector()
    net = NetworkDiagnostics(
        adapter_name="Wi-Fi",
        adapter_type="WIFI",
        gateway_ip="192.168.1.1",
        gateway_reachable=True,
        gateway_rtt_ms=2.0,
        gateway_loss_pct=0.0,
        dns_server_ip="8.8.8.8",
        dns_domain="home.local",
        dns_success=True,
        dns_latency_ms=15.0,
        internal_services_ok=False,
        wifi_ssid="Home-Fiber-5G",
        vpn_active=False,
    )
    state, conf = detector.evaluate(net)
    assert state == CorporatePresenceState.OFF_NET_REMOTE


def test_04_lifecycle_classifier_planned_shutdown():
    """Verify Windows Event 1074 triggers EXPECTED_SHUTDOWN without generating an alert."""
    classifier = EndpointLifecycleClassifier()
    net = NetworkDiagnostics(
        adapter_name="Ethernet",
        adapter_type="ETHERNET",
        gateway_ip="10.2.1.1",
        gateway_reachable=True,
        gateway_rtt_ms=1.0,
        gateway_loss_pct=0.0,
        dns_server_ip="10.2.1.10",
        dns_domain="corp.kenya-airways.com",
        dns_success=True,
        dns_latency_ms=5.0,
        internal_services_ok=True,
    )
    snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0.22631",
        network=net,
        lifecycle_events=[
            EndpointLifecycleEvent(
                event_id=1074,
                source="USER32",
                description="The process explorer.exe has initiated the shutdown of computer KQ-LT-WIN-01.",
                is_planned_shutdown=True,
            )
        ],
    )
    res = classifier.classify(snap)
    assert res.lifecycle_state == EndpointLifecycleState.EXPECTED_SHUTDOWN
    assert res.confidence_score == 1.0


def test_05_lifecycle_classifier_sleep_state():
    """Verify sleep event classifies laptop as SLEEPING rather than a network outage."""
    classifier = EndpointLifecycleClassifier()
    net = NetworkDiagnostics(
        adapter_name="Wi-Fi",
        adapter_type="WIFI",
        gateway_ip="10.2.1.1",
        gateway_reachable=True,
        gateway_rtt_ms=5.0,
        gateway_loss_pct=0.0,
        dns_server_ip="10.2.1.10",
        dns_domain="corp.kenya-airways.com",
        dns_success=True,
        dns_latency_ms=10.0,
        internal_services_ok=True,
    )
    snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-MAC-01",
        hostname="kq-lt-mac-01",
        os_type="darwin",
        os_version="15.1.0",
        network=net,
        lifecycle_events=[
            EndpointLifecycleEvent(
                event_id=1,
                source="macOS_powerd",
                description="Entering Sleep state due to ClamshellSleep",
                is_sleep=True,
            )
        ],
    )
    res = classifier.classify(snap)
    assert res.lifecycle_state == EndpointLifecycleState.SLEEPING


def test_06_lifecycle_classifier_silent_agent_unclassified():
    """Verify agent silent for > 3m without shutdown record is UNREACHABLE_UNCLASSIFIED."""
    classifier = EndpointLifecycleClassifier()
    snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0",
    )
    res = classifier.classify(snap, last_heartbeat_age_sec=240.0)
    assert res.lifecycle_state == EndpointLifecycleState.UNREACHABLE_UNCLASSIFIED
    assert "silent" in res.primary_symptom.lower()


def test_07_lifecycle_classifier_corporate_gateway_failure():
    """Verify corporate presence with unreachable gateway triggers NETWORK_FAILURE."""
    classifier = EndpointLifecycleClassifier()
    net = NetworkDiagnostics(
        adapter_name="Wi-Fi",
        adapter_type="WIFI",
        gateway_ip="10.2.1.1",
        gateway_reachable=False,
        gateway_rtt_ms=0.0,
        gateway_loss_pct=100.0,
        dns_server_ip="10.2.1.10",
        dns_domain="corp.kenya-airways.com",
        dns_success=False,
        dns_latency_ms=0.0,
        internal_services_ok=False,
        wifi_ssid="KQ-Corporate",
    )
    snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0",
        network=net,
    )
    res = classifier.classify(snap)
    assert res.lifecycle_state == EndpointLifecycleState.NETWORK_FAILURE
    assert "unreachable" in res.primary_symptom.lower()


def test_08_correlation_engine_dns_infrastructure_issue():
    """Verify multiple endpoints on healthy gateways failing DNS generates DNS_INFRASTRUCTURE_ISSUE."""
    service = EndUserExperienceService()
    
    def make_dns_failing_snap(ep_id: str, bssid: str) -> EndpointTelemetrySnapshot:
        net = NetworkDiagnostics(
            adapter_name="Wi-Fi",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=4.0,
            gateway_loss_pct=0.0,
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=False,  # Failed DNS
            dns_latency_ms=0.0,
            internal_services_ok=False,
            wifi_ssid="KQ-Corporate",
            wifi_bssid=bssid,
        )
        return EndpointTelemetrySnapshot(
            endpoint_id=ep_id,
            hostname=ep_id.lower(),
            os_type="windows",
            os_version="11.0",
            network=net,
        )

    snapshots = [
        make_dns_failing_snap("KQ-LT-01", "AP-PRIDE-01"),
        make_dns_failing_snap("KQ-LT-02", "AP-PRIDE-02"),
        make_dns_failing_snap("KQ-LT-03", "AP-PRIDE-03"),
    ]

    fleet_res = service.evaluate_fleet(snapshots)
    assert fleet_res.total_endpoints == 3
    assert fleet_res.degraded_count == 3
    hypo_types = [h["hypothesis"] for h in fleet_res.hypotheses]
    assert DiagnosticHypothesis.DNS_INFRASTRUCTURE_ISSUE.value in hypo_types


def test_09_correlation_engine_ap_rf_issue():
    """Verify multiple endpoints on same AP suffering packet loss generates ACCESS_POINT_RF_ISSUE."""
    service = EndUserExperienceService()

    def make_ap_loss_snap(ep_id: str) -> EndpointTelemetrySnapshot:
        net = NetworkDiagnostics(
            adapter_name="Wi-Fi",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=45.0,
            gateway_loss_pct=25.0,  # High Loss on AP
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=True,
            dns_latency_ms=25.0,
            internal_services_ok=True,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-FLOOR2-01",
        )
        return EndpointTelemetrySnapshot(
            endpoint_id=ep_id,
            hostname=ep_id.lower(),
            os_type="windows",
            os_version="11.0",
            network=net,
        )

    snapshots = [
        make_ap_loss_snap("KQ-LT-01"),
        make_ap_loss_snap("KQ-LT-02"),
    ]

    fleet_res = service.evaluate_fleet(snapshots)
    hypo_types = [h["hypothesis"] for h in fleet_res.hypotheses]
    assert DiagnosticHypothesis.ACCESS_POINT_RF_ISSUE.value in hypo_types


def test_10_live_zabbix_template_and_pilot_provisioning():
    """Verify Zabbix API has EU-NEM template, 10 items, 7 triggers, and validates pilot host lifecycle."""
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()

    # 1. Verify template exists
    tmpls = client.call("template.get", {
        "filter": {"host": ["Template_Nawari_End_User_Network_Experience"]},
        "selectItems": ["itemid", "name", "key_", "type"],
        "selectTriggers": ["triggerid", "description", "priority"],
    })
    assert len(tmpls) == 1, "Template_Nawari_End_User_Network_Experience must exist in Zabbix"
    tmpl = tmpls[0]
    items = tmpl.get("items", [])
    triggers = tmpl.get("triggers", [])
    assert len(items) >= 10, f"Template must have >= 10 items (got {len(items)})"
    assert len(triggers) >= 7, f"Template must have >= 7 triggers (got {len(triggers)})"

    # 2. Verify pilot host group exists
    groups = client.call("hostgroup.get", {"filter": {"name": ["Nawari / Endpoints / Pilot"]}})
    assert len(groups) == 1, "Host group 'Nawari / Endpoints / Pilot' must exist in Zabbix"
    pilot_group_id = groups[0]["groupid"]

    # 3. Dynamic test of pilot host creation, linkage, and cleanup
    test_host_name = "KQ-LT-PILOT-TEST-01"
    created = client.call("host.create", {
        "host": test_host_name,
        "name": "KQ-LT-PILOT-TEST-01 (Test Laptop)",
        "interfaces": [{
            "type": 1,
            "main": 1,
            "useip": 1,
            "ip": "127.0.0.1",
            "dns": "test.local",
            "port": "10050",
        }],
        "groups": [{"groupid": pilot_group_id}],
        "templates": [{"templateid": tmpl["templateid"]}],
        "status": 0,
    })
    test_host_id = created["hostids"][0]
    try:
        # Verify host inherited items and triggers from EU-NEM template
        h = client.call("host.get", {
            "hostids": [test_host_id],
            "selectItems": ["itemid", "name", "key_"],
            "selectTriggers": ["triggerid", "description"],
        })
        assert len(h[0].get("items", [])) >= 10
        assert len(h[0].get("triggers", [])) >= 7
    finally:
        # Clean up so baseline infrastructure host count remains strictly 11
        client.call("host.delete", [test_host_id])
