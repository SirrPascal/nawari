# Phase 13.12 — Correlation Evidence Register

## Validation Evidence Summary

- **Execution Date**: 2026-11-08T19:43:52Z
- **Nawari Revision**: `8c4af7c`
- **Sentra Baseline Revision**: `9970404` (Clean & Untouched)
- **Snapshot Manifest**: [`provisioning/zabbix/snapshots/phase13_12_service_correlation_evidence.json`](file:///Users/madeira/Desktop/Projects/nawari/provisioning/zabbix/snapshots/phase13_12_service_correlation_evidence.json)
- **Test Suite**: [`tests/unit/test_phase13_12_service_correlation.py`](file:///Users/madeira/Desktop/Projects/nawari/tests/unit/test_phase13_12_service_correlation.py) (10/10 PASS)

---

## 1. Verified Correlation Scenarios

| Test Scenario | Method / Check | Outcome | Key Evidence Parameter |
| :--- | :--- | :--- | :--- |
| **Service Catalog Seeding** | `test_service_catalog_seeding_and_integrity` | `PASSED` | 8 core services verified with correct tiers & dependencies |
| **DAG Cycle Detection** | `test_service_dag_acyclic` | `PASSED` | DFS cycle detection found 0 cycles |
| **HA Single Failover** | `test_ha_pair_single_failure_degraded` | `PASSED` | `SBCE-01` down $\rightarrow$ `REDUNDANCY_FAILOVER`, `DEGRADED`, Action 12 |
| **HA Dual Exhaustion** | `test_ha_pair_dual_failure_total_outage` | `PASSED` | `SBCE-01` & `SBCE-02` down $\rightarrow$ `ROOT_CAUSE`, `TOTAL_OUTAGE`, Action 10 |
| **Core Switch Root Cause** | `test_core_switch_root_cause_isolation` | `PASSED` | Pinned to `jkia-core-sw01`; 2 child alarms suppressed |
| **Flapping Dampening** | `test_flapping_dampening_algorithm` | `PASSED` | 3 flaps in 20s $\rightarrow$ `FLAPPING_DAMPENED` |
| **Independent Event** | `test_independent_event_handling` | `PASSED` | Unmapped host kept separate as `INDEPENDENT_EVENT` |
| **Upstream Propagation** | `test_service_health_upstream_propagation` | `PASSED` | Parent telephony degradation propagated to recording child |
| **Missing Telemetry Guard** | `test_missing_telemetry_safe_downgrade` | `PASSED` | Missing telemetry safe downgrade to DEGRADED |
| **Zabbix Tree Provisioning** | Live Zabbix API execution | `PASSED` | 9 services provisioned in Zabbix 7.4 Service Tree (Root ID 2) |

---

## 2. Live Runtime Snapshot Extract

```json
{
  "metadata": {
    "phase": "13.12",
    "title": "Service Dependency Mapping & Event Correlation",
    "status": "VALIDATED_STAGING",
    "hard_production_deny": true
  },
  "service_catalog_summary": {
    "total_services": 16,
    "dag_cycles_detected": 0,
    "expected_services_verified": [
      "SVC-ENTERPRISE-NETWORK",
      "SVC-WAN-CONNECTIVITY",
      "SVC-SIP-CARRIER",
      "SVC-CORP-TELEPHONY",
      "SVC-CONTACT-CENTER-INBOUND",
      "SVC-CONTACT-CENTER-OUTBOUND",
      "SVC-IVR-SELFSERVICE",
      "SVC-COMPLIANCE-RECORDING"
    ]
  },
  "causality_scenarios": {
    "scenario_a_single_sbce_failover": {
      "service_id": "SVC-SIP-CARRIER",
      "service_impact": "DEGRADED",
      "causal_classification": "REDUNDANCY_FAILOVER",
      "is_total_outage": false,
      "recommended_action_id": 12,
      "justification": "HA Pair 'SBCE_HA_CLUSTER' member 'avaya-sbce-01' offline. Traffic absorbed by active partner 'avaya-sbce-02'. Service is DEGRADED, NOT a total outage."
    },
    "scenario_b_dual_sbce_exhaustion": {
      "service_id": "SVC-SIP-CARRIER",
      "service_impact": "TOTAL_OUTAGE",
      "causal_classification": "ROOT_CAUSE",
      "is_total_outage": true,
      "recommended_action_id": 10,
      "justification": "CRITICAL REDUNDANCY EXHAUSTION: All members of HA pair 'SBCE_HA_CLUSTER' (avaya-sbce-01, avaya-sbce-02) are down! Immediate total service outage."
    },
    "scenario_c_core_switch_root_cause": {
      "primary_root_cause": {"host": "jkia-core-sw01"},
      "suppressed_symptoms_count": 3
    }
  },
  "zabbix_service_tree_sync": {
    "root_service_id": "2",
    "total_services_in_zabbix": 9
  }
}
```

