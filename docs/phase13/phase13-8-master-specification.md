# Phase 13.8 Master Specification: Zabbix Runtime Notification Verification, Service-Outage Semantics, and Controlled Production Transition

**Status:** Accepted Specification & Runtime Staging Implementation  
**Date:** 2026-11-08  
**Target Environment:** Kenya Airways Telephony Observability (Nawari Platform)  
**Host Target:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPU, 7.8 GiB RAM)  
**Upstream Isolation:** `sentra` working tree clean on commit `9970404`  

---

## 1. Executive Summary & Problem Statement

Phase 13.7 successfully established a deterministic notification architecture, retired the broad legacy Action 7, and demonstrated lifecycle notification routing using simulated event captures. However, operational readiness required moving beyond mock and simulated captures to **authoritative runtime verification** inside the active Zabbix 7.4 event engine, while formalizing critical distinction between single component failures and genuine total service outages.

Phase 13.8 resolves these challenges through four foundational advancements:
1. **Live Zabbix 7.4 Event & Alert Engine Verification:** Demonstrating live execution of structured Actions 10–15 within Zabbix server, querying the `alert.get` API for actual dispatch records, proving native macro resolution (`{EVENT.DURATION}`, `{HOST.NAME}`, `{EVENT.SEVERITY}`) and mutual exclusivity.
2. **Resolution of Non-Super-Admin Permission Boundary:** Identifying and correcting the Zabbix rule where users with role `Admin` silently drop notifications when their user groups lack explicit `hostgroup_rights` with `permission: 2` (read).
3. **Formalization of Service-Outage vs. Total-Outage Semantics:** Establishing that single Avaya host or appliance outages (e.g. `avaya-sbce-01`, `avaya-g450-01`, `avaya-sm-01`, `sip-trunk-carrier-01`) constitute `service_outage` (routed exclusively to the 4 voice administrators in Group 14), while strictly reserving `total_outage` (Action 10) for complete loss of primary site transport or core switching (`mock-core-switch-01` / `core-gw-01`), paging all 5 recipients including the central IT Service Desk (Group 15).
4. **Recovery Semantics & Controlled Production Transition:** Defining the technical difference between Layer 3 host reachability (ICMP) and higher-layer service restoration (SIP OPTIONS / synthetic call pass), while formally linking Phase 13.8 acceptance into the Phase 8.2 Controlled Read-Only Production Telemetry Commissioning Gate.

---

## 2. Notification Architecture & Action Topology

The Nawari notification topology operates under strict classification tags, preventing overlapping matches and duplicate alerts:

```
                                  [Zabbix Trigger Fires]
                                            |
                                            v
                             [notification_class Tag Evaluation]
                                            |
      +---------------------+---------------+-------------------+---------------------+
      |                     |               |                   |                     |
      v                     v               v                   v                     v
[total_outage]     [service_outage] [synthetic_failure]   [degradation]    [component/monitoring]
  (Action 10)        (Action 11)      (Action 12)          (Action 13)         (Actions 14, 15)
      |                     |               |                   |                     |
      v                     v               v                   v                     v
All 5 Recipients     4 Voice Admins   4 Voice Admins      Technical Admins     Technical Admins
(Group 15: Voice     (Group 14: Voice (Group 14: Voice    (Group 7: Tech       (Group 7: Tech
 + Service Desk)       Engineers)       Engineers)          Team)                Team)
```

### 2.1 Action Catalog

| Action ID | Action Name | Filter Condition | Target User Group | Recipient Count | Operational Focus |
|:---|:---|:---|:---|:---:|:---|
| **7** | `Nawari Avaya & Communication Alerting` | `triggerid > 0` | *None* | **0** | **RETIRED (Status: 1 / Disabled)**. Replaced by Actions 10–15. |
| **10** | `Total Outage Alert` | `notification_class = total_outage` | Group 15 (`Nawari Total Outage Administrators`) | **5** | Network Core transport failure, dual-core cluster down, complete site isolation. Pages Service Desk. |
| **11** | `Communication Service Outage Alert` | `notification_class = service_outage` | Group 14 (`Nawari Avaya & Communications Administrators`) | **4** | Single Avaya appliance failure, single trunk loss, registration loss. Excludes Service Desk. |
| **12** | `Synthetic Voice Failure Alert` | `notification_class = synthetic_failure` | Group 14 (`Nawari Avaya & Communications Administrators`) | **4** | Synthetic call test failure, MOS degradation (<3.8 / <3.5), one-way media. |
| **13** | `Network Degradation Alert` | `notification_class = degradation` | Group 7 (`Technical Administrators`) | Configured | Jitter, packet loss, bandwidth spikes, trunk capacity threshold alerts. |
| **14** | `Component Failure Alert` | `notification_class = component_failure` | Group 7 (`Technical Administrators`) | Configured | Redundant PSU, fan tray, ambient temperature, E1 link layer alarms. |
| **15** | `Monitoring Failure Alert` | `notification_class = monitoring_failure` | Group 7 (`Technical Administrators`) | Configured | SNMP agent unresponsive, stale trapper telemetry (>15m), missing telemetry. |

