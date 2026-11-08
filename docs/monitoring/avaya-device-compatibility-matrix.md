# Nawari — Avaya Multi-Device Observability & Compatibility Matrix

**Standard:** Nawari Phase 13.1 Enterprise Observability  
**Target Environment:** Kenya Airways Telephony Estate & Ground Operations  
**Architecture Boundary:** Zabbix monitors · Grafana visualizes · Nawari correlates and assures services  
**Verification Baseline:** Physical Reference (.131 SBCE), Documented Specifications, and Offline Staging  

---

## 1. Executive Summary & Architectural Policy

Kenya Airways operates a heterogeneous Avaya Aura enterprise telephony estate. The individual systems have fundamentally different operational roles, data planes, and telemetry interfaces. 

### Mandatory Observability Principles
1. **No Uniform Template:** Avaya systems must not receive generic, identical monitoring templates. The SBCE, Session Manager, Communication Manager, G450 Media Gateway, CMS, and Recording/WFO platforms expose completely different telemetry and have distinct operational constraints.
2. **Traceable Truth & Provenance:** Every metric must possess a defined collection method, an authoritative source, a unit, an interpretation, and a freshness guarantee.
3. **Honest Uninstrumented States:** When a metric cannot be collected via a validated interface, Nawari displays `Not available`, `Not collected`, or `N/A`, accompanied by the exact missing dependency. Fabricated zeroes, simulated placeholders, and decorative gauges are strictly prohibited.
4. **Signaling $\neq$ Media Audio Quality:** A successful SIP OPTIONS response or registered SIP trunk establishes layer-5 signaling reachability only. It does not establish call completion, audio media flow, or acceptable voice quality.
5. **Collector Safety & Polling Limits:** Polling frequencies must strictly adhere to vendor-documented limits to protect call-processing CPUs on Avaya hardware.

---

## 2. Comprehensive Avaya Estate Compatibility Matrix

