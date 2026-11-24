#!/usr/bin/env python3
import json
import os
import urllib.request
import ssl
import base64
import copy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = REPO_ROOT / "backups/grafana_live_baseline"
if not BASELINE_DIR.exists():
    BASELINE_DIR = REPO_ROOT / "communication-observability/docker/grafana/dashboards/baseline"
REMEDIATED_DIR = REPO_ROOT / "scripts/remediated_dashboards"
REMEDIATED_DIR.mkdir(parents=True, exist_ok=True)

GF_URL = os.environ.get("GRAFANA_URL", "https://10.2.1.58:18443/grafana/api")
AUTH = os.environ.get("GRAFANA_AUTH", "admin:admin")
ctx = ssl._create_unverified_context()

def gf_post(path, data):
    req = urllib.request.Request(f"{GF_URL}{path}", method="POST")
    b64 = base64.b64encode(AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {b64}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=json.dumps(data).encode(), context=ctx, timeout=25) as resp:
        return resp.status, json.loads(resp.read().decode())

def gf_get(path):
    req = urllib.request.Request(f"{GF_URL}{path}")
    b64 = base64.b64encode(AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {b64}")
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode())

remediated_manifest = []

# -------------------------------------------------------------
# 1. nawari-communication-manager
# -------------------------------------------------------------
print("\n[1/8] Remediating nawari-communication-manager...")
with open(f"{BASELINE_DIR}/nawari-communication-manager.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-comm-obs")

for p in dash.get("panels", []):
    p_id = p.get("id")
    # Panel 2: Reachability
    if p_id == 2:
        p["title"] = "CM Processor Management Reachability (ICMP) [REAL — ZABBIX]"
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
            "group": {"filter": "/.*/"},
            "host": {"filter": "Avaya Communication Manager Duplex (HQ-CORE)"},
            "item": {"filter": "ICMP ping"},
            "mode": 0
        }]
    else:
        for t in p.get("targets", []):
            if t.get("host", {}).get("name") == "avaya-cm-01" or t.get("host", {}).get("filter") == "avaya-cm-01":
                t["host"] = {"filter": "Avaya Communication Manager Duplex (HQ-CORE)"}

# Save and deploy
with open(f"{REMEDIATED_DIR}/nawari-communication-manager.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 2. nawari-session-manager
# -------------------------------------------------------------
print("\n[2/8] Remediating nawari-session-manager...")
with open(f"{BASELINE_DIR}/nawari-session-manager.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-comm-obs")

for p in dash.get("panels", []):
    for t in p.get("targets", []):
        if t.get("host", {}).get("name") == "avaya-sm-01" or t.get("host", {}).get("filter") == "avaya-sm-01":
            t["host"] = {"filter": "Avaya Session Manager Primary (HQ-CORE)"}
            
# Ensure there is a reachability stat panel in Session Manager
# Panel 4 is Uptime; let's configure Panel 4 to show Uptime if available, and add reachability target
for p in dash.get("panels", []):
    if p.get("id") == 4:
        p["title"] = "ASM Management Reachability & Uptime [REAL — ZABBIX]"
        p["targets"] = [{
            "refId": "AVAIL",
            "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
            "group": {"filter": "/.*/"},
            "host": {"filter": "Avaya Session Manager Primary (HQ-CORE)"},
            "item": {"filter": "ICMP ping"},
            "mode": 0
        }]

with open(f"{REMEDIATED_DIR}/nawari-session-manager.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 3. nawari-sbce-health
# -------------------------------------------------------------
print("\n[3/8] Remediating nawari-sbce-health...")
with open(f"{BASELINE_DIR}/nawari-sbce-health.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-comm-obs")

# Update template variable sbce_host
templating = dash.get("templating", {}).get("list", [])
for v in templating:
    if v.get("name") == "sbce_host":
        v["current"] = {
            "selected": True,
            "text": "Avaya SBCE Primary (HQ-DMZ)",
            "value": "Avaya SBCE Primary (HQ-DMZ)"
        }
        for opt in v.get("options", []):
            if opt.get("value") == "Avaya SBCE Primary (HQ-DMZ)":
                opt["selected"] = True
            else:
                opt["selected"] = False

# Panel 2: SNMP Collection Status -> Update to Management Reachability (ICMP)
for p in dash.get("panels", []):
    p_id = p.get("id")
    if p_id == 2:
        p["title"] = "SBCE Management Reachability (ICMP) [REAL — ZABBIX]"
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
            "group": {"filter": "/.*/"},
            "host": {"filter": "$sbce_host"},
            "item": {"filter": "ICMP ping"},
            "mode": 0
        }]

