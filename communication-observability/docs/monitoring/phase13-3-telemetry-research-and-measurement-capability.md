# Nawari Phase 13.3 — Telemetry Research, Measurement Capabilities and System Demarcations

**Document Standard:** Nawari Enterprise Observability & Service Assurance  
**Target Environment:** Kenya Airways Telephony Estate & Ground Operations  
**Architecture Boundary:** Zabbix (Collector) · Grafana (Visualizer) · Nawari (Correlator & Assurer)  
**Execution Standard:** Evidence-Backed Operational Truth & Traceable Telemetry Provenance  
**Production Mutation Status:** `HARD_PRODUCTION_DENY` Strictly Enforced  

---

## 1. Executive Research Summary

Phase 13.3 establishes an authoritative, vendor-verified telemetry capability framework for the entire Kenya Airways unified communications infrastructure. 

A critical finding in telecommunications observability is that modern enterprise telephony estates (particularly Avaya Aura) comprise disparate physical appliances, virtual machines, proprietary Linux platforms, and legacy DSP gateways. These components do **not** share a uniform telemetry interface. Monitoring them requires strict adherence to vendor architectural boundaries, authentic protocol capabilities, and rigorous polling safety limits.

### Primary Architectural Principles
1. **No Invented Telemetry:** If an appliance does not natively expose a metric via an authoritative interface (SNMP, API, CLI trapper, or database export), Nawari explicitly reports it as `NOT_COLLECTED`, `CONFIGURED_UNVERIFIED`, or `UNSUPPORTED`. Fabricated zeroes, simulated placeholders, and decorative gauges are strictly prohibited.
2. **Signaling vs. Media Audio Separation:** A successful SIP OPTIONS exchange or registered SIP trunk validates Layer-5 signaling path reachability only. It does **not** prove RTP/SRTP media traversal, packet integrity, or acceptable conversational audio quality.
3. **Collector CPU Safety:** Avaya call processors (e.g., Communication Manager and G450 Media Gateway Processors) execute mission-critical real-time call switching. Aggressive SNMP polling can degrade call processing or cause gateway link drops. Polling ceilings must strictly respect vendor architectural limits.

---

## 2. Subsystem Telemetry Capabilities & Demarcation Matrix

```
+----------------------------------------------------------------------------------------------------+
|                               NAWARI TELEMETRY CAPABILITY MATRIX                                   |
+----------------------------------------------------------------------------------------------------+
| Subsystem              | Supported Protocols     | Measurable Telemetry       | Non-Exposed / Uninstrumented|
+------------------------+-------------------------+----------------------------+--------------------+
| Avaya SBCE             | SNMPv3, IF-MIB HC,      | Hardware CPU, RAM, Disk,   | Per-call audio MOS |
|                        | Host Resources, EMS API | Interfaces, Bandwidth,     | without external   |
|                        |                         | Active Calls, Registrations| RTCP-XR collector  |
+------------------------+-------------------------+----------------------------+--------------------+
| Avaya Session Manager  | SNMPv3 (MIB-II, Host Res)| OS health, sockets, memory | SIP Entity states  |
|                        | CLI Trapper / REST API, | Active SIP OPTIONS RTT,    | are NOT exposed in |
|                        | Active Nawari Probe     | Failure rates, traps       | standard SNMP GET  |
+------------------------+-------------------------+----------------------------+--------------------+
| Avaya Communication    | SNMPv3 (Enterprise MIB  | Active alarms (.5),        | Real-time 5-sec    |
| Manager (CM)           | 1.3.6.1.4.1.6889.2.73)  | Hourly voice stats (.67),  | call rate counters |
|                        |                         | Hourly call rates (.145)   | or live call MOS   |
+------------------------+-------------------------+----------------------------+--------------------+
| Avaya G450 Gateway     | SNMPv2c/v3 Chassis MIB, | Uptime, PSU, Fan status,   | DSP channel stats  |
|                        | Discrete Event Traps    | E1/ISDN trunk oper status, | without module     |
|                        |                         | Discrete thermal states    | physical audit     |
+------------------------+-------------------------+----------------------------+--------------------+
| SIP Trunks             | SNMP (SBCE/SM),         | Signalling reachability,   | Conversational     |
|                        | Active SIP OPTIONS      | RTT latency, Error codes,  | audio quality /    |
|                        |                         | Registration status        | in-flight jitter   |
+------------------------+-------------------------+----------------------------+--------------------+
| Real-Call Audio        | Uninstrumented          | None (Carrier RTCP-XR /    | Real-call MOS      |
| Quality                |                         | PESQ probes missing)       | marked UNCOLLECTED |
+------------------------+-------------------------+----------------------------+--------------------+
| Synthetic Voice Probes | Asterisk AMI Probes     | Synthetic PDD, Synthetic   | Non-synthetic      |
|                        |                         | Packet Loss, Synthetic MOS | customer audio     |
+------------------------+-------------------------+----------------------------+--------------------+
| Avaya CMS              | Informix ODBC (Read-only)| Calls offered, answered,   | Real-time second-by|
|                        |                         | abandoned, ASA, AHT, SL %  | second agent state |
+------------------------+-------------------------+----------------------------+--------------------+
| Recording / WFO        | Host SNMP, Service API  | Ingestion queue, storage   | Customer voice     |
|                        |                         | capacity, process state    | audio payload      |
+------------------------+-------------------------+----------------------------+--------------------+
```

