"""Topology Change Event Data Models and Enums for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ChangeType(str, Enum):
    DEVICE_ADDED = "DEVICE_ADDED"
    DEVICE_REMOVED = "DEVICE_REMOVED"
    LINK_UP = "LINK_UP"
    LINK_DOWN = "LINK_DOWN"
    NEIGHBOUR_LOST = "NEIGHBOUR_LOST"
    NEIGHBOUR_ADDED = "NEIGHBOUR_ADDED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    SPEED_CHANGED = "SPEED_CHANGED"
    VLAN_MEMBERSHIP_CHANGED = "VLAN_MEMBERSHIP_CHANGED"


class TargetEntityType(str, Enum):
    DEVICE = "DEVICE"
    INTERFACE = "INTERFACE"
    LINK = "LINK"
    ADJACENCY = "ADJACENCY"


@dataclass
class TopologyChange:
    change_type: ChangeType | str
    target_entity_type: TargetEntityType | str
    target_entity_id: str
    change_id: int | None = None
    timestamp: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    detected_by: str = "SNMP_DISCOVERY"
    correlated_problem_id: int | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if isinstance(self.change_type, ChangeType):
            self.change_type = self.change_type.value
        if isinstance(self.target_entity_type, TargetEntityType):
            self.target_entity_type = self.target_entity_type.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopologyChange:
        return cls(**data)