---

## 3. Zabbix Runtime Event Engine & Permission Mechanics

### 3.1 The Non-Super-Admin Permission Boundary

During runtime validation against Zabbix 7.4, an architectural nuance of Zabbix user management was diagnosed:
- **Condition:** Users assigned role `Admin` (`roleid: 2`), when placed into a User Group with an empty `hostgroup_rights: []` array, are treated by the Zabbix alert manager as lacking read rights on the problem hosts.
- **Symptom:** Triggers fire and create problems in `problem.get`, action conditions match, but `alert.get` produces 0 alert dispatches without logging an explicit error.
- **Resolution:** `services/api/provisioning/notification_reconciler.py` was enhanced with `ensure_group_permissions()`, granting read access (`permission: 2`) across all monitored host groups (`Avaya Infrastructure`, `Network Infrastructure`, `Voice Carriers`, `Synthetic Probes`) to both Group 14 and Group 15:
  ```python
  client.call("usergroup.update", {
      "usrgrpid": group_id,
      "hostgroup_rights": [
          {"id": hg["groupid"], "permission": 2} for hg in host_groups
      ]
  })
  ```
- **Verification:** Post-reconciliation, Zabbix immediately dispatched 4 alerts for Group 14 actions and 5 alerts for Group 15 actions.

### 3.2 Native Macro Expansion Engine

Zabbix 7.4 native macro expansion was verified in runtime execution:
- `{HOST.NAME}`: Fully rendered to host visible name (e.g. `Simulated Core Switch 01 (Lab)`, `Voice Synthetic Probe 01`).
- `{EVENT.NAME}`: Rendered to trigger description without truncation.
- `{EVENT.SEVERITY}`: Rendered to human-readable severity string (`High`, `Disaster`, `Warning`).
- `{EVENT.DATE} {EVENT.TIME}`: Rendered to exact problem detection timestamp.
- `{EVENT.DURATION}`: Expanded in recovery messages to exact downtime duration (e.g. `Total Downtime: 5s`). Zero instances of `{EVENT.DURATION}` or `{EVENT.AGE}` left unrendered.

---

## 4. Operational Semantics: Total Outage vs. Service Outage

A critical requirement of enterprise aviation monitoring is preventing **alarm fatigue** at the Central IT Service Desk (`itservicedesk@kenya-airways.com`).

### 4.1 Strict Service Semantics Matrix

