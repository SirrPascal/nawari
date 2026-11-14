#!/usr/bin/env python3
"""
scripts/provision_eunem_pilot.py

Provisions the Nawari End-User Network Experience Monitoring (EU-NEM)
template, host groups, and pilot endpoints to the running Zabbix API.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings

TEMPLATE_FILE = PROJECT_ROOT / "provisioning/zabbix/templates/template_nawari_end_user_network_experience.yaml"

HOST_GROUPS = [
    "Nawari / Endpoints / Pilot",
    "Nawari / Endpoints / Corporate",
    "Nawari / Endpoints / Outstations",
]

PILOT_HOSTS = [
    {
        "host": "KQ-LT-WIN-01",
        "name": "KQ-LT-WIN-01 (Windows 11 Pilot Laptop)",
        "ip": "127.0.0.1",
        "dns": "kq-lt-win-01.corp.kenya-airways.com",
        "tags": [
            {"tag": "monitoring_scope", "value": "end_user"},
            {"tag": "endpoint_type", "value": "laptop"},
            {"tag": "os", "value": "windows11"},
            {"tag": "connection_type", "value": "wifi"},
            {"tag": "site", "value": "pride_centre"},
            {"tag": "environment", "value": "pilot"},
            {"tag": "telemetry_source", "value": "zabbix_agent2"},
        ],
    },
    {
        "host": "KQ-LT-MAC-01",
        "name": "KQ-LT-MAC-01 (macOS Darwin Pilot Laptop)",
        "ip": "127.0.0.1",
        "dns": "kq-lt-mac-01.corp.kenya-airways.com",
        "tags": [
            {"tag": "monitoring_scope", "value": "end_user"},
            {"tag": "endpoint_type", "value": "laptop"},
            {"tag": "os", "value": "darwin"},
            {"tag": "connection_type", "value": "wifi"},
            {"tag": "site", "value": "pride_centre"},
            {"tag": "environment", "value": "pilot"},
            {"tag": "telemetry_source", "value": "zabbix_agent2"},
        ],
    },
]


def ensure_host_groups(client: ZabbixClient) -> dict[str, str]:
    """Ensure host groups exist and return map of name -> groupid."""
    existing = client.call("hostgroup.get", {"output": ["groupid", "name"]})
    group_map = {g["name"]: g["groupid"] for g in existing}

    for name in HOST_GROUPS:
        if name not in group_map:
            res = client.call("hostgroup.create", {"name": name})
            group_map[name] = res["groupids"][0]
            print(f"[GROUP] Created host group: {name} (ID: {group_map[name]})")
        else:
            print(f"[GROUP] Exists: {name} (ID: {group_map[name]})")

    return group_map


def import_template(client: ZabbixClient) -> str:
    """Import the EU-NEM YAML template into Zabbix."""
    raw_yaml = TEMPLATE_FILE.read_text(encoding="utf-8")
    rules = {
        "template_groups": {"createMissing": True, "updateExisting": True},
        "templates": {"createMissing": True, "updateExisting": True},
        "items": {"createMissing": True, "updateExisting": True},
        "triggers": {"createMissing": True, "updateExisting": True},
        "valueMaps": {"createMissing": True, "updateExisting": True},
    }

    client.call("configuration.import", {
        "format": "yaml",
        "source": raw_yaml,
        "rules": rules,
    })
    print("[TEMPLATE] Imported Template_Nawari_End_User_Network_Experience successfully.")

    # Retrieve template ID
    tmpls = client.call("template.get", {
        "filter": {"host": ["Template_Nawari_End_User_Network_Experience"]},
        "output": ["templateid", "host", "name"],
    })
    if not tmpls:
        raise RuntimeError("Failed to find imported template in Zabbix")
    tmpl_id = tmpls[0]["templateid"]
    print(f"[TEMPLATE] Resolved template ID: {tmpl_id}")
    return tmpl_id


def provision_pilot_hosts(client: ZabbixClient, template_id: str, group_id: str) -> None:
    """Provision the 2 pilot laptop hosts."""
    existing_hosts = client.call("host.get", {
        "filter": {"host": [h["host"] for h in PILOT_HOSTS]},
        "output": ["hostid", "host"],
    })
    existing_map = {h["host"]: h["hostid"] for h in existing_hosts}

    for h_spec in PILOT_HOSTS:
        host_key = h_spec["host"]
        if host_key in existing_map:
            host_id = existing_map[host_key]
            client.call("host.update", {
                "hostid": host_id,
                "name": h_spec["name"],
                "templates": [{"templateid": template_id}],
                "groups": [{"groupid": group_id}],
                "tags": h_spec["tags"],
                "status": 0,
            })
            print(f"[HOST] Updated pilot host: {h_spec['name']} (ID: {host_id})")
        else:
            res = client.call("host.create", {
                "host": host_key,
                "name": h_spec["name"],
                "interfaces": [
                    {
                        "type": 1,  # Agent interface
                        "main": 1,
                        "useip": 1,
                        "ip": h_spec["ip"],
                        "dns": h_spec["dns"],
                        "port": "10050",
                    }
                ],
                "groups": [{"groupid": group_id}],
                "templates": [{"templateid": template_id}],
                "tags": h_spec["tags"],
                "status": 0,  # Monitored
            })
            print(f"[HOST] Created pilot host: {h_spec['name']} (ID: {res['hostids'][0]})")


def main() -> None:
    print("======================================================================")
    print("NAWARI EU-NEM PILOT PROVISIONING ENGINE")
    print("Target: Zabbix 7.4.16 API on mon-grafana01 (127.0.0.1:8088)")
    print("Scope: Host groups, Agent 2 Active Checks Template, Pilot Endpoints")
    print("======================================================================")

    settings = ZabbixSettings()
    client = ZabbixClient(settings)
    client.connect()
    print("[AUTH] Connected and authenticated to Zabbix API.")

    group_map = ensure_host_groups(client)
    pilot_group_id = group_map["Nawari / Endpoints / Pilot"]

    template_id = import_template(client)

    provision_pilot_hosts(client, template_id, pilot_group_id)

    # Verify items and triggers linked to pilot hosts
    hosts = client.call("host.get", {
        "filter": {"host": [h["host"] for h in PILOT_HOSTS]},
        "selectItems": ["itemid", "name", "key_", "type"],
        "selectTriggers": ["triggerid", "description", "priority"],
    })

    print("\n--- PROVISIONING VERIFICATION AUDIT ---")
    for h in hosts:
        print(f"Host: {h['name']} ({h['host']})")
        print(f"  Items linked:    {len(h.get('items', []))}")
        print(f"  Triggers linked: {len(h.get('triggers', []))}")
        for it in h.get("items", [])[:4]:
            print(f"    - [{it['key_']}] {it['name']} (Type: {it['type']})")

    print("\n[SUCCESS] EU-NEM pilot provisioning completed successfully.")


if __name__ == "__main__":
    main()

