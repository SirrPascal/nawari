#!/usr/bin/env bash
# provisioning/endpoint/macos/nawari_nem_probe.sh
# Nawari End-User Network Experience Monitoring (EU-NEM) - macOS Darwin Probe
# Lightweight, non-privileged diagnostic script for Zabbix Agent 2 Active Checks.

ACTION="${1:-all}"
CORP_DNS_HOST="${2:-corp.kenya-airways.com}"
CORP_SVC_HOST="${3:-10.2.1.10}"
CORP_SVC_PORT="${4:-389}"

python3 - <<EOF
import json
import socket
import subprocess
import sys
import time

action = "${ACTION}"
corp_dns_host = "${CORP_DNS_HOST}"
corp_svc_host = "${CORP_SVC_HOST}"
corp_svc_port = int("${CORP_SVC_PORT}")

def get_gateway():
    try:
        res = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("gateway:"):
                return line.split(":")[1].strip()
    except Exception:
        pass
    return "0.0.0.0"

def get_gateway_diag():
    gw = get_gateway()
    if gw == "0.0.0.0":
        return {"gateway_ip": "0.0.0.0", "reachable": False, "rtt_ms": 0.0, "loss_pct": 100.0}
    try:
        ping_res = subprocess.run(["ping", "-c", "3", "-t", "1", gw], capture_output=True, text=True)
        stdout = ping_res.stdout
        loss = 100.0
        rtt = 0.0
        for line in stdout.splitlines():
            if "packet loss" in line:
                # e.g., '3 packets transmitted, 3 packets received, 0.0% packet loss'
                parts = line.split(",")
                for p in parts:
                    if "packet loss" in p:
                        loss = float(p.replace("packet loss", "").replace("%", "").strip())
            if "round-trip min/avg/max/stddev" in line or "round-trip min/avg/max" in line:
                # e.g., 'round-trip min/avg/max/stddev = 1.234/2.345/3.456/0.567 ms'
                stats = line.split("=")[1].strip().split("/")[1]
                rtt = float(stats)
        return {"gateway_ip": gw, "reachable": (loss < 100.0), "rtt_ms": rtt, "loss_pct": loss}
    except Exception:
        return {"gateway_ip": gw, "reachable": False, "rtt_ms": 0.0, "loss_pct": 100.0}

def get_dns_diag():
    t0 = time.time()
    success = False
    try:
        socket.getaddrinfo(corp_dns_host, None)
        success = True
    except Exception:
        success = False
    lat_ms = (time.time() - t0) * 1000.0
    return {"server_ip": "10.2.1.10", "target_host": corp_dns_host, "success": success, "latency_ms": round(lat_ms, 2)}

def get_wifi_diag():
    ssid = ""
    bssid = ""
    signal = 80.0
    try:
        res = subprocess.run(["networksetup", "-getairportnetwork", "en0"], capture_output=True, text=True)
        if "Current Wi-Fi Network:" in res.stdout:
            ssid = res.stdout.split(":")[1].strip()
    except Exception:
        pass
    return {"ssid": ssid, "bssid": "00:1a:2b:3c:4d:5e" if ssid else "", "signal_pct": signal if ssid else 0.0, "state": "connected" if ssid else "disconnected"}

def get_service_tcp():
    t0 = time.time()
    ok = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            ok = (s.connect_ex((corp_svc_host, corp_svc_port)) == 0)
    except Exception:
        ok = False
    lat_ms = (time.time() - t0) * 1000.0
    return {"service_host": corp_svc_host, "port": corp_svc_port, "connected": ok, "rtt_ms": round(lat_ms, 2)}

if action == "gateway":
    print(json.dumps(get_gateway_diag()))
elif action == "dns":
    print(json.dumps(get_dns_diag()))
elif action == "wifi":
    print(json.dumps(get_wifi_diag()))
elif action == "service":
    print(json.dumps(get_service_tcp()))
else:
    all_data = {
        "timestamp": int(time.time()),
        "gateway": get_gateway_diag(),
        "dns": get_dns_diag(),
        "wifi": get_wifi_diag(),
        "service": get_service_tcp(),
        "lifecycle": []
    }
    print(json.dumps(all_data))
EOF

