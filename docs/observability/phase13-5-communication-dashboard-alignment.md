# Phase 13.5: Communication Observability Dashboard Alignment & Runtime Telemetry Validation

**Status:** IMPLEMENTED AND VALIDATED  
**Date:** 2026-11-08  
**Environment:** Local Staging Docker Environment (`localhost:8088` / `localhost:3001`)  
**Production Mutation Gate:** LOCKED (`HARD_PRODUCTION_DENY` strictly enforced on `mon-grafana01`)  
**Git Baseline:** `0f9773f` $\rightarrow$ Phase 13.5 Delivery  

---

## Executive Summary

Phase 13.5 completes the end-to-end alignment between Nawari's declarative monitoring layer in Zabbix 7.4 and the operational Grafana dashboards in the `Nawari / Communication Observability` domain. This addresses the three core findings highlighted during the Phase 13.4 evaluation:

1. **Definitive Reconciliation of the 45-versus-59 Trigger Inventory:**  
   The mathematical and operational relationship between the 45 high-level communication alert rules in the catalogue and the 59 concrete triggers provisioned across the 7 Zabbix communication templates is fully documented, verified, and reconciled.
2. **Runtime Telemetry Collection & Item Support Audit:**  
   Every item across all 7 monitored communication hosts was inspected against the live Zabbix API. Items actively collecting data, items awaiting physical layer-3 IP reachability, and calculated items pending underlying metrics are explicitly catalogued. Unsupported items are verified not to be masked as healthy.
3. **Communication Observability Dashboard Alignment:**  
   All 11 dashboards in `docker/grafana/dashboards/communication_observability/` have been audited. Nonexistent legacy hostnames (`nawari-sm-01`, `nawari-cm-01`, etc.) have been completely removed and replaced with authoritative Zabbix hostnames (`avaya-sbce-01`, `avaya-sm-01`, `avaya-cm-01`, `avaya-g450-01`, `sip-trunk-carrier-01`, `avaya-cms-01`, `nawari-voice-probe-01`). A native Zabbix Problems panel (`alexanderzobnin-zabbix-problems-panel`) has been integrated into the executive overview and device dashboards to surface firing alerts in real time.
4. **Honest Telemetry Contract & Real vs Synthetic Separation:**  
   Dashboards strictly enforce null preservation (`spanNulls: False`, explicit "No Data" mappings). Real-call audio quality (packet loss, jitter, delay) is sourced from Avaya Communication Manager hourly MIB tables (`avCmMeasIpVoStatHrData`), while Real-Call MOS is explicitly labeled `[NOT INSTRUMENTED — RTCP XR REQUIRED]` and never faked with synthetic probe metrics.

---

## 1. Definitive Reconciliation: 45 Alert Catalogue Rules vs 59 Zabbix Triggers

### Summary of Template Trigger Counts

| # | Zabbix Template Name | Catalogue Rules | Live Zabbix Triggers | Net Delta | Delta Classification |
|---|---|:---:|:---:|:---:|---|
| 1 | `Nawari Avaya SBCE by SNMP` | 8 | 15 | +7 | 4 Base SNMP inherited + 3 OS resource monitors |
| 2 | `Nawari Avaya Session Manager by SNMP` | 9 | 12 | +3 | 3 Abstract SIP entity states split into CM + SBCE targets |
| 3 | `Nawari Avaya Communication Manager by SNMP` | 6 | 6 | 0 | Exact 1:1 match with Phase 13.3 catalogue |
| 4 | `Nawari Avaya G450 Media Gateway by SNMP` | 6 | 7 | +1 | +1 Dedicated H.248 controller registration trigger |
| 5 | `Nawari SIP Trunk by Trapper` | 6 | 6 | 0 | Exact 1:1 match with Phase 13.3 catalogue |
| 6 | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 6 | 9 | +3 | +1 One-way audio + 1 Degraded MOS warning + 1 Stale probe watchdog |
| 7 | `Nawari Avaya CMS and WFO by Trapper` | 4 | 4 | 0 | Exact 1:1 match with Phase 13.3 catalogue |
| **TOTAL** | **7 Communication Templates** | **45** | **59** | **+14** | **Fully accounted for across inheritance and granularity** |

---

### Detailed Account of the 14 Additional Triggers

The 14 triggers that exist in Zabbix beyond the 45 catalogue rule areas represent necessary operational granularity, hardware health inheritance, and watchdog protections:

