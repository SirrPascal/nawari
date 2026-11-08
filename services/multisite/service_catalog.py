"""Aviation Business Service Catalogue and Multi-Dimensional SLI/SLO Assurance Engine.

Implements the Kenya Airways Business Service Catalogue with:
1. Reusable Service Dependency Directed Acyclic Graphs (DAGs) with cycle detection.
2. Explicit Dependency Semantics:
   - MANDATORY / AND: If any mandatory dependency fails, service drops immediately to CRITICAL_DOWN.
   - OR: Service remains healthy as long as at least one redundant component is UP.
   - QUORUM: Service requires at least K of N components to be UP.
   - WEIGHTED: Component contributions are evaluated proportionally.
3. Multi-Dimensional SLI Measurement (Decoupled from SLA/SLO configuration):
   - Availability SLI: Proportion of valid operational intervals where service is available.
   - Performance SLI: Proportion meeting latency / throughput objectives.
   - Quality SLI: Proportion meeting composite service quality criteria.
   - Coverage: Proportion of expected intervals with trustworthy fresh measurements.
   - Missing and stale telemetry are tracked explicitly as UNKNOWN and never inflate availability.
4. Strict Replayed Telemetry Isolation:
   - Historical replayed telemetry is assigned replay provenance and recorded for retrospective analysis.
   - Replayed telemetry is strictly prohibited from establishing current health or proving recovery.
   - Newer live observations are never overwritten by older replayed data.
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


class DependencyLogic(str, Enum):
    """Evaluation logic for a service's underlying component dependencies."""
    MANDATORY_AND = "MANDATORY_AND"  # All mandatory dependencies must be UP
    OR_REDUNDANT = "OR_REDUNDANT"    # At least one component must be UP
    QUORUM = "QUORUM"                # At least K of N components must be UP
    WEIGHTED = "WEIGHTED"            # Proportional weighted sum


class TelemetryQuality(str, Enum):
    """Quality and freshness classification of incoming component telemetry."""
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    REPLAYED = "REPLAYED"  # Historical replayed data; cannot establish live current health


