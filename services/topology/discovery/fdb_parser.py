"""BRIDGE-MIB Forwarding Database (dot1dTpFdbTable) Parser for Nawari Network Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from services.topology.identity import normalize_mac_address


@dataclass
class FDBEntry:
    mac_address: str
    bridge_port: int
    if_index: int | None = None
    status: str = "learned"  # other, invalid, learned, self, mgmt
    vlan_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FDBParser:
    """Parses BRIDGE-MIB dot1dTpFdbTable (1.3.6.1.2.1.17.4.3.1) SNMP responses."""

    # dot1dTpFdbTable columns:
    # 1: dot1dTpFdbAddress (MacAddress)
    # 2: dot1dTpFdbPort (INTEGER: bridge port number)
    # 3: dot1dTpFdbStatus (INTEGER: 1=other, 2=invalid, 3=learned, 4=self, 5=mgmt)

    STATUS_MAP = {
        1: "other",
        2: "invalid",
        3: "learned",
        4: "self",
        5: "mgmt",
    }

    @classmethod
    def parse_fdb_table(
        cls,
        raw_entries: list[dict[str, Any]],
        port_to_ifindex_map: dict[int, int] | None = None,
        default_vlan: int | None = None,
    ) -> list[FDBEntry]:
        """Parse raw FDB entries or SNMP varbinds into structured FDBEntry records."""
        if not raw_entries:
            return []

        # If entries already structured
        if "mac_address" in raw_entries[0] and "bridge_port" in raw_entries[0]:
            entries = []
            for item in raw_entries:
                mac = normalize_mac_address(item.get("mac_address"))
                if not mac:
                    continue
                b_port = int(item["bridge_port"])
                if_idx = item.get("if_index")
                if if_idx is None and port_to_ifindex_map:
                    if_idx = port_to_ifindex_map.get(b_port)

                status_val = item.get("status", "learned")
                if isinstance(status_val, int):
                    status_val = cls.STATUS_MAP.get(status_val, "learned")

                entries.append(
                    FDBEntry(
                        mac_address=mac,
                        bridge_port=b_port,
                        if_index=int(if_idx) if if_idx is not None else None,
                        status=str(status_val),
                        vlan_id=item.get("vlan_id", default_vlan),
                    )
                )
            return entries

        # Parsing OID-based SNMP varbinds
        # Table OID: 1.3.6.1.2.1.17.4.3.1.<col>.<mac_dec_bytes (6 bytes)>
        indexed_data: dict[str, dict[str, Any]] = {}
        oid_pattern = re.compile(
            r"^1\.3\.6\.1\.2\.1\.17\.4\.3\.1\.(\d+)\.(\d+\.\d+\.\d+\.\d+\.\d+\.\d+)$"
        )

        for vb in raw_entries:
            oid = vb.get("oid", "")
            val = vb.get("value")
            match = oid_pattern.match(oid)
            if not match:
                continue

            col = int(match.group(1))
            mac_octets = match.group(2).split(".")
            if len(mac_octets) != 6:
                continue

            mac_hex = ":".join(f"{int(b):02x}" for b in mac_octets)
            mac = normalize_mac_address(mac_hex)
            if not mac:
                continue

            if mac not in indexed_data:
                indexed_data[mac] = {"mac_address": mac}

            if col == 2:  # dot1dTpFdbPort
                try:
                    indexed_data[mac]["bridge_port"] = int(val)
                except (ValueError, TypeError):
                    pass
            elif col == 3:  # dot1dTpFdbStatus
                try:
                    status_int = int(val)
                    indexed_data[mac]["status"] = cls.STATUS_MAP.get(status_int, "learned")
                except (ValueError, TypeError):
                    pass

        results = []
        for mac, data in indexed_data.items():
            if "bridge_port" in data:
                b_port = data["bridge_port"]
                if_idx = port_to_ifindex_map.get(b_port) if port_to_ifindex_map else None
                results.append(
                    FDBEntry(
                        mac_address=mac,
                        bridge_port=b_port,
                        if_index=if_idx,
                        status=data.get("status", "learned"),
                        vlan_id=default_vlan,
                    )
                )
        return results

