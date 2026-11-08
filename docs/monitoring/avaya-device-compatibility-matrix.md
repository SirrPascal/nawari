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
| **Avaya Aura Session Manager (SM)** | `10.2.156.22`<br>`10.2.156.23`<br>`10.2.156.28` (DR) | SIP routing core, SIP entity connectivity, registrar, central dial plan, multi-site routing. | 1. SNMPv3 Agent<br>2. MIB-II / Host Resources<br>3. IF-MIB / TCP-MIB / UDP-MIB<br>4. SM SIP Entity Monitoring<br>5. SM SNMP Traps | - OS health, CPU, memory, uptime<br>- Interface bandwidth, TCP/UDP sockets<br>- SIP Entity States: `UP`, `PARTIALLY UP`, `DOWN`, `DENY NEW SERVICE`<br>- SIP OPTIONS round-trip response time<br>- Enterprise alarms (`avSessionManagerAlarms`) | - SNMPv3: 60s (Low impact)<br>- SIP Entity Mon: 60s (Configurable in SM)<br>- SNMP Traps: Asynchronous | **Documented & Modeled**<br>*(Requires SM MIB download from System Manager)* |
| **Avaya Aura Communication Manager (CM)** | `10.2.156.26` (Pride)<br>`10.2.156.27` (Icolo)<br>`10.2.156.30` (VIP)<br>`10.2.156.50` (DR) | Core call processing, feature server, ACD, vectoring, hunt groups, station/trunk state, dial plan. | 1. SNMPv3 (Enterprise MIB: `1.3.6.1.4.1.6889.2.73`)<br>2. Active Alarms Group<br>3. Call-Rate Group<br>4. IP Voice Stats Tables | - `avCmAlarms` (`.1`): Active alarm conditions<br>- `avCmListMeasCallRateTotal` (`.8.1.1`): Total call attempts & completion rate<br>- `avCmMeasIpVoStatSumDataLstHrTable` (`.8.1.77`): Hourly packet loss %, peak jitter (ms), peak delay (ms), codec, packet size, echo cancel, network region<br>- `avCmMeasIpVoStatHrJitterTable` (`.8.1.66`): Hourly average jitter, calls with high jitter | - Availability: 1m<br>- Call Rate: $\ge \text{5 min}$ (Max frequency)<br>- IP Voice Stats: $\ge \text{1 hour}$ (Strict vendor limit)<br>- Active Alarms: $\ge \text{1 hour}$ (Vendor limit) | **Documented & Modeled**<br>*(Requires 'IP Voice Stats Summary? y' in CM)* |
| **Avaya G450 Media Gateway** | Discovered per site (JKIA, Headquarters, Regional hubs) | Physical media gateway, TDM/PSTN trunk termination (E1/ISDN PRI), DSP media resources, analog stations. | 1. SNMPv2c/v3 Agent<br>2. IF-MIB / Chassis MIB<br>3. CM Gateway Links<br>4. Environmental Sensors | - Appliance reachability, uptime, sysDescr<br>- Media module slots & inventory (MM710, MM711, MM716, MM720)<br>- Physical port & trunk operational state<br>- Ethernet bandwidth, errors, discards<br>- Gateway-to-CM registration state<br>- Power supply, fan status, temperature | - SNMP: 60s (Low impact)<br>- Environmental: 5m<br>- Unconfirmed DSP/channel stats marked **Not collected** | **Documented & Modeled**<br>*(Physical module audit required)* |
| **Avaya CMS** (Call Management System) | Central Contact Centre Cluster | Contact centre reporting, ACD skill/split monitoring, agent performance, queue analytics, historical reporting. | 1. SNMPv3 (OS & Server health)<br>2. Informix ODBC/JDBC (Read-only query interface)<br>3. CMS Supervisor / RT Report API | - Server CPU, RAM, Disk, OS Uptime<br>- Agent Staffing: Logged in, Available, ACD talking, ACW, AUX work<br>- Queue Health: Calls waiting, Oldest call waiting, Calls offered, Calls answered, Abandoned calls, Abandon rate %<br>- Performance: ASA, AHT, Service Level Attainment (% in SLA threshold)<br>- Skill & VDN performance | - Server SNMP: 60s<br>- Informix ODBC: 15m, 30m, or 60m (Matches configured CMS reporting interval)<br>- Direct table writes strictly prohibited | **Architecture Specified**<br>*(Read-only Informix credentials required)* |
| **Recording / WFO Platform** | Enterprise Voice Recording Cluster | Compliance call recording, screen recording, quality monitoring, workforce optimization. | 1. Host Agent / SNMPv3<br>2. Supported Vendor Service API<br>3. Application Health Logs | - Server CPU, RAM, Disk storage, OS uptime<br>- Recording service process availability<br>- Real-time recording ingestion rate<br>- Recording success vs failure count<br>- Active recording buffer / queue depth<br>- Storage partition capacity & retention horizon<br>- Database connectivity & CM CTI link state<br>- Retrieval service health & audit log events | - Host SNMP: 60s<br>- Service API / Logs: 60s–5m<br>- **Strict Boundary:** Audio content is excluded; operational metadata only | **Architecture Specified**<br>*(Exact vendor/product version required)* |
| **Speech / Telephony Analytics Platform** | Central Customer Intelligence Node | Interaction analytics, sentiment analysis, speech-to-text transcript analysis. | 1. Host SNMPv3<br>2. Analytics API / Processing Queue | - Server hardware capacity & uptime<br>- Processing queue depth & audio ingestion lag<br>- Daily transcribed audio volume (hours)<br>- Service health & API response latency | - Host SNMP: 60s<br>- Analytics API: 5m<br>- Does not replace Zabbix, Nawari, or CMS | **Architecture Evaluated**<br>*(Exact vendor identity required)* |

