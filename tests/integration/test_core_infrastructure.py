"""Integration acceptance tests for Nawari Phase 1 Core Docker Infrastructure.

Validates that all core monitoring containers (PostgreSQL 17, Zabbix Server 7.4,
Zabbix Web, Zabbix SNMP Traps, Grafana 11.6+ with alexanderzobnin-zabbix-app)
are deployed, healthy, interconnected, persistent, and within resource limits.
"""

import json
import os
import platform
import socket
import subprocess
import urllib.error
import urllib.request
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
COMPOSE_BASE = os.path.join(PROJECT_ROOT, "docker", "compose.yaml")
COMPOSE_DEV = os.path.join(PROJECT_ROOT, "docker", "compose.dev.yaml")

# Read credentials from .env
ENV_VARS = {}
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                ENV_VARS[k.strip()] = v.strip()

GRAFANA_ADMIN_USER = os.environ.get("GRAFANA_ADMIN_USER", ENV_VARS.get("GRAFANA_ADMIN_USER", "admin"))
GRAFANA_ADMIN_PASSWORD = os.environ.get("GRAFANA_ADMIN_PASSWORD", ENV_VARS.get("GRAFANA_ADMIN_PASSWORD", ""))
ZBX_API_USER = os.environ.get("ZBX_API_USER", ENV_VARS.get("ZBX_API_USER", "Admin"))
ZBX_API_PASSWORD = os.environ.get("ZBX_API_PASSWORD", ENV_VARS.get("ZBX_API_PASSWORD", ""))
ZBX_API_TOKEN = os.environ.get("ZBX_API_TOKEN", ENV_VARS.get("ZBX_API_TOKEN", ""))

CONTAINERS = [
    "nawari-postgres",
    "nawari-snmptraps",
    "nawari-zabbix-server",
    "nawari-zabbix-web",
    "nawari-grafana",
]


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)


def test_01_docker_compose_config_validity():
    """Verify that docker compose config parses and validates without errors."""
    res = run_cmd([
        "docker", "compose",
        "--env-file", ENV_FILE,
        "-f", COMPOSE_BASE,
        "-f", COMPOSE_DEV,
        "config"
    ])
    assert res.returncode == 0, f"docker compose config failed: {res.stderr}"
    assert "nawari-zabbix-server" in res.stdout
    assert "nawari-grafana" in res.stdout


def test_02_containers_running_and_healthy():
    """Verify that all 5 Nawari containers are running and healthy."""
    for name in CONTAINERS:
        res = run_cmd(["docker", "inspect", name])
        assert res.returncode == 0, f"Container {name} is not found: {res.stderr}"
        data = json.loads(res.stdout)[0]
        state = data.get("State", {})
        assert state.get("Running") is True, f"Container {name} is not running (status: {state.get('Status')})"
        
        # Check health if healthcheck configured
        health = state.get("Health", {})
        if health:
            status = health.get("Status")
            assert status == "healthy", f"Container {name} healthcheck failed with status: {status}"


def test_03_image_architecture_matches_host():
    """Verify that container image architecture matches host machine architecture."""
    expected_arch = "arm64" if platform.machine() in ["arm64", "aarch64"] else "amd64"
    for name in CONTAINERS:
        res = run_cmd(["docker", "inspect", "--format", "{{.Image}}", name])
        assert res.returncode == 0
        img_id = res.stdout.strip()
        arch_res = run_cmd(["docker", "image", "inspect", "--format", "{{.Architecture}}", img_id])
        assert arch_res.returncode == 0
        arch = arch_res.stdout.strip()
        assert arch == expected_arch, f"Image {img_id} for {name} has arch '{arch}', expected '{expected_arch}'"


def test_04_postgresql_connection_and_schema():
    """Verify that PostgreSQL is healthy, accepting connections, and has Zabbix tables."""
    res = run_cmd([
        "docker", "exec", "nawari-postgres",
        "psql", "-U", "zabbix", "-d", "zabbix", "-t", "-c",
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
    ])
    assert res.returncode == 0, f"PostgreSQL query failed: {res.stderr}"
    table_count = int(res.stdout.strip())
    assert table_count >= 150, f"Expected >= 150 Zabbix tables in DB, found: {table_count}"