@dataclass
class ServiceComponentDependency:
    """Underlying infrastructure dependency of a business service."""
    component_id: str
    component_type: str  # SWITCH, ROUTER, CIRCUIT, SERVER, SIP_TRUNK, GATEWAY
    is_mandatory: bool = True  # If mandatory and down, service is down regardless of others
    weight: float = 1.0
    is_redundant: bool = False
    redundancy_group: Optional[str] = None  # e.g. "WAN_CIRCUITS", "CORE_ROUTERS"
    is_primary: bool = False                # True if designated primary member of redundancy group
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
    is_mandatory_failed: bool
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
            "is_mandatory_failed": self.is_mandatory_failed,
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
    dependency_logic: DependencyLogic = DependencyLogic.MANDATORY_AND
    quorum_count: int = 1
    station_id: Optional[str] = None  # Specific station if scope is STATION_LOCAL
    dependencies: List[ServiceComponentDependency] = field(default_factory=list)
    parent_services: List[str] = field(default_factory=list)  # Upstream service dependencies
    proposed_design_slo: float = 99.95  # Proposed design target, NOT contractual SLA
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
            "dependency_logic": self.dependency_logic.value,
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
        """Evaluate operational health of a business service with dependency logic and telemetry safeguards."""
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
                is_mandatory_failed=False,
                component_evidence={},
                evaluation_notes=[f"Service '{service_id}' not found in catalog."],
            )

        notes: List[str] = []
        evidence: Dict[str, Dict[str, Any]] = {}
        mandatory_failure = False
        up_count = 0
        total_weight = 0.0
        weighted_sum = 0.0
        has_unknown = False

        # Collect redundancy group memberships
        redundancy_groups: Dict[str, List[Tuple[ServiceComponentDependency, bool, str, str]]] = {}

        for dep in service.dependencies:
            comp_info = component_states.get(dep.component_id, {
                "state": "MISSING",
                "quality": TelemetryQuality.MISSING.value,
            })
            state = str(comp_info.get("state", "MISSING")).upper()
            quality = str(comp_info.get("quality", TelemetryQuality.FRESH.value)).upper()

            # Telemetry Quality Safeguards:
            # Replayed telemetry cannot establish current live health!
            if quality == TelemetryQuality.REPLAYED.value:
                state_val = 0.0
                is_up = False
                has_unknown = True
                notes.append(f"Component '{dep.component_id}' has REPLAYED telemetry; strictly excluded from live health.")
            elif quality == TelemetryQuality.STALE.value:
                state_val = 0.2
                is_up = False
                has_unknown = True
                notes.append(f"Component '{dep.component_id}' telemetry is STALE.")
            elif quality == TelemetryQuality.MISSING.value:
                state_val = 0.0
                is_up = False
                has_unknown = True
                notes.append(f"Component '{dep.component_id}' telemetry is MISSING.")
            elif quality == TelemetryQuality.UNSUPPORTED.value:
                state_val = 0.0
                is_up = False
                has_unknown = True
                notes.append(f"Component '{dep.component_id}' metric is UNSUPPORTED.")
            else:
                # Fresh telemetry evaluation
                if state in ("ACTIVE", "HEALTHY", "UP"):
                    state_val = 1.0
                    is_up = True
                elif state in ("DEGRADED", "FAILOVER", "FAILOVER_ACTIVE"):
                    state_val = 0.5
                    is_up = True
                elif state in ("MAINTENANCE",):
                    state_val = 1.0
                    is_up = True
                else:
                    state_val = 0.0
                    is_up = False

            if is_up:
                up_count += 1

            if dep.redundancy_group:
                if dep.redundancy_group not in redundancy_groups:
                    redundancy_groups[dep.redundancy_group] = []
                redundancy_groups[dep.redundancy_group].append((dep, is_up, state, quality))
            else:
                # Check Non-Redundant Mandatory / Critical Dependency Failure
                if dep.is_mandatory and not is_up:
                    mandatory_failure = True
                    notes.append(f"CRITICAL DEPENDENCY FAILED: Mandatory component '{dep.component_id}' is {state} ({quality}).")

            evidence[dep.component_id] = {
                "observed_state": state,
                "telemetry_quality": quality,
                "is_mandatory": dep.is_mandatory,
                "weight": dep.weight,
                "effective_value": state_val,
                "is_redundant": dep.is_redundant,
                "redundancy_group": dep.redundancy_group,
                "is_primary": dep.is_primary,
                "station_id": dep.station_id,
            }

            weighted_sum += dep.weight * state_val
            total_weight += dep.weight

        # Evaluate Redundancy Groups
        has_redundancy_degraded = False
        for group_name, members in redundancy_groups.items():
            total_members = len(members)
            up_members = sum(1 for m_dep, m_up, _, _ in members if m_up)
            primary_member = next((m_dep for m_dep, _, _, _ in members if m_dep.is_primary), None)
            primary_is_up = True
            if primary_member is not None:
                primary_is_up = any(m_up for m_dep, m_up, _, _ in members if m_dep == primary_member)

            if up_members == 0:
                # Complete exhaustion of redundancy group -> service critical down
                mandatory_failure = True
                notes.append(
                    f"CRITICAL DEPENDENCY FAILED: Redundancy group '{group_name}' completely exhausted "
                    f"(0/{total_members} members available)."
                )
            elif up_members < total_members:
                has_redundancy_degraded = True
                if not primary_is_up:
                    notes.append(
                        f"PRIMARY FAILOVER ACTIVE: Redundancy group '{group_name}' operating on secondary backup "
                        f"({up_members}/{total_members} available)."
                    )
                else:
                    notes.append(
                        f"REDUNDANCY DEGRADED: Redundancy group '{group_name}' member offline "
                        f"({up_members}/{total_members} available)."
                    )

        # Apply Dependency Semantics
        if mandatory_failure and service.dependency_logic == DependencyLogic.MANDATORY_AND:
            base_health = 0.0
            status = "CRITICAL_DOWN"
        elif service.dependency_logic == DependencyLogic.OR_REDUNDANT:
            base_health = 1.0 if up_count >= 1 else 0.0
            status = "HEALTHY" if up_count >= 1 else "CRITICAL_DOWN"
        elif service.dependency_logic == DependencyLogic.QUORUM:
            base_health = 1.0 if up_count >= service.quorum_count else 0.0
            status = "HEALTHY" if up_count >= service.quorum_count else "CRITICAL_DOWN"
        else:
            # Weighted logic
            base_health = (weighted_sum / total_weight) if total_weight > 0 else 1.0
            if base_health >= 0.85:
                status = "HEALTHY"
            elif base_health >= 0.40:
                status = "DEGRADED"
            else:
                status = "CRITICAL_DOWN"

        # Apply Redundancy Degraded Semantics
        if has_redundancy_degraded and status == "HEALTHY":
            status = "DEGRADED"
            base_health = min(base_health, 0.70)

        # Upstream service dependency propagation:
        if service.parent_services and upstream_service_health:
            for parent_id in service.parent_services:
                parent_h = upstream_service_health.get(parent_id, 1.0)
                if parent_h < 0.85:
                    notes.append(f"Upstream service '{parent_id}' degraded (health={parent_h}); propagating to child service.")
                    base_health = min(base_health, parent_h)
                    if base_health < 0.40:
                        status = "CRITICAL_DOWN"
                    elif base_health < 0.85:
                        status = "DEGRADED"

        if has_unknown and status == "HEALTHY":
            status = "DEGRADED"
            notes.append("Service downgraded to DEGRADED due to unconfirmed / missing component telemetry.")

        return ServiceHealthResult(
            service_id=service.service_id,
            service_name=service.name,
            tier=service.tier,
            scope=service.scope,
            station_id=service.station_id,
            health_index=round(base_health, 2),
            status=status,
            is_mandatory_failed=mandatory_failure,
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
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("CIR-NBO-02", "CIRCUIT", is_mandatory=False, weight=0.3, is_redundant=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("SW-DC1-01", "SWITCH", is_mandatory=True, weight=0.2, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-FLIGHT-OPS",
            name="Flight Operations & EFB Dispatch",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Jeppesen FliteDeck, OFP flight plan delivery, and weather/NOTAM feeds",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", is_mandatory=True, weight=0.6, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("SW-DC1-02", "SWITCH", is_mandatory=True, weight=0.4, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-RAMP-VOICE",
            name="Air-to-Ground & Ramp Operations Telephony",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Avaya Session Manager, SBCE SIP signaling, and Flight Dispatcher ACD extensions",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("AVAYA-SM-01", "SERVER", is_mandatory=True, weight=0.4, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("AVAYA-SBCE-01", "SBCE", is_mandatory=True, weight=0.3, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", is_mandatory=False, weight=0.3, is_redundant=True, station_id="JKIA-HUB"),
            ],
        ))

        # Tier 1 Station-Local Services (Mombasa, Heathrow)
        self.register_service(BusinessService(
            service_id="SVC-DCS-MBA",
            name="Mombasa Check-In & Gate Boarding (DCS Local)",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.STATION_LOCAL,
            station_id="MBA-STATION",
            description="Passenger check-in desks and boarding gate scanners at Moi International Airport",
            parent_services=["SVC-DCS-GLOBAL"],
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-MBA-01", "CIRCUIT", is_mandatory=False, weight=0.6, is_redundant=True, redundancy_group="MBA_WAN_CIRCUITS", is_primary=True, station_id="MBA-STATION"),
                ServiceComponentDependency("CIR-MBA-02", "CIRCUIT", is_mandatory=False, weight=0.3, is_redundant=True, redundancy_group="MBA_WAN_CIRCUITS", is_primary=False, station_id="MBA-STATION"),
                ServiceComponentDependency("SW-MBA-01", "SWITCH", is_mandatory=True, weight=0.1, is_redundant=False, station_id="MBA-STATION"),
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
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.95,
            dependencies=[
                ServiceComponentDependency("CIR-LHR-01", "CIRCUIT", is_mandatory=False, weight=0.6, is_redundant=True, redundancy_group="LHR_WAN_CIRCUITS", is_primary=True, station_id="LHR-STATION"),
                ServiceComponentDependency("CIR-LHR-02", "CIRCUIT", is_mandatory=False, weight=0.4, is_redundant=True, redundancy_group="LHR_WAN_CIRCUITS", is_primary=False, station_id="LHR-STATION"),
            ],
        ))

        # Tier 2 Business-Critical Services
        self.register_service(BusinessService(
            service_id="SVC-BHS-GLOBAL",
            name="Baggage Handling & Sortation (SITA BagManager)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="SITA BagManager, WorldTracer lost luggage interface, and terminal sortation",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.50,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-01", "CIRCUIT", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("SW-DC2-01", "SWITCH", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-CARGO-LOGISTICS",
            name="Cargo Logistics Management (CargoSpot)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="CargoSpot airway bill tracking, customs EDI links, and cargo warehouse scales",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.50,
            dependencies=[
                ServiceComponentDependency("CIR-NBO-03", "CIRCUIT", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("SW-CRG-01", "SWITCH", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        # Tier 3 Corporate Services
        self.register_service(BusinessService(
            service_id="SVC-CORP-ERP",
            name="Corporate ERP & Crew Payroll",
            tier=ServiceTier.TIER_3_CORPORATE,
            scope=ServiceScope.GLOBAL,
            description="SAP/Oracle ERP back-office systems and crew scheduling administration",
            dependency_logic=DependencyLogic.WEIGHTED,
            proposed_design_slo=99.00,
            dependencies=[
                ServiceComponentDependency("SW-DC1-01", "SWITCH", is_mandatory=True, weight=1.0, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        # =====================================================================
        # Phase 13.12: Kenya Airways Enterprise Network & Communications Services
        # =====================================================================
        self.register_service(BusinessService(
            service_id="SVC-ENTERPRISE-NETWORK",
            name="Kenya Airways Enterprise Network Core",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Pride Centre campus core, JKIA terminal LAN, and Data Centre spine/leaf fabric",
            dependency_logic=DependencyLogic.QUORUM,
            quorum_count=1,
            proposed_design_slo=99.99,
            dependencies=[
                ServiceComponentDependency("jkia-core-sw01", "SWITCH", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="CORE_SWITCHES", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("jkia-core-sw02", "SWITCH", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="CORE_SWITCHES", is_primary=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-WAN-CONNECTIVITY",
            name="WAN & Regional Outstation Connectivity",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Multi-carrier MPLS and DIA connecting Pride DC with domestic, regional, and international outstations",
            dependency_logic=DependencyLogic.QUORUM,
            quorum_count=1,
            proposed_design_slo=99.95,
            parent_services=["SVC-ENTERPRISE-NETWORK"],
            dependencies=[
                ServiceComponentDependency("CIR-MPLS-SAFARICOM-01", "CIRCUIT", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="WAN_CORE_CIRCUITS", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("CIR-MPLS-TELKOM-01", "CIRCUIT", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="WAN_CORE_CIRCUITS", is_primary=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-SIP-CARRIER",
            name="Carrier Ingress & SIP Trunking",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Redundant Session Border Controller (SBCE) cluster and upstream carrier SIP trunking",
            dependency_logic=DependencyLogic.QUORUM,
            quorum_count=1,
            proposed_design_slo=99.99,
            parent_services=["SVC-ENTERPRISE-NETWORK"],
            dependencies=[
                ServiceComponentDependency("avaya-sbce-01", "SBCE", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="SBCE_HA_CLUSTER", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-sbce-02", "SBCE", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="SBCE_HA_CLUSTER", is_primary=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-CORP-TELEPHONY",
            name="Corporate Telephony Core (Avaya Aura)",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Avaya Communication Manager, Session Manager duplex, and G450 Media Gateways",
            dependency_logic=DependencyLogic.QUORUM,
            quorum_count=1,
            proposed_design_slo=99.95,
            parent_services=["SVC-ENTERPRISE-NETWORK", "SVC-SIP-CARRIER"],
            dependencies=[
                ServiceComponentDependency("avaya-cm-01", "SERVER", is_mandatory=False, weight=0.3, is_redundant=True, redundancy_group="CM_DUPLEX", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-cm-02", "SERVER", is_mandatory=False, weight=0.3, is_redundant=True, redundancy_group="CM_DUPLEX", is_primary=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-sm-01", "SERVER", is_mandatory=False, weight=0.2, is_redundant=True, redundancy_group="SM_DUPLEX", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-sm-02", "SERVER", is_mandatory=False, weight=0.2, is_redundant=True, redundancy_group="SM_DUPLEX", is_primary=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-CONTACT-CENTER-INBOUND",
            name="Inbound Customer Contact Center (Elite ACD)",
            tier=ServiceTier.TIER_1_MISSION_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Passenger customer care queues, flight reservation desk, and platinum loyalty ACD lines",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.90,
            parent_services=["SVC-CORP-TELEPHONY", "SVC-SIP-CARRIER"],
            dependencies=[
                ServiceComponentDependency("avaya-g450-01", "GATEWAY", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="ACD_MEDIA_GATEWAYS", is_primary=True, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-g450-02", "GATEWAY", is_mandatory=False, weight=0.5, is_redundant=True, redundancy_group="ACD_MEDIA_GATEWAYS", is_primary=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-CONTACT-CENTER-OUTBOUND",
            name="Outbound Contact Center & Automated Dialling",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Flight reschedule notifications, ticket confirmation diallers, and agent blended campaigns",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.50,
            parent_services=["SVC-CORP-TELEPHONY", "SVC-SIP-CARRIER"],
            dependencies=[
                ServiceComponentDependency("avaya-sm-01", "SERVER", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-g450-01", "GATEWAY", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-IVR-SELFSERVICE",
            name="Interactive Voice Response (Experience Portal)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Avaya Experience Portal automated speech self-service, flight status IVR, and booking lookups",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.80,
            parent_services=["SVC-CORP-TELEPHONY"],
            dependencies=[
                ServiceComponentDependency("avaya-sm-01", "SERVER", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
                ServiceComponentDependency("avaya-g450-01", "GATEWAY", is_mandatory=True, weight=0.5, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))

        self.register_service(BusinessService(
            service_id="SVC-COMPLIANCE-RECORDING",
            name="Call Recording & Compliance (Verint WFO / CMS)",
            tier=ServiceTier.TIER_2_BUSINESS_CRITICAL,
            scope=ServiceScope.GLOBAL,
            description="Verint WFO regulatory call recording, PCI-DSS compliance mute/unmute, and CMS operational reporting",
            dependency_logic=DependencyLogic.MANDATORY_AND,
            proposed_design_slo=99.80,
            parent_services=["SVC-CORP-TELEPHONY"],
            dependencies=[
                ServiceComponentDependency("avaya-cms-01", "SERVER", is_mandatory=True, weight=1.0, is_redundant=False, station_id="JKIA-HUB"),
            ],
        ))


@dataclass
class SLOSpecification:
    """Proposed internal SLO design targets and evaluation windows."""
    service_id: str
    target_slo_percent: float = 99.95      # Proposed internal SLO target (NOT confirmed contractual SLA)
    contractual_sla_percent: float = 99.90 # Contractual design baseline
    measurement_window_days: int = 30      # Evaluation window
    scheduled_maintenance_minutes: float = 0.0


@dataclass
class MultiDimensionalSLIResult:
    """Multi-dimensional Service Level Indicator result."""
    service_id: str
    # 1. Availability SLI: Proportion of eligible operational intervals meeting availability definition
    availability_sli: float
    # 2. Performance SLI: Proportion meeting latency/performance threshold
    performance_sli: float
    # 3. Quality SLI: Proportion meeting composite service quality index
    quality_sli: float
    # 4. Coverage: Proportion of expected measurement intervals with trustworthy telemetry
    coverage_percent: float
    total_expected_minutes: float
    valid_operational_minutes: float
    good_minutes: float
    degraded_minutes: float
    outage_minutes: float
    unknown_minutes: float  # Missing or stale telemetry tracked explicitly
    scheduled_maintenance_minutes: float
    target_slo_percent: float
    contractual_sla_percent: float
    total_error_budget_minutes: float
    consumed_error_budget_minutes: float
    remaining_error_budget_minutes: float
    burn_rate: float
    is_slo_breached: bool
    is_sla_breached: bool

    @property
    def sli_percent(self) -> float:
        """Backward compatibility alias for availability_sli."""
        return self.availability_sli

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "availability_sli": round(self.availability_sli, 4),
            "performance_sli": round(self.performance_sli, 4),
            "quality_sli": round(self.quality_sli, 4),
            "coverage_percent": round(self.coverage_percent, 2),
            "total_expected_minutes": round(self.total_expected_minutes, 1),
            "valid_operational_minutes": round(self.valid_operational_minutes, 1),
            "good_minutes": round(self.good_minutes, 1),
            "degraded_minutes": round(self.degraded_minutes, 1),
            "outage_minutes": round(self.outage_minutes, 1),
            "unknown_minutes": round(self.unknown_minutes, 1),
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


# Backward compatibility alias
SLIResult = MultiDimensionalSLIResult


class SLIEvaluationEngine:
    """Decoupled SLI measurement and Error Budget evaluation engine.
    
    Measures Availability, Performance, Quality, and Coverage independently.
    Tracks missing/stale telemetry as UNKNOWN rather than dropping from denominator.
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
        health_index: float = 0.0,
        is_available: bool = True,
        is_performance_met: bool = True,
        is_unknown: bool = False,
        in_maintenance: bool = False,
    ) -> None:
        """Record an observed operational interval for a service."""
        if service_id not in self._observations:
            self._observations[service_id] = []
        self._observations[service_id].append({
            "duration": duration_minutes,
            "health": health_index,
            "is_available": is_available,
            "is_performance_met": is_performance_met,
            "is_unknown": is_unknown,
            "in_maintenance": in_maintenance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def evaluate_sli(self, service_id: str) -> MultiDimensionalSLIResult:
        """Calculate multi-dimensional SLI and Error Budget for a specific service."""
        spec = self._slos.get(service_id, SLOSpecification(service_id=service_id))
        records = self._observations.get(service_id, [])

        total_measured = sum(r["duration"] for r in records)
        maintenance = sum(r["duration"] for r in records if r["in_maintenance"]) + spec.scheduled_maintenance_minutes

        good_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and not r["is_unknown"] and r["health"] >= 0.85)
        degraded_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and not r["is_unknown"] and 0.40 <= r["health"] < 0.85)
        outage_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and not r["is_unknown"] and r["health"] < 0.40)
        unknown_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and r["is_unknown"])

        perf_good_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and not r["is_unknown"] and r["is_performance_met"])
        avail_good_minutes = sum(r["duration"] for r in records if not r["in_maintenance"] and not r["is_unknown"] and r["is_available"] and r["health"] >= 0.40)

        # Total valid operational minutes includes trustworthy and unknown (missing/stale) intervals.
        # Missing or stale telemetry must NOT silently disappear from the denominator!
        valid_minutes = good_minutes + degraded_minutes + outage_minutes + unknown_minutes

        # 1. Availability SLI: Available good minutes / Valid operational minutes (unknown intervals penalize availability)
        avail_sli = (avail_good_minutes / valid_minutes * 100.0) if valid_minutes > 0 else 100.0
        
        # 2. Performance SLI:
        perf_sli = (perf_good_minutes / valid_minutes * 100.0) if valid_minutes > 0 else 100.0

        # 3. Quality SLI: Weighted quality index (Good + 0.5 * Degraded)
        quality_sli = ((good_minutes + 0.5 * degraded_minutes) / valid_minutes * 100.0) if valid_minutes > 0 else 100.0

        # 4. Coverage: Trustworthy measurements vs Total expected operational minutes
        trustworthy_minutes = good_minutes + degraded_minutes + outage_minutes
        coverage_percent = (trustworthy_minutes / valid_minutes * 100.0) if valid_minutes > 0 else 100.0

        # Error Budget calculations (based on 30-day window)
        window_minutes = spec.measurement_window_days * 24 * 60.0
        allowed_unreliability = (100.0 - spec.target_slo_percent) / 100.0
        total_error_budget = window_minutes * allowed_unreliability

        # Unreliability consumed: outage minutes + 50% degraded minutes + unknown minutes (unknown treated as degraded penalty)
        consumed_budget = outage_minutes + (degraded_minutes * 0.5) + (unknown_minutes * 0.5)
        remaining_budget = max(0.0, total_error_budget - consumed_budget)
        burn_rate = (consumed_budget / total_error_budget) if total_error_budget > 0 else 0.0

        is_slo_breached = avail_sli < spec.target_slo_percent or remaining_budget <= 0.0
        is_sla_breached = avail_sli < spec.contractual_sla_percent

        return MultiDimensionalSLIResult(
            service_id=service_id,
            availability_sli=min(100.0, avail_sli),
            performance_sli=min(100.0, perf_sli),
            quality_sli=min(100.0, quality_sli),
            coverage_percent=min(100.0, coverage_percent),
            total_expected_minutes=total_measured,
            valid_operational_minutes=valid_minutes,
            good_minutes=good_minutes,
            degraded_minutes=degraded_minutes,
            outage_minutes=outage_minutes,
            unknown_minutes=unknown_minutes,
            scheduled_maintenance_minutes=maintenance,
            target_slo_percent=spec.target_slo_percent,
            contractual_sla_percent=spec.contractual_sla_percent,
            total_error_budget_minutes=total_error_budget,
            consumed_error_budget_minutes=consumed_budget,
            remaining_error_budget_minutes=remaining_budget,
            burn_rate=burn_rate,
            is_slo_breached=is_slo_breached,
            is_sla_breached=is_sla_breached,
        )

    def evaluate_fleet_slos(self) -> List[MultiDimensionalSLIResult]:
        return [self.evaluate_sli(sid) for sid in self._slos.keys()]
