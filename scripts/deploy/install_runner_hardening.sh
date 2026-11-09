#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Runner Security Hardening & Script Installation
# Target: mon-grafana01 (Ubuntu 24.04 LTS, 10.2.1.58)
# To be executed as root on mon-grafana01 during initial host setup
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RUNNER_USER="${RUNNER_USER:-nawari-runner}"
RUNNER_GROUP="${RUNNER_GROUP:-nawari-runner}"
DEPLOY_BIN="/usr/local/bin/nawari-deploy"
ROLLBACK_BIN="/usr/local/bin/nawari-rollback"
SUDOERS_FILE="/etc/sudoers.d/nawari-deploy"
LOG_DIR="/var/log/nawari"
STATE_DIR="/opt/nawari/state"

echo "=================================================================="
echo "NAWARI SELF-HOSTED RUNNER HARDENING & INSTALLATION"
echo "Target Host:   mon-grafana01"
echo "Runner User:   ${RUNNER_USER}"
echo "Deploy Script: ${DEPLOY_BIN}"
echo "=================================================================="

# 1. Ensure runner user exists (without docker group membership)
if ! id "${RUNNER_USER}" >/dev/null 2>&1; then
    echo "--> Creating dedicated runner user: ${RUNNER_USER}..."
    groupadd -r "${RUNNER_GROUP}" || true
    useradd -r -g "${RUNNER_GROUP}" -d "/home/${RUNNER_USER}" -m -s /bin/bash "${RUNNER_USER}"
fi

# Ensure user is NOT in the docker group
if id -nG "${RUNNER_USER}" | grep -qw "docker"; then
    echo "--> WARNING: Removing ${RUNNER_USER} from 'docker' group to enforce least privilege..."
    gpasswd -d "${RUNNER_USER}" docker || true
fi

# 2. Install deployment controller to /usr/local/bin/nawari-deploy
echo "--> Installing deployment script to ${DEPLOY_BIN}..."
cp "${PROJECT_ROOT}/scripts/deploy/restricted_deploy.sh" "${DEPLOY_BIN}"
chown root:root "${DEPLOY_BIN}"
chmod 0750 "${DEPLOY_BIN}"

# 3. Install rollback controller to /usr/local/bin/nawari-rollback
echo "--> Installing rollback script to ${ROLLBACK_BIN}..."
cp "${PROJECT_ROOT}/scripts/deploy/rollback.sh" "${ROLLBACK_BIN}"
chown root:root "${ROLLBACK_BIN}"
chmod 0750 "${ROLLBACK_BIN}"

# 4. Install hardened sudoers policy
echo "--> Installing sudoers policy to ${SUDOERS_FILE}..."
cp "${PROJECT_ROOT}/deploy/security/sudoers_nawari_deploy" "${SUDOERS_FILE}"
sed -i "s/nawari-runner/${RUNNER_USER}/g" "${SUDOERS_FILE}"
chown root:root "${SUDOERS_FILE}"
chmod 0440 "${SUDOERS_FILE}"

# Validate sudoers syntax
if command -v visudo >/dev/null 2>&1; then
    visudo -cf "${SUDOERS_FILE}"
    echo "    Sudoers syntax verified successfully."
fi

# 5. Create logging and state directories
mkdir -p "${LOG_DIR}" "${STATE_DIR}"
chown -R root:"${RUNNER_GROUP}" "${LOG_DIR}" "${STATE_DIR}"
chmod 0770 "${LOG_DIR}" "${STATE_DIR}"

echo "=================================================================="
echo "INSTALLATION COMPLETE"
echo "Runner ${RUNNER_USER} can now trigger deployments strictly via:"
echo "  sudo /usr/local/bin/nawari-deploy --digest <digest> --profile <profile>"
echo "=================================================================="