def test_05_zabbix_server_tcp_port():
    """Verify that Zabbix Server is listening on host port 10051."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        result = sock.connect_ex(("127.0.0.1", 10051))
        assert result == 0, f"Failed to connect to Zabbix Server on 127.0.0.1:10051 (code {result})"
    finally:
        sock.close()


def test_06_zabbix_web_http_health():
    """Verify that Zabbix Web responds HTTP 200 on index.php."""
    req = urllib.request.Request("http://127.0.0.1:8088/index.php")
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200, f"Zabbix web returned HTTP {response.status}"
        body = response.read().decode("utf-8", errors="ignore")
        assert "Zabbix" in body, "Zabbix string missing from web login page"


def test_07_zabbix_api_authentication():
    """Verify that Zabbix API authenticates via user.login and token Bearer auth."""
    # Test user.login
    login_payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"username": ZBX_API_USER, "password": ZBX_API_PASSWORD},
        "id": 1
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8088/api_jsonrpc.php",
        data=login_payload,
        headers={"Content-Type": "application/json-rpc"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        res_data = json.loads(response.read().decode("utf-8"))
        assert "result" in res_data, f"user.login failed: {res_data.get('error')}"
        assert len(res_data["result"]) > 10

    # Test token auth if ZBX_API_TOKEN is populated
    if ZBX_API_TOKEN:
        host_payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "host.get",
            "params": {"output": ["hostid", "name"]},
            "id": 2
        }).encode("utf-8")
        req_token = urllib.request.Request(
            "http://127.0.0.1:8088/api_jsonrpc.php",
            data=host_payload,
            headers={
                "Content-Type": "application/json-rpc",
                "Authorization": f"Bearer {ZBX_API_TOKEN}"
            }
        )
        with urllib.request.urlopen(req_token, timeout=5) as token_response:
            assert token_response.status == 200
            token_data = json.loads(token_response.read().decode("utf-8"))
            assert "result" in token_data, f"Token host.get failed: {token_data.get('error')}"
            assert len(token_data["result"]) > 0


def test_08_grafana_healthcheck():
    """Verify that Grafana responds HTTP 200 on /api/health with database ok."""
    req = urllib.request.Request("http://127.0.0.1:3001/api/health")
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data.get("database") == "ok", f"Grafana database status: {data.get('database')}"


def test_09_grafana_zabbix_datasource_connection():
    """Verify that Grafana's provisioned Zabbix datasource connects and reports OK."""
    import base64
    auth_header = "Basic " + base64.b64encode(
        f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:3001/api/datasources/uid/PA67C5EADE9207728/health",
        headers={"Authorization": auth_header}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data.get("status") == "OK", f"Datasource health check failed: {data}"
        assert "Zabbix API version" in data.get("message", "")


def test_10_grafana_zabbix_app_plugin_enabled():
    """Verify that alexanderzobnin-zabbix-app plugin is enabled in Grafana."""
    import base64
    auth_header = "Basic " + base64.b64encode(
        f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:3001/api/plugins/alexanderzobnin-zabbix-app/settings",
        headers={"Authorization": auth_header}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data.get("enabled") is True, f"Zabbix app plugin not enabled: {data}"


def test_11_snmp_traps_shared_spool_pipeline():
    """Verify that SNMP traps receiver and Zabbix server share the spool volume."""
    # Write a test trap directly into snmptraps container
    test_trap_entry = (
        "2026-11-07T19:40:00+0000 ZBXTRAP 10.2.1.200\n"
        "UDP: [10.2.1.200]:162->[10.2.1.58]:1162\n"
        "DISMAN-EVENT-MIB::sysUpTimeInstance = 42\n"
        "SNMPv2-MIB::snmpTrapOID.0 = 1.3.6.1.4.1.6889.1.1\n"
    )
    write_res = run_cmd([
        "docker", "exec", "nawari-snmptraps",
        "sh", "-c",
        f"printf '{test_trap_entry}' >> /var/lib/zabbix/snmptraps/snmptraps.log"
    ])
    assert write_res.returncode == 0, f"Failed to write trap: {write_res.stderr}"

    # Read from zabbix-server container
    read_res = run_cmd([
        "docker", "exec", "nawari-zabbix-server",
        "grep", "10.2.1.200", "/var/lib/zabbix/snmptraps/snmptraps.log"
    ])
    assert read_res.returncode == 0, "Zabbix server cannot read trap entry from shared spool"
    assert "10.2.1.200" in read_res.stdout


def test_12_resource_consumption_budget():
    """Verify that total memory RSS across all containers is well below 1.64 GiB."""
    res = run_cmd(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}"] + CONTAINERS)
    assert res.returncode == 0, f"docker stats failed: {res.stderr}"
    
    total_mib = 0.0
    for line in res.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        usage_str = line.split("/")[0].strip()
        if usage_str.endswith("GiB"):
            total_mib += float(usage_str[:-3].strip()) * 1024.0
        elif usage_str.endswith("MiB"):
            total_mib += float(usage_str[:-3].strip())
        elif usage_str.endswith("kB") or usage_str.endswith("KiB"):
            total_mib += float(usage_str[:-3].strip()) / 1024.0

    # Ensure total is under the 1.64 GiB cap (1680 MiB)
    assert total_mib < 1680.0, f"Total memory ({total_mib:.1f} MiB) exceeds 1.64 GiB budget"
    # In healthy idle state, should be well under 800 MiB
    assert total_mib < 800.0, f"Measured memory unexpectedly high ({total_mib:.1f} MiB)"

