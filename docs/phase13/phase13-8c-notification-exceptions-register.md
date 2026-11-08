# Phase 13.8C — Notification Exceptions & Staging Deviations Register

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Approved & Documented  
**Platform:** Zabbix 7.4.16 / PostgreSQL Engine on `mon-grafana01`  
**Purpose:** Formal record of operational exceptions, design allowances, and staging boundaries identified during Phase 13.8C.

---

## 1. Executive Summary

To maintain absolute system safety, prevent unauthorized external message delivery, and ensure 100% predictable testing in the staging environment, specific operational allowances and exceptions were established during Phase 13.8C.

This register formally records each exception, its technical justification, security impact, and prerequisites for production commissioning.

---

## 2. Exceptions & Allowances Ledger

```
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| ID | Exception Summary              | Classification        | Staging Allowance   | Production Prerequisite       |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 01 | External Email Delivery Status | Boundary / Safety     | CONFIGURED_         | Formally authorize Microsoft  |
|    |                                |                       | UNVERIFIED          | 365 OAuth / SMTP credentials  |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 02 | SMS Delivery Status            | Boundary / Safety     | CONFIGURED_         | Provision SMS gateway / GSM   |
|    |                                |                       | UNVERIFIED          | modem integration in Ph 13.15 |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 03 | Technical Admin Media ID 1     | Configuration / Fix   | Explicit Email on   | Validate production admin     |
|    |                                |                       | User ID 1 (Admin)   | distribution list media       |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 04 | Informational Triggers         | Operational Filtering | Zero Action alerts  | Audit event history in        |
|    |                                |                       | for "informational" | quarterly operational review  |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 05 | Maintenance Cache Reload       | Staging Synchronization| Manual config cache | Normal 60s polling interval   |
|    |                                |                       | reload via CLI      | in production environment     |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 06 | Multi-sample Metric Spacing    | Telemetry Injection   | 1.0s sleep between  | Real SNMP/Agent pollers       |
|    |                                |                       | trapper samples     | naturally space metrics (60s) |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
| 07 | Production Infrastructure Deny | Security Boundary     | HARD_PRODUCTION_    | Phase 13.9 controlled         |
|    |                                |                       | DENY = True         | physical commissioning only   |
+----+--------------------------------+-----------------------+---------------------+-------------------------------+
```

---

## 3. Detailed Exception Descriptions

### Exception 01: External Email Delivery Boundary
- **Description:** Real email delivery to Kenya Airways mailboxes (`@kenya-airways.com`) was prevented by keeping the staging media type directed to a controlled capture sink.
- **Classification:** Safety & Compliance Requirement.
- **Justification:** Prevents confusion, alarm, and inbox flooding during aggressive fault-injection testing.
- **Audit Value:** Delivery status is formally logged as `CONFIGURED_UNVERIFIED`.
- **Commissioning Action:** In a future controlled change window (post-Phase 13.15), Microsoft 365 OAuth credentials will be validated with an approved one-shot test email to an authorized testing distribution list.

### Exception 02: SMS Delivery Boundary
- **Description:** SMS notifications remain unconfigured and unverified.
- **Classification:** Scope Boundary.
- **Justification:** SMS notification is reserved for Severity 1 Total Outages during off-hours, pending SMS gateway provisioning.
- **Audit Value:** Status is recorded as `CONFIGURED_UNVERIFIED`.

### Exception 03: Technical Administrator Media Configuration
- **Description:** User ID 1 (`Admin`), member of User Group 7 (`Zabbix administrators`), was updated to have Media ID 1 (`Admin@kenya-airways.com`).
- **Classification:** Technical Configuration Fix.
- **Justification:** In Zabbix 7.4, recovery operations configured with `operationtype: 11` ("Notify all involved") require that the user targeted by the initial problem operation has a valid media assigned. Without media assigned, the initial problem alert fails with `No media defined for user`, which prevents Zabbix from queueing the recovery alert. Adding media to `Admin` resolved this and allowed Actions 13, 14, and 15 to process both problem and recovery alerts seamlessly.

### Exception 04: Informational Event Filtering
- **Description:** Triggers tagged with `notification_class: informational` (e.g. Host name changed, interface operational status changed intentionally) generate events in Zabbix history but do not match any action conditions in Actions 10–15.
- **Classification:** Noise Reduction Standard.
- **Justification:** Alerts should be actionable. Recording informational events in the database allows correlation without generating email or pager noise.

### Exception 05: Maintenance Window Cache Reload
- **Description:** After creating maintenance windows via API (`maintenance.create`), `zabbix_server -R config_cache_reload` was executed via Docker exec.
- **Classification:** Testing Synchronization.
- **Justification:** Zabbix Server refreshes its configuration cache from the database every 60 seconds by default (`ConfigFrequency=60`). During automated staging tests that run in < 15 seconds, forcing a cache reload ensures the server immediately honors the maintenance window. In production, maintenance windows are scheduled well in advance of maintenance activities.

### Exception 06: Metric Spacing for Trapper Count Functions
- **Description:** When injecting metrics into trapper items evaluated by count functions (e.g. `count(/template/key, #4, "eq", 0) >= 3`), test scripts insert a `1.0s` pause between samples.
- **Classification:** Test Instrumentation Detail.
- **Justification:** The PostgreSQL `history_uint` table stores item timestamps with 1-second resolution. Sending 4 samples within the same millisecond results in identical second timestamps, which Zabbix history coalesces. Real production polling uses 30-second to 60-second intervals, naturally providing discrete timestamps.

### Exception 07: Production Infrastructure Isolation
- **Description:** All test items and triggers were evaluated on staging lab hosts (`mock-core-switch-01`, `sip-trunk-carrier-01`, `nawari-voice-probe-01`, `avaya-g450-01`, `avaya-cms-01`).
- **Classification:** Security & Production Isolation.
- **Justification:** Absolute compliance with `HARD_PRODUCTION_DENY`. Real production switches, Avaya Session Managers, and carriers were never touched.

