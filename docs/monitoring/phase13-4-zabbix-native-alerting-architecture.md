# Phase 13.4 — Zabbix-Native Alerting and Correlation Architecture

## 1. Executive Summary

In Nawari Phase 13.4, the telemetry and alerting architecture has been formally realigned to establish **Zabbix 7.4 as the authoritative device-level monitoring, trigger evaluation, and event-generation engine**. 

Previously, during Phase 13.3, a standalone 45-rule Python alerting engine was authored to define the detection thresholds and severity models for Avaya communication infrastructure. In Phase 13.4, all 45 communication alert rules have been translated into native Zabbix 7.4 templates, items, triggers, and action workflows. The Python alert engine has been permanently decoupled from operational alerting and retired to a passive, backward-compatible reference and testing harness (`PASSIVE_MIGRATED_TO_ZABBIX`).

Higher-level service assurance, cross-component root-cause attribution, and Aviation Business Service impact mapping are now performed by Nawari's `ZabbixProblemConsumer` service via Zabbix's native `problem.get` / `event.get` APIs.

---

## 2. Architectural Separation of Responsibilities

The monitoring stack strictly separates raw telemetry collection, device-level alerting, notification delivery, and composite business service correlation:

```mermaid
flowchart TD
    subgraph Data Sources
        S1["Avaya SBCE (SNMP / Syslog)"]
        S2["Avaya SM (SNMP / Management API)"]
        S3["Avaya CM (SNMP / RTCP-XR / MIB-II)"]
        S4["Avaya G450 (SNMP / Syslog)"]
        S5["SIP Carrier Trunks (ICMP / SIP OPTIONS)"]
        S6["Synthetic Voice Probes (Asterisk SIP/AMI)"]
        S7["CMS & WFO (REST API / Disk Spool)"]
    end

    subgraph "Authoritative Alerting Engine: Zabbix 7.4"
        Z1["Zabbix Poller / Trapper"]
        Z2["45 Native Communication Triggers\n(Templates: SBCE, SM, CM, G450, SIP, Voice, CMS)"]
        Z3["Zabbix Event Engine\n(Problem / Recovery / Escalation)"]
        Z4["Zabbix Actions & Media Types\n(Office 365 SMTP / OAuth Script)"]
    end

    subgraph "Service Assurance: Nawari Platform"
        N1["Zabbix Problem Consumer\n(Idempotent polling via problem.get)"]
        N2["Aviation Service Correlation Engine\n(SRV-VOICE-CORP, SRV-VOICE-ATC, etc.)"]
        N3["Hierarchy Root-Cause Analysis\n(SM/CM Core > Gateway > Synthetic Probe)"]
        N4["Composite Incident Lifecycle"]
    end

    subgraph Notifications & Visualization
        M365["Microsoft 365 Exchange Online\n(Duty Engineer Notifications)"]
        Grafana["Grafana Dashboards\n(Network & Communication Observability)"]
    end

    Data Sources --> Z1
    Z1 --> Z2
    Z2 --> Z3
    Z3 -->|Step Escalation / Repeat 1800s| Z4
    Z4 --> M365
    Z3 -->|API Ingestion: problem.get| N1
    N1 --> N2
    N2 --> N3
    N3 --> N4
    Z1 -.->|Metrics| Grafana
    N4 -.->|Composite Status| Grafana
```

### Responsibility Matrix

| Capability / Function | Responsible Layer | Implementation Mechanism |
| :--- | :--- | :--- |
| **Metric Ingestion & Polling** | Zabbix 7.4 Server / Proxies | SNMPv2c/v3, ICMP ping, HTTP agent, Syslog trappers |
| **Threshold & Trigger Evaluation** | Zabbix 7.4 Trigger Engine | Native template expressions with hysteresis (`nodata()`, `last()`, `min()`) |
| **Device Problem & Recovery Generation** | Zabbix 7.4 Event Engine | State transitions with correlation tags (`scope`, `component`, `device_role`) |
| **Step Escalation & Deduplication** | Zabbix 7.4 Actions | Step duration: 1800s (30m cooldown repeat); suppression during maintenance |
| **Email Notification Dispatch** | Zabbix 7.4 Media Types | Office365 SMTP (Port 587 STARTTLS) and Modern Auth OAuth 2.0 AlertScript |
| **Aviation Business Service Mapping** | Nawari Service Assurance | `ZabbixProblemConsumer` tags-to-service routing |
| **Cross-Component Root-Cause Analysis**| Nawari Service Assurance | Dependency hierarchy ranking (e.g. Session Manager failure suppresses trunk symptom false alarms) |
| **Single-Pane Observability** | Grafana Dashboards | Read-only separation: `Network Observability` vs `Communication Observability` |

---

## 3. Python Alert Engine Decoupling

In Phase 13.3, `CommunicationAlertEngine` evaluated mock telemetries via Python dictionaries. Having two parallel alerting engines would risk:
1. **Split-brain alert states:** Discrepancies between Python evaluation and Zabbix trigger states.
2. **Notification storm:** Duplicate emails dispatched to on-call duty engineers.
3. **Operational overhead:** Maintaining alert logic in both YAML and Python.

### Decommissioning Implementation
In `services/alerting/communication_alert_engine.py`:
- `OPERATIONAL_MODE` has been set to `"PASSIVE_MIGRATED_TO_ZABBIX"`.
- The engine logs explicit deprecation notices if instantiated.
- The 45 rule dictionaries and threshold constants are retained strictly as the specification fixture and test contract.

---

## 4. Anti-Duplicate Notification & Correlation Protocol

To ensure operators are not flooded with redundant emails:
1. **Device-Level Alerts:** Dispatched strictly by Zabbix 7.4 Actions. Every trigger event carries tags: `scope=availability/performance`, `component=<subsystem>`, `host=<hostname>`.
2. **Composite Incidents:** Handled by Nawari's `ZabbixProblemConsumer`. When multiple triggers fire concurrently (e.g., Session Manager host unreachable + SIP trunk OPTIONS timeout + Asterisk synthetic call failure), Nawari groups them into a single `CompositeServiceIncident` associated with the impacted Aviation Business Service (e.g., `SRV-VOICE-CORP`).
3. **Underlying Zabbix Event IDs:** Preserved in the composite incident record (`underlying_problems`), maintaining full auditability back to Zabbix.

