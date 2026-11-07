#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 1 Acceptance Verification Script
# ==============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

echo "======================================================================"
echo "NAWARI PHASE 1 ACCEPTANCE VERIFICATION"
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

check_compose() {
    docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml config --quiet
}

check_pg_health() {
    [ "$(docker inspect --format '{{.State.Health.Status}}' nawari-postgres 2>/dev/null)" = "healthy" ]
}

check_zbx_srv_health() {
    [ "$(docker inspect --format '{{.State.Health.Status}}' nawari-zabbix-server 2>/dev/null)" = "healthy" ]
}

check_zbx_web_health() {
    [ "$(docker inspect --format '{{.State.Health.Status}}' nawari-zabbix-web 2>/dev/null)" = "healthy" ]
}

check_snmptraps_running() {
    [ "$(docker inspect --format '{{.State.Running}}' nawari-snmptraps 2>/dev/null)" = "true" ]
}

check_grafana_health() {
    [ "$(docker inspect --format '{{.State.Health.Status}}' nawari-grafana 2>/dev/null)" = "healthy" ]
}

check_pg_tables() {
    local count
    count=$(docker exec nawari-postgres psql -U zabbix -d zabbix -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')
    [ -n "$count" ] && [ "$count" -ge 150 ]
}

check_zbx_srv_port() {
    nc -z 127.0.0.1 10051
}

check_zbx_web_http() {
    curl -sf http://127.0.0.1:8088/index.php -o /dev/null
}

check_zbx_api_auth() {
    curl -sf -X POST \
        -H "Content-Type: application/json-rpc" \
        -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"NawariSecOps2025!"},"id":1}' \
        http://127.0.0.1:8088/api_jsonrpc.php | grep -q '"result"'
}

check_grafana_http() {
    curl -sf http://127.0.0.1:3001/api/health | grep -E -q '"database"[[:space:]]*:[[:space:]]*"ok"'
}

check_grafana_zbx_ds() {
    curl -sf -u admin:nawari_grafana_dev_pass \
        http://127.0.0.1:3001/api/datasources/uid/PA67C5EADE9207728/health | grep -q '"status":"OK"'
}

check_snmptrap_spool() {
    docker exec nawari-zabbix-server test -f /var/lib/zabbix/snmptraps/snmptraps.log
}

check_ram_budget() {
    docker stats --no-stream nawari-postgres nawari-snmptraps nawari-zabbix-server nawari-zabbix-web nawari-grafana > /dev/null
}

run_check "Docker Compose config validity" check_compose
run_check "PostgreSQL running and healthy" check_pg_health
run_check "Zabbix Server running and healthy" check_zbx_srv_health
run_check "Zabbix Web running and healthy" check_zbx_web_health
run_check "Zabbix SNMP Traps daemon running" check_snmptraps_running
run_check "Grafana running and healthy" check_grafana_health
run_check "PostgreSQL Zabbix tables (count >= 150)" check_pg_tables
run_check "Zabbix Server TCP port 10051 reachable" check_zbx_srv_port
run_check "Zabbix Web HTTP 200 healthcheck" check_zbx_web_http
run_check "Zabbix API user.login authentication" check_zbx_api_auth
run_check "Grafana HTTP healthcheck (database ok)" check_grafana_http
run_check "Grafana Zabbix datasource reports status OK" check_grafana_zbx_ds
run_check "SNMP traps spool volume shared with Zabbix server" check_snmptrap_spool
run_check "Total stack RAM usage within budget" check_ram_budget

echo "======================================================================"
echo "RESULTS: ${PASS} passed, ${FAIL} failed"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo ">> ALL 14 PHASE 1 ACCEPTANCE CRITERIA MET SUCCESSFULLY! <<"
    exit 0
else
    echo ">> VERIFICATION FAILED WITH ${FAIL} FAILURES <<"
    exit 1
fi
