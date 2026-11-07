"""Topology Interface Data Models and Enums for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any


class AdminStatus(IntEnum):
    UP = 1
    DOWN = 2
    TESTING = 3


class OperStatus(IntEnum):
    UP = 1
    DOWN = 2
    TESTING = 3
    UNKNOWN = 4
    DORMANT = 5
    NOT_PRESENT = 6
    LOWER_LAYER_DOWN = 7


@dataclass
class Interface:
    interface_id: str
    device_id: str
    if_index: int
    if_name: str
    if_descr: str | None = None
    if_type: int = 6  # ethernetCsmacd default
    mac_address: str | None = None
    speed_bps: int | None = None
    admin_status: int = AdminStatus.UP
    oper_status: int = OperStatus.UP
    mtu: int | None = 1500
    is_uplink: bool = False
    is_trunk: bool = False
    native_vlan: int = 1
    tagged_vlans: list[int] = field(default_factory=list)
    lag_master_id: str | None = None
    last_change: str | None = None
    last_discovered: str | None = None

    def __post_init__(self) -> None:
        if not self.last_discovered:
            self.last_discovered = datetime.now(timezone.utc).isoformat()

    @property
    def is_operational(self) -> bool:
        return self.oper_status == OperStatus.UP

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Interface:
        clean_data = dict(data)
        if "is_operational" in clean_data:
            del clean_data["is_operational"]
        return cls(**clean_data)