---

## 3. Telemetry Truth & Provenance Classification

To prevent data contamination, every telemetry record processed by Nawari carries an explicit provenance tag:

```
+---------------------------------------------------------------------------------------------------+
|                                 NAWARI PROVENANCE TAXONOMY                                        |
+---------------------------------------------------------------------------------------------------+
|  Tag                      Meaning                                         Example Source          |
|  -----------------------  ----------------------------------------------  ----------------------  |
|  REAL_HARDWARE            Direct physical/virtual appliance telemetry     Avaya SBCE IF-MIB       |
|  REAL_AVAYA_SNMP          Authoritative Avaya enterprise MIB data         Avaya CM IP Voice Table |
|  REAL_ZABBIX_TELEMETRY    Standard Zabbix collector monitoring            Switch ICMP / SNMP      |
|  APPLICATION_DERIVED      Authoritative application interface / database   Avaya CMS Informix ODBC |
|  CORRELATED_ANALYTICS     Nawari cross-domain analytics engine            Call correlation event  |
|  PREDICTIVE_STATISTICAL   Diurnal statistical baseline projection         Rolling Z-score / TTE   |
|  SERVICE_ASSURANCE_SLI    Multi-dimensional business SLI calculation      DCS Availability SLI    |
|  SYNTHETIC_PROBE          Controlled synthetic test transaction           Asterisk AMI call test  |
|  NOT_INSTRUMENTED         Deliberately uncollected / missing telemetry    Real-Call RTCP-XR MOS   |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Polling Safety & Impact Mitigation Rules

Avaya telephony processors are sensitive to excessive SNMP or management queries:
1. **Avaya CM IP Voice Tables (`.8.1.77` & `.8.1.66`):**
   - CM compiles IP voice metrics into 1-hour completed buckets.
   - Polling interval must be set to `delay: 1h` (3600 seconds).
   - More frequent polling causes duplicate reads and exhausts CM call-processing CPU.
2. **Avaya CM Active Alarms (`.1`):**
   - Alarm table traversal on large systems can involve hundreds of entries.
   - Polling interval must not be faster than 1 hour (`delay: 1h`).
3. **Avaya CM Call Rate (`.8.1.1`):**
   - Polling interval must not be faster than 5 minutes (`delay: 5m`).
4. **Avaya CMS Database Queries:**
   - Queries must be executed against historical or interval summary tables (e.g. `dagent`, `hsplit`, `hvdn`) via read-only ODBC accounts.
   - Queries must match the CMS archiving interval (15, 30, or 60 minutes) to avoid locking Informix database engines.

