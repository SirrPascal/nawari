"""Aviation Business Service Catalogue and SLI/SLO Assurance Engine.

Implements the Kenya Airways Business Service Catalogue with:
1. Reusable Service Dependency Directed Acyclic Graphs (DAGs) with cycle detection.
2. Global vs Station-Local service health isolation.
3. Telemetry state evaluation: ACTIVE, DEGRADED, DOWN, STALE, MISSING, UNSUPPORTED, REPLAYED.
   (Replayed historical telemetry is strictly prohibited from being counted as fresh live health).
4. Evidence and provenance for every service-health result.
5. Decoupled SLI measurement and Error Budget evaluation engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ServiceTier(str, Enum):
    """Operational criticality tier for an aviation business service."""
    TIER_1_MISSION_CRITICAL = "TIER_1_MISSION_CRITICAL"  # DCS, Flight Ops, Ramp Telephony
    TIER_2_BUSINESS_CRITICAL = "TIER_2_BUSINESS_CRITICAL" # BHS, CargoSpot, Retail Ticketing
    TIER_3_CORPORATE = "TIER_3_CORPORATE"                # ERP, M365 Email, Corporate Wi-Fi


class ServiceScope(str, Enum):
    """Scope of delivery: Enterprise-wide core vs local outstation delivery."""
    GLOBAL = "GLOBAL"               # Enterprise-wide service
    STATION_LOCAL = "STATION_LOCAL" # Delivery at a specific airport/station


class TelemetryQuality(str, Enum):
    """Quality and freshness classification of incoming component telemetry."""
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    REPLAYED = "REPLAYED"  # Historical replayed data; cannot count as fresh live health


@dataclass
class ServiceComponentDependency:
    """Underlying infrastructure dependency of a business service."""
    component_id: str
    component_type: str  # SWITCH, ROUTER, CIRCUIT, SERVER, SIP_TRUNK, GATEWAY
    weight: float = 1.0
    is_redundant: bool = False
    station_id: Optional[str] = None  # None if global core component


@dataclass
class ServiceHealthResult:
    """Detailed result of a service health evaluation with complete evidence provenance."""
    service_id: str
    service_name: str
    tier: ServiceTier
    scope: ServiceScope
    station_id: Optional[str]
    health_index: float  # 0.0 to 1.0
    status: str          # HEALTHY, DEGRADED, CRITICAL_DOWN, UNKNOWN
    component_evidence: Dict[str, Dict[str, Any]]
    evaluation_notes: List[str]
    provenance_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "station_id": self.station_id,
            "health_index": round(self.health_index, 2),
            "status": self.status,
            "component_evidence": self.component_evidence,
            "evaluation_notes": self.evaluation_notes,
            "provenance_timestamp": self.provenance_timestamp,
        }


@dataclass
class BusinessService:
    """Canonical representation of an aviation service within the airline catalog."""
    service_id: str
    name: str
    tier: ServiceTier
    scope: ServiceScope
    description: str
    station_id: Optional[str] = None  # Specific station if scope is STATION_LOCAL
    dependencies: List[ServiceComponentDependency] = field(default_factory=list)
    parent_services: List[str] = field(default_factory=list)  # Upstream service dependencies
    proposed_design_slo: float = 99.95  # Proposed design value, not confirmed contractual SLA
    uuid_str: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_str,
            "service_id": self.service_id,
            "name": self.name,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "station_id": self.station_id,
            "description": self.description,
            "proposed_design_slo": self.proposed_design_slo,
            "dependency_count": len(self.dependencies),
            "parent_services": self.parent_services,
        }


class ServiceCatalog:
    """Maintains definitions of business services, dependency DAGs, and health evaluations."""

    def __init__(self, auto_seed: bool = True) -> None:
        self._services: Dict[str, BusinessService] = {}
        if auto_seed:
            self._seed_kenya_airways_services()

    def register_service(self, service: BusinessService) -> None:
        self._services[service.service_id] = service

    def get_service(self, service_id: str) -> Optional[BusinessService]:
        return self._services.get(service_id)

    def get_services_by_tier(self, tier: ServiceTier) -> List[BusinessService]:
        return [s for s in self._services.values() if s.tier == tier]

    def get_services_by_station(self, station_id: str) -> List[BusinessService]:
        return [s for s in self._services.values() if s.station_id == station_id or s.scope == ServiceScope.GLOBAL]

    def get_all_services(self) -> List[BusinessService]:
        return list(self._services.values())

    def detect_dependency_cycles(self) -> List[List[str]]:
        """Detect circular dependencies within the service graph using DFS."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []

        def dfs(current: str, path: List[str]):
            visited.add(current)
            rec_stack.add(current)
            service = self.get_service(current)
            if service:
                for parent in service.parent_services:
                    if parent not in visited:
                        dfs(parent, path + [parent])
                    elif parent in rec_stack:
                        cycle_path = path[path.index(parent):] + [parent]
                        cycles.append(cycle_path)
            rec_stack.remove(current)

        for s_id in self._services.keys():
            if s_id not in visited:
                dfs(s_id, [s_id])

        return cycles

    def evaluate_service_health(
        self,
        service_id: str,
        component_states: Dict[str, Dict[str, Any]],
        upstream_service_health: Optional[Dict[str, float]] = None,
    ) -> ServiceHealthResult:
        """Evaluate operational health of a business service with detailed evidence.
        
        component_states is a dict:
        {
            "component_id": {
                "state": "ACTIVE" | "DEGRADED" | "DOWN" | "MAINTENANCE",
                "quality": "FRESH" | "STALE" | "MISSING" | "UNSUPPORTED" | "REPLAYED",
                "timestamp": iso_str,
                "latency_ms": 10.5
            }
        }
        """
        service = self.get_service(service_id)
        if not service:
            return ServiceHealthResult(
                service_id=service_id,
                service_name="Unknown",
                tier=ServiceTier.TIER_3_CORPORATE,
                scope=ServiceScope.GLOBAL,
                station_id=None,
                health_index=0.0,
                status="UNKNOWN",
                component_evidence={},
                evaluation_notes=[f"Service '{service_id}' not found in catalog."],
            )

        notes: List[str] = []
        evidence: Dict[str, Dict[str, Any]] = {}
        total_weight = 0.0
        weighted_sum = 0.0

        for dep in service.dependencies:
            comp_info = component_states.get(dep.component_id, {
                "state": "MISSING",
                "quality": TelemetryQuality.MISSING.value,
            })
            state = str(comp_info.get("state", "MISSING")).upper()
            quality = str(comp_info.get("quality", TelemetryQuality.FRESH.value)).upper()

            # Telemetry Quality Safeguards:
            # Replayed telemetry cannot count as fresh live health
            if quality == TelemetryQuality.REPLAYED.value:
                state_val = 0.5  # Replayed telemetry is informational; cannot confirm current live state
                notes.append(f"Component '{dep.component_id}' has REPLAYED telemetry; not counted as fresh live health.")
            elif quality == TelemetryQuality.STALE.value:
                state_val = 0.4
                notes.append(f"Component '{dep.component_id}' telemetry is STALE.")
            elif quality == TelemetryQuality.MISSING.value:
                state_val = 0.0
                notes.append(f"Component '{dep.component_id}' telemetry is MISSING.")
            elif quality == TelemetryQuality.UNSUPPORTED.value:
                state_val = 0.2
                notes.append(f"Component '{dep.component_id}' metric is UNSUPPORTED.")
            else:
                # Fresh telemetry evaluation
                if state in ("ACTIVE", "HEALTHY", "UP"):
                    state_val = 1.0
                elif state in ("DEGRADED", "FAILOVER", "FAILOVER_ACTIVE"):
                    state_val = 0.5
                elif state in ("MAINTENANCE",):
                    state_val = 1.0  # Excluded from penalty (tracked under maintenance)
                else:
                    state_val = 0.0

            evidence[dep.component_id] = {
                "observed_state": state,
                "telemetry_quality": quality,
                "weight": dep.weight,
                "effective_value": state_val,
                "is_redundant": dep.is_redundant,
                "station_id": dep.station_id,
            }

            weighted_sum += dep.weight * state_val
            total_weight += dep.weight

        base_health = (weighted_sum / total_weight) if total_weight > 0 else 1.0

        # Upstream service dependency propagation:
        if service.parent_services and upstream_service_health:
            for parent_id in service.parent_services:
                parent_h = upstream_service_health.get(parent_id, 1.0)
                if parent_h < 0.85:
                    notes.append(f"Upstream service '{parent_id}' degraded (health={parent_h}); propagating to child service.")
                    base_health = min(base_health, parent_h)

        health_index = max(0.0, min(1.0, base_health))

        if health_index >= 0.85:
            status = "HEALTHY"
        elif health_index >= 0.40:
            status = "DEGRADED"
        else:
            status = "CRITICAL_DOWN"

        return ServiceHealthResult(
            service_id=service.service_id,
            service_name=service.name,
            tier=service.tier,
            scope=service.scope,
            station_id=service.station_id,
            health_index=round(health_index, 2),
            status=status,
            component_evidence=evidence,
            evaluation_notes=notes,
        )

    def evaluate_all_services(self, component_states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate all services with dependency topological propagation."""
        results: Dict[str, ServiceHealthResult] = {}
        health_map: Dict[str, float] = {}

        # 1. First pass: Evaluate services without parent dependencies
        for sid, s in self._services.items():
            if not s.parent_services:
                res = self.evaluate_service_health(sid, component_states)
                results[sid] = res
                health_map[sid] = res.health_index

        # 2. Second pass: Evaluate dependent child services
        for sid, s in self._services.items():
            if s.parent_services:
                res = self.evaluate_service_health(sid, component_states, upstream_service_health=health_map)
                results[sid] = res
                health_map[sid] = res.health_index

        healthy_count = sum(1 for r in results.values() if r.status == "HEALTHY")
        degraded_count = sum(1 for r in results.values() if r.status == "DEGRADED")
        critical_count = sum(1 for r in results.values() if r.status == "CRITICAL_DOWN")

        return {
            "total_services": len(results),
            "healthy_services": healthy_count,
            "degraded_services": degraded_count,
            "critical_services": critical_count,
            "services": [r.to_dict() for r in results.values()],
        }

    def _seed_kenya_airways_services(self) -> None:
        """Seed canonical aviation services across Tier 1, 2, and 3."""
        # Tier 1 Global Services
        self.register_service(BusinessService(
            service_id="SVC-DCS-GLOBAL",
            name="Departure Control System Core (Amadeus Altea)",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Core Amadeus DCS host connectivity, check-in, and boarding gateway",
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", 0.5, False, "JKIA-HUB"),
                ServiceComponentDependency("CIR-NBO-02", "CIRCUIT", 0.3, True, "JKIA-HUB"),
                ServiceComponentDependency("SW-DC1-01", "SWITCH", 0.2, False, "JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-FLIGHT-OPS",
            name="Flight Operations & EFB Dispatch",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Jeppesen FliteDeck, OFP flight plan delivery, and weather/NOTAM feeds",
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", 0.6, False, "JKIA-HUB"),
                ServiceComponentDependency("SW-DC1-02", "SWITCH", 0.4, False, "JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-RAMP-VOICE",
            name="Air-to-Ground & Ramp Operations Telephony",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Avaya Session Manager, SBCE SIP signaling, and Flight Dispatcher ACD extensions",
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("AVAYA-SM-01", "SERVER", 0.4, False, "JKIA-HUB"),
                ServiceComponentDependency("AVAYA-SBCE-01", "SBCE", 0.3, False, "JKIA-HUB"),
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", 0.3, True, "JKIA-HUB"),
            ],
        ))

        # Tier 1 Station-Local Services (e.g. Mombasa, Heathrow)
        self.register_service(BusinessService(
            service_id="SVC-DCS-MBA",
            name="Mombasa Check-In & Gate Boarding (DCS Local)",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.STATION_LOCAL,
            station_id="MBA-STATION",
            description="Passenger check-in desks and boarding gate scanners at Moi International Airport",
            parent_services=["SVC-DCS-GLOBAL"],  # Dependent on global core DCS
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-MBA-01", "CIRCUIT", 0.6, False, "MBA-STATION"),
                ServiceComponentDependency("CIR-MBA-02", "CIRCUIT", 0.3, True, "MBA-STATION"),
                ServiceComponentDependency("SW-MBA-01", "SWITCH", 0.1, False, "MBA-STATION"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-DCS-LHR",
            name="London Heathrow T4 Check-In & Boarding",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.STATION_LOCAL,
            station_id="LHR-STATION",
            description="Passenger check-in desks and SkyTeam bag-drop at Heathrow Terminal 4",
            parent_services=["SVC-DCS-GLOBAL"],
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-LHR-01", "CIRCUIT", 0.6, False, "LHR-STATION"),
                ServiceComponentDependency("CIR-LHR-02", "CIRCUIT", 0.4, True, "LHR-STATION"),
            ],
        ))

        # Tier 2 Business-Critical Services
        self.register_service(BusinessService(
            service_id="SVC-BHS-GLOBAL",
            name="Baggage Handling & Sortation (SITA BagManager)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="SITA BagManager, WorldTracer lost luggage interface, and terminal sortation",
            proposed_design_slo=99.50,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", 0.5, False, "JKIA-HUB"),
                ServiceComponentDependency("SW-DC2-01", "SWITCH", 0.5, False, "JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-CARGO-LOGISTICS",
            name="Cargo Logistics Management (CargoSpot)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="CargoSpot airway bill tracking, customs EDI links, and cargo warehouse scales",
            proposed_design_slo=99.50,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-03", "CIRCUIT", 0.5, False, "JKIA-HUB"),
                ServiceComponentDependency("SW-CRG-01", "SWITCH", 0.5, False, "JKIA-HUB"),
            ],
        ))

        # Tier 3 Corporate Services
        self.register_service(BusinessService(
            service_id="SVC-CORP-ERP",
            name="Corporate ERP & Crew Payroll",
            tier=ServiceTier.TIER_3_CORPORATE,
            scope=ServiceScope.GLOBAL,
            description="SAP/Oracle ERP back-office systems and crew scheduling administration",
            proposed_design_slo=99.00,
            dependencies=[
                ServiceComponentDependency("SW-DC1-01", "SWITCH", 1.0, False, "JKIA-HUB"),
            ],
        ))


@dataclass
class SLOSpecification:
    """Design parameters for SLO, contractual SLA, and measurement windows."""
    service_id: str
    target_slo_percent: float = 99.95      # Proposed internal target
    contractual_sla_percent: float = 99.90 # Contractual SLA commitment
    measurement_window_days: int = 30      # Measurement evaluation window
    scheduled_maintenance_minutes: float = 0.0


@dataclass
class SLIResult:
    """Calculated Service Level Indicator and Error Budget status."""
    service_id: str
    sli_percent: float
    total_valid_minutes: float
    good_minutes: float
    degraded_minutes: float
    outage_minutes: float
    scheduled_maintenance_minutes: float
    target_slo_percent: float
    contractual_sla_percent: float
    total_error_budget_minutes: float
    consumed_error_budget_minutes: float
    remaining_error_budget_minutes: float
    burn_rate: float
    is_slo_breached: bool
    is_sla_breached: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "sli_percent": round(self.sli_percent, 4),
            "total_valid_minutes": round(self.total_valid_minutes, 1),
            "good_minutes": round(self.good_minutes, 1),
            "degraded_minutes": round(self.degraded_minutes, 1),
            "outage_minutes": round(self.outage_minutes, 1),
            "maintenance_minutes": round(self.scheduled_maintenance_minutes, 1),
            "target_slo_percent": self.target_slo_percent,
            "contractual_sla_percent": self.contractual_sla_percent,
            "total_error_budget_minutes": round(self.total_error_budget_minutes, 2),
            "consumed_error_budget_minutes": round(self.consumed_error_budget_minutes, 2),
            "remaining_error_budget_minutes": round(self.remaining_error_budget_minutes, 2),
            "burn_rate": round(self.burn_rate, 2),
            "is_slo_breached": self.is_slo_breached,
            "is_sla_breached": self.is_sla_breached,
        }


class SLIEvaluationEngine:
    """Decoupled SLI measurement and Error Budget evaluation engine.
    
    Calculates availability ratios, maintenance exclusions, and error budget burn rates.
    """

    def __init__(self) -> None:
        self._slos: Dict[str, SLOSpecification] = {}
        self._observations: Dict[str, List[Dict[str, Any]]] = {}

    def register_slo(self, spec: SLOSpecification) -> None:
        self._slos[spec.service_id] = spec
        if spec.service_id not in self._observations:
            self._observations[spec.service_id] = []

    def record_interval(
        self,
        service_id: str,
        duration_minutes: float,
        health_index: float,
        in_maintenance: bool = False,
    ) -> None:
        """Record an observed operational interval for a service."""
        if service_id not in self._observations:
            self._observations[service_id] = []
        self._observations[service_id].append({
            "duration": duration_minutes,
            "health": health_index,
            "in_maintenance": in_maintenance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def evaluate_sli(self, service_id: str) -> SLIResult:
        """Calculate SLI and Error Budget for a specific service."""
        spec = self._slos.get(service_id, SLOSpecification(service_id=service_id))
        records = self._observations.get(service_id, [])

        good_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and r["health"] >= 0.85)
        degraded_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and 0.40 <= r["health"] < 0.85)
        outage_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and r["health"] < 0.40)
        maintenance_minutes = sum(r["duration"] for r in records if r["in_maintenance"]) + spec.scheduled_maintenance_minutes

        valid_minutes = good_minutes + degraded_minutes + outage_minutes

        # SLI formula: Effective healthy minutes / Valid measured operational minutes
        if valid_minutes <= 0.0:
            sli = 100.0
        else:
            effective_healthy = good_minutes + (degraded_minutes * 0.5)
            sli = min(100.0, (effective_healthy / valid_minutes) * 100.0)

        # Configurable measurement window in minutes
        window_minutes = spec.measurement_window_days * 24 * 60.0
        allowed_unreliability = (100.0 - spec.target_slo_percent) / 100.0
        total_error_budget = window_minutes * allowed_unreliability

        # Unreliability consumed: outage minutes + 50% degraded minutes
        consumed_budget = outage_minutes + (degraded_minutes * 0.5)
        remaining_budget = max(0.0, total_error_budget - consumed_budget)
        burn_rate = (consumed_budget / total_error_budget) if total_error_budget > 0 else 0.0

        is_slo_breached = sli < spec.target_slo_percent
        is_sla_breached = sli < spec.contractual_sla_percent

        return SLIResult(
            service_id=service_id,
            sli_percent=sli,
            total_valid_minutes=valid_minutes,
            good_minutes=good_minutes,
            degraded_minutes=degraded_minutes,
            outage_minutes=outage_minutes,
            scheduled_maintenance_minutes=maintenance_minutes,
            target_slo_percent=spec.target_slo_percent,
            contractual_sla_percent=spec.contractual_sla_percent,
            total_error_budget_minutes=total_error_budget,
            consumed_error_budget_minutes=consumed_budget,
            remaining_error_budget_minutes=remaining_budget,
            burn_rate=burn_rate,
            is_slo_breached=is_slo_breached,
            is_sla_breached=is_sla_breached,
        )

    def evaluate_fleet_slos(self) -> List[SLIResult]:
        return [self.evaluate_sli(sid) for sid in self._slos.keys()]
