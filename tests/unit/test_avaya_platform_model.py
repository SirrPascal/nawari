"""Unit tests for Workstream 10D: Avaya SBCE 8.1 and Session Manager Models."""

from __future__ import annotations

import pytest

from services.voice.avaya import (
    AvayaSBCEModel,
    AvayaSessionManagerModel,
    SBCEStatus,
)


def test_sbce_license_and_resource_thresholds():
    sbce = AvayaSBCEModel(appliance_id="sbce-edge-01", mgmt_ip="10.2.156.60")

    # 1. Nominal state
    sbce.update_telemetry(
        active_sessions=150,
        max_licensed_sessions=500,
        media_utilization_pct=30.0,
        cpu_utilization_pct=45.0,
    )
    res_nominal = sbce.evaluate_health()
    assert res_nominal["status"] == "HEALTHY"
    assert res_nominal["license_utilization_pct"] == 30.0

    # 2. License warning (86%)
    sbce.update_telemetry(
        active_sessions=430,
        max_licensed_sessions=500,
        media_utilization_pct=50.0,
        cpu_utilization_pct=55.0,
    )
    res_warn = sbce.evaluate_health()
    assert res_warn["status"] == "WARNING"
    assert any("License Utilization High" in a for a in res_warn["anomalies"])

    # 3. License critical (99%)
    sbce.update_telemetry(
        active_sessions=495,
        max_licensed_sessions=500,
        media_utilization_pct=70.0,
        cpu_utilization_pct=60.0,
    )
    res_crit = sbce.evaluate_health()
    assert res_crit["status"] == "CRITICAL"
    assert any("License Exhaustion Critical" in a for a in res_crit["anomalies"])

    # 4. CPU saturation
    sbce.update_telemetry(
        active_sessions=200,
        max_licensed_sessions=500,
        cpu_utilization_pct=92.0,
    )
    res_cpu = sbce.evaluate_health()
    assert res_cpu["status"] == "CRITICAL"
    assert any("CPU Saturation Critical" in a for a in res_cpu["anomalies"])


def test_session_manager_entity_links():
    sm = AvayaSessionManagerModel(sm_id="sm-core-01", mgmt_ip="10.2.156.55")

    sm.add_or_update_link("SBCE-Trunk", "10.2.156.60", "TLS", "UP", 2.1)
    sm.add_or_update_link("CM-Trunk", "10.2.156.50", "TLS", "UP", 1.8)

    health_ok = sm.evaluate_entity_health()
    assert health_ok["status"] == "HEALTHY"
    assert health_ok["down_links_count"] == 0

    # Link down condition
    sm.add_or_update_link("Carrier-Safaricom", "196.201.214.10", "TLS", "DOWN", 0.0)
    health_down = sm.evaluate_entity_health()
    assert health_down["status"] == "CRITICAL"
    assert health_down["down_links_count"] == 1
    assert any("Carrier-Safaricom" in a for a in health_down["anomalies"])


def test_station_vs_trunk_outage_distinction():
    # 1. 480 User not registered -> Station Offline, NOT trunk failure
    res_480 = AvayaSessionManagerModel.distinguish_station_from_trunk_outage(
        sip_code=480,
        warning_header='399 avaya-sm "User not registered"',
    )
    assert res_480["category"] == "STATION_STATE"
    assert res_480["is_trunk_failure"] is False
    assert res_480["requires_noc_escalation"] is False

    # 2. 486 Busy -> Station State, NOT trunk failure
    res_486 = AvayaSessionManagerModel.distinguish_station_from_trunk_outage(sip_code=486)
    assert res_486["category"] == "STATION_STATE"
    assert res_486["is_trunk_failure"] is False

    # 3. 503 Unavailable -> Trunk failure requiring NOC escalation
    res_503 = AvayaSessionManagerModel.distinguish_station_from_trunk_outage(sip_code=503)
    assert res_503["category"] == "INFRASTRUCTURE_FAILURE"
    assert res_503["is_trunk_failure"] is True
    assert res_503["requires_noc_escalation"] is True

    # 4. 404 Not Found -> Dial plan defect
    res_404 = AvayaSessionManagerModel.distinguish_station_from_trunk_outage(sip_code=404)
    assert res_404["category"] == "DIALPLAN_DEFECT"
    assert res_404["is_trunk_failure"] is False
    assert res_404["requires_noc_escalation"] is True