| Failure Mode | Monitored Entity | Trigger Description | Classification | Action ID | Alerted Recipients | Operational Rationale |
|:---|:---|:---|:---|:---:|:---:|:---|
| **Network Core Switch Down** | `mock-core-switch-01` | `Core Switch: Total Network Core Transport Failure` | `total_outage` | **10** | **5** (All Admins + Service Desk) | Primary site transport collapsed. All voice, signaling, and data traffic severed. Critical enterprise incident. |
| **Network Core Gateway Down** | `core-gw-01` | `Network Generic Device: Unavailable by ICMP ping` | `total_outage` | **10** | **5** (All Admins + Service Desk) | Default gateway unreachable. WAN connectivity down. Central incident declared. |
| **Single SBCE Appliance Down** | `avaya-sbce-01` | `Avaya SBCE: Appliance Unreachable` | `service_outage` | **11** | **4** (Voice Admins Only) | SBCE pair operates in HA or secondary SBC exists. External SIP may failover. Voice engineers investigate; Service Desk not paged. |
| **Single G450 Gateway Down** | `avaya-g450-01` | `Avaya G450: Media Gateway Chassis Unreachable` | `service_outage` | **11** | **4** (Voice Admins Only) | Media gateway unreachable. Local analog/PRI trunks impacted, but CM core and other gateways remain up. |
| **Single Session Manager Down** | `avaya-sm-01` | `Avaya SM: Session Manager Host Unavailable` | `service_outage` | **11** | **4** (Voice Admins Only) | Session Manager cluster has secondary node (`avaya-sm-02`). SIP endpoints failover to survivor. Telephony continues. |
| **Single SIP Trunk Down** | `sip-trunk-carrier-01` | `SIP Trunk: Consecutive OPTIONS Probe Failures` | `service_outage` | **11** | **4** (Voice Admins Only) | Primary carrier down. CM route pattern automatically fails over to secondary carrier (Airtel). Service Desk not paged. |
| **Synthetic Call Failure** | `voice-synthetic-probe-01`| `Degraded voice quality on synthetic probe (MOS < 3.8)`| `synthetic_failure` | **12** | **4** (Voice Admins Only) | Media degradation observed on simulated call probe. Requires voice engineering diagnosis. |

---

## 5. Recovery Semantics: L3 Link Reachability vs. Higher-Layer Restoration

A common monitoring pathology is declaring an incident resolved the moment an ICMP ping succeeds. In telecommunications, ICMP restoration only confirms Layer 3 IP reachability.

The Nawari recovery verifier enforces three distinct recovery layers:
1. **Layer 3 Link Reachability:** ICMP ping responds. Proves the appliance OS is running and network interface is up.
   - *Status:* `HOST_REACHABLE`. Voice service restoration is **UNPROVEN**.
2. **Layer 7 Signaling Restoration:** SIP OPTIONS exchange receives `200 OK`, and CM/SM entity registration is confirmed.
   - *Status:* `SIGNALING_RESTORED`. Call setup capability restored. Media path unproven.
3. **End-to-End Media Path Verification:** Active synthetic probe executes a test call, completes RTP audio streaming, and verifies MOS $\ge 4.0$.
   - *Status:* `SERVICE_RESTORED_PROVEN`. Incident may be authoritatively closed.

---

## 6. Zero-Branding Standard

To maintain strict Kenya Airways corporate and operational neutrality:
- Recipient-facing alert messages must never expose platform internals.
- Prohibited brand terms: `"Nawari"`, `"Zabbix"`, `"Grafana"`.
- Subject line conventions:
  - `[TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}`
  - `[SERVICE OUTAGE] — {HOST.NAME} — {EVENT.NAME}`
  - `[SYNTHETIC ALERT] — {HOST.NAME} — {EVENT.NAME}`
  - `[RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}`
- Host visible names reconciled: `Voice Synthetic Probe 01` and `Endpoint Synthetic Probe 01` (removing legacy platform names).

---

## 7. Controlled Production Transition & Phase 8.2 Commissioning Gate

Phase 13.8 runtime verification is conducted in a staging environment. The transition to production is protected by strict technical gates:

```
+-------------------------------------------------------------------------+
| PHASE 13.8 ACCEPTANCE: RUNTIME STAGING NOTIFICATIONS VERIFIED (PASSED)  |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| PHASE 8.2: CONTROLLED READ-ONLY PRODUCTION TELEMETRY COMMISSIONING GATE |
|                                                                         |
| 1. Read-Only Production Telemetry:                                      |
|    - Connect to live Avaya SNMP interfaces (CM, SM, SBCE, G450)         |
|    - Ingest live syslog / trap streams                                  |
|                                                                         |
| 2. Microsoft 365 OAuth 2.0 Media Type Commissioning:                    |
|    - Transition Email Media Type from CONFIGURED_UNVERIFIED to VERIFIED |
|    - Perform single-recipient controlled email delivery test            |
|                                                                         |
| 3. Mandatory Safety Policies:                                           |
|    - HARD_PRODUCTION_DENY: ZERO automated carrier failovers or reboots  |
|    - mon-grafana01 mutation lock enforced                               |
|    - Sentra repository isolated at baseline commit 9970404              |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Executive Operational Authorization (KQ Service Desk & Voice Head)     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Live Production Telemetry & Active Incident Notification                |
+-------------------------------------------------------------------------+
```
