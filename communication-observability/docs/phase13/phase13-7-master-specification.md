# NAWARI Phase 13.7: Notification Lifecycle Validation and Incident Communication Acceptance

**Document Status:** MASTER ENGINEERING SPECIFICATION  
**Target Environment:** Kenya Airways Core Network Observability & Communication Assurance  
**Operating Host:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM)  
**System Profile:** `SIMULATION & STAGING PROFILE`  
**Production Mutation Gate:** LOCKED (`HARD_PRODUCTION_DENY` strictly enforced)  
**Authoritative Repositories:**  
- `nawari`: Active Development Workspace  
- `sentra`: Preserved Baseline Reference (`origin/main` at commit `9970404`)  

---

## 1. Executive Summary & Purpose

Phase 13.7 formalises the end-to-end notification lifecycle and incident communication acceptance across the Kenya Airways hybrid network and voice infrastructure. Following the reconciliation of the 59 communication triggers (Phase 13.5) and the 13 Network Observability dashboards (Phase 13.6), this specification governs the operational event dispatching architecture within native Zabbix 7.4.

The architecture enforces five inviolable operational principles:
1. **Zabbix-Native Alerting Engine:** All metric polling, threshold evaluation, event generation, escalation timing, and recovery correlation are performed directly by Zabbix 7.4. Custom Python engines are strictly restricted to simulation harnesses and high-level multi-domain incident correlation.
2. **Action Mutual Exclusivity & Zero Duplicate Alerts:** Because the four designated voice administrators belong to both the Voice Administrator user group (ID: 14) and the Total Outage recipient group (ID: 15), alerting actions must be strictly partitioned. Legacy untagged communication actions (Action 7) are disabled (`status = 1`), and each incoming event is classified into exactly one structured action based on its `notification_class` tag. No recipient receives duplicate notifications for the same event.
3. **Zero Platform Branding Rule:** Recipient-facing incident notifications must never contain internal monitoring tool or platform names (specifically prohibiting the words `Nawari`, `Zabbix`, or `Grafana`, and internal tool script paths). Messages must read as standard, generic, professional IT operational incident communications suitable for transmission to the IT Service Desk and executive stakeholders.
4. **Honest Downtime Semantics:** Recovery notifications explicitly quantify **monitoring-observed downtime** using the native `{EVENT.DURATION}` macro. The specification explicitly accounts for the delta between physical real-world outage duration and monitoring-observed downtime resulting from polling intervals and threshold verification windows. Recovery wording is conservative: an operational check indicates that the host or interface is responding again; it does not claim to verify higher-layer voice quality or subjective user experience.
5. **Production Boundary Safety:** The `HARD_PRODUCTION_DENY` gate remains strictly locked on `mon-grafana01`. Notification capture and lifecycle validation are conducted deterministically in staging. Real email delivery status remains `CONFIGURED_UNVERIFIED` until Microsoft 365 OAuth credentials and formal production cutover are authorized by Kenya Airways engineering leadership.

---

## 2. Notification Architecture & Action Topology

