#!/usr/bin/env python3
"""Export Zabbix host inventory via JSON‑RPC API.

The script is **read‑only** – it only queries the Zabbix server and writes two
files under the same directory:
  * ``export_host_inventory.json`` – full JSON payload
  * ``export_host_inventory.csv``  – flatten‑ed table suitable for diffing

It expects the following environment variables to be set:
  * ``ZBX_API_TOKEN`` – Zabbix API token with at least ``host.read`` permission.
  * ``ZBX_API_URL``   – JSON‑RPC endpoint, default ``http://127.0.0.1:8080/api_jsonrpc.php``.

No credentials are printed or logged.
"""

import os
import sys
import json
import csv
import urllib.request
import urllib.error
from typing import Any, Dict, List

API_URL = os.getenv(
    "ZBX_API_URL", "http://127.0.0.1:8080/api_jsonrpc.php"
)  # type: str
API_TOKEN = os.getenv("ZBX_API_TOKEN")  # type: str | None

if not API_TOKEN:
    sys.stderr.write("Error: ZBX_API_TOKEN environment variable is missing\n")
    sys.exit(1)

# Helper to issue a JSON‑RPC request
# Zabbix 6.4+ requires the API token in the Authorization header, not the body.
def json_rpc(method: str, params: Dict[str, Any]) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP error {e.code}: {e.reason}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Connection error: {e.reason}\n")
        sys.exit(1)
    if "error" in resp_data:
        err = resp_data["error"]
        sys.stderr.write(f"Zabbix API error {err.get('code')}: {err.get('data')}\n")
        sys.exit(1)
    return resp_data.get("result")

# 1️⃣ Retrieve all hosts with the required details
hosts = json_rpc(
    "host.get",
    {
        "output": ["hostid", "host", "name", "status"],
        "selectInterfaces": ["interfaceid", "type", "main", "useip", "ip", "dns", "available"],
        "selectGroups": ["name"],
        "selectParentTemplates": ["templateid", "name"],
    },
)

if not isinstance(hosts, list):
    sys.stderr.write("Unexpected response from Zabbix API – expected a list of hosts\n")
    sys.exit(1)

# 2️⃣ Normalise each host into a flat dict for CSV output
rows: List[Dict[str, Any]] = []
for h in hosts:
    host_id = h.get("hostid")
    technical_name = h.get("host")
    visible_name = h.get("name")
    status = "enabled" if h.get("status") == "0" else "disabled"
    groups = [g.get("name") for g in h.get("groups", [])]
    templates = [t.get("name") for t in h.get("parentTemplates", [])]
    interfaces = h.get("interfaces", [])

    # If a host has multiple interfaces we emit a separate row per interface.
    # The primary interface ("main": "1") is flagged; otherwise the first one.
    if not interfaces:
        rows.append(
            {
                "host_id": host_id,
                "technical_name": technical_name,
                "visible_name": visible_name,
                "status": status,
                "group_names": ",".join(groups),
                "template_names": ",".join(templates),
                "interface_id": "",
                "interface_type": "",
                "interface_ip": "",
                "interface_dns": "",
                "interface_available": "",
                "interface_main": "",
            }
        )
        continue

    for iface in interfaces:
        iface_id = iface.get("interfaceid")
        iface_type = iface.get("type")  # 1=agent, 2=SNMP, 3=IPMI, 4=JMX
        iface_ip = iface.get("ip") if iface.get("useip") == "1" else ""
        iface_dns = iface.get("dns") if iface.get("useip") == "0" else ""
        iface_available = iface.get("available")  # 0=unknown, 1=available, 2=unavailable
        iface_main = "yes" if iface.get("main") == "1" else "no"
        rows.append(
            {
                "host_id": host_id,
                "technical_name": technical_name,
                "visible_name": visible_name,
                "status": status,
                "group_names": ",".join(groups),
                "template_names": ",".join(templates),
                "interface_id": iface_id,
                "interface_type": iface_type,
                "interface_ip": iface_ip,
                "interface_dns": iface_dns,
                "interface_available": iface_available,
                "interface_main": iface_main,
            }
        )

# 3️⃣ Write JSON dump (full API payload) – useful for debugging
json_path = os.path.join(os.path.dirname(__file__), "export_host_inventory.json")
with open(json_path, "w", encoding="utf-8") as jf:
    json.dump(hosts, jf, indent=2)

# 4️⃣ Write CSV – one row per interface (or a single row when none)
csv_path = os.path.join(os.path.dirname(__file__), "export_host_inventory.csv")
fieldnames = [
    "host_id",
    "technical_name",
    "visible_name",
    "status",
    "group_names",
    "template_names",
    "interface_id",
    "interface_type",
    "interface_ip",
    "interface_dns",
    "interface_available",
    "interface_main",
]
with open(csv_path, "w", newline="", encoding="utf-8") as cf:
    writer = csv.DictWriter(cf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

print(f"Export completed: {len(rows)} rows written to CSV and JSON files.")

