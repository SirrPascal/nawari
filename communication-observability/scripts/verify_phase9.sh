#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 9 Consolidated Acceptance Verification Script
# Network Intelligence, Dynamic Topology Mapping & Dependency Graph Engine
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
    local logfile="/tmp/nawari_phase9_${PASS}_${FAIL}.log"
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
echo "NAWARI PHASE 9 CONSOLIDATED ACCEPTANCE VERIFICATION"
echo "Network Intelligence, Dynamic Topology Mapping & Dependency Engine"
echo "Target: Ubuntu 24.04 LTS Host mon-grafana01 (2 vCPU, 7.8 GiB RAM)"
echo "Baseline: 215 Passing Tests (Phases 1-8.1) + Phase 9 Engine"
echo "======================================================================"

check_schema_validity() {
    cd "${PROJECT_ROOT}"
    test -f docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_devices" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_interfaces" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_layer2_links" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_subnets" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_routing_adjacencies" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_service_dependencies" docker/postgresql/initdb/05-topology-schema.sql
    grep -q "CREATE TABLE IF NOT EXISTS topology_changes" docker/postgresql/initdb/05-topology-schema.sql
}

check_identity_and_models() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_topology_identity.py
}

check_discovery_parsers() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_topology_parsers.py
}

check_graph_and_dependency() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/unit/test_topology_graph_and_dependency.py
}

check_topology_api_and_assurance() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/integration/test_phase9_topology_engine.py
}

check_full_regression_suite() {
    cd "${PROJECT_ROOT}"
    PYTHONPATH=. "${PYTEST}" -q tests/
}

check_repository_isolation() {
    cd "${PROJECT_ROOT}"
    # Verify Sentra repository has not been modified
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

run_check "PostgreSQL Topology Schema Definitions (7 Tables & DDL)" check_schema_validity
run_check "Canonical Device Identity Cascade & Evidentiary Scoring" check_identity_and_models
run_check "Discovery Parsers (LLDP 802.1AB, CDP, FDB, Route/OSPF/BGP)" check_discovery_parsers
run_check "Topology Graph Engine, Traversal & Blast-Radius Calculation" check_graph_and_dependency
run_check "Topology REST API Contracts & Assurance Correlator Link" check_topology_api_and_assurance
run_check "Full Nawari Test Suite (Phases 1-9 Consolidated)" check_full_regression_suite
run_check "Repository Isolation & Untouched Sentra Working Tree" check_repository_isolation

echo "======================================================================"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -eq 0 ]; then
    echo "NAWARI PHASE 9: ACCEPTED & PRODUCTION READY"
    exit 0
else
    echo "NAWARI PHASE 9: FAILED VERIFICATION"
    exit 1
fi

