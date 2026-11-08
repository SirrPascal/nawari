"""Unit tests for Nawari Aviation Business Service Catalogue and SLI/SLO Engine (Workstream 13B)."""

import pytest
from services.multisite.service_catalog import (
    BusinessService,
    ServiceCatalog,
    ServiceComponentDependency,
    ServiceScope,
    ServiceTier,
    SLIEvaluationEngine,
    SLOSpecification,
    TelemetryQuality,
)


def test_canonical_service_catalog_and_dag_integrity():
    catalog = ServiceCatalog(auto_seed=True)
    services = catalog.get_all_services()
    assert len(services) >= 7

    # Check Tier 1 Services
    tier1 = catalog.get_services_by_tier(ServiceTier.TIER_1_MISSION_CRITICAL)
    tier1_ids = {s.service_id for s in tier1}
    assert "SVC-DCS-GLOBAL" in tier1_ids
    assert "SVC-FLIGHT-OPS" in tier1_ids
    assert "SVC-RAMP-VOICE" in tier1_ids
    assert "SVC-DCS-MBA" in tier1_ids

    # Check Global vs Station-Local scoping
    dcs_global = catalog.get_service("SVC-DCS-GLOBAL")
    assert dcs_global.scope == ServiceScope.GLOBAL
    assert dcs_global.station_id is None

    dcs_mba = catalog.get_service("SVC-DCS-MBA")
    assert dcs_mba.scope == ServiceScope.STATION_LOCAL
    assert dcs_mba.station_id == "MBA-STATION"
    assert "SVC-DCS-GLOBAL" in dcs_mba.parent_services

    # Verify canonical DAG is acyclic
    cycles = catalog.detect_dependency_cycles()
    assert len(cycles) == 0, f"Unexpected cycles detected: {cycles}"


def test_dependency_cycle_detection():
    catalog = ServiceCatalog(auto_seed=False)
    s1 = BusinessService("SVC-A", "Service A", ServiceTier.TIER_1_MISSION_CRITICAL, ServiceScope.GLOBAL, "Desc A", parent_services=["SVC-B"])
    s2 = BusinessService("SVC-B", "Service B", ServiceTier.TIER_1_MISSION_CRITICAL, ServiceScope.GLOBAL, "Desc B", parent_services=["SVC-C"])
    s3 = BusinessService("SVC-C", "Service C", ServiceTier.TIER_1_MISSION_CRITICAL, ServiceScope.GLOBAL, "Desc C", parent_services=["SVC-A"])
    catalog.register_service(s1)
    catalog.register_service(s2)
    catalog.register_service(s3)

    cycles = catalog.detect_dependency_cycles()
    assert len(cycles) > 0
    assert any("SVC-A" in c and "SVC-B" in c and "SVC-C" in c for c in cycles)


def test_telemetry_quality_handling_and_replayed_rejection():
    catalog = ServiceCatalog(auto_seed=True)

    # 1. All fresh and healthy
    comp_states_fresh = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
    }
    res_fresh = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_fresh)
    assert res_fresh.status == "HEALTHY"
    assert res_fresh.health_index >= 0.95

    # 2. Replayed telemetry must NOT count as fresh live health
    comp_states_replayed = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
    }
    res_replayed = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_replayed)
    assert res_replayed.health_index == 0.50
    assert any("REPLAYED telemetry" in note for note in res_replayed.evaluation_notes)

    # 3. Stale telemetry
    comp_states_stale = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
    }
    res_stale = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_stale)
    assert res_stale.health_index <= 0.40
    assert any("STALE" in note for note in res_stale.evaluation_notes)


