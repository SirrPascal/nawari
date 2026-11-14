# Avaya Session Border Controller Enterprise (SBCE) Telemetry & OID Matrix

## 1. Management IP Reconciliation & Verification Protocol

A discrepancy was identified between the legacy Sentra project notes and the Nawari Master Engineering Specification:

| Source Document | Specified Target IP | Role Description |
| :--- | :--- | :--- |
| **Sentra Inventory** (`config/avaya_device_inventory.json`) | `10.2.156.132` | `PRIDE-SBCE-01` (Management/SNMP, SIP 5061) |
| **Sentra YAML** (`config/avaya-devices.yaml`) | `10.2.156.132` | Pride SBCE Edge Appliance |
| **Sentra Runbook** (`docs/02_OPERATIONS_RUNBOOK.md`) | `10.2.156.132` | Pride SBCE TLS Endpoint |
| **Sentra Network Firewall Req** (`FW-IN-06`, `FW-OUT-02`) | `10.2.156.132` / `.20` | Pride SBCE Management & Traffic IP |
| **Nawari Master Engineering Prompt** | `10.2.156.131` | Target Pride SBCE (Primary specification) |
| **Nawari Network Architecture** (`network-architecture.md`) | `10.2.156.131` / `.132` | Pride SBCE Cluster Pair / EMS |

### 1.1 Architectural Hypothesis vs. Empirical Evidence
* **Working Hypothesis:** In an Avaya SBCE high-availability (HA) cluster, `10.2.156.131` is hypothesized to be the active SBC node (`sbc01`), while `10.2.156.132` is hypothesized to be the standby node (`sbc02`) or the Element Management System (EMS).
* **Engineering Reality:** Finding different addresses in two codebases does not independently establish operational roles. Neither address is treated as production-confirmed until validated by the Phase 4.1 audit.

### 1.2 Physical Verification Protocol (Phase 4.1 Gate)
Before locking production monitoring to either IP:
1. **Management IP Audit:** Perform non-destructive read-only queries against both `10.2.156.131` and `10.2.156.132` to retrieve `sysName`, `sysDescr`, and physical interfaces.
2. **HA Role Determination:** Inspect the appliance clustering status (via SBCE EMS or CLI `sbc status`) to definitively identify the active vs. standby node.
3. **EMS Address Architecture:** Determine whether EMS is co-located on one of the SBC nodes or operates on a dedicated standalone management address.
4. **SNMP Polling Scope:** Confirm whether SNMP polling is permitted on both cluster nodes simultaneously, or only against an HA Virtual IP (VIP).
5. **Address Classification:** Establish whether `.131` and `.132` are physical node management interfaces (M1), cluster VIPs, or signaling interfaces (A1/B1).

---

## 2. Telemetry Classification Standard

Every metric in this catalog is rigorously classified into one of five validation tiers:

| Tier | Status Label | Definition |
| :---: | :--- | :--- |
| **Tier 1** | **Confirmed on physical SBCE** | Verified by direct SNMP walk/poll against the physical Avaya SBCE appliance in the production network. |
| **Tier 2** | **Documented by Avaya but not yet tested** | Documented in official Avaya SBCE Administration / MIB guides, but not yet probed on the physical device. |
| **Tier 3** | **Available only on the mock** | Implemented and verified in the lab container environment (`nawari-mock-snmp`), requiring live validation before production trust. |
| **Tier 4** | **Unsupported or unavailable** | Probed on the target appliance or mock agent and confirmed to return `noSuchObject`, `noSuchInstance`, or unsupported. |
| **Tier 5** | **Not yet investigated** | Candidate OID identified in MIB specifications, but not yet evaluated on either mock or physical target. |

---

## 3. Cryptographic Security & SNMPv3 USM Parameters

