# Phase 13.8C — Recovery & Escalation Engineering Report

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Staging Verified & Approved  
**Platform:** Zabbix 7.4.16 / PostgreSQL Engine on `mon-grafana01`  
**Related Documents:** `phase13-8c-runtime-notification-validation.md`, `phase13-8c-action-execution-evidence.md`

---

## 1. Executive Summary

A reliable enterprise monitoring system must handle incident resolution, escalation steps, and recovery notifications with the same precision applied to initial problem detection. 

Phase 13.8C evaluated the **runtime recovery and escalation behavior** of Zabbix 7.4 under controlled fault scenarios. Key findings include:
1. **Dynamic Recovery Duration:** Zabbix native `{EVENT.DURATION}` macro expands accurately into human-readable duration strings (e.g. `1s`, `2m 14s`, `1h 12m`), providing immediate downtime context to stakeholders.
2. **Operation Type 11 Mechanics:** Recovery operations configured with `operationtype: 11` ("Notify all involved") ensure that every recipient who received the initial problem notification automatically receives the corresponding recovery notification, while preventing unauthorized recipients from receiving unlinked recovery notices.
3. **Acknowledgment Decoupling:** Operator acknowledgments (`event.acknowledge`) add vital incident management context (tickets, operator identity) without suppressing or blocking trigger recovery when telemetry normalizes.
4. **Maintenance Suppression Precision:** Zabbix suppresses all problem notifications for hosts under active maintenance windows (`suppressed: 1`), while continuing history data collection.
5. **Architectural Separation of Physical vs. Incident Duration:** Nawari distinguishes between the time an alert is active in Zabbix and the physical duration of the fault.

---

## 2. Zabbix Recovery Operation Mechanics (`operationtype: 11`)

In Zabbix Actions 10 through 15, recovery operations are configured using `operationtype: 11` ("Notify all involved").

### Operational Workflow
1. When a problem occurs, the Action's `operations` block evaluates recipient rules (e.g. User Group 15 for total outages, User Group 14 for communications outages) and records problem alert rows in the `alerts` table.
2. When the problem expression evaluates to FALSE and the recovery expression evaluates to TRUE (via Phase 13.8B dual-expression hysteresis), Zabbix triggers a recovery event.
3. Zabbix inspects the history of the problem event: any user who successfully received a notification for that specific problem ID is automatically queued for a recovery message.
4. This architecture provides two major benefits:
   - **No Orphaned Recoveries:** Users never receive a "Resolved" message for a problem they were never alerted about.
   - **Guaranteed Closure:** All stakeholders who received the emergency notification receive closure without requiring separate recipient group maintenance on recovery operations.

> [!IMPORTANT]
> **Zabbix 7.4 Runtime Requirement Identified in Phase 13.8C:** For `operationtype: 11` to queue recovery alerts, the problem alert must have completed without an internal "No media defined for user" error. In Phase 13.8C, User ID 1 (`Admin`) was provisioned with active Media ID 1 (`Admin@kenya-airways.com`), ensuring that technical recovery notifications for Actions 13, 14, and 15 execute reliably.

---

## 3. Duration Macro Evaluation & Physical vs. Incident Time

All recovery message templates across Actions 10–15 utilize the `{EVENT.DURATION}` macro in the email subject and body:

```
Subject: [RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}
Body:
The operational incident on {HOST.NAME} has cleared.
Service: {EVENT.NAME}
Recovery Time: {EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}
Observed Downtime Duration: {EVENT.DURATION}
Incident Reference: Event ID {EVENT.ID}
```

### Physical Downtime vs. Zabbix Event Duration
Nawari operational standards mandate that `{EVENT.DURATION}` must be interpreted correctly by operations staff:

| Metric | Definition | Measurement Mechanism |
| :--- | :--- | :--- |
| **Zabbix Incident Duration** (`{EVENT.DURATION}`) | The time elapsed between trigger problem generation and trigger recovery resolution. | Directly computed by Zabbix Server from event timestamps. |
| **Physical Outage Duration** | The true physical duration during which network packets were dropped or voice calls failed. | Physical duration = `{EVENT.DURATION}` + `Trigger Detection Window` (e.g. 30s–60s) + `Recovery Hysteresis Hold Time` (e.g. 60s). |