#### A. SBCE Base SNMP and OS Resource Utilization (+7 Triggers)
The Phase 13.3 catalogue defined 8 SIP-specific rules for the SBCE (reachability, capacity warning/critical, SIP failure rate, licenses, interface errors, stale telemetry). The live template adds:
1. `Nawari Generic SNMP Base: SNMP agent is not responding` [High] — Inherited from base SNMP template.
2. `Nawari Generic SNMP Base: Device has just been restarted` [Warning] — Inherited uptime watchdog.
3. `Nawari Generic SNMP Base: High ICMP ping loss` [Warning] — Inherited link-layer packet loss.
4. `Nawari Generic SNMP Base: High ICMP response time` [Warning] — Inherited link-layer RTT watchdog.
5. `Avaya SBCE: High CPU utilization (> {$CPU.UTIL.WARN}%)` [Warning] — Appliance processor health.
6. `Avaya SBCE: High memory utilization (> {$MEMORY.UTIL.WARN}%)` [Warning] — Linux kernel memory health.
7. `Avaya SBCE: High root filesystem disk usage (> {$DISK.UTIL.WARN}%)` [Warning] — Spool and log partition health.

#### B. Session Manager Granular Per-Entity Monitoring (+3 Triggers)
In the Phase 13.3 catalogue, rules 15, 16, and 17 defined generic alert logic for SIP Entity states:
- *Catalogue Rule 15:* SIP Entity DOWN
- *Catalogue Rule 16:* SIP Entity PARTIALLY UP
- *Catalogue Rule 17:* SIP Entity DENY NEW SERVICE

In production Zabbix, Communication Manager and SBCE are separate monitored entity targets with distinct SNMP OIDs / API keys. Thus, each abstract rule expands into two concrete triggers:
- `Avaya SM: SIP Entity Down (Communication Manager)` [Disaster]
- `Avaya SM: SIP Entity Down (Avaya SBCE)` [Disaster]
- `Avaya SM: SIP Entity PARTIALLY UP (Communication Manager)` [Average]
- `Avaya SM: SIP Entity PARTIALLY UP (Avaya SBCE)` [Average]
- `Avaya SM: SIP Entity DENY NEW SERVICE (Communication Manager)` [High]
- `Avaya SM: SIP Entity DENY NEW SERVICE (Avaya SBCE)` [High]  
*Net expansion:* $6 - 3 = +3$ triggers.

#### C. G450 Gateway H.248 Controller Registration (+1 Trigger)
- `Avaya G450: Media Gateway Unregistered from Communication Manager` [High]  
  *Justification:* The G450 chassis reachability trigger (ICMP) detects physical connectivity, but the gateway can be pingable while completely severed from Communication Manager H.248 call control. This dedicated trigger detects H.248 unregistration (`avaya.g450.cm_registration_state != 1`).

#### D. Voice Synthetic Probe Watchdogs & Granular Severity (+3 Triggers)
The Phase 13.3 catalogue defined 6 rules for synthetic call testing. The Zabbix template includes 3 operational additions:
1. `One-way audio detected on synthetic voice test` [High] — Specifically alerts when RTP packets are received in only one direction (firewall NAT or asymmetric routing failure).
2. `Degraded voice quality on synthetic probe (MOS < 3.8)` [Warning] — Early warning before hitting the High severity threshold ($MOS < 3.5$).
3. `Synthetic voice probe telemetry is stale (>15m)` [Warning] — Watchdog trigger alerting if the local test runner daemon terminates or fails to push results.

---

## 2. Runtime Telemetry Collection & Item Audit

A comprehensive live audit of all 7 monitored communication hosts was executed against the running Zabbix instance (`localhost:8088`).

### Host Inventory & Collection Status Matrix

| Host Technical Name | Visible Host Name | IP / Port | Linked Templates | Total Items | Supported | Unsupported | Live Data Arriving? | Telemetry Provenance State |
|---|---|---|---|:---:|:---:|:---:|:---:|---|
| `nawari-voice-probe-01` | Nawari Voice Synthetic Probe 01 | `127.0.0.1:10050` | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 14 | 14 | 0 | **YES (12 items)** | `SYNTHETIC_PROBE` (Local Asterisk) |
| `mock-avaya-sbce-01` | Simulated Avaya SBCE 01 (Lab) | `127.0.0.1:1161` | `Nawari Avaya SBCE by SNMP` | 107 | 107 | 0 | **YES (99 items)** | `SIMULATED` (nawari-mock-snmp) |
| `avaya-sbce-01` | Avaya SBCE Primary (HQ-DMZ) | `10.2.156.131:161` | `Nawari Avaya SBCE by SNMP` | 26 | 25 | 1 | Polling (val=0) | `CONFIGURED_UNVERIFIED` (Staging/Gated) |
| `avaya-sm-01` | Avaya Session Manager Primary | `10.2.156.22:161` | `Nawari Avaya Session Manager by SNMP` | 11 | 11 | 0 | Polling (val=0) | `CONFIGURED_UNVERIFIED` (Staging/Gated) |
| `avaya-cm-01` | Avaya Communication Manager Duplex | `10.102.10.25:161` | `Nawari Avaya Communication Manager by SNMP` | 12 | 12 | 0 | Polling (val=0) | `CONFIGURED_UNVERIFIED` (Staging/Gated) |
| `avaya-g450-01` | Avaya G450 Media Gateway | `10.2.156.60:161` | `Nawari Avaya G450 Media Gateway by SNMP` | 8 | 8 | 0 | Polling (val=0) | `CONFIGURED_UNVERIFIED` (Staging/Gated) |
| `sip-trunk-carrier-01` | Safaricom SIP Carrier Interconnect | `10.2.156.100` | `Nawari SIP Trunk by Trapper` | 6 | 6 | 0 | Polling (val=0) | `CONFIGURED_UNVERIFIED` (Staging/Gated) |
| `avaya-cms-01` | Avaya CMS and WFO Recording | `127.0.0.1:10050` | `Nawari Avaya CMS and WFO by Trapper` | 6 | 6 | 0 | Awaiting trapper | `CONFIGURED_UNVERIFIED` (Trapper target) |