```
+--------------------------------------------------------------------------------------------------+
|                                    ZABBIX 7.4 EVENT ENGINE                                       |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                     (Triggers generate Problem)
                                                 |
                                                 v
                       +--------------------------------------------------+
                       | Trigger Event Tag: 'notification_class'          |
                       +--------------------------------------------------+
                                                 |
         +-------------------+-------------------+--------------------+-------------------+
         |                   |                   |                    |                   |
         v                   v                   v                    v                   v
+-----------------+ +-----------------+ +-----------------+ +-----------------+ +-----------------+
| total_outage    | | service_outage  | |synthetic_failure| | degradation     | |component_failure|
| (Action ID: 10) | | (Action ID: 11) | | (Action ID: 12) | | (Action ID: 13) | | (Action ID: 14) |
+-----------------+ +-----------------+ +-----------------+ +-----------------+ +-----------------+
         |                   |                   |                    |                   |
         |                   |                   |                    +---------+---------+
         |                   |                   |                              |
         |                   |                   |                              v
         |                   |                   |                     +-----------------+
         |                   |                   |                     | monitoring_fail |
         |                   |                   |                     | (Action ID: 15) |
         |                   |                   |                     +-----------------+
         |                   |                   |                              |
         v                   v                   v                              v
+-----------------+ +-------------------------------------+            +-----------------+
| User Group 15:  | | User Group 14:                      |            | User Group 7:   |
| Total Outage    | | Nawari Avaya & Comms Administrators |            | Zabbix Admins   |
| Recipients      | | (4 Voice Engineers)                 |            | (Tech Team)     |
| (5 Recipients)  | +-------------------------------------+            +-----------------+
+-----------------+
  - John Gacomo
  - Robinson Wainaina
  - Pascal Gathungu
  - Mercy Vaati
  - IT Service Desk
```

### 2.1 Action Registry and Tag Routing

| Action ID | Action Name | Trigger Tag Filter (`notification_class`) | Target User Group | Group ID | Recipient Count | Escalation Policy | Recovery Policy |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **10** | **Total Outage Alert** | `total_outage` | Nawari Total Outage Recipients | 15 | 5 | Repeat every 30m (`1800s`), Duration `{EVENT.AGE}` | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **11** | **Communication Service Alert** | `service_outage` | Nawari Avaya & Comms Administrators | 14 | 4 | Repeat every 60m (`3600s`), Duration `{EVENT.AGE}` | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **12** | **Synthetic Voice Failure Alert**| `synthetic_failure`| Nawari Avaya & Comms Administrators | 14 | 4 | No repeat (`esc_period = 0`), Single alert | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **13** | **Network Degradation Alert** | `degradation` | Zabbix administrators | 7 | Tech Team | Repeat every 120m (`7200s`) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **14** | **Component Failure Alert** | `component_failure`| Zabbix administrators | 7 | Tech Team | Repeat every 60m (`3600s`) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| **15** | **Monitoring Failure Alert** | `monitoring_failure`| Zabbix administrators | 7 | Tech Team | No repeat (`esc_period = 0`) | Immediate, `{EVENT.DURATION}`, Notify all involved |
| *7* | *Nawari Avaya & Communication Alerting* | *None (Legacy Host Group filter)* | *Nawari Avaya & Comms Administrators* | *14* | *Retired* | **Status: 1 (DISABLED)** to prevent duplicate notifications |

### 2.2 Mutual Exclusivity Proof
1. Every trigger template and host trigger provisioned on Kenya Airways equipment is tagged with exactly one `notification_class` tag value.
2. Actions 10 through 15 evaluate `conditiontype = 26` (Tag value) with `operator = 0` (equals). Because tag values are mutually exclusive, an event tagged with `total_outage` matches **only** Action 10; it cannot match Actions 11, 12, 13, 14, or 15.
3. Legacy Action 7 is set to `status = 1` (Disabled). Therefore, Zabbix completely excludes Action 7 from problem and recovery processing.
4. Result: **Every event matches exactly one action, and the 4 administrators receive exactly one notification stream.**

---

## 3. Recipient Profiles & User Directory

### 3.1 Designated Communication Administrators
The four designated voice engineers are enrolled in both User Group 14 (`Nawari Avaya & Communications Administrators`) and User Group 15 (`Nawari Total Outage Recipients`):

| Username | Full Name | Email Address | Active Media | Severity Mask | Group Memberships |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `john.gacomo` | John Gacomo | `John.Gacomo@kenya-airways.com` | Email (Active) | 63 (All 6 Severities) | Groups 14, 15 |
| `robinson.wainaina` | Robinson Wainaina | `Robinson.Wainaina@kenya-airways.com` | Email (Active) | 63 (All 6 Severities) | Groups 14, 15 |
| `pascal.gathungu` | Pascal Gathungu | `Pascal.Gathungu@kenya-airways.com` | Email (Active) | 63 (All 6 Severities) | Groups 14, 15 |
| `mercy.vaati` | Mercy Vaati | `Mercy.Vaati@kenya-airways.com` | Email (Active) | 63 (All 6 Severities) | Groups 14, 15 |