| System Component | Candidate IPs / Targets | Role & Operational Function | Supported Collection Method | Documented Metrics & OIDs / APIs | Polling Frequency & CPU Impact | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Avaya SBCE** (Session Border Controller) | `10.2.156.131` (Pride Ref)<br>`10.2.156.132` (Addl)<br>`10.2.156.45` (DR) | Enterprise SIP perimeter, carrier SIP trunk termination, NAT traversal, topology hiding, media anchoring. | 1. SNMPv3 (USM SHA/AES)<br>2. IF-MIB (64-bit HC)<br>3. Host Resources MIB<br>4. Supported EMS Statistics API / Export | - Appliance CPU, RAM, Disk, Load Avg<br>- Physical interfaces (M1, M2, A1, B1)<br>- Traffic bps, packet errors, discards<br>- EMS: Active SIP calls, registrations (TCP/UDP/TLS), SRTP/RTP counts, direct-media, transcoding, license utilization | - SNMPv3: 30s–60s (Low impact)<br>- EMS Stats: 60s (Low impact)<br>- Dynamic License: 1h (Hourly collected) | **Reference Implemented (.131)**<br>*(.132 & .45 require physical HA audit)* |
| **Avaya Aura Session Manager (SM)** | `10.2.156.22`<br>`10.2.156.23`<br>`10.2.156.28` (DR) | SIP routing core, SIP entity connectivity, registrar, central dial plan, multi-site routing. | 1. SNMPv3 Agent (Host Resources, MIB-II, TCP/UDP sockets)<br>2. Session Manager CLI/API Trapper (Entity states)<br>3. Nawari SIP Probe Engine (Active OPTIONS RTT)<br>4. SM SNMP Traps (AV-TRAP-MIB) | - OS health, CPU, memory, uptime<br>- Interface bandwidth, TCP/UDP sockets<br>- SIP Entity States: `UP`, `PARTIALLY UP`, `DOWN`, `DENY NEW SERVICE` (via API/CLI trapper)<br>- SIP OPTIONS round-trip response time (via Nawari active probe)<br>- Enterprise alarms (via SNMP trap) | - SNMPv3: 60s (Low impact)<br>- SIP Entity Mon: 60s (Configurable in SM)<br>- SNMP Traps: Asynchronous | **Documented & Modeled**<br>*(SIP Entity states require SM CLI/API; not exposed in SNMP)* |
| **Avaya Aura Communication Manager (CM)** | `10.2.156.26` (Pride)<br>`10.2.156.27` (Icolo)<br>`10.2.156.30` (VIP)<br>`10.2.156.50` (DR) | Core call processing, feature server, ACD, vectoring, hunt groups, station/trunk state, dial plan. | 1. SNMPv3 (Enterprise MIB: `1.3.6.1.4.1.6889.2.73`)<br>2. Active Alarms Group (`.8.1.5`)<br>3. Call-Rate Group (`.8.1.145`)<br>4. IP Voice Stats Table (`.8.1.67`) | - `avCmAlarmsTable` (`1.3.6.1.4.1.6889.2.73.8.1.5`): Active alarm conditions<br>- `avCmListMeasCallRateTotalTable` (`1.3.6.1.4.1.6889.2.73.8.1.145`): Hourly measurement block representing total call attempts (`.1.2.1`) & completion rate (`.1.3.1`)<br>- `avCmMeasIpVoStatHrDataTable` (`1.3.6.1.4.1.6889.2.73.8.1.67`, reconciling legacy/draft references to `avCmMeasIpVoStatSumDataLstHrTable` and `avCmMeasIpVoStatHrJitterTable`): Hourly packet loss % (`.10`), peak jitter ms (`.11`), peak delay ms (`.12`), codec (`.8`), echo cancel (`.13`), network region (`.1`) | - Availability: 1m<br>- Call Rate: $\ge \text{5 min}$ polling limit (Hourly block data)<br>- IP Voice Stats: $\ge \text{1 hour}$ (Strict vendor limit; 600s cache)<br>- Active Alarms: $\ge \text{1 hour}$ (Vendor limit) | **Documented & Modeled**<br>*(OIDs audited & aligned with official CM 8.1 MIB .67 branch)* |
| **Avaya G450 Media Gateway** | Discovered per site (JKIA, Headquarters, Regional hubs) | Physical media gateway, TDM/PSTN trunk termination (E1/ISDN PRI), DSP media resources, analog stations. | 1. SNMPv2c/v3 Agent<br>2. IF-MIB / Chassis MIB<br>3. CM Gateway Links<br>4. Environmental Event Traps | - Appliance reachability, uptime, sysDescr<br>- Media module slots & inventory (MM710, MM711, MM716, MM720)<br>- DSP hardware: MP20/MP80 (branch) and MP120/MP160 (high-capacity)<br>- Physical port & trunk operational state<br>- Ethernet bandwidth, errors, discards<br>- Gateway-to-CM registration state<br>- Power supply, fan status<br>- Chassis thermal event state (`0: UNKNOWN`, `1: CLEARED`, `2: WARNING`) via trap events | - SNMP: 60s (Low impact)<br>- Environmental: Event traps + 5m polling<br>- DSP channel utilization strictly gated as **NOT_COLLECTED (Hardware Audit Required)** | **Documented & Modeled**<br>*(Physical module audit required)* |
| **Avaya CMS** (Call Management System) | Central Contact Centre Cluster | Contact centre reporting, ACD skill/split monitoring, agent performance, queue analytics, historical reporting. | 1. SNMPv3 (OS & Server health)<br>2. Informix ODBC/JDBC (Read-only query interface)<br>3. CMS Supervisor / RT Report API | - Server CPU, RAM, Disk, OS Uptime<br>- Agent Staffing: Logged in, Available, ACD talking, ACW, AUX work<br>- Queue Health: Calls waiting, Oldest call waiting, Calls offered, Calls answered, Abandoned calls, Abandon rate %<br>- Performance: ASA, AHT, Service Level Attainment (% in SLA threshold)<br>- Skill & VDN performance | - Server SNMP: 60s<br>- Informix ODBC: 15m, 30m, or 60m (Matches configured CMS reporting interval)<br>- Direct table writes strictly prohibited | **Architecture Specified**<br>*(Read-only Informix credentials required)* |
| **Recording / WFO Platform** | Enterprise Voice Recording Cluster | Compliance call recording, screen recording, quality monitoring, workforce optimization. | 1. Host Agent / SNMPv3<br>2. Supported Vendor Service API<br>3. Application Health Logs | - Server CPU, RAM, Disk storage, OS uptime<br>- Recording service process availability<br>- Real-time recording ingestion rate<br>- Recording success vs failure count<br>- Active recording buffer / queue depth<br>- Storage partition capacity & retention horizon<br>- Database connectivity & CM CTI link state<br>- Retrieval service health & audit log events | - Host SNMP: 60s<br>- Service API / Logs: 60s–5m<br>- **Strict Boundary:** Audio content is excluded; operational metadata only | **Architecture Specified**<br>*(Exact vendor/product version required)* |
| **Speech / Telephony Analytics Platform** | Central Customer Intelligence Node | Interaction analytics, sentiment analysis, speech-to-text transcript analysis. | 1. Host SNMPv3<br>2. Analytics API / Processing Queue | - Server hardware capacity & uptime<br>- Processing queue depth & audio ingestion lag<br>- Daily transcribed audio volume (hours)<br>- Service health & API response latency | - Host SNMP: 60s<br>- Analytics API: 5m<br>- Does not replace Zabbix, Nawari, or CMS | **Architecture Evaluated**<br>*(Exact vendor identity required)* |

---

## 3. Telemetry Truth & Provenance Classification

