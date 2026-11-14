# NAWARI Phase 13.7: Technology Viability and Architectural Assessment

**Document Status:** TECHNICAL VIABILITY AND FEASIBILITY ASSESSMENT  
**Subsystem:** Zabbix 7.4 Native Alerting, Macro Engine & Multi-Recipient Incident Communications  
**Target Environment:** Kenya Airways Core Network Observability & Communication Assurance  
**Operating Host:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM)  
**Production Gate:** LOCKED (`HARD_PRODUCTION_DENY`)  

---

## 1. Architectural Viability: Native Zabbix vs Custom Scripting

### 1.1 Evaluated Options

| Dimension | Option A: Native Zabbix 7.4 Trigger Actions | Option B: Custom External Python Daemon |
| :--- | :--- | :--- |
| **Event Detection** | Evaluated in C inside Zabbix Server timer/poller threads | Polling Zabbix API periodically via REST/JSON-RPC |
| **Detection Latency** | Sub-second from item value arrival | Periodic poll delay (typically 30–60s polling lag) |
| **Escalation Management** | Native escalation steps (`esc_step_from`, `esc_period`) | Custom database / state machine required |
| **Maintenance Windows** | Native suppression (`pause_suppressed = 1`) | Requires polling maintenance periods and correlating |
| **Recovery Correlation** | Built-in trigger correlation (`{EVENT.DURATION}`) | Requires tracking event IDs in custom local state |
| **High Availability** | Survives daemon restarts with WAL / PostgreSQL ACID | Risk of lost in-memory state or split-brain on crash |
| **Maintenance Overhead** | Standard enterprise Zabbix configuration | Custom code maintenance, test harness, dependency drift |

### 1.2 Viability Verdict
**Option A (Native Zabbix 7.4 Trigger Actions) is strongly recommended and confirmed viable.**  
Zabbix 7.4 provides built-in escalation timers, user group resolution, tag-based filtering, maintenance suppression, and macro expansion. Retiring custom Python alerting in favour of native actions eliminates architectural duplication and ensures high availability.

---

## 2. Duplicate Alert Prevention & Action Mutual Exclusivity

### 2.1 The Overlap Problem
In Phase 13.4, Action 7 (`Nawari Avaya & Communication Alerting`) was provisioned to target User Group 14 (`Nawari Avaya & Communications Administrators`) with conditions:
- Trigger Severity $\ge$ Warning
- Host Group in (`Voice Infrastructure`, `Avaya Infrastructure`, `Edge SBC`, `SIP Carrier Trunks`, `Communications Applications`, `Synthetic Probes`)

In Phase 13.6, structured actions (Actions 10–15) were introduced with tag filters (`notification_class`). When an Avaya host (such as `avaya-sm-01`) is down:
- It belongs to Host Group `Avaya Infrastructure`.
- Its trigger severity is `Disaster`.
- It has tag `notification_class = total_outage`.

Because Action 7 did not inspect tags, **both Action 7 and Action 10 triggered simultaneously**.
Furthermore, the four designated administrators:
1. John Gacomo
2. Robinson Wainaina
3. Pascal Gathungu
4. Mercy Vaati

belong to **both** User Group 14 and User Group 15 (`Nawari Total Outage Recipients`).
Consequently, the four administrators received dual notifications (two problem emails, two escalation emails, and two recovery emails) for every total outage event.

### 2.2 Evaluated Remediation Strategies

| Strategy | Mechanism | Viability Assessment |
| :--- | :--- | :--- |
| **Strategy 1: Complex Boolean Tag Inversion in Action 7** | Add `Tag "notification_class" does not equal "total_outage"` to Action 7. | **Conditionally viable, but fragile.** Requires maintaining negative tag rules whenever new classes are added. |
| **Strategy 2: Complete Retirement of Action 7 (`status = 1`)** | Update Action 7 `status = 1` in live Zabbix API. Rely entirely on structured Actions 10–15. | **Highly Viable & Clean.** Fully eliminates overlap. Every trigger has a `notification_class` tag that maps to exactly one structured action. |

### 2.3 Selected Strategy & Verification
**Strategy 2 was implemented.**
1. In `NotificationReconciler.reconcile_total_outage_policy()`, Action 7 is explicitly updated to `status = 1` (Disabled).
2. Live Zabbix API inspection confirms Action 7 status is `1`, while Actions 10 through 15 are `0` (Enabled).
3. Test case `test_12_mutual_exclusivity_zero_duplicate_action_matches` verifies that 100% of event classes match exactly one action.

