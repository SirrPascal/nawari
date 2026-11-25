"""SolarWinds Node Inventory Importer and Parser for Nawari.

Parses node records from SolarWinds Orion Information Service (SWIS) REST API,
JSON exports, and CSV dumps into standardized SolarWindsNodeRecord objects.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("nawari.solarwinds.importer")


@dataclasses.dataclass
class SolarWindsNodeRecord:
    """Standardized representation of a SolarWinds managed node."""
    node_id: str
    caption: str
    node_name: str
    ip_address: str
    sys_name: str
    vendor: str
    machine_type: str
    serial_number: Optional[str] = None
    device_type: str = "Switch"
    site: str = "Unknown"
    status: int = 1
    custom_properties: Dict[str, Any] = dataclasses.field(default_factory=dict)
    raw_record: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


class SolarWindsInventoryImporter:
    """Importer and parser for SolarWinds node records."""

    @classmethod
    def from_swis_api_response(cls, api_data: Dict[str, Any]) -> List[SolarWindsNodeRecord]:
        """Parse SWIS JSON query response (e.g. from Orion.Nodes query)."""
        results = api_data.get("results", []) if isinstance(api_data, dict) else api_data
        records = []
        for r in results:
            rec = cls._normalize_dict(r)
            if rec:
                records.append(rec)
        return records

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> List[SolarWindsNodeRecord]:
        """Load and parse SolarWinds nodes from a JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"SolarWinds inventory file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_swis_api_response(data)

    @classmethod
    def from_csv_file(cls, path: Union[str, Path]) -> List[SolarWindsNodeRecord]:
        """Load and parse SolarWinds nodes from a CSV export."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"SolarWinds CSV export not found: {file_path}")
        records = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = cls._normalize_dict(row)
                if rec:
                    records.append(rec)
        return records

    @staticmethod
    def _normalize_dict(d: Dict[str, Any]) -> Optional[SolarWindsNodeRecord]:
        node_id = str(d.get("NodeID") or d.get("node_id") or d.get("ID") or "")
        caption = str(d.get("Caption") or d.get("caption") or d.get("DisplayName") or d.get("Name") or "").strip()
        ip = str(d.get("IPAddress") or d.get("ip_address") or d.get("IP") or "").strip()
        
        if not node_id and not caption and not ip:
            return None

        node_name = str(d.get("NodeName") or d.get("node_name") or d.get("DNS") or caption).strip()
        sys_name = str(d.get("SysName") or d.get("sys_name") or caption).strip()
        vendor = str(d.get("Vendor") or d.get("vendor") or "Generic").strip()
        machine_type = str(d.get("MachineType") or d.get("machine_type") or d.get("Model") or "Unknown").strip()
        serial = d.get("SerialNumber") or d.get("serial_number") or d.get("ServiceTag")
        if serial:
            serial = str(serial).strip().upper()
        
        site = str(d.get("Site") or d.get("site") or d.get("Location") or "Unknown").strip()
        device_type = str(d.get("DeviceType") or d.get("device_type") or d.get("Category") or "Switch").strip()
        status_val = d.get("Status", 1)
        try:
            status = int(status_val)
        except (ValueError, TypeError):
            status = 1

        custom_props = d.get("CustomProperties") or d.get("custom_properties") or {}
        if not isinstance(custom_props, dict):
            custom_props = {}

        return SolarWindsNodeRecord(
            node_id=node_id,
            caption=caption,
            node_name=node_name,
            ip_address=ip,
            sys_name=sys_name,
            vendor=vendor,
            machine_type=machine_type,
            serial_number=serial,
            device_type=device_type,
            site=site,
            status=status,
            custom_properties=custom_props,
            raw_record=d,
        )
