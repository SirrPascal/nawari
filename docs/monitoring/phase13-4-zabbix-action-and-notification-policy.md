# Phase 13.4 — Zabbix Action & Notification Escalation Policy

## 1. Action Overview

In Zabbix 7.4, notifications are governed by declarative Action definitions. The unified telephony alerting action is defined in:
`provisioning/zabbix/actions/action_communication_alerting.yaml`

This action manages alerting for all Avaya telephony infrastructure, external SIP carrier trunks, and synthetic voice testing components.

---

## 2. Action Conditions & Filtering

The action triggers only when incoming trigger events satisfy all of the following conditions:

```yaml
conditions:
  - conditiontype: TRIGGER_SEVERITY
    operator: GREATER_OR_EQUAL
    value: WARNING  # Covers WARNING, AVERAGE, HIGH, DISASTER
  - conditiontype: EVENT_TAG
    operator: EQUALS
    tag: scope
    value: availability
  # OR tag: scope = performance
  - conditiontype: HOST_GROUP
    operator: IN
    values:
      - "Avaya Infrastructure"
      - "SIP Carrier Trunks"
      - "Synthetic Voice Monitoring"
```

### Maintenance Suppression
- `pause_suppressed: YES`: When a host is under active maintenance (either planned or emergency with data collection paused/unpaused), problem notifications are suppressed until the maintenance period ends.

---

## 3. Step Escalation & Cooldown Intervals

To prevent notification spam while ensuring persistent operational awareness for unacknowledged outages, Zabbix step escalations are configured:

| Step | Delay / Interval | Recipient Group | Notification Type | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Step 1** | Immediate (`0s`) | `NOC Telephony Duty` | Initial Problem Alert | Immediate notification upon trigger transition to PROBLEM state. |
| **Step 2** | `1800s` (30 minutes) | `NOC Telephony Duty`, `Telephony Tier-2 On-Call` | Escalation / Repeat Alert | Sent if the problem is still active and unacknowledged after 30 minutes. |
| **Step 3** | `3600s` (60 minutes) | `IT Operations Management`, `Telephony Duty` | Executive Incident Escalation | Sent if outage persists for > 1 hour. |

### Minimum Cooldown & Repeat Policy
- Cooldown period between repeats: **1800 seconds (30 minutes)**.
- Single notification per event transition (no duplicate emails for the same active event cycle).

---

## 4. Recovery & Update Operations

### Recovery Operation (Trigger transitions to OK)
- Dispatches immediately upon trigger recovery.
- Uses native Zabbix recovery template:
  - Subject: `RESOLVED: {EVENT.NAME} on {HOST.NAME}`
  - Body: Includes resolution timestamp `{EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}`, problem duration `{EVENT.AGE}`, and final trigger metric value `{EVENT.RECOVERY.VALUE}`.

### Update Operation (Acknowledgment / Comment Added)
- When a NOC engineer acknowledges the problem or attaches a troubleshooting note in Zabbix, an update notification is routed to subscribed engineers to notify them that the issue is actively being investigated.

---

## 5. Message Formatting Templates

All notification templates adhere to structured markdown-style plain text suitable for Microsoft 365 Exchange Online rendering:

```
[NAWARI TELEPHONY ALERT] - {TRIGGER.SEVERITY}
Event: {EVENT.NAME}
Host: {HOST.NAME} ({HOST.IP})
Component: {EVENT.TAGS.component}
Scope: {EVENT.TAGS.scope}
Severity: {TRIGGER.SEVERITY}
Trigger Status: PROBLEM
Event Time: {EVENT.DATE} {EVENT.TIME}
Current Value: {ITEM.LASTVALUE}
Operational Impact: {TRIGGER.DESCRIPTION}

Incident URL: http://zabbix.nawari.internal/tr_events.php?triggerid={TRIGGER.ID}&eventid={EVENT.ID}
```

