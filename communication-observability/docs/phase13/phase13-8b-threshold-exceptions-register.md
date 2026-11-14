# Phase 13.8B Threshold Exceptions and Gated Telemetry Register

**Author:** Antigravity Engineering (pair programming with User)  
**Date:** 2026-11-08  
**Status:** Approved & Enforced in Staging  
**Platform:** Zabbix 7.4.4 / PostgreSQL Engine on `mon-grafana01`  
**Related Milestones:** Phase 13.8A (Rationalisation), Phase 13.8B (Implementation), Phase 13.8C (Verification)

---

## 1. Executive Summary

This document establishes the authoritative **Threshold Exceptions Register** and **Gated Telemetry Register** under Phase 13.8B. Under the Nawari Trigger and Alert Threshold Standard, all monitored metrics must adhere to strict dual-expression recovery hysteresis (`recovery_mode: 1`), minimum persistence windows, and anti-flapping deadbands.

Any deviation from this operational policy requires formal documentation, architectural rationale, and automated verification guards.

### Summary Metrics
- **Total Template Triggers Audited:** 68 non-inherited triggers across 11 templates
- **Dual-Expression Hysteresis Triggers (`recovery_mode: 1`):** 67 triggers (98.53%)
- **Approved Single-Expression Exception Triggers (`recovery_mode: 0`):** 1 trigger (1.47%)
- **Gated Hardware Telemetry Metrics Isolated:** 5 metric classes (0 active fictitious triggers)

---

## 2. Approved Trigger Exceptions Register

### Exception EX-13.8B-01: System Name Change Event

| Field | Configuration Value |
| :--- | :--- |
| **Trigger ID** | `21712` |
| **Trigger Name** | `Network Generic Device: System name has changed` |
| **Parent Template** | `Network Generic Device by SNMP` (Template ID: `10226`) |
| **Metric Key** | `system.name` (OID: `1.3.6.1.2.1.1.5.0`) |
| **Severity** | `Information` (Priority 1) |
| **Notification Class** | `informational` |
| **Configured Mode** | `recovery_mode: 0` (Single-Expression Recovery) |
| **Problem Expression** | `last(/Network Generic Device by SNMP/system.name,#1)<>last(/Network Generic Device by SNMP/system.name,#2) and length(last(/Network Generic Device by SNMP/system.name))>0` |
| **Recovery Expression** | *None (Automatically closes or remains as point-in-time informational event)* |

#### Architectural & Technical Justification:
1. **Event Semantics vs. State Measurement:** A change in the SNMP `sysName.0` scalar is a discrete configuration change event, not a persistent metric excursion. There is no numeric "operating range" or physical deadband to recover from.
2. **Evaluation Dynamics:** When a device is renamed (e.g. during outstation maintenance or hostname standardisation), the condition `last(#1) <> last(#2)` evaluates to `TRUE` for exactly one polling interval. Upon the subsequent polling cycle, `last(#1) == last(#2)`, naturally resolving the comparison.
3. **Dual-Expression Inapplicability:** Forcing `recovery_mode: 1` on this trigger would require defining a synthetic recovery expression that could never cleanly capture the restored state, as the "new" name is now the desired baseline name.
4. **Automated Verification:** Verified by test assertion `test_01_template_triggers_dual_expression_recovery_mode` in `tests/unit/test_phase13_8b_threshold_implementation.py`, which explicitly identifies ID `21712` as the sole approved single-expression event.

---

## 3. Gated Telemetry Register

To prevent alert fatigue, phantom incidents, and synthetic metric fabrication, Nawari strictly isolates unverified physical metrics. No active Zabbix triggers may be instantiated for metrics that lack verified staging telemetry or official vendor MIB support.

The five gated telemetry classes are detailed below:

```
+-----------------------------------------------------------------------------------+
|                           NAWARI GATED TELEMETRY REGISTER                         |
+----------------------+------------------------------------+-----------------------+
| Metric Token         | Telemetry Identifier               | Isolation Rationale   |
+----------------------+------------------------------------+-----------------------+
| G450_DSP_UTIL        | avaya.g450.dsp_utilization_pct     | Proprietary Avaya MIB |
| CM_CALL_RTCP_JITTER  | avaya.cm.live_call.rtcp_jitter     | RTCP-XR Uncollected   |
| EMS_SIP_SERVER_ERRORS| ems.sip.server_errors              | SBCE EMS Polling Gate |
| WFO_VERINT_PIPELINE  | wfo.verint.pipeline_status         | External Spool Agent  |
| CARRIER_DEEP_SLA     | carrier.deep.sla_pct               | Carrier B2B Telemetry |
+----------------------+------------------------------------+-----------------------+
```