---

## 3. Macro Semantics and Downtime Calculation Viability

### 3.1 Supported Native Macros in Zabbix 7.4

| Macro | Field Populated | Context Evaluated | Viability & Precision |
| :--- | :--- | :--- | :--- |
| `{HOST.NAME}` | Host visual name | Problem, Escalation, Recovery | Deterministic; resolves to host inventory name. |
| `{EVENT.NAME}` | Trigger description | Problem, Escalation, Recovery | Resolves to full trigger description. |
| `{EVENT.SEVERITY}` | Severity label | Problem, Escalation, Recovery | Resolves to Warning, Average, High, Disaster. |
| `{EVENT.DATE}`, `{EVENT.TIME}` | Outage start timestamp | Problem, Escalation, Recovery | UTC timestamp of initial problem event generation. |
| `{EVENT.OPDATA}` | Operational data expression | Problem, Escalation, Recovery | Evaluates current metric value expression. |
| `{EVENT.AGE}` | Current incident duration | Escalation operations | Evaluates $(T_{\text{current}} - T_{\text{problem}})$. Format: e.g. `30m`. |
| `{EVENT.DURATION}` | Total outage duration | Recovery operations | Evaluates $(T_{\text{recovery}} - T_{\text{problem}})$. Format: e.g. `24m 30s`. |

### 3.2 Downtime Semantics
Monitoring-observed downtime reflects the time elapsed between initial problem confirmation and recovery confirmation:
- An ICMP ping poll interval of 10s with 3 consecutive failed checks results in a 30s detection window.
- Recovery occurs on the first successful ICMP response (10s recovery window).
- For a 10-minute physical outage, monitoring reports `9m 40s`.
This 20-second difference represents operational confirmation hysteresis to avoid flapping alerts on transient packet drops. This calculation is viable and mathematically sound.

---

## 4. Microsoft 365 Email Delivery Viability

### 4.1 Authentication Protocols

| Protocol | Port / Security | Enterprise Status | Nawari Readiness |
| :--- | :--- | :--- | :--- |
| **SMTP Auth (Basic)** | Port 587 (STARTTLS) | Deprecated by Microsoft; disabled on modern M365 tenants | Fallback only; requires legacy SMTP client submission enabled on mailbox |
| **OAuth 2.0 Client Credentials** | Port 443 (Graph API / Modern Auth) | Microsoft recommended enterprise standard | Provisioned via Zabbix Media Type AlertScript `m365_oauth_mail.py` |

### 4.2 Staging Safety State
In accordance with Kenya Airways change governance:
- `SMTP_USER` and `SMTP_PASS` remain empty.
- User media status remains `CONFIGURED_UNVERIFIED`.
- Zero unsolicited emails are transmitted to `*@kenya-airways.com`.
- Notification testing is performed via deterministic staging capture harnesses.

---

## 5. Technical Risk Analysis & Mitigation Matrix

| Risk ID | Identified Risk | Severity | Mitigation Strategy | Operational Status |
| :---: | :--- | :---: | :--- | :---: |
| **R1** | Action 7 re-enabled accidentally, causing duplicate alert flood. | High | Automated unit tests assert Action 7 remains `status = 1`. Reconciler enforces status 1 idempotently. | **MITIGATED** |
| **R2** | Service Desk alerted on non-critical component or monitoring faults. | Medium | Service Desk (`itservicedesk`) is strictly enrolled in Group 15 only; Actions 11–15 exclude Group 15. | **MITIGATED** |
| **R3** | Recipient-facing messages leak internal tool jargon ("Nawari", "Zabbix"). | Low | All action templates sanitized; automated regex test enforces zero platform branding. | **MITIGATED** |
| **R4** | Prolonged outage escalations overwhelm inboxes. | Medium | Repeat interval throttled to 1800s (30m) for total outages, 3600s (1h) for services. | **MITIGATED** |
| **R5** | Maintenance windows trigger false alarms during planned maintenance. | High | All actions configured with `pause_suppressed = 1`. Alerts paused during maintenance. | **MITIGATED** |

---

## 6. Viability Conclusion

Phase 13.7 notification lifecycle validation is **technically viable, operationally robust, and production-ready for staging validation**. The solution achieves zero duplicate alerts, clean incident communications, honest downtime reporting, and strict production safety.
