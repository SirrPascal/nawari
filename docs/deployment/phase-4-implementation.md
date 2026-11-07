# Nawari — Phase 4 Engineering Report: Avaya SBCE Observability & Physical Validation (Phase 4.1)

## Executive Summary

Phase 4 establishes an enterprise-grade monitoring layer for the **Avaya Session Border Controller Enterprise (SBCE)** built upon Nawari's generic network monitoring foundation.

In accordance with architectural principles:
> *"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services."*

Phase 4 moves beyond generic SNMP device reachability to capture full appliance operating resource health (CPU, RAM, root disk space, 1-minute load average), 64-bit high-capacity traffic counters on voice signaling and media interfaces, automated fault detection on carrier trunk interfaces, and real-time operational visualization in Grafana.

> [!IMPORTANT]
> **Simulation vs. Production Distinction:**
> The current milestone is successfully implemented and verified against a **simulated SBCE environment** (`nawari-mock-snmp`). Physical validation against the real Avaya appliance is governed by **Phase 4.1**, ensuring that no unverified assumptions are carried into production or Phase 5.

---

## 1. Candidate Appliance IPs & Empirical Verification Protocol

### 1.1 Candidate IP Discrepancy
* **Sentra Configuration:** Target IP `10.2.156.132` (recorded as Pride SBCE appliance/EMS).
* **Master Engineering Prompt:** Target IP `10.2.156.131` (specified as primary Pride SBCE).

### 1.2 Verification Protocol (Phase 4.1 Gate)
Finding different addresses in two repositories does not independently establish operational roles. Rather than assuming roles, Nawari establishes an empirical validation protocol:
1. **Management IP Audit:** Probe both `10.2.156.131` and `10.2.156.132` using read-only SNMPv3 queries to retrieve `sysName`, `sysDescr`, and physical interfaces.
2. **HA Role Confirmation:** Inspect appliance clustering status (via SBCE EMS or CLI `sbc status`) to verify active vs standby assignment.
3. **EMS Architecture Determination:** Establish whether EMS is co-located or operates on an independent management IP.
4. **SNMP Polling Scope:** Confirm whether SNMP polling is permitted on both physical nodes or strictly on a cluster Virtual IP (VIP).
5. **Address Classification:** Establish whether `.131` and `.132` are physical node management interfaces (M1), cluster VIPs, or signaling interfaces (A1/B1).

### 1.3 Production Hardened Configuration
In `provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml`, plaintext fallback credentials have been strictly eliminated:
```yaml
interfaces:
  - type: snmp
    ip: "${AVAYA_SBCE_HOST:-10.2.156.131}"
    port: "${AVAYA_SBCE_SNMP_PORT:-161}"
    main: 1
    useip: 1
    details:
      version: 3
      securityname: "${AVAYA_SBCE_SNMP_SEC_NAME:-Admin}"
      securitylevel: "authPriv"
      authprotocol: "${AVAYA_SBCE_SNMP_AUTH_PROTO:-SHA256}"
      authpassphrase: "${AVAYA_SBCE_SNMP_AUTH_PASS}"
      privprotocol: "${AVAYA_SBCE_SNMP_PRIV_PROTO:-AES128}"
      privpassphrase: "${AVAYA_SBCE_SNMP_PRIV_PASS}"
```

---

## 2. Telemetry Matrix & OID Classification Standard

The complete telemetry matrix is maintained in `docs/monitoring/avaya-sbce-telemetry-matrix.md`. Every metric is categorized under a 5-tier standard:

1. **Confirmed on physical SBCE:** (Pending Phase 4.1 live network audit).
2. **Documented by Avaya but not yet tested:** (Avaya enterprise MIB `.1.3.6.1.4.1.6889`, active session tables, enterprise traps).
3. **Available only on the mock:** (Verified in `nawari-mock-snmp`, including custom disk pass-through and storage index mappings).
4. **Unsupported or unavailable:** (OIDs returning `noSuchObject` or unsupported).
5. **Not yet investigated.**

### 2.1 Technical Caveats of Mock Emulation
* **Root Disk (`vfs.fs.used.percent[/]`):** Required a custom Net-SNMP pass-through script (`snmp_disk_pass.sh`) because Alpine's overlayfs does not populate `dskTable` natively. The physical appliance runs CentOS/RHEL; Phase 4.1 will verify whether it exposes `dskPercent.1` or requires `HOST-RESOURCES-MIB::hrStorageTable` discovery.
* **Physical Memory (`vm.memory.total`):** References `hrStorageSize.1` (assuming index 1 is Physical RAM). The physical appliance may use a different index or `UCD-SNMP-MIB::memTotalReal.0` (`1.3.6.1.4.1.2021.4.5.0`).
* **Interface Naming:** Virtual dummy interfaces (`M1`, `M2`, `A1`, `B1`) were created in the mock container. Physical SBCE interfaces may use physical names (`eth0`, `sbc0`) mapped via `ifAlias`.

---

## 3. Nawari Avaya SBCE Template Design

The template `provisioning/zabbix/templates/nawari_avaya_sbce.yaml` inherits from `Nawari Generic SNMP Base`.