### 3.2 Service Desk Recipient
The Kenya Airways central IT Service Desk is enrolled exclusively in User Group 15 (`Nawari Total Outage Recipients`):

| Username | Full Name | Email Address | Active Media | Severity Mask | Group Memberships |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `itservicedesk` | IT Service Desk | `ITservicedesk@kenya-airways.com` | Email (Active) | 63 (All 6 Severities) | Group 15 Only |

*Operational Rationale:* The IT Service Desk must be alerted during major network or core communications outages so that incoming call centre disruptions and enterprise service desk tickets can be correlated. However, sub-system component degradations (e.g. redundant fan failures, SNMP collection timeouts, or synthetic audio quality fluctuations) must be shielded from the Service Desk to avoid alert fatigue.

---

## 4. Deterministic Test Scenarios (Scenarios A through J)

The lifecycle validation is structured across ten deterministic operational test scenarios:

### Scenario A: Total Network Outage
- **Target Host:** `mock-core-switch-01` or `core-gw-01`
- **Trigger Condition:** ICMP ping failure (3 consecutive probe cycles failed)
- **Tag:** `notification_class = total_outage`
- **Matched Action:** Action 10 (`Total Outage Alert`)
- **Recipient Count:** Exactly 5 (4 Voice Admins + IT Service Desk)
- **Subject Template:** `[TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}`
- **Operational Requirement:** Explicitly identifies device down; excludes platform jargon; alerts all 5 stakeholders.

### Scenario B: Total Communications Outage
- **Target Hosts:** `avaya-sbce-01`, `avaya-sm-01`, `avaya-cm-01`, `avaya-g450-01`
- **Trigger Condition:** Appliance/processor unreachable by ICMP ping
- **Tag:** `notification_class = total_outage`
- **Matched Action:** Action 10 (`Total Outage Alert`)
- **Recipient Count:** Exactly 5 (4 Voice Admins + IT Service Desk)
- **Operational Requirement:** Voice core system unreachability is escalated as a total outage. Action 7 does not duplicate.

### Scenario C: SIP Trunk Outage
- **Target Host:** `sip-trunk-carrier-01`
- **Trigger Condition:** Consecutive OPTIONS probe failures (503 Service Unavailable)
- **Tag:** `notification_class = service_outage`
- **Matched Action:** Action 11 (`Communication Service Alert`)
- **Recipient Count:** Exactly 4 (Voice Admins only)
- **Operational Requirement:** IT Service Desk is strictly excluded. Message does NOT declare unrelated core network or physical switch failure.

### Scenario D: Monitoring Failure
- **Target Host:** `avaya-cm-01` or `core-gw-01`
- **Trigger Condition:** SNMP agent not responding for > 300s
- **Tag:** `notification_class = monitoring_failure`
- **Matched Action:** Action 15 (`Monitoring Failure Alert`)
- **Recipient Count:** Technical Team only (`Zabbix administrators`)
- **Operational Requirement:** Voice admins and IT Service Desk are excluded. Message explicitly clarifies: *"Underlying device may remain operational; telemetry retrieval has stalled."*

### Scenario E: Component Failure
- **Target Host:** `core-gw-01` or `avaya-g450-01`
- **Trigger Condition:** Secondary PSU failure, fan tray failure, or interface link down
- **Tag:** `notification_class = component_failure`
- **Matched Action:** Action 14 (`Component Failure Alert`)
- **Recipient Count:** Technical Team only (`Zabbix administrators`)
- **Operational Requirement:** Single hardware fault with redundancy intact does not trigger Sev 1 procedures.

