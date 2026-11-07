#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Enterprise Production Host Firewall Configuration (Ubuntu 24.04 LTS)
# Target: mon-grafana01 (10.2.1.58)
# ==============================================================================

set -euo pipefail

echo "==> Configuring UFW firewall rules for Nawari Production Host..."

# 1. Reset UFW to default state (dry-run safe or explicit enable)
ufw --force reset

# 2. Default policies: Deny all inbound, allow all outbound
ufw default deny incoming
ufw default allow outgoing

# 3. Management: SSH (TCP 22) restricted to corporate management jump hosts
MANAGEMENT_SUBNET="${MANAGEMENT_SUBNET:-10.100.0.0/16}"
echo "--> Permitting SSH from management subnet: ${MANAGEMENT_SUBNET}"
ufw allow from "${MANAGEMENT_SUBNET}" to any port 22 proto tcp comment 'Nawari SSH Jump Host Access'

# 4. HTTPS: Grafana UI (TCP 443 / 3000) for Enterprise NOC & Engineers
OPERATOR_SUBNET="${OPERATOR_SUBNET:-10.0.0.0/8}"
echo "--> Permitting Grafana HTTPS from operator subnets: ${OPERATOR_SUBNET}"
ufw allow from "${OPERATOR_SUBNET}" to any port 443 proto tcp comment 'Nawari Grafana HTTPS UI'
ufw allow from "${OPERATOR_SUBNET}" to any port 3000 proto tcp comment 'Nawari Grafana Direct UI'

# 5. Ingestion Gateway: Telemetry Ingress (TCP 8443) from Enrolled Endpoints
ENDPOINT_SUBNET="${ENDPOINT_SUBNET:-10.0.0.0/8}"
echo "--> Permitting Ingestion Gateway HTTPS from endpoint subnets: ${ENDPOINT_SUBNET}"
ufw allow from "${ENDPOINT_SUBNET}" to any port 8443 proto tcp comment 'Nawari Endpoint Telemetry Ingestion'

# 6. SNMP Traps: UDP 162 restricted strictly to Monitored Core Switches
CORE_SWITCH_SUBNET="${CORE_SWITCH_SUBNET:-10.2.156.0/24}"
echo "--> Permitting SNMP Traps UDP 162 from core switches: ${CORE_SWITCH_SUBNET}"
ufw allow from "${CORE_SWITCH_SUBNET}" to any port 162 proto udp comment 'Nawari Core Network SNMP Traps'

# 7. Zabbix Frontend: TCP 8080/8088 restricted to Network Monitoring Admins
ADMIN_SUBNET="${ADMIN_SUBNET:-10.2.0.0/16}"
echo "--> Permitting Zabbix Web Admin from admin subnet: ${ADMIN_SUBNET}"
ufw allow from "${ADMIN_SUBNET}" to any port 8080 proto tcp comment 'Nawari Zabbix Web Admin'
ufw allow from "${ADMIN_SUBNET}" to any port 8088 proto tcp comment 'Nawari Zabbix Web Alt Admin'

# 8. Loopback interface is fully trusted
ufw allow in on lo comment 'Allow all local loopback'

# 9. Enable logging
ufw logging medium

echo "==> Nawari UFW configuration complete. Review with: ufw status verbose"