To prevent data contamination and ensure absolute integrity, every telemetry metric processed by Nawari carries an explicit provenance tag and validation status:

```
+---------------------------------------------------------------------------------------------------+
|                                 NAWARI PROVENANCE TAXONOMY                                        |
+---------------------------------------------------------------------------------------------------+
|  Tag                      Meaning                                         Example Source          |
|  -----------------------  ----------------------------------------------  ----------------------  |
|  REAL_HARDWARE            Direct physical/virtual appliance telemetry     Avaya SBCE IF-MIB       |
|  REAL_AVAYA_SNMP          Authoritative Avaya enterprise MIB data         Avaya CM IP Voice Table |
|  REAL_ZABBIX_TELEMETRY    Standard Zabbix collector monitoring            Switch ICMP / SNMP      |
|  NAWARI_SIP_PROBE         Direct Nawari active SIP OPTIONS transaction    OPTIONS RTT Engine      |
|  APPLICATION_DERIVED      Authoritative application interface / database   Avaya CMS Informix ODBC |
|  CONFIGURED_UNVERIFIED    Configured model awaiting physical live audit   Avaya G450 Environmental|
|  CORRELATED_ANALYTICS     Nawari cross-domain analytics engine            Call correlation event  |
|  PREDICTIVE_STATISTICAL   Diurnal statistical baseline projection         Rolling Z-score / TTE   |
|  SERVICE_ASSURANCE_SLI    Multi-dimensional business SLI calculation      DCS Availability SLI    |
|  SYNTHETIC_PROBE          Controlled synthetic test transaction           Asterisk AMI call test  |
|  NOT_INSTRUMENTED         Deliberately uncollected / missing telemetry    Real-Call RTCP-XR MOS   |
+---------------------------------------------------------------------------------------------------+
```

### Formal Metric Validation Statuses (Phase 13.2 Standard)
1. **`VERIFIED_LIVE`**: Confirmed against active physical device telemetry streaming in production.
2. **`VERIFIED_INTEGRATION`**: Source interface and ingestion tested and verified in non-production simulation/staging environment.
3. **`CONFIGURED_UNVERIFIED`**: Schema, template, or integration path configured, but source data awaiting physical device commissioning.
4. **`SIMULATED`**: Generated by internal simulation harnesses or synthetic test engines (e.g. Asterisk AMI probe calls).
5. **`NOT_COLLECTED`**: Deliberately gated or unimplemented collection path (e.g. G450 DSP channel allocation without physical module audit).
6. **`UNSUPPORTED`**: Source platform does not expose the required metric through the investigated interface.
7. **`STALE`**: Telemetry exists but observation timestamp exceeds freshness ceiling.

---

## 4. Polling Safety & Impact Mitigation Rules

Avaya telephony processors are sensitive to excessive SNMP or management queries:
1. **Avaya CM IP Voice Table (`1.3.6.1.4.1.6889.2.73.8.1.67`):**
   - CM compiles IP voice metrics into 1-hour completed buckets (`avCmMeasIpVoStatHrData`, corresponding to SAT `list measurements ip voice-stats hourly data`).
   - Caching interval is 600s, and the polling interval must be set to `delay: 1h` (3600 seconds).
   - More frequent polling causes duplicate reads and exhausts CM call-processing CPU. Legacy references to tables under `.77` and `.66` are reconciled under this authoritative branch.
2. **Avaya CM Active Alarms (`1.3.6.1.4.1.6889.2.73.8.1.5`):**
   - Alarm table traversal on large systems can involve hundreds of entries.
   - Polling interval must not be faster than 1 hour (`delay: 1h`).
3. **Avaya CM Call Rate (`1.3.6.1.4.1.6889.2.73.8.1.145`):**
   - Metric represents hourly measurement blocks from SAT `list measurements call-rate total`.
   - Polling interval must not be faster than 5 minutes (`delay: 5m`). The 5m constraint is a query rate ceiling to protect CM processing, not a rolling 5-minute counter. Attempts is not exposed as a rolling 5m counter.
4. **Avaya G450 Environmental & DSP Management:**
   - Chassis thermal status is derived from trap events (`temperatureWarning` / `temperatureClear`), modeled as discrete states: `0: UNKNOWN`, `1: CLEARED`, `2: WARNING`. G450 does not expose a continuous analog thermometer or a separate "Critical" trap state.
   - DSP hardware architecture distinguishes branch modules (MP20 / MP80) from high-capacity appliances (MP120 / MP160). Real-time DSP channel utilization is strictly gated as `NOT_COLLECTED (Hardware Audit Required)` until physical verification.
5. **Avaya CMS Database Queries:**
   - Queries must be executed against historical or interval summary tables (e.g. `dagent`, `hsplit`, `hvdn`) via read-only ODBC accounts.
   - Queries must match the CMS archiving interval (15, 30, or 60 minutes) to avoid locking Informix database engines.

