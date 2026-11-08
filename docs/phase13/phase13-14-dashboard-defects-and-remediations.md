# Phase 13.14 — Dashboard Defects & Remediations Log

## Audit Findings & Remediations

During the Phase 13.14 operational acceptance audit, several structural, naming, and variable issues from earlier prototyping phases were audited and remediated.

---

## 1. Defects Identified & Resolved

| Defect ID | Component / Dashboard | Symptom / Issue | Root Cause | Remediation Applied |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-DASH-01** | `docker/grafana/dashboards` root | Legacy flat dashboard files coexisted with folder-nested files. | Prototyping duplication during Phase 13 restructuring. | Validated folder isolation: `communication_observability` and `network_observability` established as sole authoritative discovery paths. |
| **DEF-DASH-02** | `interface_traffic_health.json` | Interface rate calculation previously lacked explicit 64-bit HC multiplier documentation. | Brief description omitting `bps` conversion formula. | Added explicit documentation: `(delta * 8) / dt` standardizing bits per second representation. |
| **DEF-DASH-03** | `nawari-voice-service-assurance.json` | Unidirectional voice calls previously threatened to render partial MOS scores. | Prototyping code allowed estimation without RTCP receiver reports. | Enforced Missing-Media Guard: Unidirectional streams strictly return `(None, None)` and render as `UNVERIFIED_MEDIA`. |
| **DEF-DASH-04** | `nawari_service_catalog_sla.json` | Missing telemetry previously risk-tagged as 100% uptime in basic queries. | Simple availability queries dividing by good + outage only. | Fixed query logic: denominator includes `unknown_minutes`, causing missing intervals to penalize availability. |

---

## 2. Invariants Preserved

1. **Strict Zero External Platform Branding in Notifications**: While internal operational dashboards display engineering titles, all recipient-facing notifications strictly omit "Nawari", "Zabbix", and "Grafana".
2. **Hard Production Isolation**: Staging and containerized environments were read-only audited; zero live production network devices were modified.
3. **Sentra Repository Untouched**: The adjacent repository (`/Users/madeira/Desktop/Projects/sentra`) remains clean on `main` at `9970404`.
