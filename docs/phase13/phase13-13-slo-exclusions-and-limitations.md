# Phase 13.13 — SLO Exclusions, Governance & Limitations

## Overview

Under `HARD_PRODUCTION_DENY = True`, Phase 13.13 validates the mathematical algorithms, multi-burn-rate alerting rules, and telemetry integrity guards for Service Level Objectives. The following operational boundaries and governance rules govern production application.

---

## 1. Exclusions from Error Budget Consumption

In accordance with Kenya Airways SRE policy, the following conditions are strictly excluded from consuming service error budgets:

1. **Pre-Scheduled & Approved Maintenance Windows**:
   - Maintenance periods registered in Zabbix (`maintenance.create`) with prior approval from Change Advisory Board (CAB).
   - Maintenance minutes are recorded in `scheduled_maintenance_minutes` and excluded from `outage_minutes`.
2. **Upstream Commercial Power Outages with Generator Transfer**:
   - Grid power drops where standby diesel generators and UPS maintain uninterrupted runtime without operational service disruption.
3. **Declared Force Majeure & Carrier Acts**:
   - Severe physical fiber cuts across international submarine cables where domestic redundant routing remains operational.
4. **Advisory / Stale Replayed Telemetry**:
   - Telemetry marked with `TelemetryQuality.REPLAYED` is excluded from live current health evaluations and error budget tallies.

---

## 2. Invariants & Data Integrity Safeguards

- **No Silent Denominator Shrinkage**: When telemetry is missing or unverified, the missing interval MUST NOT be omitted from the denominator. It must be counted as `unknown_minutes`, lowering the coverage score and reducing availability.
- **Zero Fabrication of 100% Uptime**: When an outstation is disconnected or monitored via simulated fallbacks, the platform must report `COVERAGE_DEFICIT` and refuse to certify 100% compliance.
- **Sentra Repository Isolation**: The adjacent repository (`/Users/madeira/Desktop/Projects/sentra`) remains untouched on `main` at `9970404`.
