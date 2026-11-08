"""Canonical Multi-Site Outstation Registry and Hierarchical Topology Model.

Implements the Kenya Airways Enterprise Multi-Site Hierarchy:
Enterprise (Kenya Airways)
└── Region (East Africa, Southern Africa, Europe, Middle East, North America)
    └── Country (Kenya, Uganda, Tanzania, UK, UAE, South Africa, etc.)
        └── Station / Airport (NBO/JKIA, MBA, KIS, EDL, EBB, DAR, LHR, DXB, JNB)
            ├── Facility / Site (Pride Centre DC1, Terminal 1A, Cargo Complex, etc.)
            │   ├── Domain (NETWORK, VOICE, APPLICATIONS, ENDPOINTS)
            │   └── Infrastructure Node (Core Switch, SBCE, Check-in Client, etc.)
            └── Local Services & WAN Circuits

Enforces:
- Immutable UUID-based entity identity.
- IATA/ICAO code validation and uniqueness.
- Timezone validation.
- Primary and secondary WAN circuit relationships.
- Site ownership and operational responsibility.
- Parent-child relationship integrity and orphaned entity detection.
- Device and service associations.
- Provenance, observation timestamps, and entity lifecycle.
- Duplicate, conflicting, and orphaned entity detection.
- Clear separation between deployed Nawari sites and reference fixtures.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class EntityLifecycle(str, Enum):
    """Lifecycle state of an enterprise entity."""
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"
    STAGING = "STAGING"
    DECOMMISSIONED = "DECOMMISSIONED"


class SiteTier(str, Enum):
    """Operational tier within the Kenya Airways network."""
    HUB = "HUB"                                # JKIA Core Data Centers, Pride Centre
    DOMESTIC_PRIMARY = "DOMESTIC_PRIMARY"      # Major domestic airport (e.g. MBA Moi International)
    DOMESTIC_SECONDARY = "DOMESTIC_SECONDARY"  # Regional domestic airports (KIS, EDL, MYD)
    REGIONAL = "REGIONAL"                      # East & Central Africa (EBB, DAR, KGL, ADD, JUB)
    INTERNATIONAL = "INTERNATIONAL"            # Long-haul international stations (LHR, DXB, AMS, JNB, JFK)


class WANCircuitType(str, Enum):
    """Physical or virtual WAN connectivity transport."""
    MPLS = "MPLS"
    SD_WAN = "SD_WAN"
    INTERNET_VPN = "INTERNET_VPN"
    LTE_4G = "LTE_4G"
    VSAT = "VSAT"
    CROSS_CONNECT = "CROSS_CONNECT"


class PSTNBreakoutType(str, Enum):
    """Telephony breakout architecture."""
    CENTRAL_SIP_BACKHAUL = "CENTRAL_SIP_BACKHAUL"  # Voice backhauled to JKIA Avaya Core
    LOCAL_PSTN_GATEWAY = "LOCAL_PSTN_GATEWAY"      # Dedicated local PSTN/E1 gateway
    HYBRID = "HYBRID"                              # Local emergency breakout + Central SIP


class InfrastructureDomain(str, Enum):
    """Infrastructure technology domain within a facility site."""
    NETWORK = "NETWORK"
    VOICE = "VOICE"
    APPLICATIONS = "APPLICATIONS"
    ENDPOINTS = "ENDPOINTS"


@dataclass
class WANCircuit:
    """Individual WAN circuit connecting a station to the enterprise backbone."""
    circuit_id: str
    circuit_type: WANCircuitType
    provider: str
    bandwidth_mbps: float
    is_primary: bool
    expected_rtt_ms: float
    status: str = "ACTIVE"  # ACTIVE, DEGRADED, DOWN
    station_id: Optional[str] = None
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_observed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "circuit_id": self.circuit_id,
            "circuit_type": self.circuit_type.value,
            "provider": self.provider,
            "bandwidth_mbps": self.bandwidth_mbps,
            "is_primary": self.is_primary,
            "expected_rtt_ms": self.expected_rtt_ms,
            "status": self.status,
            "station_id": self.station_id,
            "last_observed": self.last_observed,
        }


@dataclass
class InfrastructureNode:
    """Individual physical or logical infrastructure device within a facility."""
    node_id: str
    name: str
    domain: InfrastructureDomain
    ip_address: str
    facility_id: str
    device_type: str  # SWITCH, ROUTER, FIREWALL, SBCE, PBX, SERVER, WORKSTATION
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    status: str = "ACTIVE"
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))
    lifecycle: EntityLifecycle = EntityLifecycle.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_observed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "node_id": self.node_id,
            "name": self.name,
            "domain": self.domain.value,
            "ip_address": self.ip_address,
            "facility_id": self.facility_id,
            "device_type": self.device_type,
            "mac_address": self.mac_address,
            "serial_number": self.serial_number,
            "status": self.status,
            "lifecycle": self.lifecycle.value,
            "last_observed": self.last_observed,
        }


@dataclass
class FacilitySite:
    """Specific terminal, building, data center, or facility within an Airport Station."""
    site_id: str
    site_name: str
    facility_type: str  # TERMINAL, DATA_CENTER, CARGO, HANGAR, OFFICE
    local_subnet: str
    station_id: str
    edge_proxy_ip: Optional[str] = None
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain_tags: Set[InfrastructureDomain] = field(default_factory=lambda: {
        InfrastructureDomain.NETWORK,
        InfrastructureDomain.VOICE,
        InfrastructureDomain.APPLICATIONS,
        InfrastructureDomain.ENDPOINTS,
    })
    lifecycle: EntityLifecycle = EntityLifecycle.ACTIVE
    nodes: Dict[str, InfrastructureNode] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_observed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_node(self, node: InfrastructureNode) -> None:
        node.facility_id = self.site_id
        self.nodes[node.node_id] = node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "site_id": self.site_id,
            "site_name": self.site_name,
            "facility_type": self.facility_type,
            "local_subnet": self.local_subnet,
            "station_id": self.station_id,
            "edge_proxy_ip": self.edge_proxy_ip,
            "domain_tags": [d.value for d in self.domain_tags],
            "node_count": len(self.nodes),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "lifecycle": self.lifecycle.value,
            "last_observed": self.last_observed,
        }


@dataclass
class StationRecord:
    """Canonical model for an Airport Station within Kenya Airways global network."""
    station_id: str
    iata_code: str
    icao_code: str
    station_name: str
    site_tier: SiteTier
    region: str
    country: str
    city: str
    timezone: str
    latitude: float
    longitude: float
    operational_hours: str
    operational_owner: str = "Kenya Airways Network Operations"
    management_lead: str = "NOC Station Support"
    is_deployed_nawari_site: bool = False  # True for deployed instances (e.g. JKIA, MBA); False for fixtures
    is_reference_fixture: bool = False      # Clearly labelled reference fixture
    wan_circuits: List[WANCircuit] = field(default_factory=list)
    facilities: Dict[str, FacilitySite] = field(default_factory=dict)
    pstn_breakout: PSTNBreakoutType = PSTNBreakoutType.CENTRAL_SIP_BACKHAUL
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))
    lifecycle: EntityLifecycle = EntityLifecycle.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_observed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_facility(self, facility: FacilitySite) -> None:
        facility.station_id = self.station_id
        self.facilities[facility.site_id] = facility

    def get_total_devices(self) -> int:
        return sum(len(f.nodes) for f in self.facilities.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "station_id": self.station_id,
            "iata_code": self.iata_code,
            "icao_code": self.icao_code,
            "station_name": self.station_name,
            "site_tier": self.site_tier.value,
            "region": self.region,
            "country": self.country,
            "city": self.city,
            "timezone": self.timezone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "operational_hours": self.operational_hours,
            "operational_owner": self.operational_owner,
            "management_lead": self.management_lead,
            "is_deployed_nawari_site": self.is_deployed_nawari_site,
            "is_reference_fixture": self.is_reference_fixture,
            "wan_circuits": [c.to_dict() for c in self.wan_circuits],
            "facilities": {fid: f.to_dict() for fid, f in self.facilities.items()},
            "pstn_breakout": self.pstn_breakout.value,
            "total_devices": self.get_total_devices(),
            "lifecycle": self.lifecycle.value,
            "created_at": self.created_at,
            "last_observed": self.last_observed,
        }


# Backward compatibility alias
SiteRecord = StationRecord


class MultiSiteRegistry:
    """Canonical Enterprise Multi-Site Registry and Hierarchy Engine."""

    # Valid ICAO: 4 uppercase letters, IATA: 3 uppercase letters
    IATA_REGEX = re.compile(r"^[A-Z]{3}$")
    ICAO_REGEX = re.compile(r"^[A-Z]{4}$")

    # Common valid IANA timezone prefixes
    TIMEZONE_PREFIXES = ("Africa/", "Europe/", "Asia/", "America/", "Australia/", "Indian/", "Atlantic/", "UTC")

    def __init__(self, enterprise_name: str = "Kenya Airways", auto_seed: bool = True) -> None:
        self.enterprise_name = enterprise_name
        self._stations: Dict[str, StationRecord] = {}
        self._uuid_index: Dict[str, str] = {}
        self._iata_index: Dict[str, str] = {}
        self._icao_index: Dict[str, str] = {}
        self._device_index: Dict[str, str] = {}  # device_id -> station_id
        if auto_seed:
            self.load_kenya_airways_reference_fixtures()

    def validate_station(self, station: StationRecord) -> List[str]:
        """Validate station integrity, IATA/ICAO format, uniqueness, and timezone."""
        errors: List[str] = []

        # IATA validation
        if not self.IATA_REGEX.match(station.iata_code):
            errors.append(f"Invalid IATA code '{station.iata_code}': must be exactly 3 uppercase letters.")
        elif station.iata_code in self._iata_index and self._iata_index[station.iata_code] != station.station_id:
            errors.append(f"Duplicate IATA code '{station.iata_code}' already assigned to station '{self._iata_index[station.iata_code]}'.")

        # ICAO validation
        if not self.ICAO_REGEX.match(station.icao_code):
            errors.append(f"Invalid ICAO code '{station.icao_code}': must be exactly 4 uppercase letters.")
        elif station.icao_code in self._icao_index and self._icao_index[station.icao_code] != station.station_id:
            errors.append(f"Duplicate ICAO code '{station.icao_code}' already assigned to station '{self._icao_index[station.icao_code]}'.")

        # Timezone validation
        if not any(station.timezone.startswith(p) for p in self.TIMEZONE_PREFIXES):
            errors.append(f"Invalid IANA timezone '{station.timezone}'. Must start with a valid geographical prefix.")

        # Circuit validation
        primary_circuits = [c for c in station.wan_circuits if c.is_primary]
        if station.wan_circuits and len(primary_circuits) == 0:
            errors.append(f"Station '{station.station_id}' has WAN circuits but no designated primary circuit.")

        return errors

    def register_station(self, station: StationRecord, strict: bool = True) -> None:
        """Register or update a station record with strict validation."""
        errors = self.validate_station(station)
        if strict and errors:
            raise ValueError(f"Station registration failed for '{station.station_id}': {'; '.join(errors)}")

        self._stations[station.station_id] = station
        self._uuid_index[station.uuid_str] = station.station_id
        self._iata_index[station.iata_code.upper()] = station.station_id
        self._icao_index[station.icao_code.upper()] = station.station_id

        # Index devices and check for conflicting device IDs across stations
        for fac in station.facilities.values():
            for node in fac.nodes.values():
                if node.node_id in self._device_index and self._device_index[node.node_id] != station.station_id:
                    if strict:
                        raise ValueError(f"Conflicting device ID '{node.node_id}' already assigned to station '{self._device_index[node.node_id]}'")
                self._device_index[node.node_id] = station.station_id

    # Backward compatibility alias
    def register_site(self, site: StationRecord) -> None:
        self.register_station(site)

    def get_station(self, station_id: str) -> Optional[StationRecord]:
        return self._stations.get(station_id)

    # Backward compatibility alias
    def get_site(self, site_id: str) -> Optional[StationRecord]:
        return self.get_station(site_id)

    def get_station_by_uuid(self, uuid_str: str) -> Optional[StationRecord]:
        station_id = self._uuid_index.get(uuid_str)
        return self._stations.get(station_id) if station_id else None

    def get_station_by_iata(self, iata_code: str) -> Optional[StationRecord]:
        station_id = self._iata_index.get(iata_code.upper())
        return self._stations.get(station_id) if station_id else None

    # Backward compatibility alias
    def get_site_by_iata(self, iata_code: str) -> Optional[StationRecord]:
        return self.get_station_by_iata(iata_code)

    def get_station_by_icao(self, icao_code: str) -> Optional[StationRecord]:
        station_id = self._icao_index.get(icao_code.upper())
        return self._stations.get(station_id) if station_id else None

    # Backward compatibility alias
    def get_site_by_icao(self, icao_code: str) -> Optional[StationRecord]:
        return self.get_station_by_icao(icao_code)

    def get_station_for_device(self, device_id: str) -> Optional[StationRecord]:
        station_id = self._device_index.get(device_id)
        return self._stations.get(station_id) if station_id else None

    def get_stations_by_region(self, region: str) -> List[StationRecord]:
        return [s for s in self._stations.values() if s.region.upper() == region.upper() and s.lifecycle != EntityLifecycle.DECOMMISSIONED]

    def get_stations_by_tier(self, tier: SiteTier) -> List[StationRecord]:
        return [s for s in self._stations.values() if s.site_tier == tier and s.lifecycle != EntityLifecycle.DECOMMISSIONED]

    # Backward compatibility alias
    def get_sites_by_tier(self, tier: SiteTier) -> List[StationRecord]:
        return self.get_stations_by_tier(tier)

    def get_all_stations(self) -> List[StationRecord]:
        return list(self._stations.values())

    # Backward compatibility alias
    def get_all_sites(self) -> List[StationRecord]:
        return self.get_all_stations()

    def detect_orphaned_facilities(self) -> List[str]:
        """Detect facilities associated with non-existent or decommissioned stations."""
        orphaned = []
        for station in self._stations.values():
            if station.lifecycle == EntityLifecycle.DECOMMISSIONED:
                orphaned.extend(station.facilities.keys())
        return orphaned

    def update_circuit_status(self, station_id: str, circuit_id: str, status: str) -> bool:
        """Update operational status of a specific circuit."""
        station = self.get_station(station_id)
        if not station:
            return False
        for c in station.wan_circuits:
            if c.circuit_id == circuit_id:
                c.status = status.upper()
                c.last_observed = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def calculate_station_health(self, station_id: str) -> Dict[str, Any]:
        """Compute operational health score for a specific station based on WAN circuits and facilities."""
        station = self.get_station(station_id)
        if not station:
            return {"station_id": station_id, "health_score": 0.0, "status": "UNKNOWN", "active_circuits": 0}

        if station.lifecycle in (EntityLifecycle.DECOMMISSIONED, EntityLifecycle.STAGING):
            return {"station_id": station_id, "health_score": 0.0, "status": station.lifecycle.value, "active_circuits": 0}

        if not station.wan_circuits:
            return {"station_id": station_id, "health_score": 1.0, "status": "HEALTHY", "active_circuits": 0}

        active = [c for c in station.wan_circuits if c.status == "ACTIVE"]
        degraded = [c for c in station.wan_circuits if c.status == "DEGRADED"]
        down = [c for c in station.wan_circuits if c.status == "DOWN"]

        primary_down = any(c.is_primary and c.status == "DOWN" for c in station.wan_circuits)
        primary_degraded = any(c.is_primary and c.status == "DEGRADED" for c in station.wan_circuits)

        score = (len(active) * 1.0 + len(degraded) * 0.5) / len(station.wan_circuits)
        
        if primary_down and len(active) == 0:
            status = "CRITICAL_DOWN"
            score = 0.0
        elif primary_down and len(active) > 0:
            status = "FAILOVER_ACTIVE"
            score = max(0.5, score)
        elif primary_degraded or len(down) > 0:
            status = "DEGRADED"
        else:
            status = "HEALTHY"

        return {
            "station_id": station.station_id,
            "iata_code": station.iata_code,
            "station_name": station.station_name,
            "region": station.region,
            "country": station.country,
            "tier": station.site_tier.value,
            "health_score": round(score, 2),
            "status": status,
            "is_deployed_nawari_site": station.is_deployed_nawari_site,
            "is_reference_fixture": station.is_reference_fixture,
            "active_circuits": len(active),
            "degraded_circuits": len(degraded),
            "down_circuits": len(down),
            "total_circuits": len(station.wan_circuits),
            "facility_count": len(station.facilities),
            "total_devices": station.get_total_devices(),
        }

    # Backward compatibility alias
    def calculate_site_health(self, site_id: str) -> Dict[str, Any]:
        h = self.calculate_station_health(site_id)
        h["site_id"] = h["station_id"]
        h["site_name"] = h["station_name"]
        return h

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Aggregate health metrics across the entire airline network."""
        total_stations = len(self._stations)
        tier_counts = {tier.value: 0 for tier in SiteTier}
        region_counts: Dict[str, int] = {}
        deployed_sites = 0
        reference_fixtures = 0
        healthy_count = 0
        degraded_count = 0
        critical_count = 0

        for station in self._stations.values():
            tier_counts[station.site_tier.value] += 1
            region_counts[station.region] = region_counts.get(station.region, 0) + 1
            if station.is_deployed_nawari_site:
                deployed_sites += 1
            if station.is_reference_fixture:
                reference_fixtures += 1

            health = self.calculate_station_health(station.station_id)
            if health["status"] == "HEALTHY":
                healthy_count += 1
            elif health["status"] in ("DEGRADED", "FAILOVER_ACTIVE"):
                degraded_count += 1
            else:
                critical_count += 1

        overall_score = (healthy_count * 1.0 + degraded_count * 0.6) / total_stations if total_stations > 0 else 0.0

        return {
            "enterprise": self.enterprise_name,
            "total_stations": total_stations,
            "total_sites": total_stations,  # alias
            "deployed_nawari_sites": deployed_sites,
            "reference_fixtures": reference_fixtures,
            "tier_counts": tier_counts,
            "region_counts": region_counts,
            "healthy_stations": healthy_count,
            "healthy_sites": healthy_count,  # alias
            "degraded_stations": degraded_count,
            "degraded_sites": degraded_count,  # alias
            "critical_stations": critical_count,
            "critical_sites": critical_count,  # alias
            "overall_fleet_health": round(overall_score, 2),
        }

    def load_kenya_airways_reference_fixtures(self) -> None:
        """Seed canonical outstations across the Kenya Airways network.
        
        Explicitly distinguishes between operational deployed sites and reference fixtures.
        """
        # 1. Primary Hub: JKIA (Operational Deployed Site)
        jkia = StationRecord(
            station_id="JKIA-HUB",
            iata_code="NBO",
            icao_code="HKJK",
            station_name="Jomo Kenyatta International Airport (Pride Centre Hub)",
            site_tier=SiteTier.HUB,
            region="East Africa",
            country="Kenya",
            city="Nairobi",
            timezone="Africa/Nairobi",
            latitude=-1.3192,
            longitude=36.9275,
            operational_hours="24/7",
            operational_owner="Kenya Airways Network Operations",
            management_lead="Central NOC Lead",
            is_deployed_nawari_site=True,
            is_reference_fixture=False,
            wan_circuits=[
                WANCircuit("CIR-NBO-01", WANCircuitType.CROSS_CONNECT, "Safaricom Metro Fiber", 1000.0, True, 1.5, station_id="JKIA-HUB"),
                WANCircuit("CIR-NBO-02", WANCircuitType.CROSS_CONNECT, "Airtel Metro Fiber", 1000.0, False, 1.8, station_id="JKIA-HUB"),
                WANCircuit("CIR-NBO-03", WANCircuitType.MPLS, "Liquid Intelligent Tech", 500.0, False, 2.0, station_id="JKIA-HUB"),
            ],
            pstn_breakout=PSTNBreakoutType.HYBRID,
        )
        dc1 = FacilitySite("JKIA-DC1", "Pride Centre Data Center 1", "DATA_CENTER", "10.10.10.0/24", "JKIA-HUB", "10.10.10.250")
        dc1.add_node(InfrastructureNode("SW-DC1-01", "Core Switch DC1-01", InfrastructureDomain.NETWORK, "10.10.10.1", "JKIA-DC1", "SWITCH"))
        dc1.add_node(InfrastructureNode("SW-DC1-02", "Core Switch DC1-02", InfrastructureDomain.NETWORK, "10.10.10.2", "JKIA-DC1", "SWITCH"))
        dc1.add_node(InfrastructureNode("RTR-CORE-01", "Core Gateway DC1", InfrastructureDomain.NETWORK, "10.10.10.254", "JKIA-DC1", "ROUTER"))
        dc1.add_node(InfrastructureNode("AVAYA-SM-01", "Avaya Session Manager Core", InfrastructureDomain.VOICE, "10.10.10.50", "JKIA-DC1", "SERVER"))
        dc1.add_node(InfrastructureNode("AVAYA-SBCE-01", "Avaya SBCE Core SBC", InfrastructureDomain.VOICE, "10.10.10.51", "JKIA-DC1", "SBCE"))
        jkia.add_facility(dc1)

        dc2 = FacilitySite("JKIA-DC2", "Old Airport Data Center 2 (DR)", "DATA_CENTER", "10.10.20.0/24", "JKIA-HUB", "10.10.20.250")
        dc2.add_node(InfrastructureNode("SW-DC2-01", "Core Switch DC2-01", InfrastructureDomain.NETWORK, "10.10.20.1", "JKIA-DC2", "SWITCH"))
        dc2.add_node(InfrastructureNode("RTR-CORE-02", "Core Gateway DC2", InfrastructureDomain.NETWORK, "10.10.20.254", "JKIA-DC2", "ROUTER"))
        jkia.add_facility(dc2)

        t1a = FacilitySite("JKIA-T1A", "Passenger Terminal 1A (SkyTeam Hub)", "TERMINAL", "10.10.30.0/22", "JKIA-HUB", "10.10.30.250")
        t1a.add_node(InfrastructureNode("SW-T1A-01", "Access Switch T1A-01", InfrastructureDomain.NETWORK, "10.10.30.1", "JKIA-T1A", "SWITCH"))
        t1a.add_node(InfrastructureNode("SW-T1A-02", "Access Switch T1A-02", InfrastructureDomain.NETWORK, "10.10.30.2", "JKIA-T1A", "SWITCH"))
        t1a.add_node(InfrastructureNode("AP-T1A-01", "Terminal Wi-Fi Gateway", InfrastructureDomain.NETWORK, "10.10.30.10", "JKIA-T1A", "ACCESS_POINT"))
        jkia.add_facility(t1a)

        cargo = FacilitySite("JKIA-CARGO", "Cargo Complex & Cold Storage", "CARGO", "10.10.40.0/24", "JKIA-HUB", "10.10.40.250")
        cargo.add_node(InfrastructureNode("SW-CRG-01", "Cargo Terminal Switch", InfrastructureDomain.NETWORK, "10.10.40.1", "JKIA-CARGO", "SWITCH"))
        jkia.add_facility(cargo)

        self.register_station(jkia, strict=True)

        # 2. Domestic Primary: Mombasa (Operational Deployed Site)
        mba = StationRecord(
            station_id="MBA-STATION",
            iata_code="MBA",
            icao_code="HKMO",
            station_name="Moi International Airport Mombasa",
            site_tier=SiteTier.DOMESTIC_PRIMARY,
            region="East Africa",
            country="Kenya",
            city="Mombasa",
            timezone="Africa/Nairobi",
            latitude=-4.0348,
            longitude=39.5942,
            operational_hours="24/7",
            operational_owner="KQ Coast Station Management",
            management_lead="Mombasa Duty Engineer",
            is_deployed_nawari_site=True,
            is_reference_fixture=False,
            wan_circuits=[
                WANCircuit("CIR-MBA-01", WANCircuitType.MPLS, "Safaricom MPLS", 100.0, True, 15.0, station_id="MBA-STATION"),
                WANCircuit("CIR-MBA-02", WANCircuitType.SD_WAN, "Airtel SD-WAN", 50.0, False, 18.0, station_id="MBA-STATION"),
            ],
            pstn_breakout=PSTNBreakoutType.HYBRID,
        )
        mba_t1 = FacilitySite("MBA-T1", "Mombasa Passenger Terminal 1", "TERMINAL", "10.20.10.0/24", "MBA-STATION", "10.20.1.10")
        mba_t1.add_node(InfrastructureNode("SW-MBA-01", "Mombasa Terminal Switch", InfrastructureDomain.NETWORK, "10.20.10.1", "MBA-T1", "SWITCH"))
        mba_t1.add_node(InfrastructureNode("RTR-MBA-01", "Mombasa Edge Router", InfrastructureDomain.NETWORK, "10.20.10.254", "MBA-T1", "ROUTER"))
        mba.add_facility(mba_t1)
        self.register_station(mba, strict=True)

        # 3. Reference Fixtures (Domestic Secondary, Regional, International)
        reference_sites = [
            ("KIS-STATION", "KIS", "HKKI", "Kisumu International Airport", SiteTier.DOMESTIC_SECONDARY, "East Africa", "Kenya", "Kisumu", "Africa/Nairobi", -0.0861, 34.7289, "06:00-22:00 UTC",
             [WANCircuit("CIR-KIS-01", WANCircuitType.MPLS, "Safaricom MPLS", 50.0, True, 12.0),
              WANCircuit("CIR-KIS-02", WANCircuitType.LTE_4G, "Airtel LTE Backup", 20.0, False, 35.0)],
             PSTNBreakoutType.CENTRAL_SIP_BACKHAUL),
            
            ("EDL-STATION", "EDL", "HKEL", "Eldoret International Airport", SiteTier.DOMESTIC_SECONDARY, "East Africa", "Kenya", "Eldoret", "Africa/Nairobi", 0.4045, 35.2389, "06:00-20:00 UTC",
             [WANCircuit("CIR-EDL-01", WANCircuitType.SD_WAN, "Safaricom SD-WAN", 30.0, True, 14.0),
              WANCircuit("CIR-EDL-02", WANCircuitType.INTERNET_VPN, "Airtel Internet VPN", 20.0, False, 28.0)],
             PSTNBreakoutType.CENTRAL_SIP_BACKHAUL),

            ("MYD-STATION", "MYD", "HKML", "Malindi Airport", SiteTier.DOMESTIC_SECONDARY, "East Africa", "Kenya", "Malindi", "Africa/Nairobi", -3.2297, 40.1006, "06:00-18:00 UTC",
             [WANCircuit("CIR-MYD-01", WANCircuitType.INTERNET_VPN, "Safaricom Business Internet", 20.0, True, 22.0)],
             PSTNBreakoutType.CENTRAL_SIP_BACKHAUL),

            ("EBB-STATION", "EBB", "HUEN", "Entebbe International Airport", SiteTier.REGIONAL, "East Africa", "Uganda", "Entebbe", "Africa/Kampala", 0.0424, 32.4435, "24/7",
             [WANCircuit("CIR-EBB-01", WANCircuitType.MPLS, "SITA Aviation MPLS", 50.0, True, 25.0),
              WANCircuit("CIR-EBB-02", WANCircuitType.SD_WAN, "Liquid Intelligent Tech", 30.0, False, 30.0)],
             PSTNBreakoutType.HYBRID),

            ("DAR-STATION", "DAR", "HTDA", "Julius Nyerere International Airport", SiteTier.REGIONAL, "East Africa", "Tanzania", "Dar es Salaam", "Africa/Dar_es_Salaam", -6.8781, 39.2026, "24/7",
             [WANCircuit("CIR-DAR-01", WANCircuitType.MPLS, "SITA Aviation MPLS", 50.0, True, 28.0),
              WANCircuit("CIR-DAR-02", WANCircuitType.INTERNET_VPN, "Vodacom Tanzania VPN", 30.0, False, 35.0)],
             PSTNBreakoutType.HYBRID),

            ("KGL-STATION", "KGL", "HRYR", "Kigali International Airport", SiteTier.REGIONAL, "East Africa", "Rwanda", "Kigali", "Africa/Kigali", -1.9686, 30.1395, "24/7",
             [WANCircuit("CIR-KGL-01", WANCircuitType.MPLS, "SITA Aviation MPLS", 40.0, True, 30.0),
              WANCircuit("CIR-KGL-02", WANCircuitType.SD_WAN, "MTN Rwanda SD-WAN", 20.0, False, 32.0)],
             PSTNBreakoutType.CENTRAL_SIP_BACKHAUL),

            ("LHR-STATION", "LHR", "EGLL", "London Heathrow Airport (Terminal 4)", SiteTier.INTERNATIONAL, "Europe", "United Kingdom", "London", "Europe/London", 51.4700, -0.4543, "05:00-23:00 UTC",
             [WANCircuit("CIR-LHR-01", WANCircuitType.MPLS, "SITA International MPLS", 100.0, True, 135.0),
              WANCircuit("CIR-LHR-02", WANCircuitType.SD_WAN, "BT Global SD-WAN", 100.0, False, 140.0)],
             PSTNBreakoutType.LOCAL_PSTN_GATEWAY),

            ("DXB-STATION", "DXB", "OMDB", "Dubai International Airport (Terminal 1)", SiteTier.INTERNATIONAL, "Middle East", "United Arab Emirates", "Dubai", "Asia/Dubai", 25.2532, 55.3657, "24/7",
             [WANCircuit("CIR-DXB-01", WANCircuitType.MPLS, "SITA International MPLS", 80.0, True, 85.0),
              WANCircuit("CIR-DXB-02", WANCircuitType.SD_WAN, "Etisalat SD-WAN", 50.0, False, 90.0)],
             PSTNBreakoutType.LOCAL_PSTN_GATEWAY),

            ("AMS-STATION", "AMS", "EHAM", "Amsterdam Airport Schiphol", SiteTier.INTERNATIONAL, "Europe", "Netherlands", "Amsterdam", "Europe/Amsterdam", 52.3105, 4.7683, "05:00-22:00 UTC",
             [WANCircuit("CIR-AMS-01", WANCircuitType.MPLS, "SITA International MPLS", 80.0, True, 142.0),
              WANCircuit("CIR-AMS-02", WANCircuitType.INTERNET_VPN, "KPN Business VPN", 50.0, False, 148.0)],
             PSTNBreakoutType.LOCAL_PSTN_GATEWAY),

            ("JNB-STATION", "JNB", "FAOR", "O.R. Tambo International Airport", SiteTier.INTERNATIONAL, "Southern Africa", "South Africa", "Johannesburg", "Africa/Johannesburg", -26.1367, 28.2411, "24/7",
             [WANCircuit("CIR-JNB-01", WANCircuitType.MPLS, "SITA International MPLS", 60.0, True, 65.0),
              WANCircuit("CIR-JNB-02", WANCircuitType.SD_WAN, "Vodacom Business SD-WAN", 40.0, False, 70.0)],
             PSTNBreakoutType.HYBRID),
        ]

        for sid, iata, icao, name, tier, reg, ctry, city, tz, lat, lon, hrs, cirs, pstn in reference_sites:
            st = StationRecord(
                station_id=sid,
                iata_code=iata,
                icao_code=icao,
                station_name=name,
                site_tier=tier,
                region=reg,
                country=ctry,
                city=city,
                timezone=tz,
                latitude=lat,
                longitude=lon,
                operational_hours=hrs,
                is_deployed_nawari_site=False,
                is_reference_fixture=True,
                wan_circuits=cirs,
                pstn_breakout=pstn,
            )
            fac = FacilitySite(f"{sid}-MAIN", f"{name} Main Facility", "TERMINAL", "10.99.0.0/24", sid)
            fac.add_node(InfrastructureNode(f"SW-{iata}-01", f"{iata} Edge Switch", InfrastructureDomain.NETWORK, "10.99.0.1", fac.site_id, "SWITCH"))
            st.add_facility(fac)
            self.register_station(st, strict=True)