### 3.1 Low-Level Discovery (LLD)
* **Rule Key:** `sbce.interface.discovery`
* **SNMP OID:** `discovery[{#IFNAME},1.3.6.1.2.1.31.1.1.1.1]`
* **Item Prototypes (9 per discovered interface):**
  1. Operational status (`net.if.status[ifOperStatus.{#SNMPINDEX}]`)
  2. Administrative status (`net.if.adminstatus[ifAdminStatus.{#SNMPINDEX}]`)
  3. Bits received (64-bit HC bps) (`net.if.in.octets[ifHCInOctets.{#SNMPINDEX}]`)
  4. Bits sent (64-bit HC bps) (`net.if.out.octets[ifHCOutOctets.{#SNMPINDEX}]`)
  5. Inbound errors (`net.if.in.errors[ifInErrors.{#SNMPINDEX}]`)
  6. Outbound errors (`net.if.out.errors[ifOutErrors.{#SNMPINDEX}]`)
  7. Inbound discards (`net.if.in.discards[ifInDiscards.{#SNMPINDEX}]`)
  8. Outbound discards (`net.if.out.discards[ifOutDiscards.{#SNMPINDEX}]`)
  9. Interface speed (`net.if.speed[ifHighSpeed.{#SNMPINDEX}]`)

### 3.2 Trigger Framework
* **High Severity:** Interface Link Down on voice signaling/media interfaces (`A1`, `B1`, `M1`).
* **Warning Severity:** High Bandwidth Utilization (`> 80%`).
* **Warning Severity:** High Error Rate (`> 2 errors/sec`).
* **Warning Severity:** High CPU Utilization (`> 85% for 5 min`).
* **Warning Severity:** High Memory Utilization (`> 90% for 5 min`).
* **Warning Severity:** High Root Disk Usage (`> 85%`).

---

## 4. Phase 4.1 Physical Validation Tool (`probe_physical_sbce.py`)

A safe, non-destructive audit tool was authored at `scripts/audit/probe_physical_sbce.py`.

### Capabilities:
* **SNMPv3 `authPriv` Handshake:** Probes target IP using user-supplied or environment credentials.
* **System Identity Collection:** Extracts `sysName`, `sysDescr`, `sysObjectID`, `sysUpTime`.
* **Interface Enumeration:** Walks IF-MIB to report all `ifName`, `ifDescr`, and `ifOperStatus` values.
* **Storage Table Inspection:** Walks `HOST-RESOURCES-MIB::hrStorageTable` to identify real RAM and disk indices.
* **Native OID Verification:** Checks native availability of `UCD-ssCpuIdle`, `UCD-laLoad.1`, `UCD-dskPercent.1`.
* **Avaya Enterprise Sub-tree Probe:** Probes `.1.3.6.1.4.1.6889` for active Avaya enterprise MIB objects.
* **Automated Compatibility Audit:** Produces structured Markdown / JSON audit reports matching observed appliance behavior against Nawari template keys.

---

## 5. Grafana Dashboard Scope: Appliance Health vs. Voice Quality

Provisioned at `docker/grafana/dashboards/avaya_sbce_operational_health.json`:
* **Title:** `Nawari — Avaya SBCE Operational Health` (UID: `nawari-sbce-health`)
* **Scope Boundary:** Explicitly restricted to **Appliance Operational Health**:
  * Physical interface UP does not prove SIP trunk establishment.
  * Low interface packet loss does not prove acceptable RTP jitter.
  * SIP 200 OK does not prove two-way audio flow.
  * Voice quality, jitter, packet loss, and MOS are monitored in **Phase 5**.

---

## 6. Automated Verification Results

### 6.1 Full Test Suite (`pytest tests/`)
```text
tests/integration/test_core_infrastructure.py ............               [ 28%]
tests/integration/test_phase3_network_monitoring.py .........            [ 50%]
tests/integration/test_phase4_sbce_monitoring.py .........               [ 71%]
tests/integration/test_provisioning_idempotency.py ..                    [ 76%]
tests/unit/test_config_and_schema.py .....                               [ 88%]
tests/unit/test_diff_engine.py .....                                     [100%]

============================= 42 passed in 46.07s ==============================
```

### 6.2 Phase 4 Acceptance Script (`scripts/verify_phase4.sh`)
```text
======================================================================
NAWARI PHASE 4 ACCEPTANCE VERIFICATION: AVAYA SBCE OBSERVABILITY
======================================================================
[TEST] SNMPv3 authPriv Responsiveness (User: Admin, SHA/DES) ... PASS
[TEST] Avaya SBCE Template Hierarchy & LLD Rules ... PASS
[TEST] SBCE Hosts Provisioned (Mock & Production Reconciled) ... PASS
[TEST] LLD Discovery of Voice Interfaces (M1, M2, A1, B1) ... PASS
[TEST] SBCE Appliance Resource Telemetry Active (CPU/RAM/Disk/Load) ... PASS
[TEST] Historical Metric Persistence in PostgreSQL ... PASS
[TEST] Voice Interface Fault Injection & Auto-Recovery (A1 Link Down) ... PASS
[TEST] Grafana Avaya SBCE Operational Dashboard (19 Panels) ... PASS
----------------------------------------------------------------------
VERIFICATION SUMMARY: 8 PASSED, 0 FAILED
======================================================================
>>> PHASE 4 ACCEPTANCE GATES COMPLETED SUCCESSFULLY <<<
```

---

## 7. Phase 4.1 Physical Validation Acceptance Criteria

Before transitioning to production or Phase 5, Phase 4.1 must satisfy the following 10 gates:
1. Confirm the SBCE management IP and HA roles.
2. Successfully establish SNMPv3 authPriv communication with the real appliance.
3. Retrieve its system identity and uptime.
4. Walk the supported system-resource and IF-MIB OIDs using `probe_physical_sbce.py`.
5. Match discovered interfaces to the actual SBCE interface roles.
6. Confirm which resource metrics are genuinely available natively.
7. Compare actual readings with Nawari's Zabbix items.
8. Verify that the production dashboard does not display unsupported metrics as healthy.
9. Document unsupported or unavailable metrics without fabricating replacements.
10. Confirm that no configuration changes were made to the production appliance.
