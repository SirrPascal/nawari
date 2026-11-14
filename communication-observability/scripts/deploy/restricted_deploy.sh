#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Restricted Production Deployment Controller (Stage D & E & F)
# Target: mon-grafana01 (Ubuntu 24.04 LTS, 10.2.1.58)
# Designed to be installed at: /usr/local/bin/nawari-deploy (root:root, 0750)
# ==============================================================================
set -euo pipefail

# ------------------------------------------------------------------------------
# 0. Global Constants & Hardcoded Boundaries
# ------------------------------------------------------------------------------
ALLOWED_REGISTRY="ghcr.io"
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
MIN_FREE_DISK_MB=2000
MIN_FREE_MEM_MB=400

MONITORING_CONTAINERS=(
    "nawari-postgres"
    "nawari-zabbix-server"
    "nawari-zabbix-web"
    "nawari-grafana"
    "nawari-snmptraps"
)
ROLLBACK_BIN="/usr/local/bin/nawari-rollback"
declare -A MONITORING_CONTAINER_IDS=()

# ------------------------------------------------------------------------------
# 1. Logging and Output Helpers
# ------------------------------------------------------------------------------
log() {
    local msg="[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] $*"
    echo "${msg}"
    if [ -d "$(dirname "${LOG_FILE}")" ] && [ -w "$(dirname "${LOG_FILE}")" ]; then
        echo "${msg}" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

error() {
    local msg="[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [ERROR] $*"
    echo "${msg}" >&2
    if [ -d "$(dirname "${LOG_FILE}")" ] && [ -w "$(dirname "${LOG_FILE}")" ]; then
        echo "${msg}" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

capture_monitoring_state() {
    local phase="$1"
    local container container_id
    for container in "${MONITORING_CONTAINERS[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
            container_id=$(docker inspect --format '{{.Id}}' "${container}")
            MONITORING_CONTAINER_IDS["${container}"]="${container_id}"
            log "    ${phase}: ${container} id=${container_id}"
        else
            MONITORING_CONTAINER_IDS["${container}"]="ABSENT"
            log "    ${phase}: ${container} ABSENT (not silently skipped)"
        fi
    done
}

verify_monitoring_state() {
    local phase="$1"
    local container current_id expected_id
    for container in "${MONITORING_CONTAINERS[@]}"; do
        expected_id="${MONITORING_CONTAINER_IDS[${container}]}"
        if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
            current_id=$(docker inspect --format '{{.Id}}' "${container}")
            if [[ "${expected_id}" == "ABSENT" || "${current_id}" != "${expected_id}" ]]; then
                error "${phase}: protected container ${container} changed (before=${expected_id}, after=${current_id})"
                return 1
            fi
        elif [[ "${expected_id}" != "ABSENT" ]]; then
            error "${phase}: protected container ${container} disappeared"
            return 1
        else
            log "    ${phase}: ${container} remains ABSENT"
        fi
    done
}

# ------------------------------------------------------------------------------
# 2. Argument Parsing & Strict Input Validation
# ------------------------------------------------------------------------------
RAW_DIGEST=""
PROFILE="staging"
REPO_DIR="${DEFAULT_REPO_DIR}"
PHASE_8_2_CERTIFIED="false"

usage() {
    cat <<EOF
Usage: $0 --digest <IMAGE_DIGEST> [--profile <PROFILE>] [--repo-dir <DIR>] [--phase-8-2-certified]
Example: $0 --digest sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069 --profile staging
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --digest)
            RAW_DIGEST="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --repo-dir)
            REPO_DIR="$2"
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
            error "Unknown or disallowed argument: $1"
            usage
            ;;
    esac
done

if [[ -z "${RAW_DIGEST}" ]]; then
    error "Missing required argument: --digest"
    usage
fi

# Sanitize input: allow only alphanumeric and sha256 prefix format
CLEAN_DIGEST=""
if [[ "${RAW_DIGEST}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    CLEAN_DIGEST="${RAW_DIGEST}"
elif [[ "${RAW_DIGEST}" =~ ^${ALLOWED_IMAGE}@sha256:([a-f0-9]{64})$ ]]; then
    CLEAN_DIGEST="sha256:${BASH_REMATCH[1]}"
elif [[ "${RAW_DIGEST}" =~ ^[a-f0-9]{64}$ ]]; then
    CLEAN_DIGEST="sha256:${RAW_DIGEST}"
else
    error "Invalid image digest syntax. Expected sha256:[a-f0-9]{64}, got: '${RAW_DIGEST}'"
    exit 1
fi

# Validate profile input against allowlist
case "${PROFILE}" in
    staging|single-site-production|simulation)
        ;;
    *)
        error "Disallowed profile '${PROFILE}'. Allowed profiles: [staging, single-site-production, simulation]"
        exit 1
        ;;
esac

# Validate repo directory path exists
if [[ ! -d "${REPO_DIR}" ]]; then
    error "Repository directory '${REPO_DIR}' does not exist!"
    exit 1
fi

for protected_file in \
    "${REPO_DIR}/docker/compose.yaml" \
    "${REPO_DIR}/docker/compose.app.yaml" \
    "${REPO_DIR}/scripts/deploy/check_gating.py"; do
    if [[ -e "${protected_file}" ]] && find "${protected_file}" -prune -perm /022 -print -quit | grep -q .; then
        error "Deployment input is writable by group or others: ${protected_file}"
        exit 1
    fi
done

TARGET_IMAGE="${ALLOWED_IMAGE}@${CLEAN_DIGEST}"

log "=================================================================="
log "NAWARI CONTROLLED DEPLOYMENT SEQUENCE"
log "Target Profile:   ${PROFILE}"
log "Target Digest:    ${CLEAN_DIGEST}"
log "Target Image:     ${TARGET_IMAGE}"
log "Working Repo Dir: ${REPO_DIR}"
log "=================================================================="

# Ensure state and log directories exist
mkdir -p "${STATE_DIR}" "$(dirname "${LOG_FILE}")" 2>/dev/null || true

# ------------------------------------------------------------------------------
# 3. Stage C Safety Gate: HARD_PRODUCTION_DENY Enforcement
# ------------------------------------------------------------------------------
log "--> [Gate C] Evaluating deployment eligibility and commissioning gate..."
PYTHON_BIN="python3"
if command -v /opt/nawari/bin/python3 >/dev/null 2>&1; then
    PYTHON_BIN="/opt/nawari/bin/python3"
elif command -v /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 >/dev/null 2>&1; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
fi

if [[ -f "${REPO_DIR}/scripts/deploy/check_gating.py" ]]; then
    GATING_ARGS=("--profile" "${PROFILE}")
    if [[ "${PHASE_8_2_CERTIFIED}" == "true" ]]; then
        GATING_ARGS+=("--phase-8-2-certified")
    fi
    if ! PYTHONPATH="${REPO_DIR}" "${PYTHON_BIN}" "${REPO_DIR}/scripts/deploy/check_gating.py" "${GATING_ARGS[@]}"; then
        error "Deployment rejected by safety gate. HARD_PRODUCTION_DENY is enforced. Aborting."
        exit 2
    fi
else
    log "Notice: check_gating.py not found in ${REPO_DIR}/scripts/deploy; using profile safety default"
    if [[ "${PROFILE}" == "single-site-production" && "${PHASE_8_2_CERTIFIED}" != "true" ]]; then
        error "Phase 8.2 physical commissioning certification missing for production profile. HARD_PRODUCTION_DENY."
        exit 2
    fi
fi

# ------------------------------------------------------------------------------
# 4. Host Health & Resource Preflight Checks
# ------------------------------------------------------------------------------
log "--> [Preflight] Checking host resource headroom (disk & memory)..."

# Check root disk space
if command -v df >/dev/null 2>&1; then
    FREE_DISK_MB=$(df -m / | awk 'NR==2 {print $4}')
    if [[ "${FREE_DISK_MB}" -lt "${MIN_FREE_DISK_MB}" ]]; then
        error "Insufficient host disk space: ${FREE_DISK_MB} MB free (minimum ${MIN_FREE_DISK_MB} MB required)!"
        exit 1
    fi
    log "    Disk Headroom: ${FREE_DISK_MB} MB free (OK)"
fi

# Check available memory
if command -v free >/dev/null 2>&1; then
    FREE_MEM_MB=$(free -m | awk '/^Mem:/ {print $7}')
    if [[ -n "${FREE_MEM_MB}" && "${FREE_MEM_MB}" -lt "${MIN_FREE_MEM_MB}" ]]; then
        error "Insufficient host memory headroom: ${FREE_MEM_MB} MB available (minimum ${MIN_FREE_MEM_MB} MB required)!"
        exit 1
    fi
    log "    Memory Headroom: ${FREE_MEM_MB} MB available (OK)"
fi

# Verify existing core monitoring stack containers are healthy before modifying app
log "--> [Preflight] Verifying health of authoritative monitoring infrastructure..."
if command -v docker >/dev/null 2>&1; then
    capture_monitoring_state "BEFORE"
    for c in "${MONITORING_CONTAINERS[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
            HEALTH_STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "${c}" 2>/dev/null || echo "unknown")
            if [[ "${HEALTH_STATUS}" != "healthy" && "${HEALTH_STATUS}" != "running" ]]; then
                error "Authoritative monitoring container '${c}' is in state '${HEALTH_STATUS}'. Deployment aborted to protect monitoring integrity."
                exit 1
            fi
            log "    Monitoring Container ${c}: ${HEALTH_STATUS} (OK)"
        else
            log "    Notice: Optional monitoring container '${c}' not running in this environment"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 5. Capture Last Known Good State for Controlled Rollback
# ------------------------------------------------------------------------------
CURRENT_ACTIVE_IMAGE=""
if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' | grep -q "^${APP_CONTAINER_NAME}$"; then
        CURRENT_ACTIVE_IMAGE=$(docker inspect --format '{{.Config.Image}}' "${APP_CONTAINER_NAME}" 2>/dev/null || true)
        if [[ -n "${CURRENT_ACTIVE_IMAGE}" ]]; then
            log "--> Active image before deployment: ${CURRENT_ACTIVE_IMAGE}"
            echo "${CURRENT_ACTIVE_IMAGE}" > "${LAST_KNOWN_GOOD_FILE}" 2>/dev/null || true
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 6. Pull Immutable Application Image from GHCR
# ------------------------------------------------------------------------------
log "--> Pulling application image by immutable digest: ${TARGET_IMAGE}..."
if command -v docker >/dev/null 2>&1; then
    if ! docker pull "${TARGET_IMAGE}"; then
        error "Failed to pull image ${TARGET_IMAGE} from registry!"
        exit 1
    fi
    log "    Image pull completed successfully."
fi

# ------------------------------------------------------------------------------
# 7. Atomic Application Service Deployment (--no-deps nawari-core)
# ------------------------------------------------------------------------------
log "--> Deploying application container '${APP_SERVICE_NAME}'..."
cd "${REPO_DIR}"

COMPOSE_FILES=("-f" "docker/compose.yaml")
if [[ -f "docker/compose.prod.yaml" ]]; then
    COMPOSE_FILES+=("-f" "docker/compose.prod.yaml")
fi
if [[ -f "docker/compose.app.yaml" ]]; then
    COMPOSE_FILES+=("-f" "docker/compose.app.yaml")
fi

export NAWARI_CORE_IMAGE="${ALLOWED_IMAGE}"
export NAWARI_CORE_TAG="@${CLEAN_DIGEST}"
export NAWARI_PROFILE="${PROFILE}"
export NAWARI_ENV="${PROFILE}"

# Execute targeted update: strictly --no-deps nawari-core to avoid restarting Postgres/Zabbix/Grafana
DEPLOY_CMD=(docker compose "${COMPOSE_FILES[@]}" up -d --no-deps "${APP_SERVICE_NAME}")

log "    Executing: ${DEPLOY_CMD[*]}"
if ! "${DEPLOY_CMD[@]}"; then
    error "Docker Compose failed to start ${APP_SERVICE_NAME}!"
    trigger_rollback
    exit 1
fi

# ------------------------------------------------------------------------------
# 8. Post-Deployment Health Verification (Stage E)
# ------------------------------------------------------------------------------
log "--> [Stage E] Initiating post-deployment health verification..."

verify_health() {
    local attempts=10
    local delay=3
    local url="${HEALTH_ENDPOINT}"

    log "    Polling health endpoint ${url} (max ${attempts} attempts)..."
    for ((i=1; i<=attempts; i++)); do
        if curl -f -s --max-time 3 "${url}" >/dev/null 2>&1; then
            log "    Health verification PASSED on attempt ${i}."
            return 0
        fi
        sleep "${delay}"
    done
    return 1
}

trigger_rollback() {
    error "Health verification FAILED! Initiating automatic controlled rollback..."
    if [[ -x "${ROLLBACK_BIN}" ]]; then
        ROLLBACK_CERT_ARGS=()
        if [[ "${PHASE_8_2_CERTIFIED}" == "true" ]]; then
            ROLLBACK_CERT_ARGS+=(--phase-8-2-certified)
        fi
        "${ROLLBACK_BIN}" --repo-dir "${REPO_DIR}" --profile "${PROFILE}" \
            "${ROLLBACK_CERT_ARGS[@]}" || {
            error "CRITICAL: Automatic rollback script failed! Manual intervention required."
            exit 3
        }
    elif [[ -f "${LAST_KNOWN_GOOD_FILE}" && -s "${LAST_KNOWN_GOOD_FILE}" ]]; then
        local prev_img
        prev_img=$(cat "${LAST_KNOWN_GOOD_FILE}")
        log "    Restoring previous image: ${prev_img}"
        export NAWARI_CORE_IMAGE="${prev_img}"
        export NAWARI_CORE_TAG=""
        docker compose "${COMPOSE_FILES[@]}" up -d --no-deps "${APP_SERVICE_NAME}"
    else
        error "No last known good image recorded. Cannot execute automatic rollback."
    fi
}

if ! verify_health; then
    # Capture error diagnostic logs
    if command -v docker >/dev/null 2>&1; then
        log "--- START CONTAINER LOGS (FAILURE DIAGNOSTICS) ---"
        docker logs --tail 30 "${APP_CONTAINER_NAME}" 2>&1 || true
        log "--- END CONTAINER LOGS ---"
    fi
    trigger_rollback
    exit 1
fi

# Verify monitoring stack is STILL healthy
log "--> [Stage E] Confirming monitoring stack integrity after application update..."
if command -v docker >/dev/null 2>&1; then
    verify_monitoring_state "AFTER" || {
        error "Protected monitoring infrastructure changed; initiating rollback."
        trigger_rollback
        exit 1
    }
    for c in "${MONITORING_CONTAINERS[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
            HEALTH_STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "${c}" 2>/dev/null || echo "unknown")
            log "    Monitoring Container ${c}: ${HEALTH_STATUS} (UNTOUCHED)"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 9. Audit Recording & Success Output
# ------------------------------------------------------------------------------
DEPLOY_TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
AUDIT_ENTRY="{\"timestamp\": \"${DEPLOY_TIMESTAMP}\", \"digest\": \"${CLEAN_DIGEST}\", \"profile\": \"${PROFILE}\", \"status\": \"SUCCESS\", \"image\": \"${TARGET_IMAGE}\"}"

if [ -d "${STATE_DIR}" ]; then
    echo "${AUDIT_ENTRY}" >> "${HISTORY_FILE}" 2>/dev/null || true
    echo "${CLEAN_DIGEST}" > "${LAST_KNOWN_GOOD_FILE}" 2>/dev/null || true
fi

log "=================================================================="
log "NAWARI DEPLOYMENT COMPLETED SUCCESSFULLY"
log "Active Digest: ${CLEAN_DIGEST}"
log "Timestamp:     ${DEPLOY_TIMESTAMP}"
log "=================================================================="

# Print clean JSON summary to stdout
echo "${AUDIT_ENTRY}"
exit 0
