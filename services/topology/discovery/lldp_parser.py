"""IEEE 802.1AB LLDP-MIB Table Parser for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from services.topology.identity import normalize_mac_address


@dataclass
class LLDPNeighbor:
    local_if_index: int
    remote_chassis_id: str
    remote_port_id: str
    remote_sys_name: str | None = None
    remote_port_desc: str | None = None
    remote_sys_desc: str | None = None
    chassis_id_subtype: int = 4  # 4=macAddress default
    port_id_subtype: int = 5     # 5=interfaceName default

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLDPParser:
    """Parses IEEE 802.1AB LLDP-MIB lldpRemTable SNMP responses."""

    # OID prefixes for lldpRemTable (1.0.8802.1.1.2.1.4.1.1)
    OID_PREFIX = "1.0.8802.1.1.2.1.4.1.1"

    # Column numbers in lldpRemTable:
    # 4: lldpRemChassisIdSubtype
    # 5: lldpRemChassisId
    # 6: lldpRemPortIdSubtype
    # 7: lldpRemPortId
    # 8: lldpRemPortDesc
    # 9: lldpRemSysName
    # 10: lldpRemSysDesc

    COL_CHASSIS_SUBTYPE = 4
    COL_CHASSIS_ID = 5
    COL_PORT_SUBTYPE = 6
    COL_PORT_ID = 7
    COL_PORT_DESC = 8
    COL_SYS_NAME = 9
    COL_SYS_DESC = 10

    @classmethod
    def parse_rem_table(cls, raw_entries: list[dict[str, Any]]) -> list[LLDPNeighbor]:
        """Parse raw SNMP varbind list or rows into structured LLDPNeighbor records.

        Each entry dict can be either:
        1. A row with structured keys:
           {'local_if_index': 1, 'remote_chassis_id': '...', 'remote_port_id': '...', ...}
        2. A flat SNMP varbind:
           {'oid': '1.0.8802.1.1.2.1.4.1.1.5.0.1.1', 'value': '001a2b3c4d5e'}
        """
        if not raw_entries:
            return []

        # If entries already structured:
        if "local_if_index" in raw_entries[0] and "remote_chassis_id" in raw_entries[0]:
            neighbors = []
            for item in raw_entries:
                chassis = item.get("remote_chassis_id", "")
                norm_mac = normalize_mac_address(chassis)
                neighbors.append(
                    LLDPNeighbor(
                        local_if_index=int(item["local_if_index"]),
                        remote_chassis_id=norm_mac or chassis,
                        remote_port_id=str(item.get("remote_port_id", "")),
                        remote_sys_name=item.get("remote_sys_name"),
                        remote_port_desc=item.get("remote_port_desc"),
                        remote_sys_desc=item.get("remote_sys_desc"),
                        chassis_id_subtype=int(item.get("chassis_id_subtype", 4)),
                        port_id_subtype=int(item.get("port_id_subtype", 5)),
                    )
                )
            return neighbors

        # Parsing OID-based SNMP varbinds
        # Table indices typically: .column.timeMark.localIfIndex.remIndex
        indexed_data: dict[tuple[int, int], dict[str, Any]] = {}

        oid_pattern = re.compile(
            r"^1\.0\.8802\.1\.1\.2\.1\.4\.1\.1\.(\d+)\.\d+\.(\d+)\.(\d+)$"
        )

        for vb in raw_entries:
            oid = vb.get("oid", "")
            val = vb.get("value")
            match = oid_pattern.match(oid)
            if not match:
                continue

            col = int(match.group(1))
            local_if = int(match.group(2))
            rem_idx = int(match.group(3))
            key = (local_if, rem_idx)

            if key not in indexed_data:
                indexed_data[key] = {"local_if_index": local_if}

            if col == cls.COL_CHASSIS_SUBTYPE:
                indexed_data[key]["chassis_id_subtype"] = int(val)
            elif col == cls.COL_CHASSIS_ID:
                norm = normalize_mac_address(str(val))
                indexed_data[key]["remote_chassis_id"] = norm or str(val)
            elif col == cls.COL_PORT_SUBTYPE:
                indexed_data[key]["port_id_subtype"] = int(val)
            elif col == cls.COL_PORT_ID:
                indexed_data[key]["remote_port_id"] = str(val)
            elif col == cls.COL_PORT_DESC:
                indexed_data[key]["remote_port_desc"] = str(val)
            elif col == cls.COL_SYS_NAME:
                indexed_data[key]["remote_sys_name"] = str(val)
            elif col == cls.COL_SYS_DESC:
                indexed_data[key]["remote_sys_desc"] = str(val)

        neighbors = []
        for data in indexed_data.values():
            if "remote_chassis_id" in data and "remote_port_id" in data:
                neighbors.append(
                    LLDPNeighbor(
                        local_if_index=data["local_if_index"],
                        remote_chassis_id=data["remote_chassis_id"],
                        remote_port_id=data["remote_port_id"],
                        remote_sys_name=data.get("remote_sys_name"),
                        remote_port_desc=data.get("remote_port_desc"),
                        remote_sys_desc=data.get("remote_sys_desc"),
                        chassis_id_subtype=data.get("chassis_id_subtype", 4),
                        port_id_subtype=data.get("port_id_subtype", 5),
                    )
                )
        return neighbors

