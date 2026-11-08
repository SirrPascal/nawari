# Nawari Security, Scoped RBAC & Governance Guide

**Scope:** Role-Based Access Control, Three-Identity Interlock, Audit Ledger, and Production Safety Gates  
**Service Reference:** `services.multisite.site_rbac`, `services.multisite.api_governance`  
**Security Status:** Production Remediation Hard-Gated Pending Phase 8.2 Physical Commissioning  

---

## 1. Multi-Site Scoped Role-Based Access Control (RBAC)

Nawari enforces a strict hierarchical access control model (`services.multisite.site_rbac`) mapping enterprise roles to geographical and operational boundaries.

### 1.1 Scope Hierarchy
Scopes follow a strict top-down containment model:
$$\text{ENTERPRISE / GLOBAL} \succ \text{REGIONAL} \succ \text{COUNTRY} \succ \text{STATION} \succ \text{FACILITY} \succ \text{DOMAIN}$$

A user granted a role at a higher scope automatically inherits authority over all nested subordinate entities, while a user granted authority at a station or facility scope is strictly prevented from inspecting or modifying resources outside their assigned boundary.

### 1.2 Enterprise Role Matrix

| Role | Scope Level | Permitted Operations | Restricted Operations |
| :--- | :--- | :--- | :--- |
| **GLOBAL_ADMIN** | ENTERPRISE | Full user administration, global policy authoring, system-wide configuration. | Live physical execution without second authorizer. |
| **CHIEF_INFORMATION_OFFICER** | ENTERPRISE | Executive dashboard review, Tier 3 emergency remediation authorization. | Routine configuration changes. |
| **GLOBAL_NOC_OPERATOR** | ENTERPRISE | Enterprise incident triage, alert acknowledgement, cross-station correlation. | Production remediation execution. |
| **REGIONAL_MANAGER** | REGIONAL | Regional outstation review, cross-station maintenance scheduling within region. | Access to outstations in other regions. |
| **COUNTRY_ADMIN** | COUNTRY | Management of all stations and facilities within designated country boundary. | Cross-country resource modification. |
| **STATION_DUTY_LEAD** | STATION | Station incident triage, local circuit failover requests, local node maintenance. | Modifications outside assigned station IATA. |
| **NETWORK_ENGINEER** | DOMAIN: NETWORK | Network device configuration, BGP/OSPF telemetry analysis, WAN circuit testing. | Voice PBX changes, database admin. |
| **VOICE_ENGINEER** | DOMAIN: VOICE | Avaya SBCE / SM trunk inspection, SIP ladder analysis, MOS threshold tuning. | Core network routing changes. |
| **SERVICE_OWNER** | ENTERPRISE | Business SLA definition, SLO target review, service dependency catalog management. | Direct network or server administration. |
| **READ_ONLY_AUDITOR** | ANY SCOPE | Inspection of telemetry, incident logs, dashboards, and audit trails. | All state mutations, acknowledgements. |

### 1.3 Revocation & Session Invalidation
When an operator leaves the organization or undergoes security review:
- The user account is marked `is_revoked = True`.
- All cached tokens, active leases, and approval authorizations are immediately invalidated.
- Any attempt to propose or approve an operational action with a revoked identity raises `PermissionError` and logs a high-severity security event.

---

## 2. Three-Identity Interlock for High-Risk Remediations

To prevent unauthorized, unilateral, or automated configuration changes on Kenya Airways critical infrastructure, Phase 13 implements the **Three-Identity Interlock** for Tier 3 (High-Risk) remediations.

### 2.1 The Cardinality Invariant
For any Tier 3 operational action (e.g. core router reload, BGP failover, trunk rerouting), the set of authenticated individuals must satisfy:
$$|\{P, A_1, A_2\}| = 3$$
Where:
- $P$ is the **Proposer** (the engineer or agent submitting the remediation plan).
- $A_1$ is **Authorizer 1** (e.g. Station Duty Lead or Network Operations Manager).
- $A_2$ is **Authorizer 2** (e.g. Chief Information Officer or Global NOC Lead).

> [!CAUTION]
> If any identity is reused ($P = A_1$, $P = A_2$, or $A_1 = A_2$), the system raises `ThreeIdentityCardinalityViolation` and aborts execution.

### 2.2 HMAC-SHA256 Operational Envelope Binding
Approval tokens are cryptographically bound to the complete operational payload via HMAC-SHA256:
$$\text{Envelope} = \{ \text{action\_id}, \text{playbook\_id}, \text{playbook\_version}, \text{plan\_hash}, \text{parameters\_hash}, \text{target\_env}, \text{change\_window\_id} \}$$
$$\text{Token} = \text{HMAC-SHA256}(\text{Key}, \text{CanonicalEnvelope} \parallel \text{ApproverID} \parallel \text{Nonce} \parallel \text{Expiry})$$

If an operational plan, parameter set, or change window is modified after approval has been granted, the HMAC signature verification fails immediately (`SignatureMismatchError`), invalidating the approval.

---

## 3. Cryptographically Chained Audit Ledger

All operational mutations, approvals, and incident transitions are recorded in the append-only Hardened Audit Ledger (`services.multisite.api_governance.HardenedAuditLedger`).

### 3.1 Hash Chaining & Block Verification
Each audit entry is structured as a cryptographic block:
$$H_i = \text{SHA-256}(i \parallel H_{i-1} \parallel T_i \parallel \text{ActorID} \parallel \text{Action} \parallel \text{Station} \parallel \text{Payload})$$

The ledger integrity can be verified at any time:
```python
from services.multisite.api_governance import HardenedAuditLedger
ledger = HardenedAuditLedger()
ledger.load_from_disk("/var/log/nawari/audit_ledger.json")
result = ledger.verify_integrity()
assert result["valid"] is True
```

If an unauthorized process alters or truncates an entry on disk, `verify_integrity()` detects the break in the hash chain and pinpoints the corrupted block index.

---

## 4. Production Safety Gates & Phase 8.2 Commissioning

### 4.1 The Simulation Switch (`is_simulation_mode`)
Nawari incorporates an immutable runtime safety check:
- When running with profile `simulation` or `staging`, all autonomous physical device executions are intercepted and intercepted.
- Any attempt to dispatch execution commands against live physical network devices without explicit physical commissioning credentials triggers:
  `HARD_PRODUCTION_DENY: Physical production mutations are gated pending Phase 8.2 commissioning.`

### 4.2 Prerequisites for Phase 8.2 Physical Commissioning
Physical production enablement requires:
1. Completion of physical equipment cabling and OOB console verification at JKIA Datacenter.
2. Verified multi-site WAN circuit cross-connects with Safaricom and Airtel.
3. Cryptographic deployment of operator physical hardware tokens (FIDO2 / YubiKey).
4. Formal physical commissioning sign-off executed by the Kenya Airways Head of Technical Operations.
