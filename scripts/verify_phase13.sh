#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 13 Consolidated Acceptance Verification Script
# Enterprise Platform Productisation, Multi-Site Architecture & Service Expansion
# Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPUs, 7.8 GiB RAM)
# Baseline: 299 Passing Tests (Phases 1-12) + Phase 13 Multi-Site Enterprise Suite
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
    local logfile="/tmp/nawari_phase13_${PASS}_${FAIL}.log"
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
echo "NAWARI PHASE 13 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Enterprise Platform Productisation, Multi-Site Architecture & Service Expansion"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 299 Passing Tests (Phases 1-12) + Phase 13 Enterprise Engine"
echo "======================================================================"

check_13a_site_registry() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_site_registry.py
}

check_13b_service_catalog_and_assurance() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_service_catalog.py tests/integration/test_multisite_service_assurance.py
}

check_13c_incident_lifecycle_and_notifications() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_incident_pipeline.py tests/unit/test_multisite_notifications.py tests/unit/test_multisite_recovery_verifier.py tests/integration/test_multisite_closed_loop_incident_flow.py
}

check_13d_edge_spool_and_wan_voice() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_edge_forwarder.py tests/unit/test_multisite_wan_voice_probes.py
}

check_13e_scoped_rbac_and_three_identities() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_site_rbac.py
}

check_13f_unified_noc_dashboards() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_dashboards.py
    test -f docker/grafana/dashboards/nawari_enterprise_overview.json
    test -f docker/grafana/dashboards/nawari_global_outstations.json
    test -f docker/grafana/dashboards/nawari_service_catalog_sla.json
    test -f docker/grafana/dashboards/nawari_incident_operations.json
    test -f docker/grafana/dashboards/nawari_edge_fleet.json
    "${PYTHON}" -c "
import json
dashboards = [
    'docker/grafana/dashboards/nawari_enterprise_overview.json',
    'docker/grafana/dashboards/nawari_global_outstations.json',
    'docker/grafana/dashboards/nawari_service_catalog_sla.json',
    'docker/grafana/dashboards/nawari_incident_operations.json',
    'docker/grafana/dashboards/nawari_edge_fleet.json',
]
for p in dashboards:
    with open(p) as f:
        d = json.load(f)
        assert len(d.get('panels', [])) >= 4, f'{p} has fewer than 4 panels'
"
}

check_13g_deployment_profiles_and_packaging() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_packaging.py
    test -f deploy/profiles/simulation.yaml
    test -f deploy/profiles/staging.yaml
    test -f deploy/profiles/single-site-production.yaml
    test -f deploy/profiles/multi-site-production.yaml
}

check_13h_api_governance_and_crash_recovery() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_api_governance.py
}

check_13i_capacity_and_resilience_docs() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_multisite_capacity_and_load.py
    test -f docs/architecture/capacity-and-resilience.md
    grep -q "2.20" docs/architecture/capacity-and-resilience.md
    grep -q "mon-grafana01" docs/architecture/capacity-and-resilience.md
    grep -qi "hard_production_deny" deploy/profiles/single-site-production.yaml
}

check_13j_operational_drills() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_multisite_operational_drills.py
}

check_sentra_isolation() {
    cd "${PROJECT_ROOT}"
    if [ -d "/Users/madeira/Desktop/Projects/sentra" ]; then
        cd /Users/madeira/Desktop/Projects/sentra
        local sentra_status
        sentra_status=$(git status --porcelain)
        if [ -n "${sentra_status}" ]; then
            echo "Sentra repository has uncommitted changes!" >&2
            return 1
        fi
        local head_commit
        head_commit=$(git rev-parse --short HEAD)
        if [ "${head_commit}" != "9970404" ]; then
            echo "Sentra repository is not at expected clean HEAD 9970404 (found ${head_commit})" >&2
            return 1
        fi
    fi
}

check_full_regression_suite() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/
}

run_check "13A Multi-Site Outstation Registry & Hierarchy" check_13a_site_registry
run_check "13B Aviation Business Service Catalogue & Multi-Dimensional SLIs" check_13b_service_catalog_and_assurance
run_check "13C Incident Lifecycle, Notifications & Recovery Verifier" check_13c_incident_lifecycle_and_notifications
run_check "13D Edge Telemetry Store-and-Forward & Trans-WAN Voice Probing" check_13d_edge_spool_and_wan_voice
run_check "13E Multi-Site Scoped RBAC & Three Distinct Identities" check_13e_scoped_rbac_and_three_identities
run_check "13F Unified NOC Dashboards (Outstations & Service SLA)" check_13f_unified_noc_dashboards
run_check "13G Deployment Profiles, Packaging & Phase 8.2 Gates" check_13g_deployment_profiles_and_packaging
run_check "13H API Governance, Chained Audit Ledger & Crash Recovery WAL" check_13h_api_governance_and_crash_recovery
run_check "13I Capacity, Sizing & Multi-Site Resilience Documentation" check_13i_capacity_and_resilience_docs
run_check "13J Multi-Site Failure Scenarios & Operational Drills" check_13j_operational_drills
run_check "Sentra Repository Isolation & Clean Main Baseline (9970404)" check_sentra_isolation
run_check "Consolidated Full Regression Suite (All Phases 1–13)" check_full_regression_suite

echo "======================================================================"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo "NAWARI PHASE 13 ACCEPTANCE GATE: PASSED"
    exit 0
else
    echo "NAWARI PHASE 13 ACCEPTANCE GATE: FAILED"
    exit 1
fi

