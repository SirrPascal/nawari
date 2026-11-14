# Nawari Phase 3: Network Device Monitoring & Telemetry Verification Report

## 1. Executive Summary

Phase 3 establishes the reusable **Network Device Monitoring Framework** for **Nawari**.
In strict adherence to the project charter:
> **"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services."**

Crucially, Phase 3 satisfies the explicit architectural mandate:
> **"Make the acceptance criteria include real SNMP polling and verified historical item data — not just successful template creation."**

Rather than relying on mocked database records or static mock templates, Nawari now features:
1. A live **Mock SNMP Agent** container simulating an enterprise core switch/gateway with IF-MIB virtual interfaces.
2. A declarative **SNMP Template Hierarchy** (`Nawari Generic SNMP Base` and `Nawari Network Device by SNMP`) version-controlled as code.
3. Automated **Low-Level Discovery (LLD)** discovering physical and logical interfaces while filtering out loopback and virtual link noise.
4. Active collection and verification of **real historical telemetry records** in PostgreSQL via Zabbix's `history.get` API.
5. An end-to-end **fault injection lifecycle** demonstrating automatic alert firing on interface down and automatic resolution on interface recovery.
6. Two provisioned **Grafana Operational Dashboards** for system overview and granular interface performance analysis.

---

## 2. Architecture & Components

```text
nawari/
├── docker/
│   ├── compose.yaml                # Production baseline stack
│   ├── compose.dev.yaml            # Dev stack including mock-snmp service
│   ├── mock-snmp/                  # Net-SNMP 5.9 simulation service
│   │   ├── Dockerfile
│   │   ├── snmpd.conf              # MIB-2, IF-MIB, and community configuration
│   │   ├── entrypoint.sh           # Dummy interface creation and traffic generator
│   │   └── inject_fault.sh         # Dynamic fault injection (link-down / link-up)
│   └── grafana/
│       └── dashboards/
│           ├── network_infrastructure_overview.json   # Fleet reachability & status
│           └── interface_traffic_health.json          # Granular bandwidth & error metrics
├── provisioning/zabbix/
│   ├── templates/                  # Version-controlled Zabbix 7.4 YAML templates
│   │   ├── nawari_generic_snmp.yaml      # Base system identity, uptime, ICMP
│   │   └── nawari_network_device.yaml    # IF-MIB LLD, metrics, triggers, macros
│   └── hosts/
│       ├── avaya_voice_infrastructure.yaml # Avaya SBCE target profile
│       ├── core_network.yaml               # Core gateway target profile
│       └── mock_network_device.yaml        # Simulated core switch (Phase 3 target)
├── services/api/
│   └── provisioning/
│       └── reconciler.py           # Enhanced with sync_templates() declarative importer
├── tests/integration/
│   └── test_phase3_network_monitoring.py  # 9 automated end-to-end integration tests
└── scripts/
    └── verify_phase3.sh            # 8-gate acceptance verification script
```

---

## 3. Reusable SNMP Template Hierarchy

Templates are authored in native Zabbix 7.4 YAML with deterministic UUIDv4 identifiers, enabling 100% idempotent import and synchronization across environments.

### A. Nawari Generic SNMP Base (`nawari_generic_snmp.yaml`)
Provides universal system identity, reachability, and availability metrics for all SNMP-enabled assets:
- **System Identity:** `sysName` (`1.3.6.1.2.1.1.5.0`), `sysDescr` (`1.3.6.1.2.1.1.1.0`), `sysContact` (`1.3.6.1.2.1.1.4.0`), `sysLocation` (`1.3.6.1.2.1.1.6.0`), `sysObjectID` (`1.3.6.1.2.1.1.2.0`).
- **Uptime:** `sysUpTimeInstance` (`1.3.6.1.2.1.1.3.0`) with `0.01` multiplier.
- **Availability:** `zabbix[host,snmp,available]` internal check.
- **ICMP Reachability:** `icmpping`, `icmppingloss`, `icmppingsec`.
- **Alert Triggers:**
  - SNMP agent unreachable (High, 3 failed checks).
  - Device rebooted recently (< 10 minutes uptime).
  - High ICMP packet loss (`>{$ICMP_LOSS_WARN}`, default 20%).
  - Elevated ICMP latency (`>{$ICMP_RESPONSE_TIME_WARN}`, default 150ms).

### B. Nawari Network Device by SNMP (`nawari_network_device.yaml`)
Inherits `Nawari Generic SNMP Base` and defines standard IF-MIB discovery:
- **Discovery Rule:** `net.if.discovery` via SNMP OID:
  ```text
  discovery[{#IFNAME},1.3.6.1.2.1.31.1.1.1.1,{#IFDESCR},1.3.6.1.2.1.2.2.1.2,{#IFTYPE},1.3.6.1.2.1.2.2.1.3,{#IFOPERSTATUS},1.3.6.1.2.1.2.2.1.8,{#IFADMINSTATUS},1.3.6.1.2.1.2.2.1.7]
  ```
- **Filter:** Automatically discards loopback and tunnel interfaces:
  `{$NET.IF.IFNAME.NOT_MATCHES}` = `^(lo|gre0|tunl0|sit0|erspan0|gretap0|ip_vti0|ip6.*)$`