### Scenario F: Synthetic Voice Failure
- **Target Host:** `nawari-voice-probe-01`
- **Trigger Condition:** Synthetic SIP test call failure or calculated MOS < 3.5
- **Tag:** `notification_class = synthetic_failure`
- **Matched Action:** Action 12 (`Synthetic Voice Failure Alert`)
- **Recipient Count:** Exactly 4 (Voice Admins only)
- **Operational Requirement:** Subject `[SYNTHETIC ALERT]` and body explicitly identify probe origin, preventing confusion with physical trunk disconnection.

### Scenario G: 30-Minute Prolonged Outage Escalation
- **Trigger Condition:** Total outage remaining unresolved past step 1 (> 1800s)
- **Operation Step:** Step 2..0 (`esc_period = 1800s`)
- **Subject Template:** `[TOTAL OUTAGE ESCALATION] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.AGE}`
- **Macro Expansion:** `{EVENT.AGE}` expands to current elapsed time (e.g. `30m`, `1h`).
- **Operational Requirement:** Instructs immediate escalation to designated duty manager. Single action matching maintained.

### Scenario H: Outage Recovery & Downtime Duration
- **Trigger Condition:** OK event generated after active outage
- **Recovery Operation:** Type 11 (Notify all involved)
- **Subject Template:** `[RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}`
- **Recipient Count:** Exactly 5 (all recipients involved in initial alert)
- **Macro Expansion:** `{EVENT.DURATION}` evaluates to exact elapsed time between Problem and Recovery events.
- **Operational Language:** States device is responding again; instructs root cause review without claiming unverified end-to-end voice health.

### Scenario I: Repeated Outages (Distinct Event Lifecycles)
- **Condition:** Incident 1 occurs, escalates, and recovers. Incident 2 occurs 3 hours later.
- **Operational Requirement:** Incident 2 receives a new `{EVENT.ID}`, starts an independent timer, and computes independent `{EVENT.DURATION}`. Zero state leakage across distinct events.

### Scenario J: Acknowledgment and Maintenance Window Suppression
- **Condition J1 (Acknowledgment):** Incident acknowledged with operator commentary. When recovery occurs, recovery notification is dispatched to all 5 recipients with acknowledgment history preserved.
- **Condition J2 (Maintenance):** Monitored host is placed in scheduled maintenance (`pause_suppressed = 1`). New alerts and repeat escalations are suppressed during the maintenance window.

---

## 5. Recipient-Facing Communication Templates

All templates conform to the Zero Platform Branding standard (no mentions of Nawari, Zabbix, Grafana, or internal script files):

### 5.1 Total Outage (Action 10)
```text
SUBJECT: [TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}

A total outage has been identified affecting the following device or service.

Affected Device/Service: {HOST.NAME}
Issue: {EVENT.NAME}
Severity: {EVENT.SEVERITY}
Outage Start: {EVENT.DATE} {EVENT.TIME}
Details: {EVENT.OPDATA}
Status: OUTAGE IN PROGRESS

The affected device or service is currently unavailable. Please investigate and take the necessary action to restore normal operations.

A further notification will be issued once service has been restored.
```

### 5.2 Total Outage Escalation (Action 10)
```text
SUBJECT: [TOTAL OUTAGE ESCALATION] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.AGE}

An unresolved total outage continues to affect the following device or service.

Affected Device/Service: {HOST.NAME}
Issue: {EVENT.NAME}
Severity: {EVENT.SEVERITY}
Outage Start: {EVENT.DATE} {EVENT.TIME}
Current Duration: {EVENT.AGE}
Details: {EVENT.OPDATA}
Status: OUTAGE UNRESOLVED (ESCALATION)

The affected device or service remains unavailable. Please escalate immediately to the designated duty manager.
```

