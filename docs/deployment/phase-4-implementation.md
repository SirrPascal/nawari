# Nawari — Phase 4 Engineering Report: Avaya SBCE & Communications Observability

## Executive Summary

Phase 4 of the Nawari platform establishes enterprise-grade observability for mission-critical voice infrastructure, centered on the **Avaya Session Border Controller Enterprise (SBCE)**. 

In accordance with architectural principles:
> *"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services."*

Phase 4 moves beyond generic SNMP device reachability to capture full appliance resource health (CPU, RAM, root disk, 1-minute load average), high-capacity 64-bit traffic counters on voice signaling and media interfaces, automated fault detection on carrier trunk interfaces, and real-time operational visualization in Grafana.

---

## 1. Appliance Architecture & Management IP Reconciliation

### 1.1 IP Address Discrepancy Resolution
A critical discrepancy was identified between the legacy Sentra configuration and the Nawari Master Engineering specification:
* **Sentra Configuration:** Target IP `10.2.156.132` (Pride SBCE appliance/EMS).
* **Master Engineering Prompt:** Target IP `10.2.156.131` (Pride SBCE primary active node).

### 1.2 Cluster Architecture Analysis
In a high-availability (HA) Avaya SBCE deployment:
* **`10.2.156.131`**: Active Session Border Controller node in the high-availability pair (`sbc01`), terminating active SIP signaling trunks and RTP audio.
* **`10.2.156.132`**: Standby Session Border Controller node / Element Management System (`sbc02`/EMS), maintaining replicated configuration and state synchronization.

### 1.3 Implementation Resolution
In `provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml`, the target is parameterized with primary active node as default while allowing environmental override:
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
      authprotocol: "${AVAYA_SBCE_SNMP_AUTH_PROTO:-SHA}"
      authpassphrase: "${AVAYA_SBCE_SNMP_AUTH_PASS:-sbce_secret_auth_pass}"
      privprotocol: "${AVAYA_SBCE_SNMP_PRIV_PROTO:-DES}"
      privpassphrase: "${AVAYA_SBCE_SNMP_PRIV_PASS:-sbce_secret_priv_pass}"
