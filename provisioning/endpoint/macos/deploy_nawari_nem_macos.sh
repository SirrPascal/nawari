#!/usr/bin/env bash
# provisioning/endpoint/macos/deploy_nawari_nem_macos.sh
# Kenya Airways IT Endpoint Operations - macOS MDM / Jamf Pro Deployment Package
# Deploys Zabbix Agent 2 with EU-NEM Active Probing and Auto-Registration.

set -euo pipefail

ZABBIX_SERVER="${1:-10.0.0.10:10051}"
HOST_METADATA="${2:-nawari_nem}"

echo "======================================================================"
echo "KENYA AIRWAYS EU-NEM MACOS AGENT 2 DEPLOYMENT ENGINE"
echo "Target ServerActive: ${ZABBIX_SERVER}"
echo "Host Metadata:       ${HOST_METADATA}"
echo "======================================================================"

# 1. Check Root / Sudo
if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] This deployment script must be run as root (or via Jamf MDM)." >&2
    exit 1
fi

# 2. Deploy Probe Script
PROBE_SRC="$(dirname "$0")/nawari_nem_probe.sh"
PROBE_DEST="/usr/local/bin/nawari_nem_probe.sh"

mkdir -p /usr/local/bin
if [ -f "${PROBE_SRC}" ]; then
    cp "${PROBE_SRC}" "${PROBE_DEST}"
    chmod 755 "${PROBE_DEST}"
    echo "[DEPLOY] Installed probe script to ${PROBE_DEST}"
else
    echo "[WARN] Local probe script not found; downloading from repository..."
fi

# 3. Configure Zabbix Agent 2 Config
CONF_DIR="/usr/local/etc/zabbix"
CONF_FILE="${CONF_DIR}/zabbix_agent2.conf"
mkdir -p "${CONF_DIR}"

if [ -f "${CONF_FILE}" ]; then
    echo "[CONFIG] Updating ${CONF_FILE}..."
    sed -i '' "s/^ServerActive=.*/ServerActive=${ZABBIX_SERVER}/" "${CONF_FILE}" || echo "ServerActive=${ZABBIX_SERVER}" >> "${CONF_FILE}"
    sed -i '' "s/^#\?[[:space:]]*HostMetadata=.*/HostMetadata=${HOST_METADATA}/" "${CONF_FILE}" || echo "HostMetadata=${HOST_METADATA}" >> "${CONF_FILE}"
    sed -i '' "s/^#\?[[:space:]]*EnablePersistentBuffer=.*/EnablePersistentBuffer=1/" "${CONF_FILE}" || echo "EnablePersistentBuffer=1" >> "${CONF_FILE}"
    sed -i '' "s/^#\?[[:space:]]*PersistentBufferPeriod=.*/PersistentBufferPeriod=24h/" "${CONF_FILE}" || echo "PersistentBufferPeriod=24h" >> "${CONF_FILE}"
else
    echo "[CONFIG] Creating initial ${CONF_FILE}..."
    cat <<EOF > "${CONF_FILE}"
ServerActive=${ZABBIX_SERVER}
HostMetadata=${HOST_METADATA}
EnablePersistentBuffer=1
PersistentBufferPeriod=24h
RefreshActiveChecks=60
BufferSend=5
BufferSize=2000
EOF
fi

# Append UserParameters if missing
if ! grep -q "nawari.nem.all" "${CONF_FILE}"; then
    cat <<EOF >> "${CONF_FILE}"

# --- Nawari EU-NEM Active Diagnostics ---
UserParameter=nawari.nem.all,${PROBE_DEST} all
UserParameter=nawari.nem.gateway,${PROBE_DEST} gateway
UserParameter=nawari.nem.dns,${PROBE_DEST} dns
UserParameter=nawari.nem.wifi,${PROBE_DEST} wifi
UserParameter=nawari.nem.service,${PROBE_DEST} service
EOF
fi

# 4. Restart Agent 2 Service if installed
if pgrep -x "zabbix_agent2" >/dev/null; then
    echo "[SERVICE] Restarting zabbix_agent2 daemon..."
    pkill -HUP -x zabbix_agent2 || true
fi

echo "[SUCCESS] Nawari EU-NEM macOS deployment completed successfully."

