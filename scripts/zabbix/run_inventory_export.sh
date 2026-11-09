#!/usr/bin/env bash
# =============================================================================
# Nawari – Zabbix Inventory Export Helper
#
# Run this script on mon-grafana01 (10.2.1.58) where the Zabbix stack is live.
#
# Usage:
#   ZBX_API_TOKEN=<token> bash scripts/zabbix/run_inventory_export.sh
#
# Or, if you have a .env file on the server:
#   set -a && source .env && set +a
#   bash scripts/zabbix/run_inventory_export.sh
#
# Outputs:
#   scripts/zabbix/export_host_inventory.csv
#   scripts/zabbix/export_host_inventory.json
#
# No credentials are printed or stored in log files.
# This script is READ-ONLY: it makes no changes to Zabbix.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default endpoint – the Zabbix frontend inside docker binds to ZBX_WEB_PORT
# (typically 8088 on the host, proxied to 8080 on the loopback, etc.)
# Override by setting ZBX_API_URL before running.
ZBX_API_URL="${ZBX_API_URL:-http://127.0.0.1:8080/api_jsonrpc.php}"
export ZBX_API_URL

if [[ -z "${ZBX_API_TOKEN:-}" ]]; then
  # Try loading from .env in the project root
  ENV_FILE="$(cd "$SCRIPT_DIR/../.." && pwd)/.env"
  if [[ -f "$ENV_FILE" ]]; then
    echo "[info] ZBX_API_TOKEN not set – loading from $ENV_FILE"
    # shellcheck disable=SC1090
    set -a
    source "$ENV_FILE"
    set +a
  fi
fi

if [[ -z "${ZBX_API_TOKEN:-}" ]]; then
  echo "[error] ZBX_API_TOKEN is not set and could not be loaded from .env" >&2
  echo "        Generate a token in Zabbix → Administration → API tokens" >&2
  exit 1
fi

export ZBX_API_TOKEN

echo "[info] Testing Zabbix API connectivity at $ZBX_API_URL ..."
VERSION_RESP=$(curl -sf --connect-timeout 5 "$ZBX_API_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"apiinfo.version","params":[],"id":1}' \
  2>&1) || {
  echo "[error] Cannot reach Zabbix API at $ZBX_API_URL" >&2
  echo "        Is the Zabbix stack running? Check: docker compose -f docker/compose.yaml ps" >&2
  exit 1
}
ZBXVER=$(echo "$VERSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result','unknown'))" 2>/dev/null || echo "unknown")
echo "[info] Zabbix API reachable – version: $ZBXVER"

echo "[info] Running inventory export ..."
python3 "$SCRIPT_DIR/export_host_inventory.py"

echo "[info] Export files:"
ls -lh "$SCRIPT_DIR/export_host_inventory.csv" "$SCRIPT_DIR/export_host_inventory.json"
echo ""
echo "[info] CSV preview (first 20 rows):"
head -n 20 "$SCRIPT_DIR/export_host_inventory.csv"

