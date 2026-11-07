#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 2 Provisioning & API Acceptance Verification Script
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
echo "NAWARI PHASE 2 ACCEPTANCE VERIFICATION"
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

check_unit_tests() {
    "${PYTHON_BIN}" -m pytest tests/unit/ -q > /dev/null
}

check_api_status() {
    "${PYTHON_BIN}" -m services.api.cli status > /dev/null
}

check_dry_run_plan() {
    "${PYTHON_BIN}" -m services.api.cli plan > /dev/null
}

check_reconciliation_idempotency() {
    "${PYTHON_BIN}" -m services.api.cli apply > /dev/null
}

check_integration_tests() {
    "${PYTHON_BIN}" -m pytest tests/integration/test_provisioning_idempotency.py -q > /dev/null
}

run_check "Unit Tests (Schema, Diff Engine, Secret Expansion)" check_unit_tests
run_check "Zabbix API Client Status & Connectivity" check_api_status
run_check "Declarative Desired-State Plan (Dry-Run)" check_dry_run_plan
run_check "Idempotent Reconciliation (Exit Gate: 0 changes on pass 2)" check_reconciliation_idempotency
run_check "Live Provisioning Idempotency Test Suite" check_integration_tests

echo "======================================================================"
echo "RESULTS: ${PASS} passed, ${FAIL} failed"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo ">> ALL 5 PHASE 2 ACCEPTANCE CRITERIA MET SUCCESSFULLY! <<"
    exit 0
else
    echo ">> PHASE 2 VERIFICATION FAILED WITH ${FAIL} FAILURES <<"
    exit 1
fi
