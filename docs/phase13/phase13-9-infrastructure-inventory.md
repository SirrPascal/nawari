# Phase 13.9 — Authoritative Infrastructure & Device Inventory

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Authoritative Staging & Production Inventory  
**Target Environment:** Kenya Airways Telephony Estate & Corporate Network Core  
**Source Baseline:** Zabbix 7.4.16 Database on `mon-grafana01`

---

## 1. Executive Summary

This document establishes the **authoritative physical and logical infrastructure inventory** for Kenya Airways' enterprise network and communications estate.

Each device entry details physical/logical role, IP address, Zabbix host ID, monitoring interface, assigned templates, SNMPv3 configuration, and current operational verification status.

---

## 2. Core Network & Gateway Infrastructure

```
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| ID | Host Name            | Visible Name      | IP Address   | Port    | Type       | Assigned Template             | Commissioning Status  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 01 | mock-core-switch-01  | Simulated Core    | 127.0.0.1    | 161/udp | SNMPv2c/v3 | Nawari Network Device by SNMP | VERIFIED_LIVE         |
|    | (Host 10787)         | Switch 01 (Lab)   |              |         | Net-SNMP   | (Template ID 10786)           | (Staging Agent)       |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 02 | core-gw-01           | Core Distribution | 10.2.1.1     | 161/udp | SNMPv3     | Nawari Generic SNMP Base      | CONFIGURED_           |
|    | (Host 10781)         | Gateway 01        |              |         | Cisco IOS  | (Template ID 10784)           | UNVERIFIED (Off-net)  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 03 | Zabbix server        | Zabbix server     | 127.0.0.1    | 10050   | Zabbix     | Linux by Zabbix agent         | VERIFIED_LIVE         |
|    | (Host 10084)         |                   |              |         | Agent      | (Template ID 10001)           | (Platform Core)       |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 04 | endpoint-probe-01    | Endpoint Synthetic| 127.0.0.1    | 10050   | Trapper /  | Nawari Endpoint Synthetic     | VERIFIED_LIVE         |
|    | (Host 10803)         | Probe 01          |              |         | Agent      | Probe (Template ID 10795)     | (Synthetic Engine)    |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
```

---

## 3. Avaya Aura Communications Infrastructure