| Parameter | Lab / Mock Environment | Production Requirement | Validation Status |
| :--- | :--- | :--- | :--- |
| **Target Host** | `mock-snmp:161` | `${AVAYA_SBCE_HOST}` (Unvalidated candidate: `10.2.156.131`) | **Available only on the mock** |
| **SNMP Port** | `161/udp` | `161/udp` | **Available only on the mock** |
| **SNMP Version** | `SNMPv3` | `SNMPv3` | **Available only on the mock** |
| **Security Level** | `authPriv` | `authPriv` | **Available only on the mock** |
| **Security Name** | `Admin` | `${AVAYA_SBCE_SNMP_SEC_NAME}` | **Available only on the mock** |
| **Auth Protocol** | SHA-1 (`SHA`) / SHA-256 | SHA-256 (`SHA256`) preferred | **Available only on the mock** |
| **Priv Protocol** | DES (`DES`) / AES-128 (`AES`) | AES-128 (`AES128`) required; DES deprecated | **Available only on the mock** |
| **Credential Injection** | Test passwords in mock | Environment variables only; no plaintext fallbacks | **Production Hardened** |

> [!CAUTION]
> CBC-DES is cryptographically obsolete. Although legacy Avaya configurations may still reference DES, Nawari defaults production templates to `authprotocol: SHA256` and `privprotocol: AES128`. Production staging must establish whether the physical appliance supports AES-128 without requiring legacy DES.

---

## 4. Authoritative OID & Telemetry Matrix

### 4.1 System Identity & Core Platform Uptime (MIB-2 / SNMPv2-MIB)

| Metric | OID | Source MIB | Data Type | Units / Scale | Supported Release | Validation Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **System Description** | `1.3.6.1.2.1.1.1.0` | `SNMPv2-MIB::sysDescr.0` | `DisplayString` | Text | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **System Object ID** | `1.3.6.1.2.1.1.2.0` | `SNMPv2-MIB::sysObjectID.0` | `OBJECT IDENTIFIER` | OID | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **System Uptime** | `1.3.6.1.2.1.1.3.0` | `DISMAN-EVENT-MIB::sysUpTimeInstance` | `TimeTicks` | `s` (Multiplier: `0.01`) | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **System Contact** | `1.3.6.1.2.1.1.4.0` | `SNMPv2-MIB::sysContact.0` | `DisplayString` | Text | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **System Name** | `1.3.6.1.2.1.1.5.0` | `SNMPv2-MIB::sysName.0` | `DisplayString` | Text | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **System Location** | `1.3.6.1.2.1.1.6.0` | `SNMPv2-MIB::sysLocation.0` | `DisplayString` | Text | SBCE 8.x, 10.1, 10.2 | **Available only on the mock** |
| **SNMP Poller Health** | `zabbix[host,snmp,available]` | Internal Zabbix Poller | `INTEGER` | `1=UP, 0=DOWN` | All | **Available only on the mock** |
| **ICMP Ping Status** | `icmpping` | Simple Check (fping) | `INTEGER` | `1=UP, 0=DOWN` | All | **Available only on the mock** |
| **ICMP Latency** | `icmppingsec` | Simple Check (fping) | `FLOAT` | `s` (Seconds) | All | **Available only on the mock** |
| **ICMP Packet Loss** | `icmppingloss` | Simple Check (fping) | `FLOAT` | `%` (Percentage) | All | **Available only on the mock** |

---

### 4.2 SBCE Interface Discovery & High-Capacity Telemetry (IF-MIB)

**Low-Level Discovery Rule:** `sbce.interface.discovery`  
**Discovery OID:** `discovery[{#IFNAME},1.3.6.1.2.1.31.1.1.1.1]`  
**Interface Naming Model (Simulated in Mock):**
- `M1`: Primary Appliance Management Interface
- `M2`: Secondary / HA Interconnect Interface
- `A1`: External DMZ (Carrier SIP Trunk Signaling & Media)
- `B1`: Internal Network (Core Avaya Aura Session Manager Signaling & Media)

> [!WARNING]
> In the mock environment, `M1`, `M2`, `A1`, and `B1` are virtual dummy interfaces created by `ip link`. On the physical Avaya SBCE, physical interfaces may be named `eth0`, `eth1`, `sbc0`, or Aliased via `ifAlias` (`1.3.6.1.2.1.31.1.1.1.18`). The Phase 4.1 physical probe must verify how Avaya maps physical ports to `ifName` vs `ifDescr` vs `ifAlias`.

