#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Enterprise Production Backup Automation (Workstream 8B)
# Target: mon-grafana01 (Ubuntu 24.04 LTS / Docker Compose)
# RPO Objective: <= 1.0 Hour | RTO Objective: <= 30.0 Minutes
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_ROOT="${NAWARI_BACKUP_DIR:-${PROJECT_ROOT}/backups}"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
RETENTION_DAYS="${NAWARI_BACKUP_RETENTION_DAYS:-7}"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-nawari-postgres}"
POSTGRES_USER="${POSTGRES_USER:-zabbix}"
POSTGRES_DB="${POSTGRES_DB:-zabbix}"

mkdir -p "${BACKUP_DIR}"
echo "==> [Nawari Backup] Starting backup sequence at ${TIMESTAMP}..."
echo "--> Output Directory: ${BACKUP_DIR}"

# 1. PostgreSQL Telemetry, State & Configuration Dump
DB_BACKUP_FILE="${BACKUP_DIR}/nawari_db_${TIMESTAMP}.sql.gz"
echo "--> Dumping PostgreSQL database (${POSTGRES_DB}) from ${POSTGRES_CONTAINER}..."
if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    docker exec "${POSTGRES_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists | gzip -c > "${DB_BACKUP_FILE}"
else
    echo "ERROR: PostgreSQL container ${POSTGRES_CONTAINER} is not running!" >&2
    exit 1
fi

# Verify dump file size
if [ ! -s "${DB_BACKUP_FILE}" ]; then
    echo "ERROR: Database dump file is empty or missing: ${DB_BACKUP_FILE}" >&2
    exit 1
fi
echo "    Database dump created successfully ($(du -h "${DB_BACKUP_FILE}" | cut -f1))"

# 2. Archive Grafana Provisioning & Dashboards
GRAFANA_ARCHIVE="${BACKUP_DIR}/nawari_grafana_${TIMESTAMP}.tar.gz"
echo "--> Archiving Grafana configuration and dashboards..."
if [ -d "${PROJECT_ROOT}/docker/grafana" ]; then
    tar -czf "${GRAFANA_ARCHIVE}" -C "${PROJECT_ROOT}/docker/grafana" dashboards provisioning
    echo "    Grafana archive created ($(du -h "${GRAFANA_ARCHIVE}" | cut -f1))"
fi

# 3. Archive System Configuration & Environment Metadata (excluding raw passwords)
CONFIG_ARCHIVE="${BACKUP_DIR}/nawari_config_${TIMESTAMP}.tar.gz"
echo "--> Archiving Docker compose configuration and provisioning templates..."
tar -czf "${CONFIG_ARCHIVE}" -C "${PROJECT_ROOT}" \
    docker/compose.yaml \
    docker/compose.prod.yaml \
    docker/security \
    provisioning
echo "    Configuration archive created ($(du -h "${CONFIG_ARCHIVE}" | cut -f1))"

# 4. Generate Cryptographic SHA-256 Checksums
echo "--> Generating SHA-256 checksums..."
cd "${BACKUP_DIR}"
sha256sum *.gz > SHA256SUMS
cd "${PROJECT_ROOT}"
echo "    Checksums generated in ${BACKUP_DIR}/SHA256SUMS"

# 5. Optional Encryption (if GPG recipient configured)
if [ -n "${NAWARI_BACKUP_GPG_RECIPIENT:-}" ]; then
    echo "--> Encrypting backup bundle with GPG for recipient: ${NAWARI_BACKUP_GPG_RECIPIENT}..."
    tar -czf "${BACKUP_DIR}.tar.gz" -C "${BACKUP_ROOT}" "${TIMESTAMP}"
    gpg --encrypt --recipient "${NAWARI_BACKUP_GPG_RECIPIENT}" --trust-model always "${BACKUP_DIR}.tar.gz"
    rm -f "${BACKUP_DIR}.tar.gz"
    echo "    Encrypted bundle: ${BACKUP_DIR}.tar.gz.gpg"
fi

# 6. Retention Management: Prune backups older than RETENTION_DAYS
echo "--> Pruning backups older than ${RETENTION_DAYS} days in ${BACKUP_ROOT}..."
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null || true

echo "==> [Nawari Backup] Completed successfully at $(date +%Y-%m-%d\ %H:%M:%S)!"
echo "${BACKUP_DIR}"