```
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| ID | Host Name            | Visible Name      | IP Address   | Port    | Type       | Assigned Template             | Commissioning Status  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 05 | mock-avaya-sbce-01   | Simulated Avaya   | 127.0.0.1    | 161/udp | SNMPv2c/v3 | Nawari Avaya SBCE Appliance   | VERIFIED_LIVE         |
|    | (Host 10789)         | SBCE 01 (Lab)     |              |         | Net-SNMP   | (Template ID 10788)           | (Staging Lab Bridge)  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 06 | avaya-sbce-01        | Avaya SBCE Primary| 10.2.156.131 | 161/udp | SNMPv3     | Nawari Avaya SBCE Appliance   | VERIFIED_LIVE         |
|    | (Host 10780)         | (HQ-DMZ)          |              |         | authPriv   | (Template ID 10788)           | (Virtual M1 IP Alive) |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 07 | avaya-sbce-02 (Cand.)| Avaya SBCE Sec.   | 10.2.156.132 | 161/udp | SNMPv3     | Nawari Avaya SBCE Appliance   | BLOCKED_ACCESS        |
|    |                      | (HQ-DMZ)          |              |         | authPriv   | (Template ID 10788)           | (Off-net / Standby)   |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 08 | avaya-sbce-dr (Cand.)| Avaya SBCE DR     | 10.2.156.45  | 161/udp | SNMPv3     | Nawari Avaya SBCE Appliance   | BLOCKED_ACCESS        |
|    |                      | (Airport DR)      |              |         | authPriv   | (Template ID 10788)           | (WAN Route Required)  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 09 | avaya-sm-01          | Avaya Session     | 10.2.156.22  | 161/udp | SNMPv3 +   | Nawari Avaya Session Manager  | CONFIGURED_           |
|    | (Host 10798)         | Manager Primary   |              | 5060/tcp| SIP OPTIONS| (Template ID 10790)           | UNVERIFIED (Off-net)  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 10 | avaya-sm-02 (Cand.)  | Avaya Session     | 10.2.156.23  | 161/udp | SNMPv3 +   | Nawari Avaya Session Manager  | BLOCKED_ACCESS        |
|    |                      | Manager Secondary |              | 5060/tcp| SIP OPTIONS| (Template ID 10790)           | (Off-net Subnet)      |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 11 | avaya-sm-dr (Cand.)  | Avaya Session     | 10.2.156.28  | 161/udp | SNMPv3 +   | Nawari Avaya Session Manager  | BLOCKED_ACCESS        |
|    |                      | Manager DR        |              | 5060/tcp| SIP OPTIONS| (Template ID 10790)           | (DR Subnet Off-net)   |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 12 | avaya-cm-01          | Avaya CM Duplex   | 10.102.10.25 | 161/udp | SNMPv3     | Nawari Avaya Communication    | CONFIGURED_           |
|    | (Host 10799)         | (HQ-CORE)         |              |         | authPriv   | Manager (Template ID 10797)   | UNVERIFIED (Pride DC) |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 13 | avaya-cm-standby     | Avaya CM Standby  | 10.2.156.27  | 161/udp | SNMPv3     | Nawari Avaya Communication    | BLOCKED_ACCESS        |
|    | (Candidate)          | Server            |              |         | authPriv   | Manager (Template ID 10797)   | (Standby Server Route)|
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 14 | avaya-cm-vip         | Avaya CM Active   | 10.2.156.30  | 161/udp | SNMPv3     | Nawari Avaya Communication    | BLOCKED_ACCESS        |
|    | (Candidate)          | Cluster VIP       |              |         | authPriv   | Manager (Template ID 10797)   | (Cluster VIP Route)   |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 15 | avaya-g450-01        | Avaya G450 Media  | 10.2.156.60  | 161/udp | SNMPv3 +   | Nawari Avaya G450 Gateway     | CONFIGURED_           |
|    | (Host 10800)         | Gateway (HQ)      |              |         | Trappers   | (Template ID 10796)           | UNVERIFIED (Off-net)  |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 16 | sip-trunk-carrier-01 | Safaricom SIP     | 127.0.0.1    | 5060/udp| Trappers + | Nawari Carrier SIP Trunk      | SIMULATED / STAGING   |
|    | (Host 10801)         | Carrier Trunk     |              |         | SIP OPTIONS| (Template ID 10793)           | (Active Trap / OPTIONS|
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 17 | avaya-cms-01         | Avaya CMS & WFO   | 127.0.0.1    | 10050   | Trappers + | Nawari Avaya CMS & WFO        | SIMULATED / STAGING   |
|    | (Host 10802)         | Recording (HQ)    |              |         | DB Check   | (Template ID 10792)           | (Storage Trappers)    |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
| 18 | nawari-voice-probe-01| Voice Synthetic   | 127.0.0.1    | 5038/tcp| Asterisk   | Nawari Synthetic Voice Probe  | VERIFIED_LIVE         |
|    | (Host 10791)         | Probe 01          |              | 5060/udp| Trappers   | (Template ID 10794)           | (Running Engine)      |
+----+----------------------+-------------------+--------------+---------+------------+-------------------------------+-----------------------+
```

---

## 4. Hardware Inventory & DSP Resource Profile

| Appliance Model | Physical Form Factor | Installed Modules | DSP Transcoding Resources | Environmental Model |
| :--- | :--- | :--- | :--- | :--- |
| **Avaya G450** | 3U Chassis, 8 Module Slots | Slot V1–V4: MM710 (E1/PRI), Slot V5–V8: MM711 (Analog) | Dual MP80 daughterboards (160 VoIP channels) | Dual redundant PSU, Fan Tray Assembly, Discrete Thermal Traps |
| **Avaya SBCE** | Dell PowerEdge R640 1U | Dual 10GbE SFP+ (A1/B1), Dual 1GbE RJ45 (M1/M2) | N/A (Direct SIP media pass-through / SRTP anchor) | Server BMC / iDRAC, SNMPv3 host-resources MIB |
| **Avaya CM Server** | VMware ESXi VM (Duplex) | vNIC 0: Management, vNIC 1: Control Network | Soft DSP via media gateways | Virtual hardware monitoring via hypervisor |
| **Avaya SM Server** | VMware ESXi VM (Cluster) | vNIC 0: SM Management, vNIC 1: SIP Signaling | N/A (Signaling proxy) | Virtual appliance monitoring |

---

## 5. Security & Credential Architecture

- **SNMPv3 User:** `Admin_sha256`
- **Security Level:** `authPriv` (Authentication and Encryption required)
- **Auth Protocol:** SHA-256 (`usmHMAC256SHA384AuthProtocol`)
- **Priv Protocol:** AES-128 (`usmAesCfb128PrivProtocol`)
- **Key Storage:** Stored in Zabbix host macros `{$SNMP_SECNAME}`, `{$SNMP_AUTH_PASSPHRASE}`, `{$SNMP_PRIV_PASSPHRASE}` with secret macro masking enabled (`type: 1`). Never logged or printed in clear text.

