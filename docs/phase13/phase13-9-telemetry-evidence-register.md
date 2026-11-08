# Phase 13.9 — Telemetry Evidence & Provenance Register

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Staging Audited & Gated  
**Platform:** Zabbix 7.4.16 / PostgreSQL Engine on `mon-grafana01`  
**Data Artifact:** `provisioning/zabbix/snapshots/phase13_9_telemetry_commissioning_evidence.json`

---

## 1. Overview & Provenance Framework

To maintain absolute data integrity and prevent synthetic data from being mistaken for real physical hardware measurements, Nawari classifies every monitored item using an authoritative **7-State Telemetry Ontology**:

1. **`VERIFIED_LIVE`:** Telemetry actively polled from a live responding device or confirmed staging agent. Proven with direct SNMP/socket queries.
2. **`CONFIGURED_UNVERIFIED`:** Authentic vendor MIB OIDs configured on production host definitions, awaiting L3 network route commissioning.
3. **`SIMULATED`:** Deterministic staging trapper items used for controlled fault-injection and incident lifecycle testing.
4. **`NOT_COLLECTED`:** Valid operational metrics intentionally gated because required hardware childboards, vendor APIs, or carrier agreements are uncommissioned.
5. **`UNSUPPORTED`:** Deprecated or non-existent MIB objects purged from templates.
6. **`STALE`:** Items with last collection timestamp exceeding $3 \times \text{polling interval}$.
7. **`BLOCKED_ACCESS`:** Physical devices whose target IP addresses are off-net or unrouted from the monitoring station.

---

## 2. Telemetry Classification Summary

```
+----------------------------------------------------------------------------------------------------+
|                                    NAWARI TELEMETRY PROVENANCE LEDGER                              |
+--------------------------+-------+------------+----------------------------------------------------+
| Classification           | Count | Percentage | Primary Monitored Domains                          |
+--------------------------+-------+------------+----------------------------------------------------+
| VERIFIED_LIVE            | 179   | 42.42%     | Net-SNMP mock agent, Asterisk probe, Zabbix server |
| CONFIGURED_UNVERIFIED    | 81    | 19.19%     | Avaya CM, SM, G450, Core Gateway SNMP templates    |
| SIMULATED                | 162   | 38.39%     | Staging fault-injection trappers (voice, storage)  |
| NOT_COLLECTED (Gated)    | 5     | Gated      | G450 DSP util, per-call RTCP, EMS 4xx/5xx, Verint  |
| UNSUPPORTED              | 0     | 0.00%      | Purged legacy draft OIDs                           |
| BLOCKED_ACCESS           | 8     | Target IPs | Off-net RFC 1918 production IPs (10.2.156.0/24)    |
+--------------------------+-------+------------+----------------------------------------------------+
| TOTAL AUDITED ITEMS      | 422   | 100.00%    | Across all 12 Monitored Hosts in Zabbix            |
+--------------------------+-------+------------+----------------------------------------------------+
```

---

## 3. Representative Item Provenance Register (Sample Audit)