def test_partial_outage_and_global_isolation():
    catalog = ServiceCatalog(auto_seed=True)

    # Simulate Mombasa local switch down, but JKIA core healthy
    comp_states = {
        # Core JKIA healthy
        "CIR-NBO-01": {"state": "ACTIVE", "quality": "FRESH"},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-DC1-01": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-DC1-02": {"state": "ACTIVE", "quality": "FRESH"},
        # Mombasa local down
        "CIR-MBA-01": {"state": "DOWN", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "DOWN", "quality": "FRESH"},
        "SW-MBA-01": {"state": "DOWN", "quality": "FRESH"},
    }

    eval_results = catalog.evaluate_all_services(comp_states)
    services_by_id = {s["service_id"]: s for s in eval_results["services"]}

    # Global DCS remains HEALTHY
    assert services_by_id["SVC-DCS-GLOBAL"]["status"] == "HEALTHY"
    assert services_by_id["SVC-DCS-GLOBAL"]["health_index"] >= 0.95

    # Mombasa Local DCS is CRITICAL_DOWN
    assert services_by_id["SVC-DCS-MBA"]["status"] == "CRITICAL_DOWN"
    assert services_by_id["SVC-DCS-MBA"]["health_index"] == 0.0


def test_upstream_dependency_propagation():
    catalog = ServiceCatalog(auto_seed=True)

    # Core JKIA circuits down -> Global DCS is down
    comp_states = {
        "CIR-NBO-01": {"state": "DOWN", "quality": "FRESH"},
        "CIR-NBO-02": {"state": "DOWN", "quality": "FRESH"},
        "SW-DC1-01": {"state": "DOWN", "quality": "FRESH"},
        # Mombasa local components are up
        "CIR-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
    }

    eval_results = catalog.evaluate_all_services(comp_states)
    services_by_id = {s["service_id"]: s for s in eval_results["services"]}

    # Global DCS is down
    assert services_by_id["SVC-DCS-GLOBAL"]["status"] == "CRITICAL_DOWN"

    # Mombasa child service inherits the degradation from parent global DCS!
    assert services_by_id["SVC-DCS-MBA"]["status"] == "CRITICAL_DOWN"
    assert services_by_id["SVC-DCS-MBA"]["health_index"] == 0.0


def test_sli_slo_error_budget_engine():
    engine = SLIEvaluationEngine()
    spec = SLOSpecification(
        service_id="SVC-DCS-GLOBAL",
        target_slo_percent=99.95,
        contractual_sla_percent=99.90,
        measurement_window_days=30,  # 43,200 min total
        scheduled_maintenance_minutes=60.0,
    )
    engine.register_slo(spec)

    # 1. 43,000 minutes of healthy service (~30 days)
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=43000.0, health_index=1.0)
    sli_res = engine.evaluate_sli("SVC-DCS-GLOBAL")
    assert sli_res.sli_percent == 100.0
    assert sli_res.is_slo_breached is False
    assert sli_res.is_sla_breached is False
    assert sli_res.consumed_error_budget_minutes == 0.0
    # Total error budget for 99.95% on 30 days is 43200 * 0.0005 = 21.6 minutes
    assert abs(sli_res.total_error_budget_minutes - 21.6) < 0.01

    # 2. Add an outage of 10 minutes (within the 21.6 min budget)
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=10.0, health_index=0.0)
    sli_res2 = engine.evaluate_sli("SVC-DCS-GLOBAL")
    assert sli_res2.consumed_error_budget_minutes == 10.0
    assert abs(sli_res2.remaining_error_budget_minutes - 11.6) < 0.01
    assert sli_res2.burn_rate < 0.50
    assert sli_res2.sli_percent >= 99.95
    assert sli_res2.is_slo_breached is False
    assert sli_res2.is_sla_breached is False

    # 3. Add an additional 15 minutes outage (total 25 minutes > 21.6 min budget)
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=15.0, health_index=0.0)
    sli_res3 = engine.evaluate_sli("SVC-DCS-GLOBAL")
    assert sli_res3.consumed_error_budget_minutes == 25.0
    assert sli_res3.remaining_error_budget_minutes == 0.0
    assert sli_res3.burn_rate > 1.0
    assert sli_res3.sli_percent < 99.95
    assert sli_res3.is_slo_breached is True
