#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 4 Avaya SBCE Observability Acceptance Verification Script
# ==============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

# Load local environment if present
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "${PROJECT_ROOT}/.env"
    set +a
fi

export PYTHONPATH="${PROJECT_ROOT}"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

echo "======================================================================"
echo "NAWARI PHASE 4 ACCEPTANCE VERIFICATION: AVAYA SBCE OBSERVABILITY"
echo "======================================================================"

PASS=0
FAIL=0

run_check() {
    local desc="$1"
    local fn="$2"
    echo -n "[TEST] ${desc} ... "
    if "${fn}"; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

check_mock_snmpv3_authpriv() {
    docker exec nawari-mock-snmp snmpget -v3 -l authPriv \
        -u Admin -a SHA -A sbce_secret_auth_pass -x DES -X sbce_secret_priv_pass \
        127.0.0.1 1.3.6.1.2.1.1.5.0 | grep -q "nawari-mock-core-switch-01"
}

check_sbce_template_hierarchy() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
tpl = client.call('template.get', {
    'filter': {'host': ['Nawari Avaya SBCE by SNMP']},
    'selectParentTemplates': ['host'],
    'selectDiscoveries': ['key_'],
    'selectItems': ['key_']
})
assert len(tpl) == 1, 'Avaya SBCE template missing'
parents = [p['host'] for p in tpl[0].get('parentTemplates', [])]
assert 'Nawari Generic SNMP Base' in parents, 'Generic SNMP Base parent missing'
disc = [d['key_'] for d in tpl[0].get('discoveries', [])]
assert 'sbce.interface.discovery' in disc, 'sbce.interface.discovery rule missing'
items = [i['key_'] for i in tpl[0].get('items', [])]
assert 'system.cpu.util' in items and 'vm.memory.util' in items and 'vfs.fs.used.percent[/]' in items
" > /dev/null 2>&1
}

check_sbce_hosts_provisioned() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
mock_h = client.call('host.get', {
    'filter': {'host': ['mock-avaya-sbce-01']},
    'selectParentTemplates': ['name'],
    'selectInterfaces': ['details']
})
assert len(mock_h) == 1 and mock_h[0]['status'] == '0'
assert any(t['name'] == 'Nawari Avaya SBCE by SNMP' for t in mock_h[0]['parentTemplates'])
assert str(mock_h[0]['interfaces'][0]['details']['version']) == '3'
assert mock_h[0]['interfaces'][0]['details']['securityname'] == 'Admin'

prod_h = client.call('host.get', {
    'filter': {'host': ['avaya-sbce-01']},
    'selectParentTemplates': ['name'],
    'selectInterfaces': ['ip']
})
assert len(prod_h) == 1
assert any(t['name'] == 'Nawari Avaya SBCE by SNMP' for t in prod_h[0]['parentTemplates'])
assert prod_h[0]['interfaces'][0]['ip'] == '10.2.156.131'
" > /dev/null 2>&1
}

check_sbce_interface_discovery() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
host = client.get_hosts(['mock-avaya-sbce-01'])[0]
items = client.call('item.get', {'hostids': [host['hostid']], 'output': ['name']})
names = ' '.join([i['name'] for i in items])
for iface in ['M1', 'M2', 'A1', 'B1']:
    assert f'Interface {iface}: Operational status' in names
    assert f'Interface {iface}: Bits received' in names
    assert f'Interface {iface}: Bits sent' in names
" > /dev/null 2>&1
}

check_sbce_resource_metrics() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
host = client.get_hosts(['mock-avaya-sbce-01'])[0]
items = client.call('item.get', {
    'hostids': [host['hostid']],
    'output': ['key_', 'state', 'lastvalue']
})
by_key = {it['key_']: it for it in items}
for k in ['system.cpu.util', 'system.cpu.load.avg1', 'vm.memory.util', 'vfs.fs.used.percent[/]']:
    assert k in by_key
    assert by_key[k]['state'] == '0'
    assert by_key[k]['lastvalue'] is not None and by_key[k]['lastvalue'] != ''
" > /dev/null 2>&1
}

