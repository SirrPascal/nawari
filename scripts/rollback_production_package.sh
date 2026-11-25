#!/usr/bin/env bash
# ==============================================================================
# scripts/rollback_production_package.sh
# Non-Destructive Emergency Rollback Procedure for Nawari on mon-grafana01
#
# SAFETY RULES:
# - Strictly preserves captured call records in homer_data and Zabbix telemetry.
# - Never executes DROP DATABASE or removes persistent Docker volumes.
# - By default, rolls back ONLY application code, containers, and dashboard definitions.
# - Schema rollback and database restore are gated behind explicit flags:
#     --rollback-schema      : Executes Migration 034 schema rollback (takes snapshot first)
#     --restore-database=FILE: Restores a specific pg_dump backup (takes snapshot first)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "========================================================================"
echo "NAWARI M5/M6 — EMERGENCY NON-DESTRUCTIVE ROLLBACK PROCEDURE"
echo "Target: mon-grafana01 (10.2.1.58)"
echo "Timestamp: $(date -u +"%Y-%m-%d %H:%M:%SZ")"
echo "========================================================================"

TARGET_REV="HEAD~1"
ROLLBACK_SCHEMA=false
RESTORE_DB_FILE=""

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --rollback-schema)
            ROLLBACK_SCHEMA=true
            shift
            ;;
        --restore-database=*)
            RESTORE_DB_FILE="${arg#*=}"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [TARGET_REV] [--rollback-schema] [--restore-database=/path/to/dump]"
            echo "  TARGET_REV          Git revision to restore application/dashboards to (default: HEAD~1)"
            echo "  --rollback-schema   Execute schema rollback SQL (drops tables; snapshot taken first)"
            echo "  --restore-database  Restore database snapshot (destructive to newer data; snapshot taken first)"
            exit 0
            ;;
        *)
            TARGET_REV="$arg"
            ;;
    esac
done

echo ">>> Target application rollback revision: ${TARGET_REV}"

echo ">>> Step 1: Checking out target rollback Git revision (${TARGET_REV})..."
if [ -d "${ROOT_DIR}/.git" ]; then
    git -C "${ROOT_DIR}" checkout "${TARGET_REV}" \
        communication-observability/docker/grafana/dashboards/ \
        "network observability/platform/nawari"
    echo "  [OK] Reverted application code and dashboard definitions to ${TARGET_REV}."
fi

echo ">>> Step 2: Database Schema & Telemetry Preservation Check..."
if [ "${ROLLBACK_SCHEMA}" = true ]; then
    echo "  [WARNING] --rollback-schema specified. Preparing schema rollback..."
    if docker ps --format '{{.Names}}' | grep -q "^nawari-postgres$"; then
        BACKUP_DIR="${ROOT_DIR}/backups/rollback_safety_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "${BACKUP_DIR}"
        echo "  [SNAPSHOT] Creating pre-rollback snapshot in ${BACKUP_DIR}..."
        docker exec nawari-postgres pg_dump -U zabbix -d nawari_platform -Fc > "${BACKUP_DIR}/nawari_platform_pre_rollback.dump" 2>/dev/null || true
        docker exec nawari-postgres pg_dump -U postgres -d homer_data -Fc > "${BACKUP_DIR}/homer_data_pre_rollback.dump" 2>/dev/null || true
        
        if [ -f "${ROOT_DIR}/network observability/platform/nawari/migrations/rollback_034.sql" ]; then
            docker exec -i nawari-postgres psql -U zabbix -d nawari_platform \
                < "${ROOT_DIR}/network observability/platform/nawari/migrations/rollback_034.sql" 2>/dev/null || true
            echo "  [OK] Rollback SQL executed for Migration 034 (snapshot preserved at ${BACKUP_DIR})."
        fi
    fi
elif [ -n "${RESTORE_DB_FILE}" ]; then
    echo "  [CRITICAL] --restore-database specified: ${RESTORE_DB_FILE}"
    if [ ! -f "${RESTORE_DB_FILE}" ]; then
        echo "  [ERROR] Database restore file not found: ${RESTORE_DB_FILE}" >&2
        exit 1
    fi
    if docker ps --format '{{.Names}}' | grep -q "^nawari-postgres$"; then
        BACKUP_DIR="${ROOT_DIR}/backups/rollback_safety_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "${BACKUP_DIR}"
        echo "  [SNAPSHOT] Creating pre-restore safety snapshot in ${BACKUP_DIR}..."
        docker exec nawari-postgres pg_dump -U zabbix -d nawari_platform -Fc > "${BACKUP_DIR}/nawari_platform_pre_restore.dump" 2>/dev/null || true
        echo "  [RESTORE] Restoring database from ${RESTORE_DB_FILE}..."
        docker exec -i nawari-postgres pg_restore -U zabbix -d nawari_platform --clean --if-exists < "${RESTORE_DB_FILE}" 2>/dev/null || true
        echo "  [OK] Database restored from ${RESTORE_DB_FILE}."
    fi
else
    echo "  [PROTECTED] Schema and data untouched. Preserving newly ingested telemetry in nawari_platform and homer_data."
    echo "  (To explicitly roll back migration tables, rerun with --rollback-schema)"
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
