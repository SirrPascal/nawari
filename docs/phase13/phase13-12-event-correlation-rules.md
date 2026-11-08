# Phase 13.12 — Event Correlation & Causality Rules

## Correlation Principles

Nawari's `CausalityEngine` prevents operational alert storms by evaluating incoming alarms against topology graphs, dependency trees, and redundancy state machines.

```
       [ Core Event Ingestion ]
                  |
     +------------+------------+
     |                         |
[ Upstream Infrastructure ]   [ High-Availability Redundancy ]
- Core Switch failure         - HA Pair member failure
- Port-channel failure        - Active/Standby failover
     |                         |
     v                         v
[ Root Cause Isolated ]       [ Redundancy Failover ]
(Suppress Downstream)         (Mark DEGRADED, Block Action 10)
```

---

## 1. Rule Definitions

### Rule 1: Upstream Infrastructure Root-Cause Pinning
- **Trigger Condition**: An upstream core switch or aggregation router reports an administrative or physical link drop (`link down`, `operstatus down`, `port-channel down`).
- **Correlation Action**:
  - Assign `CausalClassification.ROOT_CAUSE` to the core network device.
  - Collect all downstream host ping loss, service timeouts, and reachability alarms within a 15-second window.
  - Classify downstream alarms as `CausalClassification.DOWNSTREAM_SYMPTOM`.
  - Suppress individual downstream tickets; attach them as child symptoms to the single root-cause incident.

### Rule 2: High-Availability Failover Dampening
- **Trigger Condition**: An active problem triggers on a host belonging to an HA cluster (e.g. `SBCE_HA_CLUSTER`, `CM_DUPLEX`, `CORE_SWITCHES`).
- **Correlation Action**:
  - Inspect the operational status of all sibling members in the HA group.
  - If at least one sibling is `HEALTHY` / `UP`:
    - Mark incident as `CausalClassification.REDUNDANCY_FAILOVER`.
    - Mark service impact as `DEGRADED`.
    - Dispatch alert strictly via **Action 12** (Telephony Team).
    - Prohibit triggering **Action 10** (Total Outage).
  - If ALL members in the HA group are offline:
    - Mark incident as `CausalClassification.ROOT_CAUSE`.
    - Mark service impact as `TOTAL_OUTAGE`.
    - Dispatch alert via **Action 10** (All 5 recipients including IT Service Desk).

### Rule 3: Interface & Link Flapping Dampening
- **Trigger Condition**: An interface changes operational state $\ge 3$ times within a sliding 60-second window.
- **Correlation Action**:
  - Classify incident as `CausalClassification.FLAPPING_DAMPENED`.
  - Lock alarm state to `WARNING: LINK_FLAPPING`.
  - Suppress subsequent recovery and problem churn until interface remains stable for 180 consecutive seconds.

### Rule 4: Downstream Business Service Degradation
- **Trigger Condition**: Parent service health drops below $0.85$.
- **Correlation Action**:
  - Propagate degradation status to all dependent child services in the DAG (e.g. if `SVC-CORP-TELEPHONY` is degraded, `SVC-IVR-SELFSERVICE` and `SVC-CONTACT-CENTER-INBOUND` inherit degraded status).
  - Record the originating parent service ID in the evaluation audit log.
