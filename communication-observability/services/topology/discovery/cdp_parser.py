"""Cisco CDP MIB Table Parser for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from services.topology.identity import normalize_ip_address


@dataclass
class CDPNeighbor:
    local_if_index: int
    remote_device_id: str
    remote_port_id: str
    remote_ip: str | None = None
    remote_platform: str | None = None
    native_vlan: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CDPParser:
    """Parses CISCO-CDP-MIB cdpCacheTable SNMP responses."""

    # OID prefix: 1.3.6.1.4.1.9.9.23.1.2.1.1
    # Columns in cdpCacheTable:
    # 4: cdpCacheAddress (hex or dotted IP)
    # 5: cdpCacheVersion
    # 6: cdpCacheDeviceId (string hostname / FQDN)
    # 7: cdpCacheDevicePort (string e.g. GigabitEthernet1/0/24)
    # 8: cdpCachePlatform (string e.g. cisco WS-C3850-48P)
    # 9: cdpCacheCapabilities
    # 11: cdpCacheNativeVLAN

    COL_ADDRESS = 4
    COL_VERSION = 5
    COL_DEVICE_ID = 6
    COL_DEVICE_PORT = 7
    COL_PLATFORM = 8
    COL_CAPABILITIES = 9
    COL_NATIVE_VLAN = 11

    @classmethod
    def parse_cache_table(cls, raw_entries: list[dict[str, Any]]) -> list[CDPNeighbor]:
        """Parse raw SNMP varbind list or structured rows into CDPNeighbor records."""
        if not raw_entries:
            return []

        # If entries already structured
        if "local_if_index" in raw_entries[0] and "remote_device_id" in raw_entries[0]:
            neighbors = []
            for item in raw_entries:
                ip = normalize_ip_address(item.get("remote_ip"))
                neighbors.append(
                    CDPNeighbor(
                        local_if_index=int(item["local_if_index"]),
                        remote_device_id=str(item["remote_device_id"]),
                        remote_port_id=str(item.get("remote_port_id", "")),
                        remote_ip=ip,
                        remote_platform=item.get("remote_platform"),
                        native_vlan=int(item["native_vlan"]) if item.get("native_vlan") else None,
                    )
                )
            return neighbors

        # Parsing OID-based SNMP varbinds
        # Table indices typically: .column.cdpCacheIfIndex.cdpCacheDeviceIndex
        indexed_data: dict[tuple[int, int], dict[str, Any]] = {}
        oid_pattern = re.compile(
            r"^1\.3\.6\.1\.4\.1\.9\.9\.23\.1\.2\.1\.1\.(\d+)\.(\d+)\.(\d+)$"
        )

        for vb in raw_entries:
            oid = vb.get("oid", "")
            val = vb.get("value")
            match = oid_pattern.match(oid)
            if not match:
                continue

            col = int(match.group(1))
            local_if = int(match.group(2))
            cache_idx = int(match.group(3))
            key = (local_if, cache_idx)

            if key not in indexed_data:
                indexed_data[key] = {"local_if_index": local_if}

            if col == cls.COL_ADDRESS:
                indexed_data[key]["remote_ip"] = normalize_ip_address(str(val))
            elif col == cls.COL_DEVICE_ID:
                indexed_data[key]["remote_device_id"] = str(val).strip()
            elif col == cls.COL_DEVICE_PORT:
                indexed_data[key]["remote_port_id"] = str(val).strip()
            elif col == cls.COL_PLATFORM:
                indexed_data[key]["remote_platform"] = str(val).strip()
            elif col == cls.COL_NATIVE_VLAN:
                try:
                    indexed_data[key]["native_vlan"] = int(val)
                except (ValueError, TypeError):
                    pass

        neighbors = []
        for data in indexed_data.values():
            if "remote_device_id" in data and "remote_port_id" in data:
                neighbors.append(
                    CDPNeighbor(
                        local_if_index=data["local_if_index"],
                        remote_device_id=data["remote_device_id"],
                        remote_port_id=data["remote_port_id"],
                        remote_ip=data.get("remote_ip"),
                        remote_platform=data.get("remote_platform"),
                        native_vlan=data.get("native_vlan"),
                    )
                )
        return neighbors

