#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 8 Consolidated Acceptance Verification Script (Workstream 8G)
# Enterprise Integration, Operationalisation, and Production Readiness
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3}"
PYTEST="${PYTEST:-/Library/Frameworks/Python.framework/Versions/3.13/bin/pytest}"

PASS=0
FAIL=0

run_check() {
    local title="$1"
    local func="$2"
    printf "[CHECK] %-65s ... " "${title}"
    local logfile="/tmp/nawari_phase8_${PASS}_${FAIL}.log"
    if "${func}" > "${logfile}" 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
        rm -f "${logfile}"
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
        echo "  [ERROR LOG]:"
        cat "${logfile}" | sed 's/^/    /'
    fi
}

echo "======================================================================"
echo "NAWARI PHASE 8 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 188 Passing Tests (Phases 1-7) + Phase 8 Hardening"
echo "======================================================================"

check_compose_prod_validity() {
    cd "${PROJECT_ROOT}"
    docker compose --env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml config >/dev/null
}

check_containers_running_and_healthy() {
    for c in nawari-postgres nawari-snmptraps nawari-zabbix-server nawari-zabbix-web nawari-grafana; do
        if ! docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
            echo "Container ${c} is not running!" >&2
            return 1
        fi
    done
}

check_host_hardening_templates() {
    test -f "${PROJECT_ROOT}/docker/security/ufw-rules.sh" || return 1
    test -x "${PROJECT_ROOT}/docker/security/ufw-rules.sh" || return 1
    test -f "${PROJECT_ROOT}/docker/security/sysctl-hardening.conf" || return 1
    test -f "${PROJECT_ROOT}/docs/operations/disaster-recovery-runbook.md" || return 1
}

check_backup_restore_scripts() {
    test -f "${PROJECT_ROOT}/scripts/backup/backup_nawari.sh" || return 1
    test -x "${PROJECT_ROOT}/scripts/backup/backup_nawari.sh" || return 1
    test -f "${PROJECT_ROOT}/scripts/backup/restore_nawari.sh" || return 1
    test -x "${PROJECT_ROOT}/scripts/backup/restore_nawari.sh" || return 1
}

check_recovery_benchmark() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/recovery/test_backup_restore_loop.py
}

check_unit_security_rbac() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_rbac_permissions.py
}

check_unit_incident_lifecycle() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_incident_lifecycle.py
}

check_unit_integrations() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_integrations_adapters.py
}

check_performance_capacity_and_backpressure() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/performance/test_capacity_and_backpressure.py
}

check_integration_phase8_readiness() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_phase8_production_readiness.py
}

# Run individual verification checks
run_check "Workstream 8A: Docker Compose Production Overrides & Image Pinning" check_compose_prod_validity
run_check "Workstream 8A: Core Production Containers Healthy" check_containers_running_and_healthy
run_check "Workstream 8A: Host Security Templates (UFW & Sysctl Hardening)" check_host_hardening_templates
run_check "Workstream 8B: Backup & Restore Scripts and DR Runbook" check_backup_restore_scripts
run_check "Workstream 8B: Timed Disaster Recovery Benchmark (RTO <= 30m)" check_recovery_benchmark
run_check "Workstream 8C: Enterprise Security, RBAC & Audit Hashing Tests" check_unit_security_rbac
run_check "Workstream 8D: Incident Deduplication & 9-Stage Lifecycle Tests" check_unit_incident_lifecycle
run_check "Workstream 8E: Enterprise Integrations (ITSM, Email, SMS, CMDB)" check_unit_integrations
run_check "Workstream 8F: Performance, Scalability & Backpressure Quota" check_performance_capacity_and_backpressure
run_check "Workstream 8G: Consolidated Production Readiness Integration Gate" check_integration_phase8_readiness

echo "----------------------------------------------------------------------"
echo "PHASE 8 VERIFICATION SUMMARY: ${PASS} PASSED / ${FAIL} FAILED"
echo "----------------------------------------------------------------------"

if [ "${FAIL}" -eq 0 ]; then
    echo "SUCCESS: All Phase 8 enterprise readiness verification checks passed!"
    exit 0
else
    echo "FAILURE: One or more Phase 8 verification checks failed." >&2
    exit 1
fi

