# Phase 13.8A Master Specification: Trigger Threshold Rationalisation and Alert Policy Engineering

**Status:** Authoritative Engineering Standard & Audit Baseline  
**Date:** 2026-11-08  
**Target Environment:** Kenya Airways Telephony & Network Observability (Nawari Platform)  
**Host Target:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPU, 7.8 GiB RAM)  
**Upstream Isolation:** `sentra` working tree clean on commit `9970404`  

---

## 1. Executive Summary & Problem Statement

Prior to Phase 13.8A, the Nawari platform successfully established a 6-action tag-based routing architecture and verified basic trigger evaluation in staging. However, an operational observability platform requires more than arbitrary metric comparisons; it requires **technically defensible thresholds, calibrated persistence windows, anti-flapping recovery hysteresis, and explicit decoupling between metric measurements and incident classifications**.

Without formal threshold rationalisation:
1. **Metric Magnitude vs. Operational Impact:** High resource utilization (e.g., 90% CPU during scheduled database backup) can be misinterpreted as a Disaster, triggering Sev 1 pages when no end-user service is impacted.
2. **Transient Spikes vs. Sustained Degradation:** Brief instantaneous spikes trigger alert storms and "flapping" tickets if triggers lack persistence windows (`min()`, `count()`) or recovery hysteresis.
3. **Cumulative Counters vs. Rate Calculations:** Evaluating raw interface byte or packet counters rather than delta rates (`change()` or `rate()`) leads to invalid comparisons against static thresholds.
4. **Conflation of Distinct Telemetry Disciplines:** Synthetic voice probe MOS has historically risked being conflated with live customer-call voice quality, and SIP response latency has risked being confused with end-to-end call setup time.
5. **Fictitious / Ungated Thresholds:** Defining thresholds for metrics where hardware or telemetry collection is physically unverified (e.g., Avaya G450 DSP channel allocation without verified DSP child cards) creates fictitious assurance.

Phase 13.8A resolves these challenges by establishing the **Nawari Trigger and Alert Threshold Standard**, auditing all 72 template triggers and 55 host-level triggers across the 10 monitored templates, and creating the **Authoritative Threshold Register**.

---

## 2. The Five-Question Threshold Standard

Every trigger provisioned in Nawari must be defined, justified, and audited against the following five architectural questions:

```
+-----------------------------------------------------------------------------+
|                     NAWARI 5-QUESTION THRESHOLD FRAMEWORK                   |
+----+------------------------------------+-----------------------------------+
| Q1 | What is being measured?            | Exact OID, item key, and unit     |
+----+------------------------------------+-----------------------------------+
| Q2 | What is the acceptable range?      | Normal operating baseline         |
+----+------------------------------------+-----------------------------------+
| Q3 | How far outside before alert?      | Warning vs High vs Disaster delta |
+----+------------------------------------+-----------------------------------+
| Q4 | How long must condition persist?   | Time window or consecutive checks |
+----+------------------------------------+-----------------------------------+
| Q5 | What evidence declares recovery?   | Recovery expression & hysteresis  |
+----+------------------------------------+-----------------------------------+
```

1. **What is being measured?**  
   The exact item, OID, or calculated formula, with explicit engineering units (e.g., `%`, `ms`, `calls/s`, `packets/s`, `dBm`).
2. **What is the acceptable operating range?**  
   The expected baseline under healthy production load (e.g., CPU 10–65%, SIP OPTIONS latency < 50ms, MOS 4.1–4.4).
3. **How far outside that range must the metric go before an alert is raised?**  
   Tiered thresholds separating initial operational deterioration (Warning), significant service risk (High), and confirmed critical failure (Disaster).
4. **How long must the condition persist before it becomes a problem?**  
   The persistence window or consecutive failure count required to filter out transient micro-bursts (e.g., `min(5m) > 90%` or `count(#3, 0, "eq") = 3`).
5. **What evidence is required before recovery is declared?**  
   The exact recovery condition, including anti-flapping hysteresis margins and minimum healthy duration (e.g., recovery requires `max(5m) < 85%` for a 90% trigger).

---

## 3. Standard Severity Model

Nawari maps Zabbix native trigger severities (`priority: 1` to `priority: 5`) to explicit Kenya Airways operational incident responses:

| Zabbix Severity | Numeric | Operational Meaning | Operational Response | Escalation Target |
|:---|:---:|:---|:---|:---|
| **Information** | `1` | State change or noteworthy event without service impact (e.g. system name change, reboot flag). | Record and log in audit trail. Zero external notification. | System Logs / Audit View |
| **Warning** | `2` | Early indication of performance deterioration or capacity threshold approached. | Investigate during normal operations. Ticket created in backlog. | Technical Team Queue |
| **Average** | `3` | Sustained degradation or non-critical component failure with redundant failover active. | Technical team active investigation. Resolution within 4 hours. | Duty Engineer / Voice Eng |
| **High** | `4` | Significant service impairment or acute risk to critical operations (e.g. primary trunk down). | Urgent technical response. Resolution within 1 hour. | Voice / Network Admins (P1) |
| **Disaster** | `5` | Confirmed critical service outage or complete loss of primary transport. | Immediate Sev 1 incident declaration. Multi-channel paging. | Total Outage Group (P0) |

> [!IMPORTANT]
> **Operational Impact Rule:** Severity must reflect real-world operational service impact, not simply the numerical size of a metric. An idle server running a scheduled cron job at 95% CPU is Warning/Average; a core switch dropping 5% of voice packets under load is Disaster.

---

## 4. Architectural Decoupling: Metrics vs. Outage Classification

A foundational principle of Phase 13.8A is the **complete decoupling of metric thresholds from incident classifications**:

```
+-------------------------------------------------------------------------+
|                         METRIC MEASUREMENT                              |
|   (CPU, Memory, Packet Loss, Rate of Errors, SIP OPTIONS, MOS)          |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                        THRESHOLD EVALUATION                             |
|   (Value, Duration, Consecutive Checks, Recovery Hysteresis)            |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                          TRIGGER SEVERITY                               |
|   (Warning, Average, High, Disaster - reflecting component impact)      |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                     SERVICE-IMPACT CORRELATION                          |
|   (Topology, Redundancy, HA Nodes, Alternate Route Patterns)            |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                     NOTIFICATION CLASSIFICATION                         |
|   (total_outage, service_outage, synthetic_failure, degradation, etc.)  |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                      NOTIFICATION DISPATCH                              |
|   (Action 10 -> 5 Recip | Action 11 -> 4 Voice Admins | Action 13 -> Tech)|
+-------------------------------------------------------------------------+
```

### Operational Examples:
1. **Redundant Component Failure:** An interface link drops on `mock-core-switch-01`. The link is down (`priority: 4`), but redundant LACP trunks carry traffic. Classification: `component_failure` $\to$ routed to technical team (Group 7), **not** Service Desk.
2. **Complete Transport Collapse:** Both core switch power feeds fail or core transport drops. Classification: `total_outage` $\to$ routed to Group 15 (Service Desk + All Admins).
3. **Primary Carrier Down:** Safaricom SIP trunk fails OPTIONS probes. Route pattern automatically diverts calls to Airtel. Severity: `High`, Classification: `service_outage` $\to$ routed to Voice Engineers (Group 14), avoiding Service Desk panic.
4. **Monitoring Poller Stalled:** CM SNMP agent stops responding, but ICMP ping and live call routing continue normally. Classification: `monitoring_failure` $\to$ routed to technical administrators.

---

## 5. Domain-Specific Threshold Standards

### 5.1 Network Infrastructure & Server Standards

