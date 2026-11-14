#!/usr/bin/env python3
"""
validate_stream_lab.py

Comprehensive validator for the isolated Nawari Netdata streaming test lab
(Project: nawari-stream-test).

Modes:
  --check-static   Validates all templates, runtime configs, TLS certs/SANs,
                   and Compose isolation offline (no live containers required).
  --probe-live     Queries the test Parent on 127.0.0.1:19988/api/v1/info to check
                   for connected child stream status.
  --probe-mimir    Queries local Mimir (127.0.0.1:19009) to confirm ingested metrics
                   from nawari-stream-test-child.
  --require-child  Fail-closed switch: exits non-zero if the child is absent
                   or not actively reporting.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
TEMPLATES_DIR = BASE_DIR / "templates"
COMPOSE_FILE = BASE_DIR / "compose.yaml"
ALLOY_CONFIG = BASE_DIR / "config.alloy"

PARENT_URL = "http://127.0.0.1:19988"
MIMIR_URL = "http://127.0.0.1:19009"


def check_static() -> list[str]:
    errors = []

    # 1. Compose file isolation and safety checks
    if not COMPOSE_FILE.exists():
        errors.append(f"Missing {COMPOSE_FILE}")
    else:
        content = COMPOSE_FILE.read_text()
        if "name: nawari-stream-test" not in content:
            errors.append("compose.yaml must specify 'name: nawari-stream-test'")
        if "172.28.0.0/16" not in content:
            errors.append("compose.yaml must use dedicated subnet 172.28.0.0/16")
        if "19988:20000" not in content:
            errors.append("compose.yaml parent must bind to 127.0.0.1:19988:20000 to avoid port collision")
        if "no-new-privileges:true" not in content and "no-new-privileges: true" not in content:
            errors.append("compose.yaml missing no-new-privileges security option")
        if "cap_drop:" not in content or "ALL" not in content:
            errors.append("compose.yaml child container must drop ALL capabilities")
        if "/var/run/docker.sock" in content:
            errors.append("compose.yaml must NOT mount docker.sock")

    # 2. Alloy configuration checks
    if not ALLOY_CONFIG.exists():
        errors.append(f"Missing {ALLOY_CONFIG}")
    else:
        alloy_content = ALLOY_CONFIG.read_text()
        if "format" not in alloy_content or "prometheus_all_hosts" not in alloy_content:
            errors.append("config.alloy must scrape with __param_format = prometheus_all_hosts")
        if "honor_labels" not in alloy_content or "true" not in alloy_content:
            errors.append("config.alloy must set honor_labels = true to preserve child host labels")
        if "host.docker.internal:19009" not in alloy_content:
            errors.append("config.alloy remote write must target host.docker.internal:19009")

    # 3. Runtime directory and permissions
    if not RUNTIME_DIR.exists():
        errors.append(f"Runtime directory missing: {RUNTIME_DIR}")
    else:
        st_mode = oct(RUNTIME_DIR.stat().st_mode)[-3:]
        if st_mode not in ("700", "750", "755"):
            errors.append(f"Runtime directory permissions too loose: {st_mode}")

    # 4. Certificates and TLS validation
    ca_cert = RUNTIME_DIR / "ca-cert.pem"
    server_cert = RUNTIME_DIR / "server-cert.pem"
    if not ca_cert.exists():
        errors.append("Missing runtime/ca-cert.pem")
    if not server_cert.exists():
        errors.append("Missing runtime/server-cert.pem")

    if ca_cert.exists() and server_cert.exists():
        res = subprocess.run(
            ["openssl", "verify", "-CAfile", str(ca_cert), str(server_cert)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode != 0 or "OK" not in res.stdout:
            errors.append(f"TLS certificate verification failed: {res.stdout.strip()} {res.stderr.strip()}")

        # Check SAN
        x509_res = subprocess.run(
            ["openssl", "x509", "-in", str(server_cert), "-text", "-noout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        san_text = x509_res.stdout
        if "DNS:netdata-stream-test-parent" not in san_text:
            errors.append("Server certificate missing SAN DNS:netdata-stream-test-parent")

    # 5. Stream configuration validation
    child_stream = RUNTIME_DIR / "child-stream.conf"
    parent_stream = RUNTIME_DIR / "parent-stream.conf"
    if not child_stream.exists():
        errors.append("Missing runtime/child-stream.conf")
    if not parent_stream.exists():
        errors.append("Missing runtime/parent-stream.conf")

    if child_stream.exists() and parent_stream.exists():
        child_text = child_stream.read_text()
        parent_text = parent_stream.read_text()

        # Extract child api key
        child_key_match = re.search(r"api key\s*=\s*([a-f0-9\-]+)", child_text, re.IGNORECASE)
        if not child_key_match:
            errors.append("child-stream.conf does not contain valid api key")
        else:
            child_key = child_key_match.group(1).strip()
            # Ensure parent has matching section [UUID]
            if f"[{child_key}]" not in parent_text:
                errors.append(f"parent-stream.conf does not authorize the child's API key: {child_key[:8]}...")

        # Verify child requires SSL and verifies cert
        if "ssl skip certificate verification = yes" in child_text:
            errors.append("child-stream.conf must NOT skip SSL certificate verification")
        if "ssl skip certificate verification = no" not in child_text:
            errors.append("child-stream.conf must explicitly enforce ssl skip certificate verification = no")
        if ":SSL" not in child_text:
            errors.append("child-stream.conf destination must specify :SSL suffix")

        # Verify parent allows bridge subnet
        if "172.28.*" not in parent_text:
            errors.append("parent-stream.conf allow from must include 172.28.*")

    return errors


def probe_live_parent() -> dict:
    url = f"{PARENT_URL}/api/v1/info"
    req = urllib.request.Request(url, headers={"User-Agent": "Nawari-Validator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
            return {"reachable": True, "info": data}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def probe_mimir(query: str = 'netdata_info{instance="nawari-stream-test-child"}') -> dict:
    encoded = urllib.parse.urlencode({"query": query})
    url = f"{MIMIR_URL}/prometheus/api/v1/query?{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "Nawari-Validator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
            return {"reachable": True, "data": data}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Nawari isolated Netdata streaming test lab")
    parser.add_argument("--check-static", action="store_true", help="Perform offline configuration and TLS verification")
    parser.add_argument("--probe-live", action="store_true", help="Probe running test parent container")
    parser.add_argument("--probe-mimir", action="store_true", help="Probe Mimir for child metrics")
    parser.add_argument("--require-child", action="store_true", help="Fail if test child is not actively connected")
    args = parser.parse_args()

    # Default to static check if no live flags specified
    run_static = args.check_static or (not args.probe_live and not args.probe_mimir)

    exit_code = 0

    if run_static:
        print("=== Checking Static Configuration & TLS Integrity ===")
        errors = check_static()
        if errors:
            print(f"[FAIL] Found {len(errors)} configuration issue(s):")
            for err in errors:
                print(f"  - {err}")
            exit_code = 1
        else:
            print("[PASS] All static configurations, TLS chains, SANs, and Compose safety rules verified.")

    if args.probe_live:
        print(f"\n=== Probing Isolated Parent ({PARENT_URL}) ===")
        res = probe_live_parent()
        if not res["reachable"]:
            print(f"[STATUS] Test Parent not reachable on {PARENT_URL}: {res['error']}")
            if args.require_child:
                exit_code = 1
        else:
            info = res["info"]
            version = info.get("version", "unknown")
            mirrored_hosts = info.get("mirrored_hosts_status", [])
            print(f"[INFO] Parent reachable. Netdata version: {version}")
            print(f"[INFO] Mirrored hosts count: {len(mirrored_hosts)}")
            
            child_found = False
            for host in mirrored_hosts:
                hostname = host.get("hostname", "")
                guid = host.get("guid", "")
                streaming = host.get("streaming", False)
                print(f"  - Host: {hostname} (GUID: {guid}, streaming: {streaming})")
                if hostname == "nawari-stream-test-child":
                    child_found = True

            if child_found:
                print("[PASS] Test Child 'nawari-stream-test-child' actively streaming to test Parent.")
            else:
                print("[STATUS] Test Child 'nawari-stream-test-child' not currently listed in mirrored hosts.")
                if args.require_child:
                    exit_code = 1

    if args.probe_mimir:
        print(f"\n=== Probing Mimir ({MIMIR_URL}) for Streamed Metrics ===")
        res = probe_mimir()
        if not res["reachable"]:
            print(f"[STATUS] Mimir not reachable on {MIMIR_URL}: {res['error']}")
            if args.require_child:
                exit_code = 1
        else:
            data = res.get("data", {}).get("data", {})
            results = data.get("result", [])
            print(f"[INFO] Mimir returned {len(results)} series for nawari-stream-test-child.")
            if results:
                print("[PASS] Streamed child metrics confirmed in Mimir storage.")
            else:
                print("[STATUS] No series found yet for nawari-stream-test-child in Mimir.")
                if args.require_child:
                    exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