### 5.3 Total Outage Recovery (Action 10)
```text
SUBJECT: [RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}

The previously reported outage affecting the following device or service has been resolved.

Affected Device/Service: {HOST.NAME}
Original Issue: {EVENT.NAME}
Severity: {EVENT.SEVERITY}
Outage Start: {EVENT.DATE} {EVENT.TIME}
Recovery Time: {EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}
Total Downtime: {EVENT.DURATION}
Status: RECOVERED

The affected device or service is responding again and has returned to an operational state.

Please review the incident and establish the underlying cause where necessary.
```

---

## 6. Downtime Accounting: Monitoring-Observed vs Physical Timeline

In enterprise telemetry systems, monitoring-observed downtime ($D_{\text{mon}}$) differs deterministically from physical real-world downtime ($D_{\text{real}}$):

$$\Delta = D_{\text{mon}} - D_{\text{real}} = (\text{Delay}_{\text{recovery}} - \text{Delay}_{\text{detection}})$$

### 6.1 Parameter Modeling

| Parameter | Symbol | Nominal Value | Explanation |
| :--- | :---: | :---: | :--- |
| **Physical Outage Start** | $T_{\text{down}}$ | Real clock | Exact instant of physical link disconnection or process crash |
| **Physical Outage End** | $T_{\text{up}}$ | Real clock | Exact instant physical carrier signal or daemon resumes |
| **Poll Interval** | $P_{\text{poll}}$ | 10 seconds | Frequency of ICMP or SNMP polling by Zabbix poller |
| **Failure Confirmation Threshold** | $N_{\text{fail}}$ | 3 cycles | Number of consecutive failed attempts required before trigger state change |
| **Detection Delay** | $\text{Delay}_{\text{det}}$ | 30 seconds | $(P_{\text{poll}} \times N_{\text{fail}})$. Prevents flapping on single lost packets |
| **Problem Event Clock** | $T_{\text{prob}}$ | $T_{\text{down}} + 30\text{s}$ | Timestamp recorded in Zabbix `{EVENT.DATE} {EVENT.TIME}` |
| **Recovery Confirmation Threshold** | $N_{\text{rec}}$ | 1 cycle | Single successful response returns trigger to OK |
| **Recovery Delay** | $\text{Delay}_{\text{rec}}$ | 10 seconds | Next poll cycle interval |
| **Recovery Event Clock** | $T_{\text{rec}}$ | $T_{\text{up}} + 10\text{s}$ | Timestamp recorded in Zabbix `{EVENT.RECOVERY.TIME}` |
| **Macro Duration** | `{EVENT.DURATION}` | $T_{\text{rec}} - T_{\text{prob}}$ | Monitoring-observed downtime reported to recipients |

### 6.2 Example Quantification
For a physical outage lasting exactly 10 minutes (600s):
- $\text{Delay}_{\text{det}} = 30\text{s}$
- $\text{Delay}_{\text{rec}} = 10\text{s}$
- Monitoring-Observed Downtime: $600\text{s} + (10\text{s} - 30\text{s}) = 580\text{s} = \mathbf{9\text{m } 40\text{s}}$.

The 20-second difference represents the engineering confirmation hysteresis required to eliminate false positive alarms. This is documented as monitoring-observed downtime in all audit registers.

---

## 7. Operational Acceptance Criteria

Phase 13.7 is accepted when all the following criteria are satisfied:
1. **Automated Test Battery:** 100% pass rate across the 14 test cases in `tests/unit/test_phase13_7_notification_lifecycle.py`.
2. **Regression Integrity:** Zero failures across all existing test suites (Phases 1 through 13.6).
3. **Master Verification Gates:** `verify_phase10.sh` and `verify_phase13.sh` pass cleanly.
4. **Live Zabbix API State:** Action 7 is `status = 1` (Disabled); Actions 10–15 are `status = 0` (Enabled).
5. **Zero Platform Branding:** 0 violations of the prohibited branding regex across all rendered communications.
6. **Repository Isolation:** `sentra` working tree is clean and on commit `9970404`.
