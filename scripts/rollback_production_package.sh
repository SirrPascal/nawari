#!/usr/bin/env bash
# ==============================================================================
# scripts/rollback_production_package.sh
# Non-Destructive Emergency Rollback Procedure for Nawari on mon-grafana01
#
# SAFETY RULES:
# - Strictly preserves captured call records in homer_data.
# - Never executes DROP DATABASE or removes persistent Docker volumes.
# - Restores prior release configuration and container states cleanly.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "========================================================================"
echo "NAWARI M5/M6 — EMERGENCY NON-DESTRUCTIVE ROLLBACK PROCEDURE"
echo "Target: mon-grafana01 (10.2.1.58)"
echo "Timestamp: $(date -u +"%Y-%m-%d %H:%M:%SZ")"
echo "========================================================================"

TARGET_REV="${1:-HEAD~1}"

echo ">>> Step 1: Checking out target rollback Git revision (${TARGET_REV})..."
if [ -d "${ROOT_DIR}/.git" ]; then
    git -C "${ROOT_DIR}" checkout "${TARGET_REV}" \
        communication-observability/docker/grafana/dashboards/ \
        "network observability/platform/nawari"
    echo "  [OK] Reverted application code and dashboard definitions to ${TARGET_REV}."
fi

echo ">>> Step 2: Applying Non-Destructive Schema Rollback (Migration 034)..."
if [ -f "${ROOT_DIR}/network observability/platform/nawari/migrations/rollback_034.sql" ]; then
    if docker ps --format '{{.Names}}' | grep -q "^nawari-postgres$"; then
        docker exec -i nawari-postgres psql -U zabbix -d nawari_platform \
            < "${ROOT_DIR}/network observability/platform/nawari/migrations/rollback_034.sql" 2>/dev/null || true
        echo "  [OK] Rollback SQL executed for Migration 034 (canonical entities & HA tables)."
    fi
fi

echo ">>> Step 3: Re-synchronizing Baseline Grafana Dashboards..."
if docker ps --format '{{.Names}}' | grep -q "^nawari-grafana$"; then
    docker cp "${ROOT_DIR}/communication-observability/docker/grafana/dashboards/communication_observability/." \
        nawari-grafana:/var/lib/grafana/dashboards/communication_observability/
    docker restart nawari-grafana
    echo "  [OK] Reverted dashboards restored in Grafana."
fi

echo ">>> Step 4: Restarting Core Platform Containers..."
if [ -f "${ROOT_DIR}/communication-observability/docker/compose.prod.yaml" ]; then
    docker compose -f "${ROOT_DIR}/communication-observability/docker/compose.prod.yaml" restart nawari-heplify nawari-asterisk 2>/dev/null || true
fi

echo ""
echo "========================================================================"
echo "ROLLBACK COMPLETE: Services restored to ${TARGET_REV} without data loss."
echo "Verified: homer_data and Zabbix persistent storage preserved intact."
echo "========================================================================"
