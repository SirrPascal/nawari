"""Topology Business Service Dependency Data Models and Enums for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class DependentType(str, Enum):
    DEVICE = "DEVICE"
    INTERFACE = "INTERFACE"
    SUBNET = "SUBNET"
    ROUTE = "ROUTE"
    PATH = "PATH"


class Criticality(str, Enum):
    CRITICAL = "CRITICAL"
    REDUNDANT = "REDUNDANT"
    OPTIONAL = "OPTIONAL"


class FailureImpact(str, Enum):
    TOTAL_OUTAGE = "TOTAL_OUTAGE"
    DEGRADATION = "DEGRADATION"
    FAILOVER_TRIGGERED = "FAILOVER_TRIGGERED"


@dataclass
class ServiceDependency:
    dependency_id: str
    service_id: str
    dependent_type: DependentType | str
    dependent_id: str
    criticality: Criticality | str = Criticality.CRITICAL
    failure_impact: FailureImpact | str = FailureImpact.DEGRADATION
    impact_weight: float = 1.00
    notes: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.dependent_type, DependentType):
            self.dependent_type = self.dependent_type.value
        if isinstance(self.criticality, Criticality):
            self.criticality = self.criticality.value
        if isinstance(self.failure_impact, FailureImpact):
            self.failure_impact = self.failure_impact.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceDependency:
        return cls(**data)