---

### Audit Findings on Physical Targets & Item Support

1. **Local Live Telemetry is Flowing:**
   - `nawari-voice-probe-01` is actively receiving live test results from `nawari-asterisk` container (`setup_time=200ms`, `duration=5.02s`, `sip_status=200`, `outcome=ANSWERED`, `mos=4.41`).
   - `mock-avaya-sbce-01` is actively receiving live SNMPv3 data from `nawari-mock-snmp` on port 1161 (CPU, memory, disk, network interfaces A1/B1/M1).
2. **Physical Targets Polling Responsively:**
   - Physical production targets (`avaya-sbce-01`, `avaya-sm-01`, `avaya-cm-01`, `avaya-g450-01`, `sip-trunk-carrier-01`) have their ICMP simple checks polling. Because the local Docker staging network does not route to Kenya Airways corporate VLANs (`10.2.156.0/24`, `10.102.10.0/24`), these return `val=0` (unreachable), and Zabbix triggers correctly generate `[DISASTER]` and `[HIGH]` problems.
3. **Unsupported Item Audit on `avaya-sbce-01`:**
   - Item: `Appliance memory utilization` (`vm.memory.util`)
   - Type: `CALCULATED` (formula: `(1 - (last(//vm.memory.available) / last(//vm.memory.total))) * 100`)
   - State: `UNSUPPORTED` (Reason: `Cannot evaluate function: not enough data at "last(//vm.memory.available)"`).
   - *Analysis:* This is expected behavior for Zabbix calculated items prior to receiving initial values for the underlying constituent items (`vm.memory.available` and `vm.memory.total`). Once physical SNMP polling is established during Phase 8.2 commissioning, this item transitions to `SUPPORTED`. It is **not** silently treated as healthy.

---

## 3. Communication Observability Dashboard Alignment

### Complete Elimination of Legacy Hostnames

All 11 dashboards in `docker/grafana/dashboards/communication_observability/` were audited and updated to remove legacy/staging placeholder names:

- `nawari-sbce-01` $\rightarrow$ `avaya-sbce-01` (or approved regex `/.*sbce.*/`)
- `nawari-sm-01` $\rightarrow$ `avaya-sm-01`
- `nawari-cm-01` $\rightarrow$ `avaya-cm-01`
- `avaya-cm-01.nawari.local` $\rightarrow$ `avaya-cm-01`
- `nawari-g450-01` $\rightarrow$ `avaya-g450-01`
- `nawari-cms-01` $\rightarrow$ `avaya-cms-01`
- `nawari-wfo-01` $\rightarrow$ `avaya-cms-01`
- Carrier trunk targets $\rightarrow$ `sip-trunk-carrier-01`

### Integration of Native Zabbix Problems Panel

The executive dashboard `nawari_communication_overview.json` now includes a native Zabbix Problems panel:
- **Panel ID:** 16
- **Title:** `Active Voice Infrastructure Problems [ZABBIX NATIVE EVENT ENGINE]`
- **Panel Plugin:** `alexanderzobnin-zabbix-problems-panel` (Alexander Zobnin Zabbix App v6.10.2)
- **Host Groups Filter:** `/Voice Infrastructure|Avaya Infrastructure|Edge SBC|SIP Carrier Trunks|Communications Applications/`
- **Host Filter:** `/.*/`
- **Result Format:** `problems`
- **Displayed Columns:** Time, Recovery time, Severity, Host, Problem Name, Duration, Acknowledgment Status.
- **Operational Value:** Real-time visibility into firing communication alarms with severity-based coloring (Information, Warning, Average, High, Disaster) directly aligned with Zabbix's event state.

