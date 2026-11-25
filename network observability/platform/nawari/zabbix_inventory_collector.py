"""Zabbix Host Inventory Collector and Parser for Nawari.

Parses host records from Zabbix JSON-RPC API and exported snapshots into
standardized ZabbixHostRecord objects.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("nawari.zabbix.collector")


@dataclasses.dataclass
class ZabbixInterfaceRecord:
    interface_id: str
    ip: str
    dns: str
    main: bool
    type: int  # 1: Agent, 2: SNMP, 3: IPMI, 4: JMX
    port: str = "10050"


@dataclasses.dataclass
class ZabbixHostRecord:
    """Standardized representation of a Zabbix managed host."""
    host_id: str
    technical_host: str
    visible_name: str
    status: int  # 0: Monitored, 1: Unmonitored
    interfaces: List[ZabbixInterfaceRecord] = dataclasses.field(default_factory=list)
    host_groups: List[str] = dataclasses.field(default_factory=list)
    templates: List[str] = dataclasses.field(default_factory=list)
    inventory: Dict[str, Any] = dataclasses.field(default_factory=dict)
    description: str = ""
    raw_record: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def primary_ip(self) -> Optional[str]:
        for iface in self.interfaces:
            if iface.main and iface.ip and iface.ip != "127.0.0.1" and iface.ip != "mock-snmp":
                return iface.ip
        for iface in self.interfaces:
            if iface.ip and iface.ip != "127.0.0.1" and iface.ip != "mock-snmp":
                return iface.ip
        return self.interfaces[0].ip if self.interfaces else None

    @property
    def all_ips(self) -> List[str]:
        return [i.ip for i in self.interfaces if i.ip]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host_id": self.host_id,
            "technical_host": self.technical_host,
            "visible_name": self.visible_name,
            "status": self.status,
            "primary_ip": self.primary_ip,
            "all_ips": self.all_ips,
            "host_groups": self.host_groups,
            "templates": self.templates,
            "inventory": self.inventory,
            "description": self.description,
        }


class ZabbixInventoryCollector:
    """Collector and parser for Zabbix host records."""

    @classmethod
    def from_api(cls, api_url: str, token: str, timeout: int = 15) -> List[ZabbixHostRecord]:
        """Fetch host inventory directly from Zabbix JSON-RPC API."""
        payload = {
            "jsonrpc": "2.0",
            "method": "host.get",
            "params": {
                "output": ["hostid", "host", "name", "status", "description"],
                "selectInterfaces": ["interfaceid", "ip", "dns", "main", "type", "port"],
                "selectGroups": ["groupid", "name"],
                "selectParentTemplates": ["templateid", "name"],
                "selectInventory": ["serialno_a", "model", "vendor", "location", "site_address_a", "type", "name", "alias", "os"],
            },
            "id": 1,
        }
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "error" in data:
                raise RuntimeError(f"Zabbix API error: {data['error']}")
            return cls.from_json_list(data.get("result", []))

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> List[ZabbixHostRecord]:
        """Load host inventory from a saved JSON export."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Zabbix inventory file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_json_list(data)

    @classmethod
    def from_json_list(cls, hosts_data: List[Dict[str, Any]]) -> List[ZabbixHostRecord]:
        records = []
        for h in hosts_data:
            rec = cls._normalize_host_dict(h)
            if rec:
                records.append(rec)
        return records

    @staticmethod
    def _normalize_host_dict(d: Dict[str, Any]) -> Optional[ZabbixHostRecord]:
        host_id = str(d.get("hostid") or d.get("host_id") or "")
        tech_host = str(d.get("host") or d.get("technical_host") or "").strip()
        visible_name = str(d.get("name") or d.get("visible_name") or tech_host).strip()

        if not host_id and not tech_host:
            return None

        status_val = d.get("status", 0)
        try:
            status = int(status_val)
        except (ValueError, TypeError):
            status = 0

        interfaces = []
        for iface in d.get("interfaces", []):
            ifid = str(iface.get("interfaceid") or "")
            ip = str(iface.get("ip") or "").strip()
            dns = str(iface.get("dns") or "").strip()
            main = str(iface.get("main", "1")) in ("1", "true", "True")
            itype = int(iface.get("type", 1))
            port = str(iface.get("port", "10050"))
            interfaces.append(ZabbixInterfaceRecord(
                interface_id=ifid, ip=ip, dns=dns, main=main, type=itype, port=port
            ))

        groups = [str(g.get("name")) for g in d.get("groups", []) if g.get("name")]
        templates = [str(t.get("name")) for t in d.get("parentTemplates", []) if t.get("name")]
        inventory = d.get("inventory") or {}
        if not isinstance(inventory, dict):
            inventory = {}

        desc = str(d.get("description") or "")

        return ZabbixHostRecord(
            host_id=host_id,
            technical_host=tech_host,
            visible_name=visible_name,
            status=status,
            interfaces=interfaces,
            host_groups=groups,
            templates=templates,
            inventory=inventory,
            description=desc,
            raw_record=d,
        )
