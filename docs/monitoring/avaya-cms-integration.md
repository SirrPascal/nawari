# Nawari — Avaya Call Management System (CMS) Integration Architecture

**Standard:** Nawari Phase 13.1 Contact Centre Observability  
**Target System:** Avaya CMS (R19 / R20 / R21)  
**Database Engine:** IBM Informix Dynamic Server (IDS)  
**Access Model:** Read-Only ODBC / JDBC Connection over Encrypted TLS  

---

## 1. Role & Architectural Boundaries

Avaya Call Management System (CMS) is the authoritative contact-centre reporting and ACD analytics platform for Kenya Airways customer service, baggage tracing, and ticketing reservation queues.

Unlike network appliances, CMS is an application platform. Its monitoring model is divided into two distinct planes:
1. **Server & OS Health:** Standard infrastructure monitoring via SNMPv3 or host agent (CPU, RAM, disk partitions, Informix database engine process availability).
2. **Contact Centre Business Telemetry:** Read-only data extraction from CMS real-time and historical tables, normalized into Nawari.

```mermaid
flowchart LR
    subgraph CMS["Avaya CMS Server"]
        IDS["IBM Informix Database Engine"]
        Host["Linux / Solaris Host OS"]
    end

    subgraph Nawari["Nawari Observability Engine"]
        SNMP["Zabbix SNMPv3 Agent (Server Health)"]
        ODBC["Nawari CMS Ingestion Adapter (Read-Only ODBC)"]
    end

    subgraph Grafana["Grafana Communication Observability"]
        Dash["Avaya CMS & Contact Centre Dashboard"]
    end

    Host -->|SNMPv3 (60s)| SNMP
    IDS -->|Read-Only ODBC (15m/30m)| ODBC
    SNMP --> Dash
    ODBC --> Dash
```

---

## 2. Supported Contact Centre Telemetry

### 2.1 Agent Performance & State Metrics
- **Logged In Agents (`logged_in`):** Total count of agents logged into ACD skills.
- **Available / Idle Agents (`avail`):** Agents awaiting incoming customer calls.
- **ACD Talking (`acdtalk`):** Agents actively handling incoming queue calls.
- **After Call Work (`acw`):** Agents completing post-call wrap-up work.
- **Auxiliary Work (`aux`):** Agents in non-call work states (e.g., Break, Training, Meal).

### 2.2 Queue & Skill Performance Metrics
- **Calls Offered (`calls_offered`):** Total incoming customer calls routed to the skill group.
- **Calls Answered (`calls_answered`):** Inbound calls successfully connected to an agent.
- **Abandoned Calls (`calls_abandoned`):** Callers who hung up before reaching an agent.
- **Abandonment Rate (`abandon_rate`):** Percentage of offered calls abandoned:
  $$\text{Abandonment Rate} = \frac{\text{Abandoned Calls}}{\text{Calls Offered}} \times 100$$
- **Calls Waiting (`calls_waiting`):** Live count of queued callers currently on hold.
- **Oldest Call Waiting (`oldest_call_waiting`):** Duration (seconds) of the longest-waiting caller currently in queue.
- **Average Speed of Answer (ASA):** Mean wait duration (seconds) before call connection:
  $$\text{ASA} = \frac{\text{Total Queue Answer Time}}{\text{Calls Answered}}$$
- **Average Talk Time (ATT):** Mean conversation duration per connected call.
- **Service Level Attainment (% in SLA):** Proportion of calls answered within Kenya Airways target threshold (e.g. 80% answered within 20 seconds):
  $$\text{Service Level} = \frac{\text{Calls Answered within Threshold}}{\text{Calls Offered}} \times 100$$

### 2.3 Vector Directory Number (VDN) Metrics
- Inbound flow distribution across customer service entry numbers (e.g., Flying Blue, Reservations, Baggage Operations).

---

## 3. Database Access Protocol & Safety Controls

1. **Dedicated Read-Only Account:** Connection must use a restricted Informix database user (e.g. `nawari_ro`) with explicit `SELECT` privileges only on reporting tables.
2. **Encrypted Wire Protocol:** Informix connection must use TLS (`CSL=1`, encrypted connection).
3. **Query Throttling & Reporting Intervals:**
   - Real-time queries must be throttled to prevent locking Informix storage engines.
   - Historical interval aggregations must align with CMS configured interval: **15 minutes, 30 minutes, or 60 minutes**.
   - Nawari preserves the original CMS timestamp (`row_date`, `starttime`, `intv`) without modification.
4. **Zero Media Data:** CMS does not process, inspect, or store RTP voice media packets. CMS metrics reflect call volume, routing outcomes, and agent productivity; they must never be presented as voice audio quality or MOS.