with open(f"{REMEDIATED_DIR}/nawari-sbce-health.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 4. nawari-g450-gateway
# -------------------------------------------------------------
print("\n[4/8] Remediating nawari-g450-gateway...")
with open(f"{BASELINE_DIR}/nawari-g450-gateway.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-comm-obs")

for p in dash.get("panels", []):
    p_id = p.get("id")
    if p_id == 2:
        p["title"] = "G450 Management Reachability (ICMP) [REAL — ZABBIX]"
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "alexanderzobnin-zabbix-datasource", "uid": "PA67C5EADE9207728"},
            "group": {"filter": "/.*/"},
            "host": {"filter": "Avaya G450 Media Gateway (HQ-GATEWAY)"},
            "item": {"filter": "ICMP ping"},
            "mode": 0
        }]
    else:
        for t in p.get("targets", []):
            if t.get("host", {}).get("name") == "avaya-g450-01" or t.get("host", {}).get("filter") == "avaya-g450-01":
                t["host"] = {"filter": "Avaya G450 Media Gateway (HQ-GATEWAY)"}

with open(f"{REMEDIATED_DIR}/nawari-g450-gateway.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 5. nawari-comm-overview
# -------------------------------------------------------------
print("\n[5/8] Remediating nawari-comm-overview...")
with open(f"{BASELINE_DIR}/nawari-comm-overview.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-comm-obs")

for p in dash.get("panels", []):
    for t in p.get("targets", []):
        h = t.get("host", {})
        h_str = h.get("name", h.get("filter", ""))
        if "avaya-cm-01" in h_str:
            t["host"] = {"filter": "Avaya Communication Manager Duplex (HQ-CORE)"}
        elif "avaya-sbce-01" in h_str:
            t["host"] = {"filter": "Avaya SBCE Primary (HQ-DMZ)"}
        elif "avaya-sm-01" in h_str:
            t["host"] = {"filter": "Avaya Session Manager Primary (HQ-CORE)"}

with open(f"{REMEDIATED_DIR}/nawari-comm-overview.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 6. nawari-sw-cisco-logs
# -------------------------------------------------------------
print("\n[6/8] Remediating nawari-sw-cisco-logs...")
with open(f"{BASELINE_DIR}/nawari-sw-cisco-logs.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-network-obs")

for p in dash.get("panels", []):
    p_id = p.get("id")
    # Panel 2: Log Rate by Facility
    if p_id == 2:
        p["title"] = "Cisco Log Rate by Facility (logs/sec)"
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "loki", "uid": "P8E80F9AEF21F6940"},
            "expr": 'sum by (cisco_facility) (rate({source="solarwinds", environment="production"}[$__interval]))',
            "queryType": "range"
        }]
        # Set min interval to 1m
        p["interval"] = "1m"
    # Panel 3: Severity Breakdown (Pie Chart) -> Instant query
    elif p_id == 3:
        p["title"] = "Events by Severity Level (Selected Time Range)"
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "loki", "uid": "P8E80F9AEF21F6940"},
            "expr": 'sum by (cisco_severity) (count_over_time({source="solarwinds", environment="production"}[$__range]))',
            "instant": True,
            "queryType": "instant"
        }]
    elif p_id == 5:
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "loki", "uid": "P8E80F9AEF21F6940"},
            "expr": '{source="solarwinds", environment="production"}',
            "queryType": "range"
        }]

with open(f"{REMEDIATED_DIR}/nawari-sw-cisco-logs.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 7. nawari-net-coverage
# -------------------------------------------------------------
print("\n[7/8] Remediating nawari-net-coverage...")
with open(f"{BASELINE_DIR}/nawari-net-coverage.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-network-obs")

for p in dash.get("panels", []):
    p_id = p.get("id")
    # Panel 3: Syslog Association Coverage (Stat)
    if p_id == 3:
        p["targets"] = [{
            "refId": "A",
            "datasource": {"type": "loki", "uid": "P8E80F9AEF21F6940"},
            "expr": 'sum(count_over_time({source="solarwinds", environment="production"}[$__range]))',
            "instant": True,
            "queryType": "instant"
        }]

with open(f"{REMEDIATED_DIR}/nawari-net-coverage.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

# -------------------------------------------------------------
# 8. nawari-net-avail
# -------------------------------------------------------------
print("\n[8/8] Remediating nawari-net-avail...")
with open(f"{BASELINE_DIR}/nawari-net-avail.json") as f:
    raw = json.load(f)
dash = raw["dashboard"]
folder_uid = raw.get("meta", {}).get("folderUid", "nawari-network-obs")

for p in dash.get("panels", []):
    p_id = p.get("id")
    # Panel 2: ICMP Packet Loss Percentage (%)
    if p_id == 2:
        field_cfg = p.get("fieldConfig", {}).get("defaults", {})
        if field_cfg.get("unit") == "percentunit":
            field_cfg["unit"] = "percent"
            field_cfg["min"] = 0
            field_cfg["max"] = 100

with open(f"{REMEDIATED_DIR}/nawari-net-avail.json", "w") as f:
    json.dump(dash, f, indent=2)
st, res = gf_post("/dashboards/db", {"dashboard": dash, "overwrite": True, "folderUid": folder_uid})
print(f"Deploy status: {st} -> {res.get('status')}")

print("\nAll 8 target dashboards remediated and deployed successfully!")