```

---

## 2. Telemetry Matrix & Supported OID Catalog

The complete telemetry matrix is cataloged in `docs/monitoring/avaya-sbce-telemetry-matrix.md`.

### 2.1 Interface Mapping & 64-bit HC Octet Counters
Avaya SBCE physical interfaces are mapped into standard `IF-MIB` indices:
* **`M1`**: Primary Management Interface (SSH, EMS, Web GUI, SNMP polling).
* **`M2`**: Secondary / HA Heartbeat Interconnect.
* **`A1`**: External DMZ Interface (Carrier SIP Trunks, TLS/TCP Signaling, RTP Audio).
* **`B1`**: Internal Core Interface (Avaya Aura Session Manager, Core Media Servers).

All octet traffic items use 64-bit counters (`ifHCInOctets` / `ifHCOutOctets`) with `CHANGE_PER_SECOND` and 8x multiplier preprocessing to report precise bits per second (bps) without 32-bit roll-over distortions.

### 2.2 Appliance Resource Health
Avaya SBCE runs a hardened enterprise Linux operating system exposing standard system and resource MIBs:
* **CPU Utilization (`system.cpu.util`)**: OID `1.3.6.1.4.1.2021.11.11.0` (`ssCpuIdle`). Calculated as `100 - idle%`.
* **1-Minute Load Average (`system.cpu.load.avg1`)**: OID `1.3.6.1.4.1.2021.10.1.3.1` (`laLoad.1`).
* **Total Physical Memory (`vm.memory.total`)**: OID `1.3.6.1.2.1.25.2.3.1.5.1` (`hrStorageSize.1`) * allocation units.
* **Available Physical Memory (`vm.memory.available`)**: OID `1.3.6.1.4.1.2021.4.6.0` (`memAvailReal`) * 1024.
* **Calculated Memory Utilization (`vm.memory.util`)**: `(1 - (last(//vm.memory.available) / last(//vm.memory.total))) * 100`.
* **Root Filesystem Space Utilization (`vfs.fs.used.percent[/]`)**: OID `1.3.6.1.4.1.2021.9.1.9.1` (`dskPercent.1`).

---

## 3. Nawari Avaya SBCE Template Design

The template `provisioning/zabbix/templates/nawari_avaya_sbce.yaml` was designed and imported into Zabbix 7.4.

### 3.1 Template Architecture
* **Name:** `Nawari Avaya SBCE by SNMP`
* **Groups:** `Templates/Network devices`, `Templates/Applications`
* **Hierarchy:** Inherits `Nawari Generic SNMP Base` (inheriting ICMP ping, SNMP availability, sysName, sysDescr, uptime, and baseline restart triggers).

### 3.2 Low-Level Discovery (LLD)
* **Rule Key:** `sbce.interface.discovery`
* **SNMP OID:** `discovery[{#IFNAME},1.3.6.1.2.1.31.1.1.1.1]`
* **Filter:** Configurable via macros `{$SBCE.IF.MATCHES}` and `{$SBCE.IF.NOT_MATCHES}`.
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

### 3.3 Trigger Framework
* **High Severity:** Interface Link Down on voice signaling/media interfaces (`A1`, `B1`, `M1`). Expression: `last(/Nawari Avaya SBCE by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=2 and {$IFCONTROL}=1`.
* **Warning Severity:** High Bandwidth Utilization (`> 80%`).
* **Warning Severity:** High Error Rate (`> 2 errors/sec`).
* **Warning Severity:** High CPU Utilization (`> 85% for 5 min`).
* **Warning Severity:** High Memory Utilization (`> 90% for 5 min`).
* **Warning Severity:** High Root Disk Usage (`> 85%`).

---

## 4. SNMPv3 Security Profile Verification

The production appliance specifies SNMPv3 with `authPriv`:
* **User:** `Admin`
* **Authentication:** SHA-1 / SHA-256 (`authpassphrase: sbce_secret_auth_pass`)
* **Privacy / Encryption:** DES / AES-128 (`privpassphrase: sbce_secret_priv_pass`)

The mock agent container (`nawari-mock-snmp`) was enhanced to support real SNMPv3 `authPriv` with both DES and AES ciphers. Host queries and Zabbix server SNMP poller verification confirmed successful authenticated and encrypted communication:
```bash
snmpget -v3 -l authPriv -u Admin -a SHA -A sbce_secret_auth_pass -x DES -X sbce_secret_priv_pass 127.0.0.1:1161 1.3.6.1.2.1.1.5.0
# Returns: SNMPv2-MIB::sysName.0 = STRING: "nawari-mock-core-switch-01"
```

---

## 5. Fault Injection & Problem Lifecycle Validation

A rigorous test of the event-management lifecycle was executed against the simulated Avaya SBCE:
1. **Initial State:** Interface `A1` (External DMZ Signaling) was UP (`ifOperStatus: 1`), 0 active problems.
2. **Fault Injection:** Executed `/usr/local/bin/inject_fault.sh link-down A1`.
3. **Problem Event Creation:** Within Zabbix poller cycle, Zabbix triggered:
   * **Problem:** `Interface A1: Link down`
   * **Severity:** `4` (HIGH)
   * **Event ID:** `144`
4. **Recovery Injection:** Executed `/usr/local/bin/inject_fault.sh link-up A1`.
5. **Automatic Problem Resolution:** Zabbix poller detected `ifOperStatus: 1`, automatically closing the problem event.

---

## 6. Grafana Operational Dashboard (`nawari-sbce-health`)

A dedicated operational dashboard was built and provisioned at `docker/grafana/dashboards/avaya_sbce_operational_health.json`:
* **Dashboard Title:** `Nawari — Avaya SBCE Operational & Voice Telemetry`
* **UID:** `nawari-sbce-health`
* **Panels (19 total across 4 functional rows):**
  * **Row 1 (Appliance Health & System Resources):**
    * SNMPv3 Reachability Status (Stat: Green/Red)
    * System Uptime (Stat: Days/Hours)
    * CPU Utilization Gauge (0–100% with 75% warn, 85% crit thresholds)
    * RAM Utilization Gauge (0–100% with 80% warn, 90% crit thresholds)
    * Root Disk Utilization Gauge (0–100% with 75% warn, 85% crit thresholds)
    * 1-Minute Load Average (Stat with trend line)
  * **Row 2 (Voice Signaling & Media Interface Matrix):**
    * Interface `A1` Status (Stat: LINK UP / LINK DOWN)
    * Interface `B1` Status (Stat: LINK UP / LINK DOWN)
    * Interface `M1` Status (Stat: LINK UP / LINK DOWN)
    * Interface `M2` Status (Stat: LINK UP / LINK DOWN)
  * **Row 3 (Voice Path Traffic & Bandwidth Utilization):**
    * `A1` External DMZ Signaling Traffic (bps, In/Out time series)
    * `B1` Internal Media & Core Signaling Traffic (bps, In/Out time series)
  * **Row 4 (Voice Path Quality & Active Problem Feed):**
    * Packet Error Rate on Voice Paths (pps)
    * Packet Discard Rate on Voice Paths (pps)
    * Avaya SBCE Live Problem & Alarm Feed (`alexanderzobnin-zabbix-problems-panel`)

---

## 7. Automated Acceptance Verification

### 7.1 Test Suite Results
The full test suite was executed via `pytest`, verifying 42/42 tests passing with zero failures:
```text
tests/integration/test_core_infrastructure.py ............               [ 28%]
tests/integration/test_phase3_network_monitoring.py .........            [ 50%]
tests/integration/test_phase4_sbce_monitoring.py .........               [ 71%]
tests/integration/test_provisioning_idempotency.py ..                    [ 76%]
tests/unit/test_config_and_schema.py .....                               [ 88%]
tests/unit/test_diff_engine.py .....                                     [100%]

============================= 42 passed in 43.02s ==============================
```

### 7.2 Phase 4 Verification Gates (`scripts/verify_phase4.sh`)
The dedicated Phase 4 gate script passed all 8 acceptance checks:
1. `SNMPv3 authPriv Responsiveness (User: Admin, SHA/DES)` — **PASS**
2. `Avaya SBCE Template Hierarchy & LLD Rules` — **PASS**
3. `SBCE Hosts Provisioned (Mock & Production Reconciled)` — **PASS**
4. `LLD Discovery of Voice Interfaces (M1, M2, A1, B1)` — **PASS**
5. `SBCE Appliance Resource Telemetry Active (CPU/RAM/Disk/Load)` — **PASS**
6. `Historical Metric Persistence in PostgreSQL` — **PASS**
7. `Voice Interface Fault Injection & Auto-Recovery (A1 Link Down)` — **PASS**
8. `Grafana Avaya SBCE Operational Dashboard (19 Panels)` — **PASS**

---

## 8. Git Commit & Phase 5 Transition

All Phase 4 deliverables are ready for commit to the `main` branch. 

With appliance-level observability, SNMPv3 security, and interface telemetry verified, the platform is prepared for **Phase 5: Voice Telemetry, SIP Health & Synthetic Call Testing**, which will introduce:
1. Asterisk 22 synthetic SIP call generation in an isolated profile.
2. SIP signaling transaction metrics (INVITE, 200 OK, BYE, 4xx/5xx failure rates).
3. RTP voice stream quality telemetry (Jitter, Packet Loss, RTT, estimated MOS).
4. Correlated service health metrics bridging network transport to voice user experience.