```
+----+----------------------+-------------------+-----------------------+---------------------------------------+---------------+-------------------------+
| ID | Host Visible Name    | Subsystem         | Item Key              | SNMP OID / Source                     | Polling Delay | Telemetry Status        |
+----+----------------------+-------------------+-----------------------+---------------------------------------+---------------+-------------------------+
| 01 | Simulated Core Switch| NETWORK_CORE      | system.descr[sysDescr]| .1.3.6.1.2.1.1.1.0                    | 1h            | VERIFIED_LIVE           |
| 02 | Simulated Core Switch| NETWORK_CORE      | system.uptime[sysUpT] | .1.3.6.1.2.1.1.3.0                    | 1m            | VERIFIED_LIVE           |
| 03 | Simulated Core Switch| NETWORK_CORE      | net.if.in[ifHCInOct11]| .1.3.6.1.2.1.31.1.1.1.6.11 (eth0)     | 1m            | VERIFIED_LIVE           |
| 04 | Simulated Core Switch| NETWORK_CORE      | net.if.out[ifHCOut11] | .1.3.6.1.2.1.31.1.1.1.10.11 (eth0)    | 1m            | VERIFIED_LIVE           |
| 05 | Simulated Core Switch| NETWORK_CORE      | core.switch.total_out | Zabbix trapper (Incident injection)   | 0 (trapper)   | SIMULATED               |
| 06 | Avaya SBCE Primary   | AVAYA_SBCE        | system.cpu.util       | .1.3.6.1.4.1.2021.11.11.0             | 1m            | VERIFIED_LIVE (M1)      |
| 07 | Avaya SBCE Primary   | AVAYA_SBCE        | vfs.fs.used.percent[/]| .1.3.6.1.4.1.2021.9.1.9.1             | 5m            | VERIFIED_LIVE (M1)      |
| 08 | Avaya SBCE Primary   | AVAYA_SBCE        | ems.sip.server_errors | GATED (EMS API Token Required)        | N/A           | NOT_COLLECTED           |
| 09 | Avaya CM Duplex      | AVAYA_CM          | avaya.cm.ip_voice.loss| .1.3.6.1.4.1.6889.2.73.8.1.67.1.10.1  | 1h            | CONFIGURED_UNVERIFIED   |
| 10 | Avaya CM Duplex      | AVAYA_CM          | avaya.cm.ip_voice.jitt| .1.3.6.1.4.1.6889.2.73.8.1.67.1.11.1  | 1h            | CONFIGURED_UNVERIFIED   |
| 11 | Avaya CM Duplex      | AVAYA_CM          | avaya.cm.call_rate.att| .1.3.6.1.4.1.6889.2.73.8.1.145.1.2.1 | 5m            | CONFIGURED_UNVERIFIED   |
| 12 | Avaya CM Duplex      | AVAYA_CM          | avaya.cm.live_rtcp    | GATED (Per-call RTCP pipeline needed) | N/A           | NOT_COLLECTED           |
| 13 | Avaya G450 Gateway   | AVAYA_G450        | avaya.g450.cm_reg_stat| .1.3.6.1.4.1.6889.2.69.2.1.4.1        | 1m            | CONFIGURED_UNVERIFIED   |
| 14 | Avaya G450 Gateway   | AVAYA_G450        | ifOperStatus.e1.1     | .1.3.6.1.2.1.2.2.1.8.1                | 1m            | CONFIGURED_UNVERIFIED   |
| 15 | Avaya G450 Gateway   | AVAYA_G450        | avaya.g450.dsp_util   | GATED (MP20/80 childboard audit req.) | N/A           | NOT_COLLECTED           |
| 16 | Voice Synthetic Probe| VOICE_QUALITY     | voice.synthetic.mos   | Asterisk AMI G.107 E-model pipeline   | 1m            | VERIFIED_LIVE           |
| 17 | Voice Synthetic Probe| VOICE_QUALITY     | voice.synthetic.jitter| Asterisk RTCP synthetic measurement   | 1m            | VERIFIED_LIVE           |
| 18 | Safaricom SIP Trunk  | CARRIER_SIP       | sip.trunk.options_stat| SIP OPTIONS handshake trapper / probe | 30s           | SIMULATED               |
| 19 | Safaricom SIP Trunk  | CARRIER_SIP       | carrier.deep.sla_pct  | GATED (Carrier SLA API required)       | N/A           | NOT_COLLECTED           |
| 20 | Avaya CMS & WFO      | RECORDING_CMS      | wfo.recording.disk_free| CMS storage partition trapper         | 1m            | SIMULATED               |
| 21 | Avaya CMS & WFO      | RECORDING_CMS      | wfo.verint.pipeline   | GATED (Verint vendor API required)     | N/A           | NOT_COLLECTED           |
+----+----------------------+-------------------+-----------------------+---------------------------------------+---------------+-------------------------+
```

---

## 4. Rate-Based Interface Throughput Computation Evidence

Nawari enforces rate-based calculations for all network bandwidth monitoring. Testing confirmed counter deltas on 64-bit High-Capacity counters:

### Formula
$$\text{Throughput (bps)} = \frac{(\text{ifHCInOctets}_{t_2} - \text{ifHCInOctets}_{t_1}) \times 8}{t_2 - t_1}$$

### Direct SNMP Verification Log
```text
Sample t1: 19:28:24.120 -> Counter64: 5562140
Sample t2: 19:28:25.240 -> Counter64: 5562140 (Delta = 0 octets over 1.12s)
Computed Rate: 0.00 bps (Accurate idle interface reading)

Synthetic Rate Verification (Unit Test):
Sample t1: 1,000,000 octets
Sample t2: 2,000,000 octets
Elapsed: 10.0 seconds
Computed Rate: ((2,000,000 - 1,000,000) * 8) / 10.0 = 800,000.00 bps (800 kbps) -> MATCH
```

---

## 5. Direct Source Evidence Comparison

| Measured Metric | Direct Net-SNMP Query Output | Zabbix Database Retrieved Value | Correlation Status |
| :--- | :--- | :--- | :--- |
| **System Description** | `"Nawari Aviation Simulated Core Switch & Distribution Gateway (Net-SNMP 5.9)"` | `"Nawari Aviation Simulated Core Switch & Distribution Gateway (Net-SNMP 5.9)"` | **100% IDENTICAL** |
| **System Uptime** | `7908851 Timeticks (21:58:08.51)` | Matches Zabbix history clock | **100% CORRELATED** |
| **SNMPv3 Authentication** | User: `Admin_sha256`, Protocol: SHA-256 | Configured in Zabbix host macro `{$SNMP_SECNAME}` | **100% MATCH** |
| **64-bit HC In Octets** | 19 interface counters traversed via IF-MIB | Discovered via LLD prototype `.1.3.6.1.2.1.31.1.1.1.6` | **100% MATCH** |

