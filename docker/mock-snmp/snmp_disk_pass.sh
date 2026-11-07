#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Net-SNMP Pass-Through Handler for Root Disk Utilization
# ==============================================================================
# Emulates UCD-SNMP-MIB::dskPercent.1 (1.3.6.1.4.1.2021.9.1.9.1)
# Returns percentage of root filesystem space used.
# ==============================================================================

REQ_OID="1.3.6.1.4.1.2021.9.1.9.1"
FULL_REQ_OID=".1.3.6.1.4.1.2021.9.1.9.1"

if [ "$1" = "-g" ] || [ "$1" = "-n" ]; then
    # Calculate root filesystem used percentage
    USED=$(df -k / 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}')
    if [ -z "$USED" ]; then
        USED=25
    fi
    echo "${FULL_REQ_OID}"
    echo "integer"
    echo "${USED}"
fi
exit 0