| Metric Prototype | Prototype Key | OID | Source MIB | Type / Preprocessing | Units | Validation Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Operational Status** | `net.if.status[ifOperStatus.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.8.{#SNMPINDEX}` | `IF-MIB::ifOperStatus` | `INTEGER` (1:UP, 2:DOWN) | Enum | **Available only on the mock** |
| **Administrative Status** | `net.if.adminstatus[ifAdminStatus.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.7.{#SNMPINDEX}` | `IF-MIB::ifAdminStatus` | `INTEGER` (1:UP, 2:DOWN) | Enum | **Available only on the mock** |
| **Interface High Speed** | `net.if.speed[ifHighSpeed.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.15.{#SNMPINDEX}` | `IF-MIB::ifHighSpeed` | `Gauge32` * `1000000` | `bps` | **Available only on the mock** |
| **Inbound High-Capacity Traffic** | `net.if.in[ifHCInOctets.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.6.{#SNMPINDEX}` | `IF-MIB::ifHCInOctets` | `Counter64` (`CHANGE_PER_SECOND` * 8) | `bps` | **Available only on the mock** |
| **Outbound High-Capacity Traffic** | `net.if.out[ifHCOutOctets.{#SNMPINDEX}]` | `1.3.6.1.2.1.31.1.1.1.10.{#SNMPINDEX}` | `IF-MIB::ifHCOutOctets` | `Counter64` (`CHANGE_PER_SECOND` * 8) | `bps` | **Available only on the mock** |
| **Inbound Packet Discards** | `net.if.in.discards[ifInDiscards.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.13.{#SNMPINDEX}` | `IF-MIB::ifInDiscards` | `Counter32` (`CHANGE_PER_SECOND`) | `!pps` | **Available only on the mock** |
| **Inbound Packet Errors** | `net.if.in.errors[ifInErrors.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.14.{#SNMPINDEX}` | `IF-MIB::ifInErrors` | `Counter32` (`CHANGE_PER_SECOND`) | `!err/s` | **Available only on the mock** |
| **Outbound Packet Discards** | `net.if.out.discards[ifOutDiscards.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.19.{#SNMPINDEX}` | `IF-MIB::ifOutDiscards` | `Counter32` (`CHANGE_PER_SECOND`) | `!pps` | **Available only on the mock** |
| **Outbound Packet Errors** | `net.if.out.errors[ifOutErrors.{#SNMPINDEX}]` | `1.3.6.1.2.1.2.2.1.20.{#SNMPINDEX}` | `IF-MIB::ifOutErrors` | `Counter32` (`CHANGE_PER_SECOND`) | `!err/s` | **Available only on the mock** |

---

### 4.3 Appliance Hardware & Resource Capacity (HOST-RESOURCES & UCD-SNMP)

> [!IMPORTANT]
> The mock implementation required specific adaptations that must NOT be assumed identical on the physical SBCE:
> 1. **Root Disk (`vfs.fs.used.percent[/]`):** The mock required a custom pass-through script (`snmp_disk_pass.sh`) to emulate `UCD-SNMP-MIB::dskPercent.1` (`1.3.6.1.4.1.2021.9.1.9.1`) because Alpine overlayfs did not populate `dskTable`. The physical Avaya SBCE runs a CentOS/RHEL-based appliance OS; it may expose root storage under `dskPercent.1` or via `HOST-RESOURCES-MIB::hrStorageTable` (`1.3.6.1.2.1.25.2.3`).
> 2. **Physical Memory Total (`vm.memory.total`):** The mock references `hrStorageSize.1` (assuming index 1 is Physical RAM). On a physical appliance, `hrStorageIndex` for Physical RAM is not guaranteed to be 1. Alternatively, `UCD-SNMP-MIB::memTotalReal.0` (`1.3.6.1.4.1.2021.4.5.0`) must be verified.