| Metric Category | Target Subsystem | Warning Threshold | High Threshold | Disaster / Outage Threshold | Persistence / Measurement Method |
|:---|:---|:---|:---|:---|:---|
| **CPU Utilization** | Core Switch / Gateway / Linux Host | `> 80%` | `> 90%` | `> 95%` (with confirmed service impact) | `min(10m)` for Warning; `min(5m)` for High/Disaster. Anti-flapping recovery: `max(5m) < 75%`. |
| **Memory Utilization**| Appliances & Host VM | `> 85%` | `> 95%` | Critical exhaustion impacting processes | `min(10m)` for Warning; `min(5m)` for High. Anti-flapping recovery: `max(5m) < 80%`. |
| **Disk Space Free** | Root & Recording Volumes | `< 20%` free | `< 10%` free | `< 5%` free or inode exhaustion | `last() < 20%` for Warning; `last() < 10%` for High. |
| **Interface Utilization** | 1G / 10G Trunk Interfaces | `> 80%` | `> 90%` | `> 95%` with packet discards | Must be calculated as 8-bit octet delta rate: `rate(/host/net.if.in[ifHCInOctets]) * 8 / ifSpeed * 100`. Persistence: `min(10m)` for Warning; `min(5m)` for High. |
| **Interface Discards** | Switch Ports & SBC NICs | `> 10 discards/s` | `> 50 discards/s` | `> 200 discards/s` with call loss | Calculated via `rate()`. Counter totals strictly forbidden. |
| **Interface Errors** | Switch Ports & SBC NICs | `> 5 errors/s` | `> 25 errors/s` | `> 100 errors/s` with CRC drops | Calculated via `rate()`. |
| **ICMP Packet Loss** | Core Network Devices | `> 1%` for 5 min | `> 3%` for 3 min | `> 5%` for 2 min (Disaster) | `min(5m) > 1%`. Instantaneous ping drops ignored. |
| **Network RTT (LAN)** | Campus LAN (HQ Core) | `> 15 ms` (base + 50%) | `> 30 ms` | `> 60 ms` sustained | `min(5m) > 15ms`. Baseline is < 5ms. |
| **Network RTT (WAN)** | Dedicated Telco WAN | `> 45 ms` (base + 25%) | `> 70 ms` (base + 50%) | `> 120 ms` sustained | Baseline is 25–35ms. |
| **Network RTT (Outstations)** | Regional Airports (MBA, KIS) | `> 90 ms` | `> 140 ms` | `> 220 ms` sustained | Baseline is 50–70ms. |
| **Device Availability**| Core Switch & Gateways | 1 failed check | 2 consecutive failed checks | 3 consecutive failed checks (`count(#3, 0, "eq") = 3`) | Polling: 30s. Problem after 90s. Recovery: 2 consecutive passes (`count(#2, 1, "eq") = 2`). |

### 5.2 Voice & Communications Standards

| Metric Category | Target Entity | Warning Threshold | High Threshold | Disaster / Outage Threshold | Persistence / Measurement Method |
|:---|:---|:---|:---|:---|:---|
| **SIP OPTIONS Response** | Carrier Trunk / Session Manager | 2 failed probes (60s) | 4 failed probes (120s) | 6 consecutive failed probes (180s) | Polling: 30s. Trigger: `count(#4, 0, "eq") >= 3`. Recovery: 3 consecutive 200 OK. |
| **SIP Registration** | Session Manager $\to$ CM | State: `PARTIALLY_UP` (3) | State: `DENY_NEW_SERVICE` (4) | State: `DOWN` (2) | Evaluated from Avaya SM SIP entity state OID. |
| **SIP Response Latency** | Carrier Trunk / SM Core | `> 500 ms` sustained | `> 1,000 ms` sustained | `> 2,500 ms` or SIP 504 Timeout | Strictly distinct from Call Setup Time. Measures SIP transaction round-trip (INVITE $\to$ 100 Trying / 180 Ringing). |
| **Synthetic Voice MOS**| Synthetic Probe Node | `< 3.8` | `< 3.5` | `< 3.0` sustained across 2 runs | Label: `SYNTHETIC_MOS`. Strictly separated from live customer calls. E-Model ITU-T G.107 calculation. |
| **Call Setup Time** | Synthetic Probe Node | `> 3,000 ms` | `> 5,000 ms` | `> 10,000 ms` or SIP 408 | Strictly distinct from SIP RTT. Measures elapsed time from INVITE dispatch to 200 OK / Answer. |
| **Synthetic Call Success**| Synthetic Probe Node | 1 failed test | 2 consecutive failed tests | 3 consecutive failed tests (`count(#3, 0, "eq") = 3`) | Evaluates end-to-end call lifecycle (AMI dial, RTP media, Q.850 normal clearing). |
| **One-Way Audio** | Synthetic Probe Node | Transient 1s drop | Detected on test call | Confirmed bidirectional media failure | Analyzes RTP stream sequence & packet count in both directions. |
| **Real-Call Packet Loss**| CM Duplex Core (Hourly) | `> 1.0%` in 1h window | `> 2.5%` in 1h window | `> 5.0%` in 1h window | Hourly summary table (`avCmMeasIpVoStatHrData`). Aggregates completed call legs. |
| **Real-Call Peak Jitter**| CM Duplex Core (Hourly) | `> 20 ms` in 1h window | `> 30 ms` in 1h window | `> 50 ms` in 1h window | Maximum jitter recorded across calls in measurement hour. |
| **WFO Compliance Recording** | WFO Recording Spool | `< 15%` free spool disk | `< 5%` free spool disk | Recording pipeline stalled / worker crash | Essential for aviation safety compliance (ICAO / IATA regulations). |

