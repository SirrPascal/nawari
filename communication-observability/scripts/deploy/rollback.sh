#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Application Rollback Controller (Stage F)
# Target: mon-grafana01 (Ubuntu 24.04 LTS, 10.2.1.58)
# Designed to be installed at: /usr/local/bin/nawari-rollback (root:root, 0750)
# ==============================================================================
set -euo pipefail

ALLOWED_IMAGE="ghcr.io/sirrpascal/nawari/nawari-core"
DEFAULT_REPO_DIR="/opt/nawari"
STATE_DIR="${DEFAULT_REPO_DIR}/state"
LOG_FILE="/var/log/nawari/deployments.log"
HISTORY_FILE="${STATE_DIR}/deployment_history.jsonl"
LAST_KNOWN_GOOD_FILE="${STATE_DIR}/last_known_good_digest"
APP_SERVICE_NAME="nawari-core"
APP_CONTAINER_NAME="nawari-core"
HEALTH_PORT=8443
HEALTH_ENDPOINT="http://127.0.0.1:${HEALTH_PORT}/api/v1/health"

log() {
    local msg="[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [ROLLBACK] $*"
    echo "${msg}"
    if [ -d "$(dirname "${LOG_FILE}")" ] && [ -w "$(dirname "${LOG_FILE}")" ]; then
        echo "${msg}" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

error() {
    local msg="[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [ROLLBACK ERROR] $*"
    echo "${msg}" >&2
    if [ -d "$(dirname "${LOG_FILE}")" ] && [ -w "$(dirname "${LOG_FILE}")" ]; then
        echo "${msg}" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

TARGET_DIGEST=""
REPO_DIR="${DEFAULT_REPO_DIR}"
PROFILE="staging"
PHASE_8_2_CERTIFIED="false"

usage() {
    cat <<EOF
Usage: $0 [--digest <IMAGE_DIGEST>] [--repo-dir <DIR>]
If --digest is omitted, the previous known good digest from ${LAST_KNOWN_GOOD_FILE} is used.
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --digest)
            TARGET_DIGEST="$2"
            shift 2
            ;;
        --repo-dir)
            REPO_DIR="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --phase-8-2-certified)
            PHASE_8_2_CERTIFIED="true"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown argument: $1"
            usage
            ;;
    esac
done

case "${PROFILE}" in
    staging|single-site-production|simulation) ;;
    *)
        error "Disallowed profile '${PROFILE}'"
        exit 1
        ;;
esac

if [[ -f "${REPO_DIR}/scripts/deploy/check_gating.py" ]]; then
    GATING_ARGS=(--profile "${PROFILE}")
    if [[ "${PHASE_8_2_CERTIFIED}" == "true" ]]; then
        GATING_ARGS+=(--phase-8-2-certified)
    fi
    if ! PYTHONPATH="${REPO_DIR}" python3 "${REPO_DIR}/scripts/deploy/check_gating.py" "${GATING_ARGS[@]}"; then
        error "Rollback rejected by HARD_PRODUCTION_DENY safety gate."
        exit 2
    fi
fi

if [[ -z "${TARGET_DIGEST}" ]]; then
    if [[ -f "${LAST_KNOWN_GOOD_FILE}" && -s "${LAST_KNOWN_GOOD_FILE}" ]]; then
        TARGET_DIGEST=$(head -n 1 "${LAST_KNOWN_GOOD_FILE}" | tr -d '[:space:]')
        log "Discovered last known good digest from state: ${TARGET_DIGEST}"
    else
        error "No target digest provided and ${LAST_KNOWN_GOOD_FILE} does not exist or is empty!"
        exit 1
    fi
fi

# Sanitize digest
CLEAN_DIGEST=""
if [[ "${TARGET_DIGEST}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    CLEAN_DIGEST="${TARGET_DIGEST}"
elif [[ "${TARGET_DIGEST}" =~ ^${ALLOWED_IMAGE}@sha256:([a-f0-9]{64})$ ]]; then
    CLEAN_DIGEST="sha256:${BASH_REMATCH[1]}"
elif [[ "${TARGET_DIGEST}" =~ ^[a-f0-9]{64}$ ]]; then
    CLEAN_DIGEST="sha256:${TARGET_DIGEST}"
else
    error "Invalid rollback digest format: '${TARGET_DIGEST}'"
    exit 1
fi

log "=================================================================="
log "NAWARI CONTROLLED ROLLBACK SEQUENCE"
log "Target Rollback Target: ${CLEAN_DIGEST}"
log "Repo Directory:         ${REPO_DIR}"
log "=================================================================="

cd "${REPO_DIR}"

COMPOSE_FILES=("-f" "docker/compose.yaml")
if [[ -f "docker/compose.prod.yaml" ]]; then
    COMPOSE_FILES+=("-f" "docker/compose.prod.yaml")
fi
if [[ -f "docker/compose.app.yaml" ]]; then
    COMPOSE_FILES+=("-f" "docker/compose.app.yaml")
fi

if [[ "${CLEAN_DIGEST}" =~ ^sha256: ]]; then
    export NAWARI_CORE_IMAGE="${ALLOWED_IMAGE}"
    export NAWARI_CORE_TAG="@${CLEAN_DIGEST}"
    FULL_ROLLBACK_IMAGE="${ALLOWED_IMAGE}@${CLEAN_DIGEST}"
else
    export NAWARI_CORE_IMAGE="${CLEAN_DIGEST}"
    export NAWARI_CORE_TAG=""
    FULL_ROLLBACK_IMAGE="${CLEAN_DIGEST}"
fi

# Pull rollback image
if command -v docker >/dev/null 2>&1 && [[ "${CLEAN_DIGEST}" =~ ^sha256: ]]; then
    log "--> Pulling rollback image ${FULL_ROLLBACK_IMAGE}..."
    docker pull "${FULL_ROLLBACK_IMAGE}" || log "Notice: Local image cache will be used"
fi

# Re-deploy ONLY nawari-core with --no-deps
log "--> Recreating ${APP_SERVICE_NAME} container to rollback target..."
docker compose "${COMPOSE_FILES[@]}" up -d --no-deps "${APP_SERVICE_NAME}"

# Verify health
log "--> Verifying health of rolled-back container..."
HEALTH_OK=false
for ((i=1; i<=10; i++)); do
    if curl -f -s --max-time 3 "${HEALTH_ENDPOINT}" >/dev/null 2>&1; then
        HEALTH_OK=true
        log "    Health check PASSED after rollback (attempt ${i})."
        break
    fi
    sleep 3
done

if [[ "${HEALTH_OK}" != "true" ]]; then
    error "CRITICAL: Rolled-back container failed health check! Manual emergency intervention required."
    exit 2
fi

ROLLBACK_TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
AUDIT_ENTRY="{\"timestamp\": \"${ROLLBACK_TIMESTAMP}\", \"digest\": \"${CLEAN_DIGEST}\", \"status\": \"ROLLED_BACK\", \"image\": \"${FULL_ROLLBACK_IMAGE}\"}"

if [ -d "${STATE_DIR}" ]; then
    echo "${AUDIT_ENTRY}" >> "${HISTORY_FILE}" 2>/dev/null || true
fi

log "=================================================================="
log "ROLLBACK SUCCESSFULLY COMPLETED"
log "Active Digest: ${CLEAN_DIGEST}"
log "Timestamp:     ${ROLLBACK_TIMESTAMP}"
log "=================================================================="

echo "${AUDIT_ENTRY}"
exit 0