---

## 3. Deep-Dive Subsystem Telemetry Research

### 3.1 Avaya Session Border Controller for Enterprise (SBCE)
- **Role:** Perimeter SIP security, topology hiding, carrier trunk demarcation, media relay.
- **Physical Reference Appliance:** `10.2.156.131` (Pride DC1 SBC).
- **Supported Collection Paths:**
  1. *SNMPv3 (USM SHA/AES-128):* Standard IF-MIB (`1.3.6.1.2.1.2.2` / `1.3.6.1.2.1.31.1.1`) providing 64-bit high-capacity interface counters (`ifHCInOctets`, `ifHCOutOctets`, `ifInErrors`, `ifOutDiscards`) across M1, M2, A1, B1 physical interfaces. Host Resources MIB (`1.3.6.1.2.1.25`) for CPU cores, physical memory, and `/` disk partition.
  2. *EMS (Element Management System) Statistics API:* Provides active TLS/TCP/UDP registration counts, active concurrent calls, direct-media vs. transrated sessions, and allocated SBC session licenses.
  3. *SNMP Traps / Syslog:* Hardware alarms, peer heartbeat failures, and licensing exhaustion traps.
- **Measurement Boundary:** SBCE does not execute per-call audio psychoacoustic analysis (PESQ/POLQA) without external RTP collectors.

### 3.2 Avaya Aura Session Manager (ASM)
- **Role:** Core SIP routing engine, registrar, and dial plan orchestrator.
- **Investigation Finding — The SNMP Demarcation:**
  Standard Avaya Aura Session Manager 8.x appliances run an SNMP daemon restricted to:
  - MIB-II (`1.3.6.1.2.1`): `system`, `interfaces`, `tcp`, `udp` socket counters.
  - Host Resources MIB (`1.3.6.1.2.1.25`): CPU core utilization, memory buffers, filesystem capacity.
  - Avaya Trap MIB: Asynchronous notification traps.
  **Critical Architectural Demarcation:** SIP Entity Link states (`UP`, `PARTIALLY UP`, `DOWN`, `DENY NEW SERVICE`) are **not** exposed via SNMP GET OIDs. They are managed internally by the Session Manager Management Console and System Manager (SMGR).
- **Nawari Implementation:**
  1. *Host Telemetry:* Monitored via SNMPv3 for appliance infrastructure health.
  2. *SIP Entity Operational States:* Collected via Session Manager CLI / REST Trapper (`statapp`, `smgrep`, SMGR REST integration) pushing discrete health states into Nawari.
  3. *Signaling Reachability & Latency:* Nawari deploys an active SIP probe executing periodic `SIP OPTIONS` transactions against SM listening ports, recording round-trip time (RTT in ms) and SIP response codes.

