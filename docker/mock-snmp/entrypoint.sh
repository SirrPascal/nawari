#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Mock SNMP Agent Entrypoint
# ==============================================================================
set -e

echo "[MOCK-SNMP] Initializing virtual network interfaces for IF-MIB simulation..."

# Create dummy network interfaces to simulate a core switch and Avaya SBCE:
# ge-0-0-1: Primary Core Uplink
# ge-0-0-2: Voice VLAN Trunk
# sbc-ext0: Generic SBC external
# sbc-int0: Generic SBC internal
# M1: Avaya SBCE Primary Management
# M2: Avaya SBCE Secondary Management
# A1: Avaya SBCE External DMZ (Signaling / Carrier SIP Trunks)
# B1: Avaya SBCE Internal Media / Core Signaling
for iface in ge-0-0-1 ge-0-0-2 sbc-ext0 sbc-int0 M1 M2 A1 B1; do
    if ! ip link show "${iface}" >/dev/null 2>&1; then
        echo "[MOCK-SNMP] Creating dummy interface: ${iface}"
        ip link add "${iface}" type dummy || true
        ip link set "${iface}" up || true
    fi
done

# Assign dummy IP addresses for routing simulation
ip addr add 10.2.1.254/24 dev ge-0-0-1 2>/dev/null || true
ip addr add 10.2.156.1/24 dev ge-0-0-2 2>/dev/null || true
ip addr add 10.2.156.131/24 dev M1 2>/dev/null || true
ip addr add 10.2.156.133/24 dev A1 2>/dev/null || true
ip addr add 10.2.156.134/24 dev B1 2>/dev/null || true

# Generate background traffic to advance ifHCInOctets / ifHCOutOctets on SBCE and core interfaces
(
    while true; do
        ping -c 2 -W 1 127.0.0.1 >/dev/null 2>&1 || true
        ping -c 2 -W 1 -I M1 10.2.156.131 >/dev/null 2>&1 || true
        ping -c 2 -W 1 -I A1 10.2.156.133 >/dev/null 2>&1 || true
        sleep 5
    done
) &

# Initialize SNMPv3 users directly into snmpd.conf
echo "createUser ${AVAYA_SBCE_SNMP_SEC_NAME:-Admin} SHA \"${AVAYA_SBCE_SNMP_AUTH_PASS:-sbce_secret_auth_pass}\" DES \"${AVAYA_SBCE_SNMP_PRIV_PASS:-sbce_secret_priv_pass}\"" >> /etc/snmp/snmpd.conf
echo "createUser ${AVAYA_SBCE_SNMP_SEC_NAME:-Admin}_aes SHA \"${AVAYA_SBCE_SNMP_AUTH_PASS:-sbce_secret_auth_pass}\" AES \"${AVAYA_SBCE_SNMP_PRIV_PASS:-sbce_secret_priv_pass}\"" >> /etc/snmp/snmpd.conf

echo "[MOCK-SNMP] Starting Net-SNMP daemon (snmpd)..."
exec snmpd -f -Lo -C -c /etc/snmp/snmpd.conf
