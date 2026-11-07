#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Mock SNMP Agent Entrypoint
# ==============================================================================
set -e

echo "[MOCK-SNMP] Initializing virtual network interfaces for IF-MIB simulation..."

# Create dummy network interfaces to simulate a core switch / router
# ge-0/0/1: Primary Core Uplink
# ge-0/0/2: Voice VLAN Trunk
# sbc-ext0: External SIP DMZ
# sbc-int0: Internal Media Interface
for iface in ge-0-0-1 ge-0-0-2 sbc-ext0 sbc-int0; do
    if ! ip link show "${iface}" >/dev/null 2>&1; then
        echo "[MOCK-SNMP] Creating dummy interface: ${iface}"
        ip link add "${iface}" type dummy || true
        ip link set "${iface}" up || true
    fi
done

# Assign dummy IP addresses for routing simulation
ip addr add 10.2.1.254/24 dev ge-0-0-1 2>/dev/null || true
ip addr add 10.2.156.1/24 dev ge-0-0-2 2>/dev/null || true

# Generate background traffic to advance ifHCInOctets / ifHCOutOctets
(
    while true; do
        ping -c 2 -W 1 127.0.0.1 >/dev/null 2>&1 || true
        sleep 5
    done
) &

# Optional SNMPv3 user creation from environment variables
if [ -n "${SNMPV3_USER:-}" ]; then
    echo "createUser ${SNMPV3_USER} SHA ${SNMPV3_AUTH_PASS:-auth_passphrase} DES ${SNMPV3_PRIV_PASS:-priv_passphrase}" >> /etc/snmp/snmpd.conf
    echo "rouser ${SNMPV3_USER} authpriv" >> /etc/snmp/snmpd.conf
fi

echo "[MOCK-SNMP] Starting Net-SNMP daemon (snmpd)..."
exec snmpd -f -Lo -C -c /etc/snmp/snmpd.conf
