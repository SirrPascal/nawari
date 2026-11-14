# NAWARI Phase 13.7: Notification Evidence Register & Configuration Audit

**Document Status:** AUTHORITATIVE AUDIT & CONFIGURATION REGISTER  
**Target Environment:** Kenya Airways Core Network Observability & Communication Assurance  
**Operating Host:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM)  
**System Profile:** `SIMULATION & STAGING PROFILE`  
**Audit Timestamp:** 2026-11-08 17:42:00 UTC  
**Production Gate:** `HARD_PRODUCTION_DENY` Strictly Enforced  

---

## 1. Zabbix 7.4 Action Configuration Audit

The following table documents the authoritative configuration state queried directly from the running Zabbix 7.4 JSON-RPC API on `http://localhost:8088/api_jsonrpc.php`:

| Action ID | Action Name | Live API Status | Event Source | Filter Condition | Target User Group (ID) | Step 1 Operation | Step 2..0 Escalation | Recovery Operation |
| :---: | :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- |
| **10** | **Total Outage Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = total_outage` | Nawari Total Outage Recipients (15) | Send message to Group 15 | Repeat every 1800s (`30m`), Duration: `{EVENT.AGE}` | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **11** | **Communication Service Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = service_outage` | Nawari Avaya & Comms Administrators (14) | Send message to Group 14 | Repeat every 3600s (`60m`), Duration: `{EVENT.AGE}` | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **12** | **Synthetic Voice Failure Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = synthetic_failure`| Nawari Avaya & Comms Administrators (14) | Send message to Group 14 | None (`esc_period = 0`, single alert) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **13** | **Network Degradation Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = degradation` | Zabbix administrators (7) | Send message to Group 7 | Repeat every 7200s (`120m`) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **14** | **Component Failure Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = component_failure`| Zabbix administrators (7) | Send message to Group 7 | Repeat every 3600s (`60m`) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **15** | **Monitoring Failure Alert** | `0` (Enabled) | Triggers (0) | `Tag notification_class = monitoring_failure`| Zabbix administrators (7) | Send message to Group 7 | None (`esc_period = 0`, single alert) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **7** | *Nawari Avaya & Communication Alerting* | **`1` (Disabled)** | Triggers (0) | *Severity $\ge$ Warning AND Host Group in Comms* | *Nawari Avaya & Comms Administrators (14)* | *Superseded* | *Superseded* | *Superseded* |

*Audit Verification:* Legacy Action 7 is disabled (`status = 1`) to guarantee that the four administrators (who belong to both Group 14 and Group 15) never receive dual notifications for total outage events.

---

## 2. User Directory & Group Membership Register

### 2.1 User Groups

| Group ID | Group Name | Purpose | Enrolled User Count | Members |
| :---: | :--- | :--- | :---: | :--- |
| **15** | `Nawari Total Outage Recipients` | Designated recipients for total outages, Sev 1 network/core failures, and recovery duration notifications. | **5** | `john.gacomo`, `robinson.wainaina`, `pascal.gathungu`, `mercy.vaati`, `itservicedesk` |
| **14** | `Nawari Avaya & Communications Administrators` | Designated engineering team for voice/telephony service outages and synthetic quality alerts. | **4** | `john.gacomo`, `robinson.wainaina`, `pascal.gathungu`, `mercy.vaati` |
| **7** | `Zabbix administrators` | Technical operations team for hardware component faults, link drops, and SNMP collection failures. | **NOC** | `Admin`, technical duty engineers |

### 2.2 User Media Profiles

All user media profiles are configured with the native Email media type (ID: 1) with delivery status locked at `CONFIGURED_UNVERIFIED`:

| Username | User ID | Full Name | Destination Email | Media ID | Active Status | Active Period | Severity Bitmask |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| `john.gacomo` | `3` | John Gacomo | `John.Gacomo@kenya-airways.com` | `1` | `0` (Enabled) | `1-7,00:00-24:00` | 63 (All 6 Severities) |
| `robinson.wainaina` | `4` | Robinson Wainaina | `Robinson.Wainaina@kenya-airways.com` | `1` | `0` (Enabled) | `1-7,00:00-24:00` | 63 (All 6 Severities) |
| `pascal.gathungu` | `5` | Pascal Gathungu | `Pascal.Gathungu@kenya-airways.com` | `1` | `0` (Enabled) | `1-7,00:00-24:00` | 63 (All 6 Severities) |
| `mercy.vaati` | `6` | Mercy Vaati | `Mercy.Vaati@kenya-airways.com` | `1` | `0` (Enabled) | `1-7,00:00-24:00` | 63 (All 6 Severities) |
| `itservicedesk` | `7` | IT Service Desk | `ITservicedesk@kenya-airways.com` | `1` | `0` (Enabled) | `1-7,00:00-24:00` | 63 (All 6 Severities) |

*Safety Guard:* `SMTP_USER` and `SMTP_PASS` remain unpopulated. No live emails are dispatched to the Kenya Airways mail exchange.

---

## 3. Trigger Tagging Inventory (`notification_class`)

Across the 70 monitored triggers provisioned on templates and hosts, `notification_class` tags are distributed as follows:

| Tag Value (`notification_class`) | Trigger Count | Trigger Examples | Trigger Action Target |
| :--- | :---: | :--- | :--- |
| `total_outage` | **6** | `Device unreachable by ICMP ping`, `SBC Appliance Unreachable`, `Session Manager Host Unavailable`, `Media Gateway Chassis Unreachable` | Action 10 (Group 15: 5 recipients) |
| `service_outage` | **8** | `SIP Trunk: SIP entity down`, `Media Gateway Unregistered from CM`, `Consecutive OPTIONS Probe Failures`, `Recording Pipeline Failure` | Action 11 (Group 14: 4 voice admins) |
| `synthetic_failure` | **9** | `Synthetic Voice Probe: MOS below threshold 3.5`, `One-way audio detected on synthetic test`, `Synthetic voice test failed` | Action 12 (Group 14: 4 voice admins) |
| `degradation` | **52** | `Avaya SBCE: High CPU utilization`, `High packet loss to default gateway`, `Interface High Bandwidth Utilization`, `CM: Real-Call Packet Loss High` | Action 13 (Group 7: Tech team) |
| `component_failure` | **15** | `Power Supply Unit Failure`, `Fan Tray Failure`, `Interface Link Down`, `E1/ISDN Primary Rate Interface Down` | Action 14 (Group 7: Tech team) |
| `monitoring_failure` | **12** | `SNMP agent is not responding`, `Avaya SM: Management Telemetry Stale or Loss of Monitoring`, `No SNMP data collection` | Action 15 (Group 7: Tech team) |
| `informational` | **8** | `Device has just been restarted`, `System name has changed`, `Certificate expiration warning` | Logged (No active page) |

*Total Triggers Tagged:* **110** (including host-level trigger instances across network switches and Avaya nodes).

---

## 4. Zero Platform Branding Audit Register

All six action templates were audited for prohibited platform nomenclature. The table below registers the audit status:

| Action Name | Problem Template Scan | Escalation Template Scan | Recovery Template Scan | Audit Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Outage Alert** | Passed (0 violations) | Passed (0 violations) | Passed (0 violations) | **VERIFIED CLEAN** |
| **Communication Service Alert** | Passed (0 violations) | Passed (0 violations) | Passed (0 violations) | **VERIFIED CLEAN** |
| **Synthetic Voice Failure Alert**| Passed (0 violations) | N/A (Single alert) | Passed (0 violations) | **VERIFIED CLEAN** |
| **Network Degradation Alert** | Passed (0 violations) | Passed (0 violations) | Passed (0 violations) | **VERIFIED CLEAN** |
| **Component Failure Alert** | Passed (0 violations) | Passed (0 violations) | Passed (0 violations) | **VERIFIED CLEAN** |
| **Monitoring Failure Alert** | Passed (0 violations) | N/A (Single alert) | Passed (0 violations) | **VERIFIED CLEAN** |

*Prohibited Tokens:* `\b(nawari|zabbix|grafana)\b` (case-insensitive) - **0 Matches found across 100% of templates.**

---

## 5. Security and Governance Baseline

| Boundary Control | Enforcement Mechanism | Verified State | Audit Result |
| :--- | :--- | :--- | :---: |
| **Production Mutation Gate** | `AutomationPolicyEngine.evaluate_policy(action, simulation_mode=True)` | `HARD_PRODUCTION_DENY` strictly enforced | **PASS** |
| **Packaging Gate** | `DeploymentProfileManager.validate_deployment_eligibility("single-site-production")` | Blocked pending Phase 8.2 certification (`HARD_PRODUCTION_DENY`) | **PASS** |
| **Sentra Git Isolation** | `git -C /Users/madeira/Desktop/Projects/sentra status` | Clean working tree; HEAD on `9970404` | **PASS** |
| **Nawari Regression Gate** | `scripts/verify_phase10.sh` & `scripts/verify_phase13.sh` | 9/9 Passed (Phase 10); 12/12 Passed (Phase 13) | **PASS** |
| **Phase 13.7 Test Suite** | `pytest tests/unit/test_phase13_7_notification_lifecycle.py` | 14/14 Passed (100% pass rate) | **PASS** |

---

## 6. Audit Conclusion & Production Acceptance Gate

Phase 13.7 establishes full compliance with the notification lifecycle, mutual exclusivity, honest downtime semantics, and recipient segregation requirements. The platform remains safely quarantined in the staging profile with `HARD_PRODUCTION_DENY` locked, pending Kenya Airways executive authorization for Phase 8.2 physical cutover.
