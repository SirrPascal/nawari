"""Topology Subnet and Routing Adjacency Data Models for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Subnet:
    subnet_id: str
    network_cidr: str
    vlan_id: int | None = None
    gateway_ip: str | None = None
    site_id: str = "NBO-HQ"
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subnet:
        return cls(**data)


@dataclass
class RoutingAdjacency:
    adjacency_id: str
    local_device_id: str
    remote_device_id: str | None
    protocol: str  # OSPF, BGP, STATIC, CONNECTED
    local_ip: str
    remote_ip: str
    state: str     # FULL, 2WAY, ESTABLISHED, ACTIVE, IDLE
    area_or_asn: str | None = None
    metric: int | None = None
    last_flap: str | None = None
    last_verified: str | None = None

    def __post_init__(self) -> None:
        if not self.last_verified:
            self.last_verified = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingAdjacency:
        return cls(**data)

