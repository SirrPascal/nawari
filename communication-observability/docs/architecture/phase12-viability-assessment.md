# Nawari Phase 12 Technical Viability Assessment
## Controlled Operational Automation, Rollback Safety & Resource Envelope

**Document Version:** 1.0.0  
**Status:** Architectural Baseline for Review  
**Date:** 2026-11-08  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM)  
**Container Resource Budget:** $\le 2.2\text{ GiB}$ total memory consumption across all Nawari containers  

---

## 1. Executive Summary

This viability assessment provides an evidence-based technical evaluation of the architectural safety gates, transactional state machines, rollback engines, and cryptographic audit chains proposed for **Phase 12: Controlled Operational Automation & Remediation Playbooks**.

The core objective is proving that operational remediation can be executed safely, idempotently, and within the strict resource envelope of `mon-grafana01` (2 vCPUs, 7.8 GiB RAM) without risking automated runaway loops, unverified mutations, or unvetted core network outages.

---

## 2. Component Technical Viability Matrix

### 2.1 Action Transactional State Machine & Idempotency (Workstream 12A/12D)
- **Purpose:** Execute discrete operational playbooks with transactional step logging and deterministic idempotency guarantees.
- **Design:** Implemented as a finite-state machine (`PROPOSED` $\to$ `PENDING_APPROVAL` $\to$ `APPROVED` $\to$ `EXECUTING` $\to$ `VERIFYING` $\to$ `COMPLETED` / `ROLLED_BACK` / `REJECTED`).
- **Idempotency:** Enforced via UUIDv4 idempotency keys and state checks. Duplicate submissions with an existing idempotency key return the existing action record without re-executing steps.
- **Memory Overhead:** Negligible. Active action records consume $\approx 2\text{ KB}$ per execution.
- **Verdict:** **Approved — Mandatory Foundation for Workstream 12A/12D**.

---

### 2.2 Two-Person Rule, Change Windows & Approval Interlocks (Workstream 12B)
- **Purpose:** Require human authorization for high-consequence operational mutations (carrier trunk failovers, core routing changes).
- **Security:** Tokens are HMAC-SHA256 signatures generated from `action_id`, `operator_id`, `nonce`, and `expires_at` (15-minute window).
- **Two-Person Rule:** High-Risk actions require two distinct operator tokens (proposer $\neq$ approver) before state can transition to `APPROVED`.
- **Change Window Check:** Validates whether current time falls within scheduled maintenance windows; actions outside windows are blocked.
- **Verdict:** **Approved — Mandatory for Workstream 12B**.

---

### 2.3 Automated Remediation Playbooks & Risk Tiers (Workstream 12C)
- **Purpose:** Predefined, validated procedures covering Low, Moderate, and High-risk actions.
- **Risk Tiering:**
  - *Low-Risk:* Diagnostic probes, synthetic test calls, SNMP queries (Automated).
  - *Moderate-Risk:* Monitoring restarts, probe threshold updates (Single-operator approval).
  - *High-Risk:* Route shifts, trunk failover, interface toggles (Recommendation-only initially; strict change control).
- **Verdict:** **Approved — Core Engine for Workstream 12C**.

---

### 2.4 Automated Rollback Engine & Post-Verification Gating (Workstream 12E)
- **Purpose:** Ensure that any action failing post-action verification or encountering intermediate errors is immediately and cleanly reverted.
- **Mechanism:** Every playbook step implements an explicit `inverse_action(context)` callable. The engine tracks executed steps on an internal stack; on any exception or verification failure, steps are unrolled in reverse order ($N \dots 1$).
- **Timeout Protection:** Post-verification has a strict timeout (e.g. 60 seconds). If service restoration is not proven within the timeout, rollback initiates automatically.
- **Verdict:** **Approved — Mandatory for Workstream 12E**.

---

### 2.5 Cryptographically Chained Immutable Audit Trail (Workstream 12G)
- **Purpose:** Maintain a tamper-evident log of all operational proposals, approvals, executions, and rollbacks adhering to ICAO/IATA aviation standards.
- **Mechanism:** Blockchain-style SHA-256 block chaining where each record includes the hash of the preceding record:
  $$\text{Hash}_n = \text{SHA256}(\text{Hash}_{n-1} \,\|\, \text{Payload}_n)$$
- **Performance:** SHA-256 hashing in Python standard library (`hashlib`) takes $< 5\ \mu\text{s}$ per record.
- **Verdict:** **Approved — Mandatory for Workstream 12G**.

---

## 3. Host Resource Budget Analysis (`mon-grafana01`)

| Component / Process | Allocated RAM Ceiling | Projected Phase 12 RAM | CPU Impact (% of 2 vCPUs) |
| :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | 512 MiB | 512 MiB (unchanged) | $1.0 - 3.0\%$ |
| **Zabbix Server 7.4** | 768 MiB | 768 MiB (unchanged) | $2.0 - 5.0\%$ |
| **Zabbix Frontend** | 256 MiB | 256 MiB (unchanged) | $< 1.0\%$ |
| **Grafana 11** | 256 MiB | 268 MiB (+12 MiB for operations dashboard) | $1.0 - 2.0\%$ |
| **Nawari Services (Phases 1-11)** | 280 MiB | 280 MiB (unchanged) | $< 2.0\%$ |
| **Phase 12 Action Engine** | **120 MiB** | **$\approx 15 - 25\text{ MiB}$** (action state, audit chain) | **$< 0.5\%$** (discrete event-driven) |
| **Total Container Envelope** | **$\le 2.20\text{ GiB}$** | **$\approx 2.10\text{ GiB}$** | **$\le 15\%$ peak vCPU** |

*Conclusion:* Phase 12 operates well within the $2.20\text{ GiB}$ host ceiling, leaving $> 5.5\text{ GiB}$ host headroom for the OS and buffer caches.

---

## 4. Failure Modes & Mitigations

| Failure Mode | Risk Level | Architectural Mitigation |
| :--- | :--- | :--- |
| **Runaway Remediation Loops** | Critical | **Rate Limiter & Circuit Breaker:** Max 3 actions/hr per device. 3 consecutive failures within 15 minutes trips a global `LOCKED_CIRCUIT_BREAKER` requiring manual NOC intervention. |
| **Partial Execution / Half-State** | High | **Transactional Unroll:** The rollback engine unrolls completed steps in reverse order if any step fails. |
| **Remediation Worse Than Fault** | Critical | **Mandatory Post-Verification:** If post-action verification (e.g. synthetic test call) fails to prove improvement within 60s, automatic rollback triggers immediately. |
| **Blast Radius Miscalculation** | High | **Topology Gating:** If topology confidence $< 0.80$ or downstream nodes $> 5$, automated execution is strictly blocked. |
| **Stale Operator Approvals** | Medium | **Token Expiration:** Approval tokens expire after 15 minutes; pre-action checks re-verify fault conditions before execution begins. |
| **Production Environment Mutation** | Critical | **Simulation Gating:** Local runs enforce `SIMULATED_REMEDIATION` metadata; live physical mutations remain strictly gated behind Phase 8.2 commissioning. |

---

## 5. Viability Conclusion & Approval

Phase 12 is **technically viable, operationally safe, and resource-compliant** for implementation.

Implementation proceeds across Workstreams 12A through 12H with isolated simulation adapters and full regression preservation.