---

## 4. Telemetry Integrity: Real vs Synthetic Separation

### Strict Enforcement of Audio Quality Truth

| Metric | Dashboard Display Title | Source Protocol | Telemetry Nature | Null / Missing Data Handling |
|---|---|---|---|---|
| **Real-Call MOS** | `Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]` | None (Pending RTCP-XR RFC 3611 Block 7) | `NOT_YET_COLLECTED` | Strictly renders `Not Instrumented (RTCP-XR Required)`; never faked with synthetic MOS. |
| **Real-Call Packet Loss** | `Real-Call Packet Loss % (CM Last Hour) [REAL — AVAYA SNMP]` | SNMP (Avaya CM MIB table `avCmMeasIpVoStatHrData`, leaf `.6`) | `REAL` (Historical hourly) | Strictly renders `No Data` when uncollected; never coerced to `0%`. |
| **Real-Call Peak Jitter** | `Real-Call Peak Jitter (Last Hour) [REAL — AVAYA SNMP]` | SNMP (Avaya CM MIB `avCmMeasIpVoStatHrData`, leaf `.7`) | `REAL` (Historical hourly) | Strictly renders `No Data` when uncollected. |
| **Real-Call Peak Delay** | `Real-Call Peak Delay (Last Hour) [REAL — AVAYA SNMP]` | SNMP (Avaya CM MIB `avCmMeasIpVoStatHrData`, leaf `.8`) | `REAL` (Historical hourly) | Strictly renders `No Data` when uncollected. |
| **Synthetic Voice MOS** | `Synthetic Voice MOS [SYNTHETIC — ASTERISK]` | Zabbix Trapper / Asterisk AMI (`voice.synthetic.mos`) | `SYNTHETIC` | Renders live probe MOS (4.41); hover description explicitly states probe limitation. |

---

## 5. Notification Pipeline & Security Boundaries

### Administrator Notification Readiness

All four designated Kenya Airways administrators are fully provisioned in Zabbix:
- **User Group:** `Nawari Avaya & Communications Administrators` (ID: `16`)
- **Action:** `Nawari Avaya & Communication Alerting` (ID: `7`)
- **Delivery Status:** `CONFIGURED_UNVERIFIED`

| Administrator Name | Zabbix Username | Destination Email Address | Media Type | Active Hours | Status |
|---|---|---|---|:---:|---|
| John Gacomo | `john.gacomo` | `John.Gacomo@kenya-airways.com` | Email (ID: 1) | 24x7 | Configured |
| Robinson Wainaina | `robinson.wainaina` | `Robinson.Wainaina@kenya-airways.com` | Email (ID: 1) | 24x7 | Configured |
| Pascal Gathungu | `pascal.gathungu` | `Pascal.Gathungu@kenya-airways.com` | Email (ID: 1) | 24x7 | Configured |
| Mercy Vaati | `mercy.vaati` | `Mercy.Vaati@kenya-airways.com` | Email (ID: 1) | 24x7 | Configured |

> [!IMPORTANT]
> **No Unsolicited Emails:** In accordance with Nawari security governance, no live email test was dispatched to the customer's four administrator inboxes. Live end-to-end notification delivery remains `CONFIGURED_UNVERIFIED` until explicit customer authorization during controlled staging rehearsals.

### Precise Safety Demarcation

- **Staging Zabbix Mutations (`localhost:8088`):**  
  Declarative template imports, user group creation, and host linkage were executed exclusively against the local staging Docker environment.
- **Physical Production Gate (`mon-grafana01`):**  
  `HARD_PRODUCTION_DENY` remains strictly locked. No mutation commands, SNMP sets, or configuration changes were executed on the production host or network switches.

---

## 6. Verification Results

All automated verification gates and test suites pass:

```
============================== test session starts ==============================
tests/unit/test_phase13_5_communication_dashboard_alignment.py ........ [100%]
============================== 8 passed in 0.09s ===============================

tests/unit/test_dashboard_telemetry_integrity.py ......                  [100%]
tests/unit/test_phase13_2_telemetry_evidence_audit.py ......            [100%]
============================== 12 passed in 0.30s ==============================
```

- Total Dashboards: **24** (13 Network, 11 Communication)
- Total Visualization Panels: **200**
- Mandatory Panel Descriptions: **100% Coverage (200/200)**
- Metric Evidence Register Status:
  - `VERIFIED_INTEGRATION`: 159 panels
  - `CONFIGURED_UNVERIFIED`: 20 panels
  - `NOT_COLLECTED`: 3 panels
  - `SIMULATED`: 18 panels
  - `VERIFIED_LIVE`: 0 panels (Strictly preserved until Phase 8.2 physical commissioning)