### 3.1 Gate GT-01: Avaya G450 Media Gateway DSP Utilization
- **Metric Key:** `avaya.g450.dsp_utilization_pct`
- **Target Component:** Avaya G450 Media Gateway VoIP DSP Resources (MP120/MP160)
- **Current Collection Status:** `GATED_UNSUPPORTED`
- **Root Cause & Technical Limitation:** Standard RFC 1213 / HOST-RESOURCES MIB does not expose DSP channel occupancy. Avaya proprietary `AVAYA-AURA-CM-MEDIA-GATEWAY-MIB` requires authenticated SNMPv3 context engine mapping (`-E <engineID> -n <context>`) which is unavailable in the mock lab environment.
- **Commissioning Prerequisite:** Physical G450 chassis access with verified SNMPv3 context mapping during Phase 13.9/13.10.

### 3.2 Gate GT-02: Avaya CM Live Customer Call RTCP Jitter
- **Metric Key:** `avaya.cm.live_call.rtcp_jitter`
- **Target Component:** Avaya Aura Communication Manager Real-Time Media Streams
- **Current Collection Status:** `GATED_UNCOLLECTED`
- **Root Cause & Technical Limitation:** Customer voice streams traverse the media plane between IP deskphones and G450 DSPs. CM does not expose per-call RTCP jitter via scalar SNMP polling. RTCP extended reports (RTCP-XR) must be collected via external NetFlow/IPFIX or SIP CDR/QoS records.
- **Commissioning Prerequisite:** Deployment of the Nawari RTCP-XR collector agent or Avaya Session Border Controller media analytics feed in Phase 13.10.

### 3.3 Gate GT-03: Avaya SBCE EMS SIP Server Errors
- **Metric Key:** `ems.sip.server_errors`
- **Target Component:** Avaya Session Border Controller Element Management System (EMS)
- **Current Collection Status:** `GATED_UNSUPPORTED`
- **Root Cause & Technical Limitation:** SBCE EMS does not publish granular 5xx SIP server response breakdowns over SNMP. Current SNMP templates monitor aggregate session load and network interface statistics.
- **Commissioning Prerequisite:** Integration with SBCE REST API or syslog audit receiver in Phase 13.11.

### 3.4 Gate GT-04: Verint WFO Compliance Recording Deep Pipeline Health
- **Metric Key:** `wfo.verint.pipeline_status`
- **Target Component:** Verint Workforce Optimization / Call Recording Ingestion Cluster
- **Current Collection Status:** `GATED_SIMULATION_ONLY`
- **Root Cause & Technical Limitation:** Physical Verint API integration requires Microsoft SQL Server database agent hooks or proprietary Verint health APIs. In staging, basic spool disk utilization (`wfo.recording.disk_free_pct`) is monitored, while deep pipeline health remains gated.
- **Commissioning Prerequisite:** Production Verint cluster agent installation and API credentials validation in Phase 13.12.

### 3.5 Gate GT-05: Carrier Deep SLA Telemetry
- **Metric Key:** `carrier.deep.sla_pct`
- **Target Component:** External Telco / Safaricom MPLS Core Interconnect
- **Current Collection Status:** `GATED_EXTERNAL`
- **Root Cause & Technical Limitation:** External telecommunications carriers do not provide real-time private MIB telemetry. Nawari measures carrier health through edge probes (SIP OPTIONS round-trip, ICMP loss/rtt, DNS resolution).
- **Commissioning Prerequisite:** Integration with Carrier B2B SLA reporting portals or edge TWAMP probes in Phase 13.11.

---

## 4. Policy Compliance and Audit Verification

1. **Automated Gating Enforcement:** The automated test `test_06_gated_telemetry_isolation` in `tests/unit/test_phase13_8b_threshold_implementation.py` systematically verifies that no active trigger exists across any template for these 5 gated keys.
2. **Zero Fictitious Alerts:** No mock alerts or fake triggers may be activated to simulate support for these metrics.
3. **Roadmap Alignment:** Gated items remain locked behind the **Phase 8.2 Production Telemetry Commissioning Gate** (Phase 13.9).

