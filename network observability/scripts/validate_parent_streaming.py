import argparse
import configparser
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_LAB = ROOT / "server" / "local-lab"
RUNTIME = LOCAL_LAB / "runtime"


def validate_static_configuration():
    errors = []
    warnings = []

    parent_stream = RUNTIME / "stream.conf"
    if not parent_stream.exists():
        errors.append(f"Missing Parent stream.conf at {parent_stream}")
    else:
        cfg = configparser.ConfigParser()
        cfg.read(parent_stream)
        sections = cfg.sections()
        if not sections:
            errors.append("Parent stream.conf has no API key sections")
        else:
            api_key = sections[0]
            if cfg.get(api_key, "enabled", fallback="") != "yes":
                errors.append(f"Parent stream section [{api_key}] is not enabled")
            allow_from = cfg.get(api_key, "allow from", fallback="")
            if allow_from == "127.0.0.1":
                warnings.append(
                    "Parent stream.conf restricts 'allow from = 127.0.0.1'. "
                    "In Docker Desktop for Mac, bridge connections arrive from 172.25.*. "
                    "Parent will reject container connections unless allow from includes 172.25.*."
                )

    child_stream = RUNTIME / "test-child-stream.conf"
    if not child_stream.exists():
        errors.append(f"Missing Test Child stream.conf at {child_stream}")
    else:
        cfg = configparser.ConfigParser()
        cfg.read(child_stream)
        if "stream" not in cfg:
            errors.append("Child stream.conf missing [stream] section")
        else:
            sec = cfg["stream"]
            if sec.get("enabled") != "yes":
                errors.append("Child stream is not enabled")
            if sec.get("ssl skip certificate verification") != "no":
                errors.append("Child must enforce TLS certificate verification (ssl skip certificate verification = no)")
            dest = sec.get("destination", "")
            if ":SSL" not in dest:
                errors.append(f"Child destination must enforce :SSL encryption, got: {dest}")

    ca_cert = RUNTIME / "ca-cert.pem"
    server_cert = RUNTIME / "server-cert.pem"
    if not ca_cert.exists():
        errors.append(f"Missing CA certificate at {ca_cert}")
    if not server_cert.exists():
        errors.append(f"Missing Server certificate at {server_cert}")

    compose_file = LOCAL_LAB / "compose.test-child.yaml"
    if not compose_file.exists():
        errors.append(f"Missing compose.test-child.yaml at {compose_file}")
    else:
        text = compose_file.read_text()
        if "container_name: nawari-test-child" not in text:
            errors.append("compose.test-child.yaml must specify explicit container_name: nawari-test-child")
        if 'profiles: ["test-child"]' not in text:
            errors.append('compose.test-child.yaml must specify profiles: ["test-child"] for opt-in execution')
        if "no-new-privileges:true" not in text:
            warnings.append("Security hardening: recommend adding no-new-privileges:true to compose.test-child.yaml")
        if "/var/run/docker.sock" in text:
            errors.append("Security violation: Test Child must not mount docker.sock")

    alloy_candidate = LOCAL_LAB / "config.parent-scrape.alloy"
    if not alloy_candidate.exists():
        errors.append(f"Missing config.parent-scrape.alloy at {alloy_candidate}")
    else:
        alloy_text = alloy_candidate.read_text()
        if "prometheus_all_hosts" not in alloy_text:
            errors.append("Alloy parent scrape missing format=prometheus_all_hosts")
        if "honor_labels" not in alloy_text:
            errors.append("Alloy parent scrape missing honor_labels = true")

    return errors, warnings


