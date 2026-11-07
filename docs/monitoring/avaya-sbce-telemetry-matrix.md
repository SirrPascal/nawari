# Avaya Session Border Controller Enterprise (SBCE) Telemetry & OID Matrix

## 1. Management IP Reconciliation

A discrepancy was identified between the legacy Sentra project notes and the current Nawari Master Engineering Specification:

| Source Document | Specified Target IP | Role Description |
| :--- | :--- | :--- |
| **Sentra Inventory** (`config/avaya_device_inventory.json`) | `10.2.156.132` | `PRIDE-SBCE-01` (Management/SNMP, SIP 5061) |
| **Sentra YAML** (`config/avaya-devices.yaml`) | `10.2.156.132` | Pride SBCE Edge Appliance |
| **Sentra Runbook** (`docs/02_OPERATIONS_RUNBOOK.md`) | `10.2.156.132` | Pride SBCE TLS Endpoint |
| **Sentra Network Firewall Req** (`FW-IN-06`, `FW-OUT-02`) | `10.2.156.132` / `.20` | Pride SBCE Management & Traffic IP |
| **Nawari Master Engineering Prompt** | `10.2.156.131` | Target Pride SBCE (Primary specification) |
| **Nawari Network Architecture** (`network-architecture.md`) | `10.2.156.131` / `.132` | Pride SBCE Cluster Pair / EMS |

### Reconciliation Resolution:
In enterprise Avaya SBCE deployments, Session Border Controllers are deployed in High Availability (HA) active/standby clusters orchestrated by an Element Management System (EMS):
1. **Primary Polling Target:** `10.2.156.131` is the authoritative primary target for the active cluster peer / primary appliance interface.
2. **Secondary / Cluster Target:** `10.2.156.132` represents the standby cluster peer or dedicated EMS management interface previously recorded during Sentra staging.
3. **Dynamic Environment Configuration:** In Nawari, the IP address is parameterized through the declarative engine as:
   ```yaml
   ip: "${AVAYA_SBCE_HOST:-10.2.156.131}"
   ```
   This allows operators to seamlessly target `10.2.156.131` (primary active), switch to `10.2.156.132` for secondary node polling, or route through the EMS without modifying version-controlled template code.

---

## 2. Cryptographic Security & SNMPv3 USM Parameters

| Parameter | Specification | Staging / Production Baseline |
| :--- | :--- | :--- |
| **Target Host** | `10.2.156.131` | Set via `AVAYA_SBCE_HOST` |
| **SNMP Port** | `161/udp` | Set via `AVAYA_SBCE_SNMP_PORT` |
| **SNMP Version** | `SNMPv3` | Required for Avaya appliance compliance |
| **Security Level** | `authPriv` | Authenticated and encrypted |
| **Security Name** | `Admin` | Set via `AVAYA_SBCE_SNMP_SEC_NAME` |
| **Authentication Protocol** | `SHA` (HMAC-SHA-96) | Set via `AVAYA_SBCE_SNMP_AUTH_PROTO` |
| **Privacy Protocol** | `DES` (CBC-DES) / `AES-128` | Set via `AVAYA_SBCE_SNMP_PRIV_PROTO` |
| **Context Name** | `""` (Default) | Standard SNMPv3 root context |

> [!WARNING]
> While DES is the currently configured privacy cipher on the deployed SBCE, DES is cryptographically weak. An engineering migration plan to AES-128 is recommended following production staging validation with Avaya appliance firmware releases 10.1 and 10.2.

---

## 3. Authoritative OID & Telemetry Matrix

This matrix establishes every OID utilized by the `Nawari Avaya SBCE by SNMP` template, detailing source MIB, data type, transformation, supported Avaya release, and operational purpose.

### A. System Identity & Core Platform Uptime (MIB-2 / SNMPv2-MIB)

| Metric | OID | Source MIB | Data Type | Units / Scale | Supported Release | Validation Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **System Description** | `1.3.6.1.2.1.1.1.0` | `SNMPv2-MIB::sysDescr.0` | `DisplayString` | N/A | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **System Object ID** | `1.3.6.1.2.1.1.2.0` | `SNMPv2-MIB::sysObjectID.0` | `OBJECT IDENTIFIER` | N/A | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **System Uptime** | `1.3.6.1.2.1.1.3.0` | `DISMAN-EVENT-MIB::sysUpTimeInstance` | `TimeTicks` | `s` (Multiplier: `0.01`) | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **System Contact** | `1.3.6.1.2.1.1.4.0` | `SNMPv2-MIB::sysContact.0` | `DisplayString` | N/A | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **System Name** | `1.3.6.1.2.1.1.5.0` | `SNMPv2-MIB::sysName.0` | `DisplayString` | N/A | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **System Location** | `1.3.6.1.2.1.1.6.0` | `SNMPv2-MIB::sysLocation.0` | `DisplayString` | N/A | SBCE 8.x, 10.1, 10.2 | **Verified** |
| **SNMP Poller Health** | `zabbix[host,snmp,available]` | Internal Zabbix Poller | `INTEGER` | `1=UP, 0=DOWN` | All | **Verified** |
| **ICMP Ping Status** | `icmpping` | Simple Check (fping) | `INTEGER` | `1=UP, 0=DOWN` | All | **Verified** |
| **ICMP Latency** | `icmppingsec` | Simple Check (fping) | `FLOAT` | `s` (Seconds) | All | **Verified** |
| **ICMP Packet Loss** | `icmppingloss` | Simple Check (fping) | `FLOAT` | `%` (Percentage) | All | **Verified** |

---

