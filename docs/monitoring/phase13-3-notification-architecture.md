# Nawari Phase 13.3 — Notification Architecture & Microsoft 365 Integration

**Document Standard:** Nawari Enterprise Observability & Service Assurance  
**Target Environment:** Kenya Airways Telephony Estate & Operations Center (NOC/VOC)  
**Channel Provider:** Microsoft 365 Exchange Online (`smtp.office365.com:587`)  
**Security Standard:** Strict STARTTLS (`ssl.CERT_REQUIRED`) · Modern Auth XOAUTH2 · Secret Masking  

---

## 1. Notification Architecture Overview

The Nawari Notification Subsystem bridges telemetry event evaluation and human operational response. It is engineered with strict guardrails to guarantee timely notification of genuine incidents while eliminating notification spam, false alarms, and credential leakage.

```
+----------------------------------------------------------------------------------------------------+
|                               NAWARI NOTIFICATION PIPELINE                                         |
+----------------------------------------------------------------------------------------------------+
|  Telemetry Stream                                                                                  |
|        |                                                                                           |
|        v                                                                                           |
|  [ Communication Alert Engine ]                                                                    |
|        |                                                                                           |
|        +---> State Machine: PENDING (hold duration) --> FIRING                                     |
|        |                                                                                           |
|        +---> Deduplication: Keyed by (alert_id, entity_id)                                         |
|        |                                                                                           |
|        +---> Cooldown & Flapping Protection: 1800s suppression window                              |
|        |                                                                                           |
|        +---> Recovery Verification: 3-cycle nominal rule (Missing data resets cycle)               |
|        |                                                                                           |
|        +---> Maintenance Check: Suppressed if entity in active maintenance window                  |
|        |                                                                                           |
|        v                                                                                           |
|  [ Notification Dispatcher ]                                                                       |
|        |                                                                                           |
|        v                                                                                           |
|  [ Microsoft 365 Email Provider ] <--------- Safe Startup Check (Unconfigured = Disabled)          |
|        |                                                                                           |
|        +---> Strict STARTTLS (ssl.CERT_REQUIRED)                                                   |
|        |                                                                                           |
|        +---> Auth Mode: Modern OAuth2 / XOAUTH2 or SMTP AUTH                                       |
|        |                                                                                           |
|        +---> Secret Masking & Exponential Backoff Retry                                            |
|        |                                                                                           |
|        v                                                                                           |
|  [ Recipient: NOC / VOC / Engineering Operations ]                                                 |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Notification Lifecycle & Guardrails

### 2.1 Deduplication & Incident Keying
Every active incident is indexed by a deterministic composite fingerprint:
`fingerprint = sha256(f"{alert_id}:{entity_id}".encode()).hexdigest()`

- **Single Active Notification:** Only one notification is dispatched when an incident first transitions from `PENDING` to `FIRING`.
- **Repeat Reminders:** Subsequent reminders (`REPEAT_REMINDER`) are throttled by the cooldown interval (default: 1,800 seconds / 30 minutes).

### 2.2 Strict Recovery Verification
A common failure mode in monitoring systems is clearing an alert because the monitoring target became completely unreachable (reporting `None` or failing to collect). 

Nawari enforces a **Strict Recovery Contract**:
1. When a metric condition evaluates False, the instance enters `RECOVERING` state.
2. The instance requires **3 consecutive valid telemetry cycles** confirming nominal parameters.
3. **Missing or `None` telemetry CANNOT resolve an alert.** If telemetry is absent, `nominal_recovery_cycles` is reset to 0, and the incident remains held in `FIRING` or `RECOVERING`.
4. Only upon 3 valid nominal cycles does the engine transition to `RESOLVED` and dispatch an authoritative `RECOVERY` notification.

### 2.3 Maintenance Window Suppression
Administrative maintenance windows can be declared by entity ID. Any telemetry evaluations for entities under active maintenance transition through lifecycle states internally (for historical auditing), but outbound notification dispatch is completely suppressed.

---

## 3. Microsoft 365 Email Provider Specification

The notification provider [`services/integrations/m365_email_provider.py`](file:///Users/madeira/Desktop/Projects/nawari/services/integrations/m365_email_provider.py) connects Nawari directly to Microsoft 365 Exchange Online.

### 3.1 Connection & Cryptographic Security
- **Target Endpoint:** `smtp.office365.com` on port `587`.
- **Mandatory STARTTLS:** Connection initiates over plain SMTP, immediately upgrades via `STARTTLS`, and strictly validates server identity:
  ```python
  context = ssl.create_default_context()
  context.verify_mode = ssl.CERT_REQUIRED
  context.check_hostname = True
  ```
- **Plaintext Rejection:** Transmitting notifications over unencrypted port 25 or without STARTTLS is completely disallowed.

### 3.2 Authentication Models
1. **Modern Authentication (OAuth 2.0 / XOAUTH2):**
   Exchange Online requires OAuth 2.0 token-based authentication. The provider generates standard SASL XOAUTH2 authentication strings:
   `user=<sender_email>\x01auth=Bearer <oauth2_token>\x01\x01`
2. **SMTP Client Submission (App Password):**
   Supports dedicated application credentials with TLS authentication.

### 3.3 Safe Startup & Configuration Protocol
To ensure platform safety out of the box:
- Default `.env.example` leaves all M365 variables empty.
- When unconfigured, `M365EmailProvider` starts up safely in an **inactive/disabled** state (`is_configured() == False`).
- Calls to `send_notification()` return a graceful failure result (`success=False, error="M365 Email Provider not configured..."`) rather than crashing or throwing unhandled exceptions.
- **Handoff Protocol:** To activate live email notifications, the administrator must populate the `.env` file with tenant credentials and execute `scripts/test_m365_email.py --to admin@domain.com`.

### 3.4 Transient Error Handling & Exponential Backoff
SMTP network operations are subject to rate limiting and transient connectivity drops. The provider implements automatic retries:
- Default: 3 attempts with exponential backoff: `delay = backoff_base * (backoff_multiplier ** (attempt - 1))`.
- 4xx SMTP transient errors trigger retries; 5xx permanent authentication or mailbox rejections fail immediately.

### 3.5 Sensitive Data Protection & Secret Masking
Passwords and bearer tokens are never emitted into log streams:
`mask_secret("VerySecretPassword123!")` $\rightarrow$ `"Ve***************3!"`

---

## 4. Rich Notification Templates

Nawari generates dual-format notifications (HTML + plain-text fallback) structured for immediate operational comprehension:

| Event Type | Subject Line Format | Visual Styling | Key Payload Elements |
| :--- | :--- | :--- | :--- |
| `PROBLEM_INITIAL` | `[NAWARI - {SEVERITY}] {NAME} on {ENTITY}` | Red/Orange banner with severity badge | Entity, Alert ID, Metric, Observed Value, Threshold, Runbook Link |
| `REPEAT_REMINDER` | `[REMINDER - {SEVERITY}] {NAME} on {ENTITY}` | Yellow warning banner | Initial firing timestamp, duration active, current observed value |
| `RECOVERY` | `[RECOVERED] {NAME} on {ENTITY}` | Green recovery banner | Incident duration, recovery confirmation time, nominal observed value |
| `TEST_MESSAGE` | `[NAWARI TEST] Verification probe` | Blue informational banner | Timestamp, environment, diagnostic token |
| `MAINTENANCE` | `[MAINTENANCE] {ENTITY} under maintenance` | Gray operational banner | Start time, scheduled duration, suppressed alert count |

### Sample HTML Template Layout
```html
<div style="font-family: Arial, sans-serif; max-width: 600px; border: 1px solid #dcdcdc; border-radius: 6px;">
  <div style="background-color: #d32f2f; color: #ffffff; padding: 12px 16px; font-weight: bold; font-size: 16px;">
    [DISASTER] Avaya SBCE Appliance Unreachable
  </div>
  <div style="padding: 16px;">
    <p><strong>Entity:</strong> <code>sbce-pride-01</code> (10.2.156.131)</p>
    <p><strong>Metric:</strong> <code>avaya.sbce.reachability</code></p>
    <p><strong>Observed Value:</strong> <span style="color: #d32f2f; font-weight: bold;">0</span> (Threshold: == 0)</p>
    <p><strong>Evidence Class:</strong> <code>VERIFIED_INTEGRATION</code></p>
    <div style="background-color: #f5f5f5; padding: 10px; border-left: 4px solid #d32f2f; margin-top: 12px;">
      <strong>Runbook Action:</strong> Check SBCE physical power, hypervisor VM status, and edge firewall rules.
    </div>
  </div>
  <div style="background-color: #fafafa; padding: 8px 16px; font-size: 11px; color: #888888; border-top: 1px solid #eeeeee;">
    Nawari Enterprise Observability · Kenya Airways Ground Operations
  </div>
</div>
```

