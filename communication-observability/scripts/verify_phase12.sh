#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 12 Consolidated Acceptance Verification Script
# Controlled Operational Automation, Remediation Playbooks & Human Governance
# Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)
# Baseline: 280 Passing Tests (Phases 1-11) + Phase 12 Action Engine
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
    local logfile="/tmp/nawari_phase12_${PASS}_${FAIL}.log"
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
echo "NAWARI PHASE 12 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Controlled Operational Automation, Playbooks & Human-in-the-Loop"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 280 Passing Tests (Phases 1-11) + Phase 12 Action Engine"
echo "======================================================================"

check_automation_architecture() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_actions_framework_and_policy.py
}

check_approval_and_rbac() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_actions_approval_and_rbac.py
}

check_playbooks_and_rollback_preconditions() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_actions_playbooks_and_rollback.py
}

check_execution_engine_and_circuit_breakers() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_actions_execution_engine.py
}

check_audit_chain_integrity() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_actions_audit_chain.py
}

check_remediation_pipeline_integration() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_controlled_remediation_pipeline.py
}

check_operations_dashboard() {
    cd "${PROJECT_ROOT}"
    test -f docker/grafana/dashboards/nawari_controlled_operations.json
    "${PYTHON}" -c "
import json
with open('docker/grafana/dashboards/nawari_controlled_operations.json') as f:
    d = json.load(f)
assert d['uid'] == 'nawari-controlled-operations'
assert len(d['panels']) >= 6
for p in d['panels']:
    if p.get('type') != 'row':
        assert 'description' in p and len(p['description']) > 15
"
}

check_full_regression_suite() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/
}

check_repository_isolation() {
    cd "${PROJECT_ROOT}"
    if [ -d "/Users/madeira/Desktop/Projects/sentra" ]; then
        cd /Users/madeira/Desktop/Projects/sentra
        local sentra_status
        sentra_status=$(git status --porcelain)
        if [ -n "${sentra_status}" ]; then
            echo "Sentra repository has uncommitted changes!" >&2
            return 1
        fi
    fi
}

run_check "Workstream 12A: Automation Architecture & Policy Boundaries" check_automation_architecture
run_check "Workstream 12B: Approval Tokens, Replay Guard & Two-Person Rule" check_approval_and_rbac
run_check "Workstream 12C: Remediation Playbooks & Rollback Preconditions" check_playbooks_and_rollback_preconditions
run_check "Workstream 12D: Action Execution Service, Idempotency & Circuit Breakers" check_execution_engine_and_circuit_breakers
run_check "Workstream 12E/12F: Pipeline Integration & Verification" check_remediation_pipeline_integration
run_check "Workstream 12G: Cryptographically Chained Audit Ledger (SHA-256)" check_audit_chain_integrity
run_check "Workstream 12G: Controlled Operations Dashboard JSON Schema" check_operations_dashboard
run_check "Workstream 12H: Full Nawari Regression Suite (Phases 1-12)" check_full_regression_suite
run_check "Repository Isolation: Untouched Sentra Working Tree" check_repository_isolation

echo "======================================================================"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo "NAWARI PHASE 12: ACCEPTED & PRODUCTION READY"
    exit 0
else
    echo "NAWARI PHASE 12: VERIFICATION FAILED"
    exit 1
fi

