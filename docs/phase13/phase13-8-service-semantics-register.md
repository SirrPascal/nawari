# Phase 13.8 Service Semantics & Trigger Classification Register

**Status:** Authoritative Operational Classification Matrix  
**Date:** 2026-11-08  
**Total Reconciled Triggers:** 59 triggers across 7 templates  
**Governance Standard:** Kenya Airways Incident Management & Alert Fatigue Prevention  

---

## 1. Classification Philosophy

Triggers are assigned a `notification_class` tag that deterministically dictates the alerting action, the notified personnel, and the escalation profile:

1. `total_outage` $\to$ **Action 10**: Paged to all 5 recipients (Voice Admins + Central IT Service Desk). Reserved strictly for network core switch / gateway transport collapse or complete site blackouts.
2. `service_outage` $\to$ **Action 11**: Paged to the 4 Voice Administrators (Group 14). Single appliance / host unreachability, primary SIP trunk failure, or registration drops where telephony continues on backup routes.
3. `synthetic_failure` $\to$ **Action 12**: Paged to the 4 Voice Administrators (Group 14). Synthetic MOS score collapse, one-way audio, or end-to-end call failure.
4. `degradation` $\to$ **Action 13**: Routed to Technical Administrators (Group 7). Latency, jitter, packet loss, high memory/CPU, or trunk utilization thresholds.
5. `component_failure` $\to$ **Action 14**: Routed to Technical Administrators (Group 7). Redundant power supplies, fan trays, ambient temperatures, DSP card hardware alarms.
6. `monitoring_failure` $\to$ **Action 15**: Routed to Technical Administrators (Group 7). SNMP agent timeout, stale trapper feeds (>15m).
7. `informational` $\to$ Logged in Zabbix; zero external notifications dispatched.

---

## 2. Trigger Classification Register (Sample Breakdown by Subsystem)

### 2.1 Network Infrastructure Core (Total Outage Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Template Network Core Switch` / `mock-core-switch-01` | `Core Switch: Total Network Core Transport Failure` | Disaster | `total_outage` | 10 | Group 15 (5 Recip) | Core switch down. Entire site voice & data offline. |
| `Template Network Generic` / `core-gw-01` | `Network Generic Device: Unavailable by ICMP ping` | Disaster | `total_outage` | 10 | Group 15 (5 Recip) | WAN default gateway down. Site isolated. |

### 2.2 Avaya Infrastructure Appliances (Service Outage Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Avaya SBCE by SNMP` / `avaya-sbce-01` | `Avaya SBCE: Appliance Unreachable` | Disaster | `service_outage` | 11 | Group 14 (4 Admins) | Single SBCE down. Backup SBCE / HA active. Voice engineers page; Service Desk excluded. |
| `Avaya SM by SNMP` / `avaya-sm-01` | `Avaya SM: Session Manager Host Unavailable` | Disaster | `service_outage` | 11 | Group 14 (4 Admins) | Single SM down. Secondary SM node active in cluster. Telephony unaffected for users. |
| `Avaya G450 by SNMP` / `avaya-g450-01` | `Avaya G450: Media Gateway Chassis Unreachable` | Disaster | `service_outage` | 11 | Group 14 (4 Admins) | Media gateway down. Local TDM trunks affected; core CM duplex remains functional. |
| `Avaya CM by SNMP` / `avaya-cm-01` | `Avaya CM: Communication Manager Processor Unreachable` | Disaster | `service_outage` | 11 | Group 14 (4 Admins) | Active server switchover to standby duplex core occurs. |
| `Avaya SIP Trunk` / `sip-trunk-carrier-01` | `SIP Trunk: Endpoint Unreachable` | Disaster | `service_outage` | 11 | Group 14 (4 Admins) | Primary carrier trunk endpoint unreachable. Outbound calls route to secondary carrier. |
| `Avaya SIP Trunk` / `sip-trunk-carrier-01` | `SIP Trunk: Consecutive OPTIONS Probe Failures` | High | `service_outage` | 11 | Group 14 (4 Admins) | OPTIONS keepalive failed. Route pattern marks trunk busy; backup route engaged. |

### 2.3 Synthetic Probes (Synthetic Failure Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Voice Synthetic Probe` / `voice-synthetic-probe-01` | `Degraded voice quality on synthetic probe (MOS < 3.8)` | Average | `synthetic_failure` | 12 | Group 14 (4 Admins) | Simulated call probe detected voice degradation. |
| `Voice Synthetic Probe` / `voice-synthetic-probe-01` | `Unacceptable voice quality on synthetic probe (MOS < 3.5)` | High | `synthetic_failure` | 12 | Group 14 (4 Admins) | Voice quality unacceptable on synthetic test. |
| `Voice Synthetic Probe` / `voice-synthetic-probe-01` | `One-way audio detected on synthetic probe` | High | `synthetic_failure` | 12 | Group 14 (4 Admins) | RTP stream missing in one direction during test call. |

### 2.4 Performance & Network Degradation (Degradation Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Avaya SBCE by SNMP` | `Avaya SBCE: High memory utilization (> 90%)` | Warning | `degradation` | 13 | Group 7 (Tech) | Memory leak or call load high on SBC. |
| `Avaya SM by SNMP` | `Avaya SM: High SIP call rate abnormal spike` | Warning | `degradation` | 13 | Group 7 (Tech) | Potential call storm or DDoS on Session Manager. |
| `Avaya G450 by SNMP` | `Avaya G450: DSP resource pool utilization > 85%` | Warning | `degradation` | 13 | Group 7 (Tech) | Transcoding channels nearing exhaustion. |
| `Avaya SIP Trunk` | `SIP Trunk: High Round-Trip Delay (> 150ms)` | Warning | `degradation` | 13 | Group 7 (Tech) | Carrier latency elevated. |

### 2.5 Hardware & Component Alarms (Component Failure Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Avaya G450 by SNMP` | `Avaya G450: Power supply unit 2 fault` | High | `component_failure` | 14 | Group 7 (Tech) | Secondary PSU failed. Redundancy lost, chassis remains on PSU 1. |
| `Avaya G450 by SNMP` | `Avaya G450: Fan tray tachometer abnormal` | Warning | `component_failure` | 14 | Group 7 (Tech) | Cooling fan degraded. |
| `Avaya G450 by SNMP` | `Avaya G450: E1/ISDN Primary link down` | Average | `component_failure` | 14 | Group 7 (Tech) | Physical link down on E1 port. |

### 2.6 Monitoring Telemetry Health (Monitoring Failure Triggers)

| Template / Host | Trigger Description | Severity | Classification Tag | Action | Alerted Group | Operational Rationale |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| `Avaya CM by SNMP` | `Avaya CM: Performance Telemetry Stale (> 2h)` | Warning | `monitoring_failure` | 15 | Group 7 (Tech) | CM SNMP agent or poller paused. Telemetry collection stalled. |
| `Endpoint Probe` | `Endpoint probe telemetry is stale (>15m)` | Warning | `monitoring_failure` | 15 | Group 7 (Tech) | Probe agent has stopped sending heartbeats. |

---

## 3. Audit Verification

The complete 59-trigger matrix has been verified in `tests/unit/test_phase13_8_runtime_verification_and_service_semantics.py` and `tests/unit/test_phase13_5_communication_dashboard_alignment.py`. Every trigger deterministically evaluates to its designated operational action with zero collisions.
