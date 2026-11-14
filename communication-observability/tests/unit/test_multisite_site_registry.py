"""Unit tests for Nawari Multi-Site Outstation Registry (Workstream 13A)."""

import pytest
from services.multisite.site_registry import (
    FacilitySite,
    InfrastructureDomain,
    InfrastructureNode,
    MultiSiteRegistry,
    PSTNBreakoutType,
    SiteTier,
    StationRecord,
    WANCircuit,
    WANCircuitType,
)


def test_canonical_site_seeding_and_hierarchy():
    registry = MultiSiteRegistry(auto_seed=True)
    fleet = registry.get_fleet_summary()
    assert fleet["total_stations"] >= 12
    assert fleet["healthy_stations"] >= 10
    assert "East Africa" in fleet["region_counts"]
    assert "Europe" in fleet["region_counts"]

    # Lookup by ID
    jkia = registry.get_station("JKIA-HUB")
    assert jkia is not None
    assert jkia.iata_code == "NBO"
    assert jkia.icao_code == "HKJK"
    assert jkia.site_tier == SiteTier.HUB
    assert jkia.region == "East Africa"
    assert jkia.country == "Kenya"
    assert len(jkia.wan_circuits) >= 3
    assert len(jkia.facilities) >= 4
    assert "JKIA-DC1" in jkia.facilities
    assert jkia.get_total_devices() >= 7

    # Verify UUID immutability
    assert len(jkia.uuid_str) == 36
    by_uuid = registry.get_station_by_uuid(jkia.uuid_str)
    assert by_uuid is not None
    assert by_uuid.station_id == "JKIA-HUB"

    # Lookup by IATA
    mba = registry.get_station_by_iata("MBA")
    assert mba is not None
    assert mba.city == "Mombasa"
    assert mba.site_tier == SiteTier.DOMESTIC_PRIMARY
    assert mba.management_lead == "Mombasa Duty Engineer"

    # Lookup by ICAO
    lhr = registry.get_station_by_icao("EGLL")
    assert lhr is not None
    assert lhr.iata_code == "LHR"
    assert lhr.country == "United Kingdom"
    assert lhr.timezone == "Europe/London"

    # Region filtering
    europe_stations = registry.get_stations_by_region("Europe")
    iata_codes = {s.iata_code for s in europe_stations}
    assert "LHR" in iata_codes
    assert "AMS" in iata_codes


def test_site_circuit_status_updates_and_health():
    registry = MultiSiteRegistry(auto_seed=True)
    site_id = "MBA-STATION"

    # Initial state should be healthy
    health = registry.calculate_station_health(site_id)
    assert health["status"] == "HEALTHY"
    assert health["health_score"] == 1.0
    assert health["active_circuits"] == 2

    # Simulate primary MPLS circuit drop
    ok = registry.update_circuit_status(site_id, "CIR-MBA-01", "DOWN")
    assert ok is True

    # Now health should be FAILOVER_ACTIVE (secondary SD-WAN is active)
    health_failover = registry.calculate_station_health(site_id)
    assert health_failover["status"] == "FAILOVER_ACTIVE"
    assert health_failover["down_circuits"] == 1
    assert health_failover["active_circuits"] == 1
    assert health_failover["health_score"] == 0.5

    # Simulate secondary drop as well
    registry.update_circuit_status(site_id, "CIR-MBA-02", "DOWN")
    health_crit = registry.calculate_station_health(site_id)
    assert health_crit["status"] == "CRITICAL_DOWN"
    assert health_crit["health_score"] == 0.0
    assert health_crit["active_circuits"] == 0

    # Restore primary
    registry.update_circuit_status(site_id, "CIR-MBA-01", "ACTIVE")
    health_restored = registry.calculate_station_health(site_id)
    assert health_restored["status"] == "DEGRADED"  # 1 active, 1 down
    assert health_restored["health_score"] == 0.5


def test_facility_sites_and_domain_tags():
    station = StationRecord(
        station_id="TEST-STATION",
        iata_code="TST",
        icao_code="HTST",
        station_name="Test Airport",
        site_tier=SiteTier.DOMESTIC_SECONDARY,
        region="East Africa",
        country="Kenya",
        city="Test City",
        timezone="Africa/Nairobi",
        latitude=0.0,
        longitude=36.0,
        operational_hours="08:00-17:00",
    )
    facility = FacilitySite(
        site_id="TST-T1",
        site_name="Test Terminal 1",
        facility_type="TERMINAL",
        local_subnet="10.99.1.0/24",
        station_id="TEST-STATION",
        edge_proxy_ip="10.99.1.250",
        domain_tags={InfrastructureDomain.NETWORK, InfrastructureDomain.APPLICATIONS},
    )
    facility.add_node(InfrastructureNode("SW-TST-01", "Test Switch", InfrastructureDomain.NETWORK, "10.99.1.1", "TST-T1", "SWITCH"))
    facility.add_node(InfrastructureNode("RTR-TST-01", "Test Router", InfrastructureDomain.NETWORK, "10.99.1.254", "TST-T1", "ROUTER"))
    station.add_facility(facility)
    assert station.get_total_devices() == 2
    assert "TST-T1" in station.facilities
    d = station.to_dict()
    assert d["total_devices"] == 2
    assert "TST-T1" in d["facilities"]
