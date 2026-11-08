#!/usr/bin/env python3
"""
scripts/test_end_user_network_experience.py

Executes the End-User Network Experience Monitoring (EU-NEM) pilot verification suite.
Validates presence detection, lifecycle state machine, multi-endpoint correlation,
and live Zabbix API integration. Persists evidence snapshot to:
provisioning/zabbix/snapshots/eu_nem_pilot_evidence.json.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("eunem_pilot")

SNAPSHOT_FILE = PROJECT_ROOT / "provisioning/zabbix/snapshots/eu_nem_pilot_evidence.json"


def main() -> None:
    print("=" * 80)
    print("NAWARI EU-NEM PILOT VERIFICATION & SIMULATION ENGINE")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("Scope: Presence Detection, Lifecycle Classification, Topology Correlation")
    print("=" * 80)

    # 1. Connect to Zabbix API and verify live resources
    logger.info("Connecting to Zabbix API (127.0.0.1:8088)...")
    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()

    tmpls = client.call("template.get", {
        "filter": {"host": ["Template_Nawari_End_User_Network_Experience"]},
        "selectItems": ["itemid", "name", "key_"],
        "selectTriggers": ["triggerid", "description"],
    })
    if not tmpls:
        raise RuntimeError("Template_Nawari_End_User_Network_Experience not found in Zabbix")
    logger.info(f"Verified Zabbix Template: {tmpls[0]['name']} (ID: {tmpls[0]['templateid']})")
    logger.info(f"  Items: {len(tmpls[0].get('items', []))}, Triggers: {len(tmpls[0].get('triggers', []))}")

    hosts = client.call("host.get", {
        "filter": {"host": ["KQ-LT-WIN-01", "KQ-LT-MAC-01"]},
        "output": ["hostid", "host", "name"],
        "selectHostGroups": ["name"],
    })
    logger.info(f"Verified Zabbix Pilot Hosts: {[h['host'] for h in hosts]}")

    detector = CorporatePresenceDetector()
    classifier = EndpointLifecycleClassifier(detector)
    service = EndUserExperienceService(classifier)

    scenarios_tested = []

    # Scenario 1: Nominal Healthy Operations (Windows & Mac)
    print("\n--- [SCENARIO 1] Nominal Healthy Laptops ---")
    win_snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01.corp.kenya-airways.com",
        os_type="windows",
        os_version="11.0.22631",
        network=NetworkDiagnostics(
            adapter_name="Wi-Fi 6",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=3.2,
            gateway_loss_pct=0.0,
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=True,
            dns_latency_ms=8.5,
            internal_services_ok=True,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-01",
            wifi_signal_pct=88.0,
        ),
    )
    mac_snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-MAC-01",
        hostname="kq-lt-mac-01.corp.kenya-airways.com",
        os_type="darwin",
        os_version="15.1.0",
        network=NetworkDiagnostics(
            adapter_name="en0",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=4.1,
            gateway_loss_pct=0.0,
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=True,
            dns_latency_ms=10.2,
            internal_services_ok=True,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-01",
            wifi_signal_pct=82.0,
        ),
    )
    res1 = service.evaluate_fleet([win_snap, mac_snap])
    logger.info(f"Fleet Status: Total={res1.total_endpoints}, Healthy={res1.healthy_count}, Degraded={res1.degraded_count}")
    logger.info(f"Primary Hypothesis: {res1.hypotheses[0]['hypothesis']}")
    assert res1.healthy_count == 2
    scenarios_tested.append({"scenario": "Nominal Healthy Fleet", "passed": True, "hypothesis": res1.hypotheses[0]['hypothesis']})

    # Scenario 2: Wi-Fi Access Point / RF Congestion
    print("\n--- [SCENARIO 2] Wi-Fi AP RF Congestion (2 laptops on AP-PRIDE-02) ---")
    ap_win = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0",
        network=NetworkDiagnostics(
            adapter_name="Wi-Fi",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=75.0,
            gateway_loss_pct=28.0,  # High Loss on AP
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=True,
            dns_latency_ms=30.0,
            internal_services_ok=True,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-02",
        ),
    )
    ap_mac = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-MAC-01",
        hostname="kq-lt-mac-01",
        os_type="darwin",
        os_version="15.1",
        network=NetworkDiagnostics(
            adapter_name="en0",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=82.0,
            gateway_loss_pct=32.0,  # High Loss on AP
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=True,
            dns_latency_ms=35.0,
            internal_services_ok=True,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-02",
        ),
    )
    res2 = service.evaluate_fleet([ap_win, ap_mac])
    logger.info(f"Fleet Status: Degraded={res2.degraded_count}, Hypotheses={len(res2.hypotheses)}")
    logger.info(f"Derived Root Cause: {res2.hypotheses[0]['hypothesis']} on {res2.hypotheses[0]['target_infrastructure']}")
    assert res2.hypotheses[0]['hypothesis'] == DiagnosticHypothesis.ACCESS_POINT_RF_ISSUE.value
    scenarios_tested.append({"scenario": "Wi-Fi AP RF Congestion", "passed": True, "hypothesis": res2.hypotheses[0]['hypothesis']})

    # Scenario 3: Corporate DNS Resolver Failure
    print("\n--- [SCENARIO 3] Corporate DNS Resolver Outage ---")
    dns_win = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0",
        network=NetworkDiagnostics(
            adapter_name="Wi-Fi",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=3.0,
            gateway_loss_pct=0.0,
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=False,  # Failed
            dns_latency_ms=0.0,
            internal_services_ok=False,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-01",
        ),
    )
    dns_mac = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-MAC-01",
        hostname="kq-lt-mac-01",
        os_type="darwin",
        os_version="15.1",
        network=NetworkDiagnostics(
            adapter_name="en0",
            adapter_type="WIFI",
            gateway_ip="10.2.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=4.0,
            gateway_loss_pct=0.0,
            dns_server_ip="10.2.1.10",
            dns_domain="corp.kenya-airways.com",
            dns_success=False,  # Failed
            dns_latency_ms=0.0,
            internal_services_ok=False,
            wifi_ssid="KQ-Corporate",
            wifi_bssid="AP-PRIDE-03",
        ),
    )
    res3 = service.evaluate_fleet([dns_win, dns_mac])
    logger.info(f"Derived Root Cause: {res3.hypotheses[0]['hypothesis']} -> {res3.hypotheses[0]['target_infrastructure']}")
    assert res3.hypotheses[0]['hypothesis'] == DiagnosticHypothesis.DNS_INFRASTRUCTURE_ISSUE.value
    scenarios_tested.append({"scenario": "Corporate DNS Resolver Outage", "passed": True, "hypothesis": res3.hypotheses[0]['hypothesis']})

    # Scenario 4: User-Initiated Clean Shutdown (Event 1074)
    print("\n--- [SCENARIO 4] Clean OS Shutdown Anti-False-Positive Filter ---")
    shutdown_snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-WIN-01",
        hostname="kq-lt-win-01",
        os_type="windows",
        os_version="11.0",
        lifecycle_events=[
            EndpointLifecycleEvent(
                event_id=1074,
                source="USER32",
                description="User initiated clean reboot",
                is_planned_shutdown=True,
            )
        ],
    )
    eval4 = classifier.classify(shutdown_snap)
    logger.info(f"Evaluated State: {eval4.lifecycle_state.value} (Confidence: {eval4.confidence_score})")
    assert eval4.lifecycle_state == EndpointLifecycleState.EXPECTED_SHUTDOWN
    scenarios_tested.append({"scenario": "Clean OS Shutdown Filter", "passed": True, "state": eval4.lifecycle_state.value})

    # Scenario 5: Off-Net / Remote Worker
    print("\n--- [SCENARIO 5] Off-Net / Remote Home Worker Filter ---")
    remote_snap = EndpointTelemetrySnapshot(
        endpoint_id="KQ-LT-MAC-01",
        hostname="kq-lt-mac-01",
        os_type="darwin",
        os_version="15.1",
        network=NetworkDiagnostics(
            adapter_name="en0",
            adapter_type="WIFI",
            gateway_ip="192.168.1.1",
            gateway_reachable=True,
            gateway_rtt_ms=2.5,
            gateway_loss_pct=0.0,
            dns_server_ip="8.8.8.8",
            dns_domain="home.local",
            dns_success=True,
            dns_latency_ms=12.0,
            internal_services_ok=False,
            wifi_ssid="Home-Fiber",
            vpn_active=False,
        ),
    )
    eval5 = classifier.classify(remote_snap)
    logger.info(f"Evaluated Presence: {eval5.presence_state.value}, Lifecycle: {eval5.lifecycle_state.value}")
    assert eval5.presence_state == CorporatePresenceState.OFF_NET_REMOTE
    assert eval5.lifecycle_state == EndpointLifecycleState.OUTSIDE_CORPORATE_NETWORK
    scenarios_tested.append({"scenario": "Off-Net Remote Worker", "passed": True, "state": eval5.lifecycle_state.value})

    # Persist Snapshot Evidence
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pilot_hosts": [h["host"] for h in hosts],
        "template": tmpls[0]["name"],
        "template_id": tmpls[0]["templateid"],
        "items_count": len(tmpls[0].get("items", [])),
        "triggers_count": len(tmpls[0].get("triggers", [])),
        "scenarios_tested": scenarios_tested,
        "grafana_dashboard_uid": "nawari-eu-nem-pilot",
        "status": "ACCEPTED",
    }
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    logger.info(f"Saved EU-NEM pilot evidence snapshot to: {SNAPSHOT_FILE}")

    print("\n" + "=" * 80)
    print("EU-NEM PILOT VERIFICATION COMPLETE: ALL 5 SCENARIOS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()