def probe_parent_status(url="http://127.0.0.1:19998"):
    report = {
        "parent_url": url,
        "reachable": False,
        "mirrored_hosts": [],
        "mirrored_count": 0,
        "test_child_connected": False,
    }
    try:
        req = urllib.request.Request(f"{url}/api/v1/info")
        with urllib.request.urlopen(req, timeout=3) as resp:
            report["reachable"] = True
            data = json.loads(resp.read().decode())
            report["version"] = data.get("version")
            report["hosts_available"] = data.get("hosts-available")
            hosts = data.get("mirrored_hosts_status", [])
            report["mirrored_hosts"] = [
                {
                    "hostname": h.get("hostname"),
                    "guid": h.get("guid"),
                    "hops": h.get("hops"),
                    "reachable": h.get("reachable"),
                }
                for h in hosts
            ]
            report["mirrored_count"] = len(hosts)
            for h in hosts:
                if h.get("hostname") == "nawari-test-child" and h.get("reachable"):
                    report["test_child_connected"] = True
    except Exception as e:
        report["error"] = str(e)
    return report


def probe_parent_exposition(url="http://127.0.0.1:19998", target_instance="nawari-test-child"):
    report = {
        "endpoint": f"{url}/api/v1/allmetrics?format=prometheus_all_hosts&source=as-collected",
        "exposed": False,
        "matched_lines": 0,
        "sample_metric": None
    }
    try:
        req = urllib.request.Request(report["endpoint"])
        with urllib.request.urlopen(req, timeout=5) as resp:
            lines = resp.read().decode(errors="replace").splitlines()
            target_str = f'instance="{target_instance}"'
            matches = [l for l in lines if target_str in l]
            report["matched_lines"] = len(matches)
            if matches:
                report["exposed"] = True
                report["sample_metric"] = matches[0]
    except Exception as e:
        report["error"] = str(e)
    return report


def probe_mimir_child_metrics(mimir_url="http://127.0.0.1:19009", instance="nawari-test-child"):
    report = {
        "mimir_url": mimir_url,
        "target_instance": instance,
        "found_series": 0,
        "sample_metric": None,
    }
    try:
        expr = f'up{{instance="{instance}"}}'
        url = f"{mimir_url}/prometheus/api/v1/query?query={urllib.parse.quote(expr)}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("data", {}).get("result", [])
            report["found_series"] = len(results)
            if results:
                report["sample_metric"] = results[0]
    except Exception as e:
        report["error"] = str(e)
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate Netdata Parent streaming readiness.")
    parser.add_argument("--mode", choices=["static", "live", "e2e"], default="static",
                        help="Execution mode (default: static)")
    parser.add_argument("--require-child", action="store_true",
                        help="Enforce non-zero exit if test child is not streaming and in Mimir")
    args = parser.parse_args()

    print("=== 1. Validating Static Configuration ===")
    errors, warnings = validate_static_configuration()
    if errors:
        print("Static validation FAILED:")
        for err in errors:
            print(f"  [ERROR] {err}")
    else:
        print("Static validation PASSED: Configuration, TLS security, and manifests are valid.")

    if warnings:
        print("Configuration Warnings:")
        for warn in warnings:
            print(f"  [WARN]  {warn}")

    if args.mode in ("live", "e2e"):
        print("")
        print("=== 2. Probing Running Parent API ===")
        parent_status = probe_parent_status()
        print(f"Parent Reachable: {parent_status.get('reachable')}, Mirrored Hosts: {parent_status.get('mirrored_count')}")
        print(f"Test Child Connected: {parent_status.get('test_child_connected')}")

        print("")
        print("=== 3. Probing Parent Multi-Host Prometheus Exposition ===")
        expo_status = probe_parent_exposition()
        print(f"Test Child Metrics Exposed: {expo_status.get('exposed')} (Matched Lines: {expo_status.get('matched_lines')})")

        print("")
        print("=== 4. Probing Mimir for Ingested Test Child Series ===")
        mimir_status = probe_mimir_child_metrics()
        print(f"Mimir Test Child Series: {mimir_status.get('found_series')}")

        if args.require_child:
            if not parent_status.get("test_child_connected"):
                print("")
                print("[CRITICAL FAILURE] Required test child is not connected to Parent!")
                sys.exit(2)
            if not expo_status.get("exposed"):
                print("")
                print("[CRITICAL FAILURE] Required test child metrics not exposed by Parent!")
                sys.exit(3)
            if mimir_status.get("found_series") == 0:
                print("")
                print("[CRITICAL FAILURE] Required test child series not found in Mimir!")
                sys.exit(4)

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
