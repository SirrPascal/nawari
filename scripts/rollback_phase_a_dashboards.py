#!/usr/bin/env python3
"""
Nawari Phase A Dashboard Rollback Script.
Restores all Grafana dashboards from the pre-remediation baseline backup.
"""

import json
import os
import urllib.request
import ssl
import base64
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = REPO_ROOT / "backups/grafana_live_baseline"
if not BASELINE_DIR.exists():
    BASELINE_DIR = REPO_ROOT / "communication-observability/docker/grafana/dashboards/baseline"

GF_URL = os.environ.get("GRAFANA_URL", "https://10.2.1.58:18443/grafana/api")
AUTH = os.environ.get("GRAFANA_AUTH", "admin:admin")
ctx = ssl._create_unverified_context()

def gf_post(path, data):
    req = urllib.request.Request(f"{GF_URL}{path}", method="POST")
    b64 = base64.b64encode(AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {b64}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=json.dumps(data).encode(), context=ctx, timeout=20) as resp:
        return resp.status, json.loads(resp.read().decode())

def rollback():
    manifest_path = BASELINE_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found in {BASELINE_DIR}")
        
    with open(manifest_path) as f:
        manifest = json.load(f)
        
    print(f"Loaded baseline manifest with {len(manifest)} dashboards from {BASELINE_DIR}")
    
    for item in manifest:
        filename = item["filename"]
        filepath = BASELINE_DIR / filename
        with open(filepath) as f:
            raw = json.load(f)
            
        dash = raw.get("dashboard", {})
        folder_uid = raw.get("meta", {}).get("folderUid", item.get("folder_uid", ""))
        
        st, res = gf_post("/dashboards/db", {
            "dashboard": dash,
            "overwrite": True,
            "folderUid": folder_uid
        })
        print(f"Rollback [{item['uid']}] '{item['title']}': HTTP {st} -> {res.get('status')}")
        
    print("\nRollback complete. All dashboards restored to pre-remediation baseline.")

if __name__ == "__main__":
    rollback()