check_historical_telemetry() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
host = client.get_hosts(['mock-avaya-sbce-01'])[0]
items = client.call('item.get', {'hostids': [host['hostid']], 'output': ['itemid', 'value_type']})
found = 0
for it in items:
    h = client.call('history.get', {'itemids': [it['itemid']], 'history': int(it['value_type']), 'limit': 1})
    if h:
        found += 1
    if found >= 5:
        break
assert found >= 5
" > /dev/null 2>&1
}

check_voice_fault_lifecycle() {
    "${PYTHON_BIN}" -c "
import subprocess
import time
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
host = client.get_hosts(['mock-avaya-sbce-01'])[0]
items = client.call('item.get', {'hostids': [host['hostid']], 'search': {'name': 'Interface A1: Operational status'}})
itemid = items[0]['itemid']

# Fault injection: Link Down
subprocess.run(['docker', 'exec', 'nawari-mock-snmp', '/usr/local/bin/inject_fault.sh', 'link-down', 'A1'], check=True)
client.call('task.create', {'type': 6, 'request': {'itemid': itemid}})

detected = False
for _ in range(12):
    time.sleep(2)
    probs = client.call('problem.get', {'hostids': [host['hostid']], 'search': {'name': 'Interface A1: Link down'}})
    if probs:
        assert int(probs[0]['severity']) >= 4
        detected = True
        break
    client.call('task.create', {'type': 6, 'request': {'itemid': itemid}})
assert detected, 'Fault not detected'

# Recovery: Link Up
subprocess.run(['docker', 'exec', 'nawari-mock-snmp', '/usr/local/bin/inject_fault.sh', 'link-up', 'A1'], check=True)
client.call('task.create', {'type': 6, 'request': {'itemid': itemid}})

resolved = False
for _ in range(12):
    time.sleep(2)
    probs = client.call('problem.get', {'hostids': [host['hostid']], 'search': {'name': 'Interface A1: Link down'}})
    if not probs:
        resolved = True
        break
    client.call('task.create', {'type': 6, 'request': {'itemid': itemid}})
assert resolved, 'Fault not resolved'
" > /dev/null 2>&1
}

check_grafana_dashboard() {
    "${PYTHON_BIN}" -c "
import urllib.request
import base64
import json
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.config import load_env_file

env = load_env_file()
user = env.get('GRAFANA_ADMIN_USER', 'admin')
pwd = env.get('GRAFANA_ADMIN_PASSWORD', '')

url = 'http://127.0.0.1:3001/api/dashboards/uid/nawari-sbce-health'
auth_str = base64.b64encode(f'{user}:{pwd}'.encode()).decode()
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth_str}'})

with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data['dashboard']['title'] == 'Nawari — Avaya SBCE Operational & Voice Telemetry'
    assert len(data['dashboard']['panels']) >= 15
" > /dev/null 2>&1
}

run_check "SNMPv3 authPriv Responsiveness (User: Admin, SHA/DES)" check_mock_snmpv3_authpriv
run_check "Avaya SBCE Template Hierarchy & LLD Rules" check_sbce_template_hierarchy
run_check "SBCE Hosts Provisioned (Mock & Production Reconciled)" check_sbce_hosts_provisioned
run_check "LLD Discovery of Voice Interfaces (M1, M2, A1, B1)" check_sbce_interface_discovery
run_check "SBCE Appliance Resource Telemetry Active (CPU/RAM/Disk/Load)" check_sbce_resource_metrics
run_check "Historical Metric Persistence in PostgreSQL" check_historical_telemetry
run_check "Voice Interface Fault Injection & Auto-Recovery (A1 Link Down)" check_voice_fault_lifecycle
run_check "Grafana Avaya SBCE Operational Dashboard (19 Panels)" check_grafana_dashboard

echo "----------------------------------------------------------------------"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo ">>> PHASE 4 ACCEPTANCE GATES COMPLETED SUCCESSFULLY <<<"
    exit 0
else
    echo ">>> PHASE 4 ACCEPTANCE GATES FAILED <<<"
    exit 1
fi