### 3.3 Avaya Aura Communication Manager (CM)
- **Role:** Enterprise PBX, ACD feature engine, call routing, and vectoring.
- **Official Enterprise MIB:** `1.3.6.1.4.1.6889.2.73` (`avaya.mibs.cm`).
- **Telemetry Capabilities & Polling Boundaries:**
  1. *Active Alarms (`avCmAlarmsTable` - `.8.1.5`):* Exposes active CM hardware and software alarms. Polling ceiling: strictly $\ge 1\text{ hour}$ (`delay: 1h`) to avoid processor locking during table scans.
  2. *Hourly IP Voice Quality (`avCmMeasIpVoStatHrData` - `.8.1.67`):* Maps to SAT command `list measurements ip voice-stats hourly data`. Compiles packet loss %, peak jitter (ms), peak delay (ms), codec, echo cancellation, and network region across completed 1-hour intervals. Cache duration: 600s; Polling interval: strictly $\ge 1\text{ hour}$ (`delay: 1h`).
  3. *Call Processing Rates (`avCmListMeasCallRateTotalTable` - `.145`):* Maps to SAT `list measurements call-rate total`. Telemetry represents hourly measurement blocks. Polling ceiling: $\ge 5\text{ minutes}$ (`delay: 5m`) as an enforced query rate ceiling to protect CM call switching. Attempts is not exposed as a rolling 5-minute counter in this table.
- **Demarcation:** Real-time per-call MOS is unavailable via CM SNMP.

### 3.4 Avaya G450 Media Gateway
- **Role:** Branch gateway, TDM/ISDN PRI trunk termination, DSP transcoding, analog emergency lines.
- **Supported Telemetry:**
  1. *Chassis & Interface SNMP:* Uptime, power supply modules (PSU 1 & PSU 2 redundancy), fan tray assembly, E1/ISDN PRI trunk operational status (`ifOperStatus.e1.1`).
  2. *Chassis Thermal Model:* Discrete event-derived states (`0: UNKNOWN`, `1: CLEARED`, `2: WARNING`) populated via trap events (`temperatureWarning` / `temperatureClear`). G450 firmware does not provide an analog thermistor gauge or a separate "Critical" trap.
  3. *Hardware Module Architecture:* Differentiates legacy/branch gateways (MP20 / MP80) from high-capacity G450 appliances (MP120 / MP160).
  4. *DSP Channel Utilization:* Gated strictly as `NOT_COLLECTED (Hardware Audit Required)` until physical module serial numbers and VoIP engine licenses are verified.

### 3.5 Avaya Call Management System (CMS)
- **Role:** Contact centre historical and interval reporting, queue performance, agent split analytics.
- **Supported Interface:** Read-only Informix ODBC connection (`dagent`, `hsplit`, `hvdn` tables).
- **Measurable Metrics:** Calls offered, calls answered, abandoned calls, abandon rate %, Average Speed of Answer (ASA), Average Handle Time (AHT), and Service Level Attainment (% answered within threshold).
- **Demarcation:** Polling queries must align with CMS archiving intervals (15m, 30m, 60m). Direct database writes and sub-minute polling are strictly prohibited. Status: `CONFIGURED_UNVERIFIED`.

### 3.6 Workforce Optimization (WFO) & Call Recording
- **Role:** Compliance voice recording, screen capture, quality evaluation.
- **Supported Interface:** Host SNMPv3 + Recording Service Management API.
- **Measurable Telemetry:** Operating system capacity, recording ingestion rate, queue buffer depth, storage partition capacity and retention horizon, and CTI link state.
- **Data Boundary:** Customer audio payload and media streams are strictly excluded from Nawari. Only operational metadata and infrastructure capacity are collected. Status: `CONFIGURED_UNVERIFIED`.

---

## 4. Voice Quality Observability: The Hard Reality

In enterprise VoIP environments, voice quality claims are often subject to operational deception. Nawari enforces total transparency:

1. **Real-Call Telemetry Absence:**
   Without dedicated carrier-grade RTCP-XR aggregators (e.g. Oracle Acme Packet, Ribbon, or endpoint IP phone firmware RTCP-XR streaming), live conversational MOS cannot be measured across customer calls. Nawari honestly marks real-call MOS as `NOT_COLLECTED (Carrier RTCP-XR required)`.
2. **Synthetic Probing Capability:**
   Nawari utilizes Asterisk AMI probe calls traversing the telephony core between test extensions. These probes measure synthetic Post-Dial Delay (PDD), synthetic jitter, synthetic packet loss, and compute an estimated R-factor/MOS using ITU-T G.107 E-model calculations.
3. **Explicit Labeling:**
   All synthetic telemetry is explicitly labeled `[SYNTHETIC — ASTERISK]` across all panels, alert instances, and service degradation reports to guarantee that operators never confuse test calls with genuine customer passenger experience.

