"""Unit tests for Nawari Aviation Business Service Catalogue and SLI/SLO Engine (Workstream 13B)."""

import pytest
from services.multisite.service_catalog import (
    BusinessService,
    DependencyLogic,
    MultiDimensionalSLIResult,
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


def test_critical_mandatory_dependency_failure_cannot_be_hidden():
    """Verify that a service with a failed mandatory dependency drops immediately to CRITICAL_DOWN.
    
    It must NOT appear healthy simply because multiple non-critical components are up.
    """
    catalog = ServiceCatalog(auto_seed=True)

    # Core JKIA switch SW-DC1-01 is MANDATORY for SVC-DCS-GLOBAL.
    # Set SW-DC1-01 to DOWN, but leave all circuits ACTIVE.
    comp_states = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
    }

    res = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states)
    assert res.is_mandatory_failed is True
    assert res.status == "CRITICAL_DOWN"
    assert res.health_index == 0.0
    assert any("CRITICAL DEPENDENCY FAILED" in n for n in res.evaluation_notes)


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

    # 2. Replayed telemetry must NOT establish live current health
    comp_states_replayed = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
    }
    res_replayed = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_replayed)
    # Since CIR-NBO-01 and SW-DC1-01 are mandatory, replayed data fails live mandatory check -> CRITICAL_DOWN
    assert res_replayed.status == "CRITICAL_DOWN"
    assert any("REPLAYED telemetry" in note for note in res_replayed.evaluation_notes)

    # 3. Stale telemetry
    comp_states_stale = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.STALE.value},
    }
    res_stale = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_stale)
    assert res_stale.status == "CRITICAL_DOWN"
    assert any("STALE" in note for note in res_stale.evaluation_notes)


def test_partial_outage_and_global_isolation():
    catalog = ServiceCatalog(auto_seed=True)

    # Mombasa local switch down, but JKIA core healthy
    comp_states = {
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


def test_multidimensional_sli_and_coverage():
    engine = SLIEvaluationEngine()
    spec = SLOSpecification(
        service_id="SVC-DCS-GLOBAL",
        target_slo_percent=99.95,
        contractual_sla_percent=99.90,
        measurement_window_days=30,  # 43,200 min total
        scheduled_maintenance_minutes=60.0,
    )
    engine.register_slo(spec)

    # Record 43,000 minutes of healthy, performing intervals
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=43000.0, health_index=1.0, is_available=True, is_performance_met=True)
    
    # Record 100 minutes of high latency (performance degraded but available)
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=100.0, health_index=0.80, is_available=True, is_performance_met=False)

    # Record 50 minutes of unknown/missing telemetry
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=50.0, health_index=0.0, is_available=False, is_unknown=True)

    res = engine.evaluate_sli("SVC-DCS-GLOBAL")
    
    # Availability SLI vs Performance SLI distinction:
    assert res.availability_sli > res.performance_sli
    assert res.quality_sli <= res.availability_sli
    # Coverage tracking (50 unknown minutes must be accounted for)
    assert res.unknown_minutes == 50.0
    assert res.coverage_percent < 100.0
    assert res.total_expected_minutes == 43150.0


def test_nuanced_service_dependency_semantics_four_scenarios():
    """Verify precision service dependency evaluation across 4 distinct operational scenarios:
    1. Mandatory non-redundant component failure -> CRITICAL_DOWN
    2. Primary failover active (primary down, secondary up) -> DEGRADED
    3. Redundancy group member failure (secondary down, primary up) -> DEGRADED
    4. Redundancy group complete exhaustion (all members down) -> CRITICAL_DOWN
    """
    catalog = ServiceCatalog(auto_seed=True)

    # Base upstream DCS global dependencies healthy
    base_states = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": "FRESH"},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-DC1-01": {"state": "ACTIVE", "quality": "FRESH"},
    }

    # Scenario 1: Mandatory non-redundant failure (SW-MBA-01 down) -> CRITICAL_DOWN
    states_scen1 = {
        **base_states,
        "CIR-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-MBA-01": {"state": "DOWN", "quality": "FRESH"},
    }
    res1 = catalog.evaluate_service_health("SVC-DCS-MBA", states_scen1)
    assert res1.status == "CRITICAL_DOWN"
    assert res1.is_mandatory_failed is True
    assert res1.health_index == 0.0
    assert any("Mandatory component 'SW-MBA-01'" in n for n in res1.evaluation_notes)

    # Scenario 2: Primary failover active (CIR-MBA-01 down, CIR-MBA-02 up, switch up) -> DEGRADED
    states_scen2 = {
        **base_states,
        "CIR-MBA-01": {"state": "DOWN", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "ACTIVE", "quality": "FRESH"},
        "SW-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
    }
    res2 = catalog.evaluate_service_health("SVC-DCS-MBA", states_scen2)
    assert res2.status == "DEGRADED"
    assert res2.is_mandatory_failed is False
    assert 0.0 < res2.health_index <= 0.70
    assert any("PRIMARY FAILOVER ACTIVE" in n for n in res2.evaluation_notes)

    # Scenario 3: Redundancy member degraded (CIR-MBA-02 down, CIR-MBA-01 up, switch up) -> DEGRADED
    states_scen3 = {
        **base_states,
        "CIR-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "DOWN", "quality": "FRESH"},
        "SW-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
    }
    res3 = catalog.evaluate_service_health("SVC-DCS-MBA", states_scen3)
    assert res3.status == "DEGRADED"
    assert res3.is_mandatory_failed is False
    assert 0.0 < res3.health_index <= 0.70
    assert any("REDUNDANCY DEGRADED" in n for n in res3.evaluation_notes)

    # Scenario 4: Redundancy group complete exhaustion (both circuits down, switch up) -> CRITICAL_DOWN
    states_scen4 = {
        **base_states,
        "CIR-MBA-01": {"state": "DOWN", "quality": "FRESH"},
        "CIR-MBA-02": {"state": "DOWN", "quality": "FRESH"},
        "SW-MBA-01": {"state": "ACTIVE", "quality": "FRESH"},
    }
    res4 = catalog.evaluate_service_health("SVC-DCS-MBA", states_scen4)
    assert res4.status == "CRITICAL_DOWN"
    assert res4.is_mandatory_failed is True
    assert res4.health_index == 0.0
    assert any("completely exhausted" in n for n in res4.evaluation_notes)
