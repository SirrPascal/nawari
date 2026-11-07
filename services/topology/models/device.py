"""Topology Device Data Models and Enums for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    CORE_ROUTER = "CORE_ROUTER"
    DIST_SWITCH = "DIST_SWITCH"
    ACCESS_SWITCH = "ACCESS_SWITCH"
    SBC = "SBC"
    FIREWALL = "FIREWALL"
    PBX = "PBX"
    SERVER = "SERVER"
    WORKSTATION = "WORKSTATION"
    GATEWAY = "GATEWAY"


class ConfidenceLevel(str, Enum):
    CONFIRMED = "CONFIRMED"      # >= 0.95: Direct mutual protocol handshake (LLDP/CDP)
    PROBABLE = "PROBABLE"        # 0.75 - 0.90: IP routing / exclusive FDB MAC
    INFERRED = "INFERRED"        # 0.50 - 0.74: ARP cache / traceroute TTL
    UNKNOWN = "UNKNOWN"          # < 0.50: Unresolved IP/MAC


@dataclass
class Device:
    device_id: str
    canonical_name: str
    management_ip: str
    vendor: str
    model: str | None = None
    device_type: DeviceType | str = DeviceType.ACCESS_SWITCH
    zabbix_host_id: int | None = None
    sys_object_id: str | None = None
    chassis_mac: str | None = None
    serial_number: str | None = None
    os_version: str | None = None
    site_id: str = "NBO-HQ"
    is_managed: bool = True
    confidence_score: float = 1.00
    first_seen: str | None = None
    last_discovered: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.first_seen:
            self.first_seen = now_iso
        if not self.last_discovered:
            self.last_discovered = now_iso
        if isinstance(self.device_type, DeviceType):
            self.device_type = self.device_type.value

    @property
    def confidence_level(self) -> ConfidenceLevel:
        if self.confidence_score >= 0.95:
            return ConfidenceLevel.CONFIRMED
        if self.confidence_score >= 0.75:
            return ConfidenceLevel.PROBABLE
        if self.confidence_score >= 0.50:
            return ConfidenceLevel.INFERRED
        return ConfidenceLevel.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        clean_data = dict(data)
        if "confidence_level" in clean_data:
            del clean_data["confidence_level"]
        return cls(**clean_data)

