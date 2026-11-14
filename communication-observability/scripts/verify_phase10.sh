#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 10 Consolidated Acceptance Verification Script
# Advanced Communications Intelligence & Voice Service Assurance
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
    local logfile="/tmp/nawari_phase10_${PASS}_${FAIL}.log"
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
echo "NAWARI PHASE 10 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Communications Intelligence, SIP Transaction Modeling & RTCP-XR"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 235 Passing Tests (Phases 1-9) + Phase 10 Engine"
echo "======================================================================"

check_sip_transaction_intelligence() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_sip_transaction_engine.py
}

check_call_lifecycle_correlation() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_call_lifecycle_correlation.py
}

check_rtcp_xr_media_intelligence() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_rtcp_xr_analyzer.py
}

check_avaya_platform_model() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_avaya_platform_model.py
}

check_dialplan_and_routing_assurance() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_dialplan_assurance.py
}

check_voice_topology_integration() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_voice_topology_assurance.py
}

check_grafana_dashboard_provisioning() {
    cd "${PROJECT_ROOT}"
    test -f docker/grafana/dashboards/nawari_voice_intelligence.json
    "${PYTHON}" -c "
import json
with open('docker/grafana/dashboards/nawari_voice_intelligence.json') as f:
    d = json.load(f)
assert d['uid'] == 'nawari-voice-intelligence'
assert len(d['panels']) >= 6
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

run_check "Workstream 10A: SIP Transaction Intelligence & Ladders" check_sip_transaction_intelligence
run_check "Workstream 10B: Call Lifecycle, Q.850 & Privacy Masking" check_call_lifecycle_correlation
run_check "Workstream 10C: RTCP-XR VoIP Metrics & Extended E-Model" check_rtcp_xr_media_intelligence
run_check "Workstream 10D: Avaya SBCE 8.1 & Session Manager Models" check_avaya_platform_model
run_check "Workstream 10E: Kenya Airways Dial Plan & Route Assurance" check_dialplan_and_routing_assurance
run_check "Workstream 10F: Voice Service Topological Linkage" check_voice_topology_integration
run_check "Workstream 10G: Voice Intelligence Dashboard JSON Schema" check_grafana_dashboard_provisioning
run_check "Workstream 10H: Full Nawari Regression Suite (Phases 1-10)" check_full_regression_suite
run_check "Repository Isolation: Untouched Sentra Working Tree" check_repository_isolation

echo "======================================================================"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo "NAWARI PHASE 10: ACCEPTED & PRODUCTION READY"
    exit 0
else
    echo "NAWARI PHASE 10: FAILED VERIFICATION"
    exit 1
fi

