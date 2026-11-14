"""Topology Layer 2 / Layer 3 Link Data Models and Enums for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DiscoveryProtocol(str, Enum):
    LLDP = "LLDP"
    CDP = "CDP"
    BRIDGE_FDB = "BRIDGE_FDB"
    MANUAL_CONFIG = "MANUAL_CONFIG"
    ROUTING = "ROUTING"
    ENDPOINT_TRACEROUTE = "ENDPOINT_TRACEROUTE"


class LinkType(str, Enum):
    ACCESS = "ACCESS"
    TRUNK = "TRUNK"
    PORT_CHANNEL_MEMBER = "PORT_CHANNEL_MEMBER"
    CROSS_CONNECT = "CROSS_CONNECT"
    ROUTED = "ROUTED"


class LinkStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DEGRADED_UNIDIRECTIONAL = "DEGRADED_UNIDIRECTIONAL"
    STALE = "STALE"
    DECOMMISSIONED = "DECOMMISSIONED"


@dataclass
class Layer2Link:
    link_id: str
    source_interface_id: str
    target_interface_id: str
    discovery_protocol: DiscoveryProtocol | str
    link_type: LinkType | str = LinkType.TRUNK
    is_bidirectional: bool = True
    confidence: float = 0.95
    evidence_metadata: dict[str, Any] = field(default_factory=dict)
    status: LinkStatus | str = LinkStatus.ACTIVE
    first_detected: str | None = None
    last_verified: str | None = None

    def __post_init__(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.first_detected:
            self.first_detected = now_iso
        if not self.last_verified:
            self.last_verified = now_iso
        if isinstance(self.discovery_protocol, DiscoveryProtocol):
            self.discovery_protocol = self.discovery_protocol.value
        if isinstance(self.link_type, LinkType):
            self.link_type = self.link_type.value
        if isinstance(self.status, LinkStatus):
            self.status = self.status.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layer2Link:
        return cls(**data)

