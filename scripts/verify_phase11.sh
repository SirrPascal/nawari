#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 11 Consolidated Acceptance Verification Script
# Evidence-Driven Analytics, Dynamic Baselines & Predictive Service Assurance
# Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)
# Baseline: 258 Passing Tests (Phases 1-10) + Phase 11 Analytics Engine
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
    local logfile="/tmp/nawari_phase11_${PASS}_${FAIL}.log"
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
echo "NAWARI PHASE 11 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Evidence-Driven Analytics, Dynamic Baselines & Predictive Assurance"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 258 Passing Tests (Phases 1-10) + Phase 11 Analytics Engine"
echo "======================================================================"

check_telemetry_foundation() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_telemetry_foundation.py
}

check_dynamic_baselines() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_dynamic_baselines.py
}

check_anomaly_detection() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_anomaly_detection.py
}

check_predictive_degradation() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_predictive_degradation.py
}

check_intelligent_diagnosis() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_intelligent_diagnosis.py
}

check_predictive_dashboard() {
    cd "${PROJECT_ROOT}"
    test -f docker/grafana/dashboards/nawari_predictive_intelligence.json
    "${PYTHON}" -c "
import json
with open('docker/grafana/dashboards/nawari_predictive_intelligence.json') as f:
    d = json.load(f)
assert d['uid'] == 'nawari-predictive-intelligence'
assert len(d['panels']) >= 6
for p in d['panels']:
    if p.get('type') != 'row':
        assert 'description' in p and len(p['description']) > 15
"
}

check_model_governance() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_analytics_model_governance.py
}

check_pipeline_integration() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_predictive_assurance_pipeline.py
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

run_check "Workstream 11A: Telemetry Foundation & Feature Extraction" check_telemetry_foundation
run_check "Workstream 11B: Dynamic Multi-Seasonal Baselines" check_dynamic_baselines
run_check "Workstream 11C: Statistical Anomaly Detection Engine" check_anomaly_detection
run_check "Workstream 11D: Predictive Degradation & TTE Forecaster" check_predictive_degradation
run_check "Workstream 11E: Intelligent Diagnosis & Evidence Ranking" check_intelligent_diagnosis
run_check "Workstream 11F: Predictive Intelligence Dashboard JSON Schema" check_predictive_dashboard
run_check "Workstream 11G: Model Governance & Hysteresis Controls" check_model_governance
run_check "Workstream 11H: End-to-End Pipeline Integration" check_pipeline_integration
run_check "Workstream 11H: Full Nawari Regression Suite (Phases 1-11)" check_full_regression_suite
run_check "Repository Isolation: Untouched Sentra Working Tree" check_repository_isolation

echo "======================================================================"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo "NAWARI PHASE 11: ACCEPTED & PRODUCTION READY"
    exit 0
else
    echo "NAWARI PHASE 11: VERIFICATION FAILED"
    exit 1
fi

