"""Integration tests for Nawari Multi-Site Architecture and Service Assurance (Workstreams 13A & 13B)."""

import pytest
from services.multisite.service_catalog import (
    BusinessService,
    ServiceCatalog,
    ServiceScope,
    ServiceTier,
    SLIEvaluationEngine,
    SLOSpecification,
    TelemetryQuality,
)
from services.multisite.site_registry import (
    MultiSiteRegistry,
    SiteTier,
)


def test_multisite_outstation_failure_isolation_and_service_assurance():
    """Verify that a complete outstation WAN failure degrades only local services, preserving global services."""
    registry = MultiSiteRegistry(auto_seed=True)
    catalog = ServiceCatalog(auto_seed=True)
    engine = SLIEvaluationEngine()

    # Register SLO for Global DCS and Mombasa Local DCS
    engine.register_slo(SLOSpecification(service_id="SVC-DCS-GLOBAL", target_slo_percent=99.95, measurement_window_days=30))
    engine.register_slo(SLOSpecification(service_id="SVC-DCS-MBA", target_slo_percent=99.95, measurement_window_days=30))

    # Initial state: 10,000 minutes of healthy operation across fleet
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=10000.0, health_index=1.0)
    engine.record_interval("SVC-DCS-MBA", duration_minutes=10000.0, health_index=1.0)

    # 1. Simulate dual WAN circuit cut at Mombasa (Moi International)
    # Primary Safaricom MPLS down, secondary Airtel SD-WAN down
    registry.update_circuit_status("MBA-STATION", "CIR-MBA-01", "DOWN")
    registry.update_circuit_status("MBA-STATION", "CIR-MBA-02", "DOWN")

    mba_health = registry.calculate_station_health("MBA-STATION")
    assert mba_health["status"] == "CRITICAL_DOWN"
    assert mba_health["active_circuits"] == 0

    # 2. Map circuit states into service component telemetry
    component_states = {
        # Core JKIA infrastructure remains completely healthy
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "AVAYA-SM-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "AVAYA-SBCE-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        # Mombasa local WAN links are down
        "CIR-MBA-01": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
        "CIR-MBA-02": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
        "SW-MBA-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
    }

    eval_summary = catalog.evaluate_all_services(component_states)
    services_by_id = {s["service_id"]: s for s in eval_summary["services"]}

    # Global Mission-Critical Services remain HEALTHY
    assert services_by_id["SVC-DCS-GLOBAL"]["status"] == "HEALTHY"
    assert services_by_id["SVC-DCS-GLOBAL"]["health_index"] >= 0.95
    assert services_by_id["SVC-FLIGHT-OPS"]["status"] == "HEALTHY"
    assert services_by_id["SVC-RAMP-VOICE"]["status"] == "HEALTHY"

    # Only Mombasa Station-Local DCS is affected
    assert services_by_id["SVC-DCS-MBA"]["status"] == "CRITICAL_DOWN"
    assert services_by_id["SVC-DCS-MBA"]["health_index"] <= 0.20

    # 3. Record a 60-minute duration under this state into the SLI Engine
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=60.0, health_index=services_by_id["SVC-DCS-GLOBAL"]["health_index"])
    engine.record_interval("SVC-DCS-MBA", duration_minutes=60.0, health_index=services_by_id["SVC-DCS-MBA"]["health_index"])

    # Global DCS SLI remains compliant
    global_sli = engine.evaluate_sli("SVC-DCS-GLOBAL")
    assert global_sli.sli_percent >= 99.95
    assert global_sli.is_slo_breached is False

    # Mombasa Local DCS consumed 60 minutes of error budget (> 21.6 min budget)
    mba_sli = engine.evaluate_sli("SVC-DCS-MBA")
    assert mba_sli.consumed_error_budget_minutes >= 60.0
    assert mba_sli.is_slo_breached is True
    assert mba_sli.burn_rate > 1.0


def test_replayed_outstation_telemetry_does_not_corrupt_live_sli():
    """Verify that replayed telemetry from outstation store-and-forward buffers is flagged and does not falsely satisfy live SLI."""
    catalog = ServiceCatalog(auto_seed=True)

    # Replayed telemetry for JKIA core components
    replayed_states = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.REPLAYED.value},
    }

    res = catalog.evaluate_service_health("SVC-DCS-GLOBAL", replayed_states)
    # Replayed data is capped at 0.50 health index to prevent false live health claims
    assert res.health_index == 0.50
    assert res.status == "DEGRADED"
    assert any("REPLAYED telemetry" in note for note in res.evaluation_notes)