| Metric | OID | Source MIB | Data Type | Preprocessing / Units | Validation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CPU Idle Percentage** | `1.3.6.1.4.1.2021.11.11.0` | `UCD-SNMP-MIB::ssCpuIdle.0` | `INTEGER` | `100 - ssCpuIdle` (`%`) | **Available only on the mock** |
| **1-Minute Load Average** | `1.3.6.1.4.1.2021.10.1.3.1` | `UCD-SNMP-MIB::laLoad.1` | `FLOAT` | Load average value | **Available only on the mock** |
| **Total Physical Memory** | `1.3.6.1.2.1.25.2.3.1.5.1` | `HOST-RESOURCES-MIB::hrStorageSize.1` | `INTEGER` | `* 1024` (`B`) | **Available only on the mock** (Index 1 assumption) |
| **Available Physical Memory** | `1.3.6.1.4.1.2021.4.6.0` | `UCD-SNMP-MIB::memAvailReal.0` | `INTEGER` | `* 1024` (`B`) | **Available only on the mock** |
| **Memory Utilization %** | Calculated | Calculated Item | `FLOAT` | `(1 - (avail / total)) * 100` | **Available only on the mock** |
| **Root Disk Used %** | `1.3.6.1.4.1.2021.9.1.9.1` | `UCD-SNMP-MIB::dskPercent.1` | `INTEGER` | `%` (Root filesystem `/`) | **Available only on the mock** (Pass-through emulation) |
| **Processor Core Load Discovery** | `1.3.6.1.2.1.25.3.3.1.2` | `HOST-RESOURCES-MIB::hrProcessorLoad` | `INTEGER` | `%` per core | **Documented by Avaya but not yet tested** |
| **Process Count** | `1.3.6.1.2.1.25.1.6.0` | `HOST-RESOURCES-MIB::hrSystemProcesses.0` | `Gauge32` | Processes | **Documented by Avaya but not yet tested** |

---

### 4.4 Avaya Enterprise Specifics & Enterprise Traps

| Telemetry Target | OID / Branch | Source MIB | Operational Significance | Validation Status |
| :--- | :--- | :--- | :--- | :--- |
| **Avaya Enterprise Root** | `1.3.6.1.4.1.6889.*` | `AVAYA-SBC-MIB` | Avaya proprietary enterprise tree | **Documented by Avaya but not yet tested** |
| **Active SIP Calls / Sessions** | `1.3.6.1.4.1.6889.2.69.*` | Avaya SBCE Enterprise MIB | Concurrent active SIP sessions across trunks | **Documented by Avaya but not yet tested** |
| **License / Capacity Usage** | `1.3.6.1.4.1.6889.2.69.1.*` | Avaya SBCE Enterprise MIB | Allocated vs consumed trunk session licenses | **Not yet investigated** |
| **Avaya SBCE Traps** | `1.3.6.1.4.1.6889.2.69.2.*` | `AVAYA-SBC-TRAPS-MIB` | Hardware failure, HA failover, SIP trunk down | **Documented by Avaya but not yet tested** |
| **Cold / Warm Start Trap** | `1.3.6.1.6.3.1.1.5.1` / `.2` | `SNMPv2-MIB` | Appliance reboot notifications | **Available only on the mock** |
| **Link Down Trap** | `1.3.6.1.6.3.1.1.5.3` | `IF-MIB` | Physical network interface disconnect trap | **Available only on the mock** |

---

## 5. Scope Boundary: Operational Appliance Health vs. Voice Quality

To prevent misleading operational conclusions, the following scope boundaries are enforced:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PHASE 4 / 4.1 SCOPE:                            │
│                 SBCE APPLIANCE OPERATIONAL HEALTH                      │
├────────────────────────────────────────────────────────────────────────┤
│  ✓ Physical interface operational status (A1, B1, M1, M2)              │
│  ✓ Interface bitrates & bandwidth utilization (64-bit HC counters)     │
│  ✓ Interface packet errors and discards                                │
│  ✓ Operating system CPU, memory, root disk space, and load average     │
│  ✓ Unexpected reboot and SNMP agent unreachable events                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ DOES NOT PROVE
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          PHASE 5 SCOPE:                                │
│                     VOICE SERVICE ASSURANCE                            │
├────────────────────────────────────────────────────────────────────────┤
│  ✗ Interface A1 UP   ≠   SIP Trunk to Carrier Established             │
│  ✗ Interface B1 UP   ≠   SIP Options Ping to Session Manager Succeeds │
│  ✗ 0 Packet Discards ≠   Acceptable RTP Jitter (< 30ms)               │
│  ✗ SIP 200 OK        ≠   Two-Way Audio Flowing (RTP bidirectional)    │
│  ✗ Low Ping Latency  ≠   Tolerable Mean Opinion Score (MOS > 4.0)     │
└────────────────────────────────────────────────────────────────────────┘
```

The Grafana dashboard `nawari-sbce-health` is titled **`Nawari — Avaya SBCE Operational Health`** and explicitly represents appliance infrastructure health. Real-time SIP signaling transactions, RTP packet loss, jitter, RTT, and MOS are deferred to Phase 5.
