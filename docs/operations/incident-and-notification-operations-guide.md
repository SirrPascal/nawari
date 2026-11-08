# Nawari Incident & Notification Operations Guide

**Scope:** Incident Lifecycle Management, Multi-Channel Notification Routing, DLQ Redelivery, and Recovery Assurance  
**Target Infrastructure:** JKIA NOC Control Plane & Regional Engineering Centers  
**Service Reference:** `services.multisite.incident_pipeline`, `services.multisite.notifications`, `services.multisite.recovery_verifier`  

---

## 1. Incident Lifecycle & Correlation Pipeline

Nawari employs a deterministic, thread-safe incident lifecycle pipeline designed to prevent alert storms and guarantee verified service restoration.

```
       [ Raw Operational Alerts (Zabbix, SNMP, Synthetic, Voice) ]
                                   |
                                   v
             +-------------------------------------------+
             |         Alert Correlation Engine          |
             +-------------------------------------------+
               |                  |                    |
        (Maintenance)       (Parent Down)        (Fingerprint Duplicate)
               |                  |                    |
               v                  v                    v
          [ MUTED ]         [ SUPPRESSED ]      [ DEDUPLICATED ]
               |                  |                    |
               +------------------+--------------------+
                                   |
                              (New Alert)
                                   v
                   +-------------------------------+
                   |    Incident State: NEW        |
                   +---------------+---------------+
                                   |
                                   v
                   +-------------------------------+
                   | Incident State: CORRELATED    |
                   +---------------+---------------+
                                   |
                         (Operator Acknowledged)
                                   v
                   +-------------------------------+
                   | Incident State: INVESTIGATING |
                   +---------------+---------------+
                                   |
                         (Remediation Initiated)
                                   v
                   +-------------------------------+
                   |  Incident State: REMEDIATING  |
                   +---------------+---------------+
                                   |
                   +---------------+---------------+
                   |   Recovery Verifier Engine    |
                   | (3 Fresh Healthy Observations)|
                   +---------------+---------------+
                                   |
                              (Verified)
                                   v
                   +-------------------------------+
                   |   Incident State: RESOLVED    |
                   +---------------+---------------+
                                   |
                         (Hold Window Satisfied)
                                   v
                   +-------------------------------+
                   |    Incident State: CLOSED     |
                   +-------------------------------+
```

### 1.1 Ingestion & Deduplication
- **Deduplication Key:** Hash of `(entity_id, metric_name, station_id)`.
- **Deduplication Window:** 600 seconds (10 minutes). When identical alerts arrive within this window, the existing incident counter is incremented and work notes updated rather than generating duplicate incidents.

### 1.2 Upstream Dependency Suppression (Topology-Aware)
- When a designated parent entity (e.g. Core Datacenter Router `RTR-CORE-DC1`) is declared down, all subordinate alerts from dependent circuits and outstation switches (e.g. `CIR-MBA-01`, `CIR-KIS-01`) are automatically tagged `SUPPRESSED`.
- Suppressed incidents do not trigger high-urgency wake-up notifications to station duty engineers, focusing troubleshooting on the root cause.

### 1.3 Recurrence Detection
- If an alert matching a resolved incident arrives within 3,600 seconds (1 hour) of resolution, the incident is automatically **REOPENED**, its recurrence count incremented, and severity escalated if warranted.

---

## 2. Multi-Channel Notification Router & DLQ

### 2.1 Escalation Matrix by Severity

| Severity Level | Target Audience | Channels Dispatched | Escalation SLA |
| :--- | :--- | :--- | :--- |
| **P1 Critical** | Incident Commander, Station Duty Lead, Network Eng, Service Owner | SMS, Email, Teams/Slack, PagerDuty | 5 minutes |
| **P2 Major** | Station Duty Lead, Network/Voice Engineers | Email, Teams/Slack | 15 minutes |
| **P3 Moderate** | Systems Administrators, Network Operations Queue | Email, Dashboard Banner | 60 minutes |
| **P4 Low / Info** | Operational Audit Log | Dashboard Banner Only | Next Business Day |

### 2.2 Retry Logic & Dead Letter Queue (DLQ)
External communication channels (SMS gateways, SMTP relays, Webhooks) are subject to transient network failures.
- **Initial Delivery:** Attempted immediately upon incident creation or escalation.
- **Transient Failures:** Messages transitioning to `FAILED` are retried with exponential backoff.
- **Maximum Retries:** 3 attempts.
- **Dead Letter Queue (`DEAD_LETTER`):** Messages failing all 3 attempts are moved to the DLQ.

### 2.3 DLQ Operational Redelivery Runbook
When messages accumulate in the DLQ:
1. Review DLQ depth in `nawari_incident_operations` dashboard.
2. Check upstream carrier connectivity (e.g. Safaricom SMS API, Corporate SMTP relay).
3. Once the underlying carrier issue is resolved, execute the DLQ retry command:
   ```bash
   python3 -c "from services.multisite.notifications import NotificationRouter; router = NotificationRouter(); router.retry_failed_messages()"
   ```
4. Confirm message status transitions from `DEAD_LETTER` to `DELIVERED`.

---

## 3. Metric-Aware Recovery Verifier

A core engineering safeguard in Nawari is that **incidents cannot be closed by manual assertion alone**. They require metric-driven verification through the `MetricAwareRecoveryVerifier`.

### 3.1 The Three-Observation Rule
To transition an incident from `REMEDIATING` to `RESOLVED`:
- The verifier must record **at least 3 consecutive fresh, healthy observations**.
- Any single unhealthy or degraded observation immediately resets the consecutive count to zero.

### 3.2 Telemetry Source Freshness Windows

| Source Type | Nominal Cadence | Maximum Allowed Age ($T_{\text{fresh}}$) | Required Consecutive Healthy |
| :--- | :--- | :--- | :--- |
| **SYNTHETIC_PROBE** | 10–15s | 30.0 seconds | 3 |
| **VOICE_PROBE** | 15–30s | 60.0 seconds | 3 |
| **SNMP_POLLING** | 60s | 90.0 seconds | 3 |
| **ENDPOINT_AGENT** | 120s | 180.0 seconds | 3 |

### 3.3 Strict Rejection of Replayed Telemetry
> [!CAUTION]
> Historical telemetry forwarded from outstation store-and-forward buffers (`is_replayed=True`) **is strictly disqualified from recovery verification**. Only live, real-time observations recorded after the remediation timestamp can verify service restoration.