### B. SBCE Interface Discovery & High-Capacity Telemetry (IF-MIB)

**Low-Level Discovery Rule:** `sbce.interface.discovery`  
**Discovery OID:** `discovery[{#IFNAME},1.3.6.1.2.1.31.1.1.1.1]`  
**Interface Naming Convention:**
- `M1`: Primary Appliance Management Interface
- `M2`: Secondary / HA Management Interface
- `A1`: External DMZ (Signaling & Carrier SIP Trunk Media)
- `A2`: External Redundant DMZ
- `B1`: Internal Network (Core Session Manager & Media Flow)
- `B2`: Internal Redundant Interface

| Metric Prototype | Prototype Key | OID | Source MIB | Type / Preprocessing | Units | Alert Threshold |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Operational Status** | `net.if.status[ifOperStatus.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.8.{#SNMPINDEX}` | `IF-MIB::ifOperStatus` | `INTEGER` (1:UP, 2:DOWN) | Enum | Status = 2 (High for A1/B1; Average for M1) |
| **Administrative Status** | `net.if.adminstatus[ifAdminStatus.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.7.{#SNMPINDEX}` | `IF-MIB::ifAdminStatus` | `INTEGER` (1:UP, 2:DOWN) | Enum | Informational |
| **Interface High Speed** | `net.if.speed[ifHighSpeed.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.15.{#SNMPINDEX}` | `IF-MIB::ifHighSpeed` | `Gauge32` * `1000000` | `bps` | Informational |
| **Inbound High-Capacity Traffic** | `net.if.in[ifHCInOctets.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.6.{#SNMPINDEX}` | `IF-MIB::ifHCInOctets` | `Counter64` (`CHANGE_PER_SECOND` * 8) | `bps` | `>{$IF_UTIL_MAX}`% (80%) |
| **Outbound High-Capacity Traffic** | `net.if.out[ifHCOutOctets.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.10.{#SNMPINDEX}` | `IF-MIB::ifHCOutOctets` | `Counter64` (`CHANGE_PER_SECOND` * 8) | `bps` | `>{$IF_UTIL_MAX}`% (80%) |
| **Inbound Packet Discards** | `net.if.in.discards[ifInDiscards.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.13.{#SNMPINDEX}` | `IF-MIB::ifInDiscards` | `Counter32` (`CHANGE_PER_SECOND`) | `!pps` | Trend warning |
| **Inbound Packet Errors** | `net.if.in.errors[ifInErrors.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.14.{#SNMPINDEX}` | `IF-MIB::ifInErrors` | `Counter32` (`CHANGE_PER_SECOND`) | `!err/s` | `>{$IF_ERRORS_WARN}` (2 err/s) |
| **Outbound Packet Discards** | `net.if.out.discards[ifOutDiscards.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.19.{#SNMPINDEX}` | `IF-MIB::ifOutDiscards` | `Counter32` (`CHANGE_PER_SECOND`) | `!pps` | Trend warning |
| **Outbound Packet Errors** | `net.if.out.errors[ifOutErrors.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.20.{#SNMPINDEX}` | `IF-MIB::ifOutErrors` | `Counter32` (`CHANGE_PER_SECOND`) | `!err/s` | `>{$IF_ERRORS_WARN}` (2 err/s) |

---

### C. Appliance Hardware & Resource Capacity (HOST-RESOURCES-MIB & UCD-SNMP)

| Metric | OID | Source MIB | Data Type | Preprocessing / Units | Alert Trigger |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CPU Idle Percentage** | `1.3.6.1.4.1.2021.11.11.0` | `UCD-SNMP-MIB::ssCpuIdle.0` | `INTEGER` | `100 - ssCpuIdle` (`%`) | CPU Utilization > 85% for 5m |
| **Processor Load Discovery** | `discovery[{#CPU.INDEX},1.3.6.1.2.1.25.3.3.1.2]` | `HOST-RESOURCES-MIB::hrProcessorLoad` | `INTEGER` | `%` (Per-core utilization) | Core load > 90% |
| **Total Physical Memory** | `1.3.6.1.4.1.2021.4.5.0` | `UCD-SNMP-MIB::memTotalReal.0` | `INTEGER` | `* 1024` (`B`) | Base inventory |
| **Available Physical Memory** | `1.3.6.1.4.1.2021.4.6.0` | `UCD-SNMP-MIB::memAvailReal.0` | `INTEGER` | `* 1024` (`B`) | Base inventory |
| **Memory Utilization %** | Calculated | `(1 - (memAvailReal / memTotalReal)) * 100` | `FLOAT` | `%` | Memory Utilization > 90% for 5m |
| **Root Disk Storage Used %** | `1.3.6.1.4.1.2021.9.1.9.1` | `UCD-SNMP-MIB::dskPercent.1` | `INTEGER` | `%` (Root filesystem `/`) | Disk Space Used > 85% |

---

### D. Asynchronous Trap Ingestion & Telephony Event Forwarding

| Trap Event / OID | Source MIB | Description | Severity Translation |
| :--- | :--- | :--- | :--- |
| **Avaya Enterprise Root** | `1.3.6.1.4.1.6889.*` | Generic Avaya enterprise trap root | Classified via normalizer |
| **Avaya EPM Alarm** | `1.3.6.1.4.1.6889.2.69` | Experience Portal & Media Gateway hardware alarms | Critical / Major / Minor |
| **Cold Start / Link Down Trap** | `1.3.6.1.6.3.1.1.5.1` / `.3` | Standard RFC 1907 SNMP traps emitted on reboot or port drop | High (Reboot / Link failure) |
