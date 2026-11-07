#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Mock SNMP Agent Fault Injection Script
# ==============================================================================
set -euo pipefail

CMD="${1:-help}"
IFACE="${2:-ge-0-0-1}"

case "${CMD}" in
    link-down)
        echo "[FAULT-INJECTION] Setting interface ${IFACE} DOWN..."
        ip link set "${IFACE}" down
        echo "[FAULT-INJECTION] Interface ${IFACE} is now DOWN (ifOperStatus should report down/2)."
        ;;
    link-up)
        echo "[FAULT-INJECTION] Setting interface ${IFACE} UP..."
        ip link set "${IFACE}" up
        echo "[FAULT-INJECTION] Interface ${IFACE} is now UP (ifOperStatus should report up/1)."
        ;;
    status)
        ip link show "${IFACE}"
        ;;
    *)
        echo "Usage: $0 {link-down|link-up|status} [interface_name]"
        exit 1
        ;;
esac
