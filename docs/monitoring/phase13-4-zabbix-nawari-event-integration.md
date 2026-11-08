# Phase 13.4 — Zabbix to Nawari Event Integration & Service Correlation

## 1. Overview

Nawari’s Service Assurance layer consumes monitoring events from Zabbix 7.4 via the `ZabbixProblemConsumer` service (`services/assurance/zabbix_problem_consumer.py`).

Rather than duplicating device-level threshold checks, Nawari treats Zabbix as the single authoritative source of truth for device problem states. Nawari’s unique responsibility is **cross-component service correlation, root-cause attribution, and Aviation Business Service impact modeling**.

---

## 2. Ingestion Mechanics & Idempotency

### Polling Contract
- Uses Zabbix API method `problem.get` with parameters:
  - `output`: `["eventid", "objectid", "name", "severity", "clock", "r_eventid", "r_clock", "acknowledged"]`
  - `selectTags`: `"extend"`
  - `recent`: `True`
- Ingestion is strictly **idempotent**: re-polling the same active Zabbix `eventid` updates existing state without triggering duplicate notifications or creating ghost incident tickets.

### State Transitions & Recovery Tracking
1. **Initial Problem Detection:** Trigger fires in Zabbix -> problem ingested with `r_eventid == "0"` -> mapped to service -> evaluated against active composite incident.
2. **Problem Recovery:** Zabbix sets `r_eventid` and `r_clock` -> Nawari marks underlying problem as recovered. If all underlying problems linked to an incident are recovered, the composite incident automatically transitions to `RESOLVED`.

---

## 3. Aviation Business Service Mapping

Incoming problems are mapped to Aviation Business Services based on host tags and component identifiers:

| Component Tag / Host Prefix | Aviation Business Service ID | Service Name | Operational Scope |
| :--- | :--- | :--- | :--- |
| `sm-core`, `cm-core`, `sbce-core`, `sip-trunk`, `voice-probe` | `SRV-VOICE-CORP` | Corporate Voice Telephony | HQ & Regional Staff Calling, SIP Interconnects |
| `g450-gateway`, `g450-hardware`, `g450-trunk` | `SRV-VOICE-ATC` | Air Traffic / Operations Voice | Airside Operations, Ground Dispatch, E1/PSTN |
| `contact-centre`, `cms-` | `SRV-CONTACT-CENTRE` | Customer Contact Centre | Airline Booking, Baggage Desk, Agent ACD Queues |
| `call-recording`, `wfo-` | `SRV-VOICE-RECORDING` | Compliance Voice Recording | Legal/Regulatory Audio Archival & Quality Monitoring |

---

## 4. Root-Cause Attribution Algorithm

When an upstream core system fails, multiple downstream systems and synthetic probes typically fail concurrently. For example, if **Session Manager** goes down:
- SIP carrier trunks fail their OPTIONS heartbeat to SM.
- Synthetic Asterisk probes fail test calls into SM.
- Contact centre ACD queues cannot route inbound calls.

If each symptom generated an independent priority ticket, the NOC would receive dozens of confusing alarms. 

Nawari's `ZabbixProblemConsumer` applies an authoritative **telephony dependency hierarchy**:

```python
self.telephony_hierarchy = [
    "sm-core",          # Rank 0: Session Manager Core Routing
    "cm-core",          # Rank 1: Communication Manager Call Control
    "sbce-core",        # Rank 2: Perimeter Session Border Controller
    "sip-trunk",        # Rank 3: External Carrier Interconnect
    "g450-gateway",     # Rank 4: Local TDM / Media Gateway
    "voice-probe",      # Rank 5: Downstream Synthetic Test Probe
    "contact-centre",   # Rank 6: Application Layer ACD / CMS
    "call-recording",   # Rank 7: Application Layer Compliance Recorder
]
```

When a new problem is added to a composite incident, Nawari evaluates all underlying problems against this hierarchy. The lowest index (highest rank) is attributed as the `root_cause_candidate`. In the example above, the incident title and notifications identify the **Session Manager failure as the root cause**, suppressing false attribution to the downstream synthetic probe or trunk.

---

## 5. Duplicate Notification Prevention

To avoid conflicting communications:
1. **Device Level:** Zabbix Actions manage email notifications directly to duty engineers with built-in step escalation (30m cooldown repeat) and maintenance suppression.
2. **Service Level:** Nawari only dispatches high-level composite notifications when an entire Aviation Business Service experiences a new degradation state. When duplicate polling occurs, `notification_dispatched` flags guarantee that exactly one notification is delivered.