- **Metric Prototypes:**
  1. `net.if.status[ifOperStatus.{#SNMPINDEX}]` (Operational Status: 1=UP, 2=DOWN)
  2. `net.if.adminstatus[ifAdminStatus.{#SNMPINDEX}]` (Admin Status)
  3. `net.if.speed[ifSpeed.{#SNMPINDEX}]` (Link Speed in bps)
  4. `net.if.in[ifInOctets.{#SNMPINDEX}]` (Inbound Traffic bps: `CHANGE_PER_SECOND` * 8)
  5. `net.if.out[ifOutOctets.{#SNMPINDEX}]` (Outbound Traffic bps: `CHANGE_PER_SECOND` * 8)
  6. `net.if.in.errors[ifInErrors.{#SNMPINDEX}]` (Inbound Error Rate: err/s)
  7. `net.if.out.errors[ifOutErrors.{#SNMPINDEX}]` (Outbound Error Rate: err/s)
  8. `net.if.in.discards[ifInDiscards.{#SNMPINDEX}]` (Inbound Discards: pps)
  9. `net.if.out.discards[ifOutDiscards.{#SNMPINDEX}]` (Outbound Discards: pps)
- **Trigger Prototypes:**
  1. **Link Down:** `{$IFCONTROL:"{#IFNAME}"}=1 and last(...) = 2` (Average severity)
  2. **High Bandwidth Utilization (>80%):** Inbound or outbound rate exceeds `{$IF_UTIL_MAX}`% of link speed (Warning severity)
  3. **High Error Rate:** Inbound or outbound error rate exceeds `{$IF_ERRORS_WARN}` (Warning severity)

---

## 4. Live Verification: Discovery, Polling & Historical Metrics

Using the simulated target `mock-core-switch-01` (`nawari-mock-snmp`), the framework was verified end-to-end:

### A. Interface Discovery Execution
- The LLD rule executed and automatically discovered interfaces:
  - `ge-0-0-1`: Primary Core Uplink
  - `ge-0-0-2`: Voice VLAN Trunk
  - `sbc-ext0`: External SIP DMZ
  - `sbc-int0`: Internal Media Interface
  - `eth0`: Management network
- Noise filtering verified: Loopback (`lo`) and tunnel devices were excluded.
- Total item count expanded from 10 base items to **55 live monitored items**.

### B. Real Historical Metric Storage (PostgreSQL)
Historical metric persistence was confirmed directly via Zabbix API `history.get`:
- `system.name`: `"nawari-mock-core-switch-01"` (history table `history_str`)
- `system.uptime[sysUpTime.0]`: `478.79`, `483.81` seconds (history table `history`)
- `net.if.status[ifOperStatus.12]`: `1` (UP) (history table `history_uint`)

---

## 5. Fault Injection & Problem Lifecycle Verification

The monitoring loop was tested through controlled fault injection:
1. **Link Down Injection:**
   ```bash
   docker exec nawari-mock-snmp /usr/local/bin/inject_fault.sh link-down ge-0-0-1
   ```
   - Linux kernel set `ge-0-0-1` to DOWN.
   - Net-SNMP reported `ifOperStatus.12 = down(2)`.
   - Zabbix poller detected status transition and fired trigger `32596` (`Interface ge-0-0-1: Link down`).
   - Active problem event generated in Zabbix: `name: 'Interface ge-0-0-1: Link down', severity: 3`.

2. **Link Up Recovery:**
   ```bash
   docker exec nawari-mock-snmp /usr/local/bin/inject_fault.sh link-up ge-0-0-1
   ```
   - Linux kernel set `ge-0-0-1` to UP.
   - Net-SNMP reported `ifOperStatus.12 = up(1)`.
   - Zabbix poller detected status recovery.
   - Trigger returned to value `0` (OK) and Problem event cleared automatically.

---

## 6. Grafana Operational Dashboards

Two production-grade Grafana dashboards were provisioned and linked to the Zabbix datasource:

1. **`Nawari — Network Infrastructure Overview` (`nawari-net-overview`):**
   - Fleet-level SNMP availability and reachability stats.
   - Device inventory table with live uptime, descriptions, and ICMP latency.
   - Interface operational state matrix (table of all discovered interfaces with UP/DOWN color badges).
   - Live problem incident feed powered by the Zabbix Problems panel.

2. **`Nawari — Interface Traffic & Performance Health` (`nawari-interface-health`):**
   - Dynamic template variables for `$group`, `$host`, and `$interface`.
   - Time-series graph for Ingress and Egress traffic (bps) with 70% (yellow) and 80% (red) utilization threshold lines.
   - Time-series graph for packet error rates (err/s) with 2 err/s warning threshold.
   - Time-series graph for packet discard rates (pps).
   - Current operational and administrative state indicator panels.

---

## 7. Automated Acceptance Suite Results

The Phase 3 implementation is verified by two test harnesses:

### A. Pytest Integration Suite (`tests/`)
```text
============================= 33 passed in 25.28s ==============================
- Core Docker Infrastructure (Phase 1):           12/12 PASSED
- Declarative Provisioning Idempotency (Phase 2):   2/2  PASSED
- Network Device Monitoring & LLD (Phase 3):       9/9  PASSED
- Configuration & Diff Engine Unit Tests:         10/10 PASSED
```

### B. Shell Acceptance Script (`scripts/verify_phase3.sh`)
```text
======================================================================
NAWARI PHASE 3 ACCEPTANCE VERIFICATION: NETWORK OBSERVABILITY
======================================================================
[TEST] Mock Net-SNMP Daemon UDP 161 ... PASS
[TEST] Template Hierarchy (Base + Network Device) ... PASS
[TEST] Mock Host Provisioning & Group Linkage ... PASS
[TEST] LLD Interface Discovery (IF-MIB) ... PASS
[TEST] Real PostgreSQL Historical Telemetry ... PASS
[TEST] Trigger Prototypes Instantiation ... PASS
[TEST] Provisioned Grafana Dashboards ... PASS
[TEST] Full Phase 3 Integration Suite (9/9) ... PASS
----------------------------------------------------------------------
VERIFICATION SUMMARY: 8 Passed, 0 Failed
----------------------------------------------------------------------
>> ALL PHASE 3 ACCEPTANCE GATES PASSED <<
```

