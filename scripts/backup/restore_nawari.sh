#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Enterprise Production Cold Restore Automation (Workstream 8B)
# Target: mon-grafana01 (Ubuntu 24.04 LTS / Docker Compose)
# RTO Target: <= 30.0 Minutes
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKUP_TARGET="${1:-}"

if [ -z "${BACKUP_TARGET}" ]; then
    echo "Usage: $0 <path_to_backup_directory_or_db_dump>" >&2
    echo "Example: $0 /var/backups/nawari/20261108_020000" >&2
    exit 1
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-nawari-postgres}"
POSTGRES_USER="${POSTGRES_USER:-zabbix}"
POSTGRES_DB="${POSTGRES_DB:-zabbix}"

echo "==> [Nawari Restore] Initiating disaster recovery restoration from: ${BACKUP_TARGET}"

TARGET_DIR=""
DB_DUMP=""

if [ -d "${BACKUP_TARGET}" ]; then
    TARGET_DIR="${BACKUP_TARGET}"
    # Find database dump in directory
    DB_DUMP="$(ls -1 "${TARGET_DIR}"/nawari_db_*.sql.gz 2>/dev/null | head -n 1 || true)"
elif [ -f "${BACKUP_TARGET}" ]; then
    DB_DUMP="${BACKUP_TARGET}"
    TARGET_DIR="$(dirname "${BACKUP_TARGET}")"
fi

if [ -z "${DB_DUMP}" ] || [ ! -f "${DB_DUMP}" ]; then
    echo "ERROR: Could not locate database dump (.sql.gz) in ${BACKUP_TARGET}" >&2
    exit 1
fi

# 1. Cryptographic SHA-256 Integrity Verification
if [ -f "${TARGET_DIR}/SHA256SUMS" ]; then
    echo "--> Verifying SHA-256 checksums..."
    cd "${TARGET_DIR}"
    if sha256sum --check --status SHA256SUMS 2>/dev/null; then
        echo "    Integrity verified: SHA-256 signatures match."
    else
        echo "ERROR: SHA-256 checksum verification failed! Archive may be corrupt or tampered with." >&2
        exit 2
    fi
    cd "${PROJECT_ROOT}"
else
    echo "WARNING: SHA256SUMS file not found in ${TARGET_DIR}; skipping cryptographic verification."
fi

# 2. Verify Target Container Readiness
echo "--> Verifying PostgreSQL container (${POSTGRES_CONTAINER}) connectivity..."
if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo "ERROR: PostgreSQL container ${POSTGRES_CONTAINER} is not running!" >&2
    exit 1
fi

until docker exec "${POSTGRES_CONTAINER}" pg_isready -h localhost -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    echo "    Waiting for PostgreSQL to accept connections..."
    sleep 2
done
echo "    PostgreSQL is ready."

# 3. Database Restoration
echo "--> Restoring database from ${DB_DUMP}..."
gunzip -c "${DB_DUMP}" | docker exec -i "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1

echo "    Database restoration stream complete."

# 4. Post-Restore Verification
echo "--> Performing database sanity checks..."
HOST_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c "SELECT COUNT(*) FROM hosts;" 2>/dev/null || echo "0")
ITEM_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c "SELECT COUNT(*) FROM items;" 2>/dev/null || echo "0")

echo "    Sanity Check: ${HOST_COUNT} hosts and ${ITEM_COUNT} items present in database."

if [ "${HOST_COUNT}" -eq 0 ]; then
    echo "WARNING: Database contains 0 hosts. Please verify restoration integrity."
fi

echo "==> [Nawari Restore] Cold restoration successfully completed!"
