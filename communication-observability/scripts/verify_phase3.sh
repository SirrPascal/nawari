#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 3 Network Monitoring Framework Acceptance Verification Script
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
echo "NAWARI PHASE 3 ACCEPTANCE VERIFICATION: NETWORK OBSERVABILITY"
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

check_mock_snmp_responsiveness() {
    docker exec nawari-mock-snmp snmpget -v2c -c public 127.0.0.1 SNMPv2-MIB::sysName.0 | grep -q "nawari-mock-core-switch-01"
}

check_templates_present() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
b = client.call('template.get', {'filter': {'host': ['Nawari Generic SNMP Base']}})
n = client.call('template.get', {'filter': {'host': ['Nawari Network Device by SNMP']}})
assert len(b) == 1 and len(n) == 1
" > /dev/null 2>&1
}

check_mock_host_monitored() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
hosts = client.call('host.get', {'filter': {'host': ['mock-core-switch-01']}})
assert len(hosts) == 1 and hosts[0]['status'] == '0'
" > /dev/null 2>&1
}

check_lld_interface_discovery() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
hosts = client.call('host.get', {'filter': {'host': ['mock-core-switch-01']}})
items = client.call('item.get', {'hostids': [hosts[0]['hostid']], 'output': ['name']})
names = ' '.join([i['name'] for i in items])
assert 'ge-0-0-1' in names and 'ge-0-0-2' in names and 'sbc-ext0' in names
assert len(items) >= 45
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
hosts = client.call('host.get', {'filter': {'host': ['mock-core-switch-01']}})
it = client.call('item.get', {'hostids': [hosts[0]['hostid']], 'filter': {'key_': ['system.name']}})
h = client.call('history.get', {'itemids': [it[0]['itemid']], 'history': 1, 'limit': 5})
assert len(h) > 0 and 'nawari-mock-core-switch-01' in h[0]['value']
" > /dev/null 2>&1
}

check_triggers_instantiated() {
    "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings

settings = get_settings()
client = ZabbixClient(settings.zabbix)
client.connect()
hosts = client.call('host.get', {'filter': {'host': ['mock-core-switch-01']}})
triggers = client.call('trigger.get', {'hostids': [hosts[0]['hostid']]})
assert len(triggers) >= 15
" > /dev/null 2>&1
}

check_grafana_dashboards() {
    "${PYTHON_BIN}" -c "
import sys, urllib.request, json, base64
sys.path.insert(0, '${PROJECT_ROOT}')
from tests.integration.test_core_infrastructure import GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD

auth_header = 'Basic ' + base64.b64encode(f'{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}'.encode()).decode()
req = urllib.request.Request('http://127.0.0.1:3001/api/search?type=dash-db', headers={'Authorization': auth_header})
with urllib.request.urlopen(req) as resp:
    dashboards = json.loads(resp.read().decode())
    uids = [d.get('uid') for d in dashboards]
    assert 'nawari-net-overview' in uids and 'nawari-interface-health' in uids
" > /dev/null 2>&1
}

check_integration_test_suite() {
    "${PYTHON_BIN}" -m pytest tests/integration/test_phase3_network_monitoring.py -q > /dev/null 2>&1
}

run_check "Mock Net-SNMP Daemon UDP 161" check_mock_snmp_responsiveness
run_check "Template Hierarchy (Base + Network Device)" check_templates_present
run_check "Mock Host Provisioning & Group Linkage" check_mock_host_monitored
run_check "LLD Interface Discovery (IF-MIB)" check_lld_interface_discovery
run_check "Real PostgreSQL Historical Telemetry" check_historical_telemetry
run_check "Trigger Prototypes Instantiation" check_triggers_instantiated
run_check "Provisioned Grafana Dashboards" check_grafana_dashboards
run_check "Full Phase 3 Integration Suite (9/9)" check_integration_test_suite

echo "----------------------------------------------------------------------"
echo "VERIFICATION SUMMARY: ${PASS} Passed, ${FAIL} Failed"
echo "----------------------------------------------------------------------"

if [ "${FAIL}" -eq 0 ]; then
    echo ">> ALL PHASE 3 ACCEPTANCE GATES PASSED <<"
    exit 0
else
    echo ">> PHASE 3 VERIFICATION FAILED WITH ${FAIL} FAILURES <<"
    exit 1
fi