---

## 6. Anti-Flapping Hysteresis & Persistence Formulation

To eliminate alert noise and bouncing tickets, triggers must utilize native Zabbix mathematical persistence functions and recovery expressions:

### 6.1 Utilization Hysteresis (Example: CPU & Memory)
- **Problem Expression:**
  ```
  min(/host/system.cpu.util, 5m) > 90
  ```
- **Recovery Expression (Hysteresis Margin of 10%):**
  ```
  max(/host/system.cpu.util, 5m) < 80
  ```
- *Operational Behavior:* The alert fires only if CPU remains continuously above 90% for 5 minutes. The alert clears only after CPU drops below 80% and stays below 80% for 5 minutes.

### 6.2 Availability Hysteresis (Example: Device Reachability)
- **Polling Interval:** 30 seconds
- **Problem Expression:**
  ```
  count(/host/icmpping, #3, "eq", 0) = 3
  ```
- **Recovery Expression:**
  ```
  count(/host/icmpping, #2, "eq", 1) = 2
  ```
- *Operational Behavior:* Requires 3 consecutive missed pings (90 seconds) to declare down; requires 2 consecutive successful pings (60 seconds) to declare recovered.

---

## 7. Gated & Deferred Telemetry Register (Unsupportable Metrics)

Under Kenya Airways engineering governance, **no threshold may be placed into active production monitoring without verified physical hardware and collection support**. The following metrics are formally identified as **Gated / Deferred**:

| Metric Concept | Reason for Deferral | Gating Requirement | Safe Staging Behavior |
|:---|:---|:---|:---|
| **Avaya G450 DSP Channel Allocation** | DSP resource allocation MIB requires physical MP120 / MP160 child cards installed in chassis slots V2–V4. | Physical inspection of G450 media gateway hardware modules in Phase 8.2. | Zero active triggers. Item marked `GATED_UNVERIFIED`. |
| **Real-Time Per-Call RTCP Jitter** | Communication Manager does not expose live per-second RTCP via SNMP; it only generates hourly historical summaries or RTCP-XR voice packets to dedicated collectors. | Deployment of private RTCP collector or Homer/HEP sniffer in Phase 8.2. | Monitoring restricted to hourly summaries (`avCmMeasIpVoStatHrData`). No fictitious 1-minute real-time triggers. |
| **SBCE EMS Deep License Allocation** | Live EMS active call counts require authenticated REST API or validated SNMPv3 engine ID. | Provisioning of EMS read-only service account credentials. | Maintained in `CONFIGURED_UNVERIFIED` state; triggers tagged `monitoring_failure` upon timeout. |
| **Session Manager SIP Entity Status by SNMP** | Avaya Session Manager restricts SIP entity status tables to internal trace daemons and management web service unless specific sub-agent is active. | Verification of Avaya SM SNMP daemon MIB support during on-site commissioning. | Triggers use synthetic probe cross-check rather than raw unverified SNMP tables. |

---

## 8. Implementation Roadmap Integration

Phase 13.8A establishes the necessary architectural prerequisite for the upcoming milestones:

```
[Phase 13.7 Notification Lifecycle & Tag Routing: ACCEPTED]
                       │
                       ▼
[Phase 13.8A: Trigger Threshold Rationalisation & Alert Policy Engineering]  <-- CURRENT
  ├── Authoritative 16-field Trigger Register
  ├── 5-Question Validation Framework
  ├── Anti-flapping Persistence & Hysteresis Formulas
  └── Gated / Deferred Telemetry Isolation
                       │
                       ▼
[Phase 13.8B: Zabbix Template Threshold & Recovery Expression Implementation]
  ├── Update Zabbix template YAMLs with hysteresis expressions
  ├── Reconcile trigger priorities to 5-tier severity model
  └── Deploy rate-based interface counters
                       │
                       ▼
[Phase 13.8C: Alert Behavior, Event Classification & Runtime Verification]
  ├── Live ZabbixSender failure & recovery test batteries
  ├── Macro expansion & 0-branding verification
  └── Complete staging acceptance gate
                       │
                       ▼
[Phase 13.9: Controlled Read-Only Production Telemetry Commissioning]
```