Engineers and Service Desk personnel are instructed never to present `{EVENT.DURATION}` as the sole contractual physical SLA downtime, but rather as the **confirmed observability event duration**.

---

## 4. Escalation Policy & Step Durations

In staging Actions 10–15, escalation configuration is set to:
- **Default Operation Step Duration:** `1h` (3600 seconds).
- **Execution Step:** `From: 1`, `To: 1` (Immediate dispatch upon problem generation).
- **Escalation Phase:** For Phase 13.8C, operations are set to Step 1–1 to deliver immediate alerts without multi-hour delays. Future phases will introduce Step 2 escalations to Level 3 / Vendor Support if unacknowledged after 60 minutes.

```
+---------------------------------------------------------------------------------------------------+
|                                 ESCALATION POLICY STRUCTURE                                       |
+----------+--------------------+---------------+---------------------+-----------------------------+
| Step     | Time From Trigger  | Action Taken  | Target Recipients   | Notification Message        |
+----------+--------------------+---------------+---------------------+-----------------------------+
| Step 1   | Immediate (0 min)  | Dispatch      | Primary Duty Admins | Initial Problem Notice      |
| Step 2   | T + 60 minutes     | Escalation    | Duty Managers       | Unacknowledged Escalation   |
| Recovery | Upon Normalization | Closure       | All Involved (Op 11)| Incident Cleared & Duration |
+----------+--------------------+---------------+---------------------+-----------------------------+
```

---

## 5. Operator Acknowledgment Behavior

In Event 08 of Phase 13.8C, an incident was acknowledged using `event.acknowledge` with ticket `#INC-94810`.

### Observed Behaviors
1. **Audit Traceability:** Zabbix permanently records the acknowledging user (`Admin`), the timestamp, and the operator's message (`Incident #INC-94810: Investigating core fiber link`) in the event record.
2. **Dashboard Indicator:** The incident is marked with an "Acknowledged" badge on Grafana and Zabbix problem views, alerting other team members that an engineer is actively handling the issue.
3. **Unimpeded Recovery:** When telemetry normalized (`core.switch.total_outage_state = 0`), Zabbix successfully generated the recovery event and dispatched all 5 recovery notifications. Acknowledging a problem **does not suppress or impede recovery notifications**.

---

## 6. Maintenance Window Suppression

In Event 09, a maintenance window was applied to `mock-core-switch-01`.

### Observed Behaviors
1. **Suppression Tagging:** When the problem was injected during the active maintenance window, Zabbix created the event with `"suppressed": "1"` and populated `"suppression_data"`.
2. **Escalator Halt:** The Zabbix escalator process checked the maintenance state and immediately halted notification processing. **0 alert records were generated.**
3. **Telemetry Preservation:** Raw metrics (`core.switch.total_outage_state`) continued to be stored in the PostgreSQL database, ensuring historical reporting remains intact without generating alerting noise.

---

## 7. Recovery Differentiation: Reachability vs. Service Restoration

Nawari enforces a strict architectural rule regarding recovery differentiation:

```
[INFRASTRUCTURE EVENT]
  Device unreachable (ICMP lost) -> Host Trigger PROBLEM -> Admin Group 7 Alerted
  Device reachable (ICMP ok)     -> Host Trigger RECOVERED -> Admin Group 7 Notified: "Hardware reachable"
                                                             (Service NOT yet restored)

[SERVICE RESTORATION EVENT]
  SIP OPTIONS handshake OK       -> Service Trigger RECOVERED -> Comm Admins (Grp 14) + Desk (Grp 15) Notified:
  Synthetic Call MOS > 3.9                                    "Voice Communications Service Fully Restored"
```

This prevents false declarations of service recovery when a server or gateway has booted its network stack but voice processing daemons (e.g. Session Manager or Communication Manager) have not yet initialized.

