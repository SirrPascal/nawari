# Phase 13.9 — Avaya Aura & G450 MIB Conformance & Metric Validation

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Vendor Conformance Audited  
**Target Firmware:** Avaya Aura Communication Manager 8.1.x, Session Manager 8.1.x, SBCE 8.1.x, G450 Gateway (MGP 41.x)  
**Enterprise OID Subtree:** `1.3.6.1.4.1.6889` (Avaya Inc.)

---

## 1. Executive Summary

This report delivers the authoritative **vendor MIB conformance analysis** for Kenya Airways' Avaya telephony estate.

Historic implementations and preliminary monitoring templates frequently made two dangerous assumptions:
1. They assumed enterprise switches and PBXs expose high-frequency continuous analog metrics (e.g. per-second call rates, continuous degrees Celsius sensors, rolling per-call RTCP streams) over standard SNMP.
2. They polled internal measurement buffers at frequencies exceeding vendor specifications, threatening call processor performance.

Phase 13.9 strictly aligns Nawari's Zabbix templates with official Avaya Aura 8.1 MIB definitions and hardware event models.

---

## 2. Avaya Aura Communication Manager (CM) MIB Architecture

Avaya CM metrics reside in the enterprise subtree `1.3.6.1.4.1.6889.2.73` (`avaya.mibs.cm`).

### 2.1 Table `.67`: IP Voice Statistics (`avCmMeasIpVoStatHrData`)
- **Root OID:** `1.3.6.1.4.1.6889.2.73.8.1.67`
- **Corresponding SAT Command:** `list measurements ip voice-stats hourly data`
- **Internal Mechanism:** CM aggregates RTP quality metrics into completed 1-hour measurement buckets grouped by network region.
- **Cache Duration:** CM caches this data internally for 600 seconds (10 minutes).
- **Mandatory Polling Limit:** Must be polled at $\ge 1\text{ hour}$ intervals (`delay: 1h`). Querying faster returns identical cached data while consuming switch CPU cycles.
- **Validated Leaf Objects:**
  - `...67.1.1` (`avCmMeasIpVoStatHrNetReg`): Network region ID (e.g. Region 1 = Pride DC, Region 2 = JKIA).
  - `...67.1.8` (`avCmMeasIpVoStatHrCodec`): Negotiated audio compression codec (e.g. G.711A, G.729).
  - `...67.1.10` (`avCmMeasIpVoStatHrLossPct`): Packet loss percentage over completed hour (0–100%).
  - `...67.1.11` (`avCmMeasIpVoStatHrPeakJitter`): Peak packet delay variation (ms).
  - `...67.1.12` (`avCmMeasIpVoStatHrPeakDelay`): Peak round-trip network transit delay (ms).
  - `...67.1.13` (`avCmMeasIpVoStatHrEchoCancel`): Echo canceller operational status.

### 2.2 Table `.145`: Call Processing Rate (`avCmListMeasCallRateTotalTable`)
- **Root OID:** `1.3.6.1.4.1.6889.2.73.8.1.145`
- **Corresponding SAT Command:** `list measurements call-rate total`
- **Internal Mechanism:** Compiles total completed calls and attempts across the system.
- **The "5-Minute" Rule:** In vendor documentation, 5 minutes is defined as the **strict maximum polling frequency ceiling** (`delay: 5m`). Querying the SAT buffer faster risks call processor resource contention.
- **Counter Behavior:** Exposes **hourly cumulative blocks** (total attempts and completed calls), **not** rolling 5-minute instantaneous rates. Nawari documents this semantic clearly in Grafana panels.

### 2.3 Table `.5`: Active Alarms (`avCmAlarmsTable`)
- **Root OID:** `1.3.6.1.4.1.6889.2.73.8.1.5`
- **Corresponding SAT Command:** `display alarms`
- **Severity Mapping:** `1: WARNING`, `2: MINOR`, `3: MAJOR`.
- **Polling Limit:** $\ge 1\text{ hour}$ (`delay: 1h`) to avoid tree walking overhead.

---

## 3. Avaya G450 Media Gateway Discrete Event Architecture

### 3.1 Chassis Thermal Model: Discrete Trap Notifications
The G450 Media Gateway Processor (MGP) firmware does not expose an analog thermistor gauge over standard SNMP. Instead, thermal health is governed by discrete trap notifications:
- `temperatureWarning` (OID `1.3.6.1.4.1.6889.2.6.2.1.0.3`): Dispatched when chassis internal sensors exceed safe operating limits.
- `temperatureClear` (OID `1.3.6.1.4.1.6889.2.6.2.1.0.4`): Dispatched when fans return temperatures to nominal thresholds.

#### Event-Derived State Model in Nawari:
- State `0`: `UNKNOWN` (Initial state or telemetry stale > 15m)
- State `1`: `CLEARED` (Nominal operation)
- State `2`: `WARNING` (Chassis thermal warning active; fan inspection required)

### 3.2 H.248 Media Gateway Controller Registration
- **OID:** `1.3.6.1.4.1.6889.2.69.2.1.4.1` (`avG450RegistrationState`)
- **Operational States:**
  - `1`: `registered` (Active communication with primary CM)
  - `2`: `unregistered` (Lost signaling; survivable remote engine active)
  - `3`: `registering` (In-flight registration handshake)

---

## 4. Avaya SBCE 8.1 MIB & API Separation

Avaya Session Border Controller Enterprise (SBCE) requires distinct handling for basic appliance health versus deep SIP analytics:

```
+-----------------------------------+-----------------------------------+-----------------------------------+
| Telemetry Domain                  | Supported Protocol                | Provenance / Status               |
+-----------------------------------+-----------------------------------+-----------------------------------+
| Host CPU, Memory, Disk, Uptime    | SNMPv3 (HOST-RESOURCES-MIB / UCD) | VERIFIED_LIVE (Net-SNMP engine)   |
| Interface Bitrates & Errors       | SNMPv3 (IF-MIB 64-bit HC)         | VERIFIED_LIVE (M1, A1, B1 ifaces) |
| Basic SIP Trunk Registration      | SIP OPTIONS ping via Asterisk     | VERIFIED_LIVE (Probe engine)      |
| Granular SIP 4xx/5xx Error Rates  | REST API via SBCE EMS             | NOT_COLLECTED (Token Auth needed) |
| Active Call Concurrent Sessions   | SNMP enterprise gauge             | CONFIGURED_UNVERIFIED             |
+-----------------------------------+-----------------------------------+-----------------------------------+
```

---

## 5. Summary of Compliance Adjustments

1. **Purged Illegal Analog Sensors:** Removed non-existent `temperature.celsius` continuous analog sensors from G450 templates; replaced with discrete trap-derived states.
2. **Corrected Polling Intervals:** Set CM Table `.67` to `1h` (3600s) and Table `.145` to `5m` (300s), fully respecting SAT cache boundaries.
3. **Explicit Gating of Unverified Metrics:** Kept DSP utilization, live per-call RTCP jitter, and deep EMS errors strictly gated as `NOT_COLLECTED`.

