# Nawari Phase 10 Master Technical Specification
## Advanced Communications Intelligence & Voice Service Assurance

**Document Version:** 1.0.0  
**Status:** Approved Master Architecture Specification  
**Date:** 2026-11-08  
**Baseline Commit:** [`0a3de05`](file:///Users/madeira/Desktop/Projects/nawari) (Phase 9 Complete, 235 Passing Tests)  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPUs, 7.8 GiB RAM) & Kenya Airways Enterprise Voice Infrastructure  
**Core Architectural Directive:**  
> *"Zabbix monitors. Grafana visualizes. Nawari discovers topology, correlates cross-domain evidence, and assures services. Asterisk provides controlled synthetic voice testing in a separately gated deployment profile."*

---

## 1. Executive Summary & Problem Statement

Across Phases 1 through 9, Nawari evolved from a device-centric infrastructure monitoring stack into an enterprise service assurance platform with dynamic Layer 2/Layer 3 topological awareness. 

However, existing voice observability remains largely **coarse-grained**:
* Zabbix tracks high-level Avaya SBCE MIB counters (e.g. `avSbceActiveSessions`, `avSbceMediaUtilization`).
* The synthetic Asterisk runner measures coarse end-to-end call metrics (setup time, answer state, average RTCP jitter and loss).
* When a call experiences high latency, one-way audio, or a call setup failure, Nawari cannot dissect the **internal phases of the signaling handshake** or the **micro-burst behavior of the voice media stream**:
  1. Did a 4-second delay occur during DNS SRV lookup, initial `INVITE` proxy routing, Avaya digest authentication, or station alerting?
  2. Was a SIP `480 Temporarily Unavailable` caused by an Avaya Session Manager trunk failure or simply an off-shift deskphone?
  3. Was audio distortion caused by transit network packet drops or endpoint jitter-buffer discards?
  4. Was a call routed over the cost-effective primary SIP trunk or an expensive secondary carrier route?
  5. Which exact physical switches, trunk interfaces, and SBC ports in the Phase 9 topology carried the degraded voice call?

**Phase 10 delivers Communications Intelligence.** It provides deep protocol transaction modeling, transaction state machines, RFC 3611 RTCP-XR VoIP metrics analysis, Avaya Aura platform models, Kenya Airways dialed number plan assurance, and tight integration with the Phase 9 topological dependency graph.

```
+----------------------------------------------------------------------------------------------------+
|                                    NAWARI PHASE 10 PIPELINE                                        |
|                                                                                                    |
|  [ Multi-Source Telemetry Ingestion ]                                                              |
|         │                                                                                          |
|         ├─► SIP Signaling Transactions (RFC 3261: INVITE, 180, 200, ACK, BYE, CANCEL, PRACK)      |
|         ├─► Asterisk 22 AMI & Channel Lifecycle Events (Uniqueid, Linkedid, DialBegin, Hangup)     |
|         ├─► RTCP & RTCP-XR (RFC 3611 VoIP Metrics: Burst/Gap Loss, Discards, Delay, Signal)       |
|         ├─► Avaya SBCE 8.1 & Session Manager 8.1.3 Telemetry (SNMP MIBs, Status, Reason Headers)   |
|         └─► Phase 9 Topology Graph & Change Events (Physical switches, links, interfaces)          |
|                     │                                                                              |
|                     ▼                                                                              |
|  [ 10A: SIP Transaction Intelligence ]                                                             |
|         │  - Full RFC 3261 client & server transaction state machines                              |
|         │  - Phase-by-phase latency dissection: PDD (Post-Dial Delay), Alerting, Answer, Teardown  |
|         │  - Chronological SIP Call-Flow Ladder generation                                         |
|         ▼                                                                                          |
|  [ 10B: Call Lifecycle & Cause Code Translation ]                                                  |
|         │  - Multi-leg correlation: SIP Call-ID <-> Asterisk Uniqueid <-> Avaya Session ID         |
|         │  - ITU-T Q.850 & SIP response code translation (RFC 3326 Reason header parser)           |
|         │  - PII masking: E.164 and customer extension digit sanitization                          |
|         ▼                                                                                          |
|  [ 10C: RTP/RTCP & RTCP-XR Media Intelligence ]                                                    |
|         │  - RFC 3611 VoIP Metrics: Burst density/duration, gap density/duration                   |
|         │  - Loss classification: Network packet drop vs Jitter buffer discard                     |
|         │  - Defensible ITU-T G.107 E-model Extended MOS Calculation (Strict Invariant Guards)     |
|         ▼                                                                                          |
|  [ 10D: Avaya Aura Platform Intelligence ]                                                         |
|         │  - SBCE 8.1, Session Manager 8.1.3, and Communication Manager service models             |
|         │  - Differentiation: Station State (480/486) vs Trunk Infrastructure Outage (503/504)    |
|         ▼                                                                                          |
|  [ 10E: Dial Plan & Routing Assurance ]                                                            |
|         │  - Kenya Airways numbering plan validation (HQ 1xxx, JKIA 2xxx, Outstations 4xxx)        |
|         │  - Carrier route group assurance (Primary Safaricom -> Secondary Airtel -> ISDN)         |
|         │  - Strict cryptographic blocking of emergency numbers (999/112/911)                      |
|         ▼                                                                                          |
|  [ 10F: Voice Service Dependency Correlation (Topological Linkage) ]                               |
|         │  - Maps SIP dialog legs to physical switches, ports, and SBCs via Phase 9 Topology Graph |
|         │  - Correlates voice quality degradations with physical link state changes & flaps        |
|         ▼                                                                                          |
|  [ 10G/10H: Dashboards & Consolidated Acceptance ]                                                 |
|            - Provisioned Grafana dashboard: nawari_voice_intelligence.json                         |
|            - 235 existing tests preserved + Phase 10 test suite (100% pass rate)                   |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Principles & Invariants

### Invariant 1: No Unauthorised Packet Sniffing or Raw Audio Capture
* Zero promiscuous raw packet captures (`tcpdump`, `pcap`) on physical production networks without prior change authorization.
* Zero storage or recording of voice audio payloads. All media intelligence is derived strictly from **in-flight protocol headers, Asterisk AMI/RTCP telemetry, and RTCP-XR control reports**.

### Invariant 2: Strict Privacy & Call Metadata Masking
* Telephone numbers, customer dialed digits, and personal identities must be sanitized at collection time:
  $$\text{E.164 } +254\,712\,345\,678 \longrightarrow +254\,7**\,***\,678$$
  $$\text{Internal Extension } 4286 \longrightarrow 4286 \text{ (allowlisted diagnostic extension only)}$$
* Unallowlisted extension digits in synthetic or passive logs are redacted prior to persistence or visualization.

### Invariant 3: Defensible Media Quality & MOS Calculation Guards
* `estimated_mos` and `r_factor` must **NEVER** be fabricated, assumed, or calculated from partial evidence:
  - If RTCP Sender/Receiver Reports or RTCP-XR metrics blocks are missing, `estimated_mos` MUST be `None`, and `is_valid` MUST be `False`.
  - SIP `200 OK` indicates signaling completion only; it must **never** be interpreted as proof of successful bidirectional speech delivery.
  - SIP `OPTIONS` responses confirm trunk reachability; they do **not** verify end-to-end voice quality or codec negotiation.

### Invariant 4: Controlled, Gated Synthetic Voice Testing
* Synthetic calls remain strictly gated:
  1. Cryptographic blocking of emergency numbers (`999`, `112`, `911`).
  2. Strict allowlisting against `voice_destination_allowlist.json`.
  3. Bounded call duration ($\le 15\text{s}$) and mandatory cool-down delays ($\ge 30\text{s}$).
  4. Automatic circuit breaker trip after consecutive failures.

### Invariant 5: Resource Budget & Host VM Protection
* The production VM (`mon-grafana01`) is constrained to **2 vCPUs and 7.8 GiB RAM**.
* Total container memory footprint across all services must remain $\le 2.2\text{ GiB}$.
* Do **not** introduce external message brokers (e.g. Kafka, RabbitMQ) or new databases. All state and session intelligence are stored natively in PostgreSQL and bounded in-memory ring buffers.

### Invariant 6: Sentra Repository Isolation & Clean Baseline
* Work is executed strictly within `nawari/`.
* The `sentra/` repository remains 100% clean and untouched.
* All 235 existing tests across Phases 1–9 must remain passing with zero regressions.

---

## 3. Detailed Component Architecture & Workstream Specifications

### Workstream 10A: SIP Transaction Intelligence & Call-Flow Ladders
Located in `services/voice/sip/`:
* **RFC 3261 Protocol Parser:**
  - Efficient, streaming parser for SIP request lines, status lines, and mandatory headers (`Via`, `From`, `To`, `Call-ID`, `CSeq`, `Contact`, `Max-Forwards`, `Content-Type`, `Content-Length`).
  - Supports RFC 3326 `Reason` headers, RFC 3262 `PRACK` / `100rel`, and `Warning` headers.
* **Transaction State Machine:**
  - Client Transaction: `CALLING` $\to$ `PROCEEDING` $\to$ `COMPLETED` $\to$ `TERMINATED`.
  - Server Transaction: `TRYING` $\to$ `PROCEEDING` $\to$ `COMPLETED` $\to$ `CONFIRMED` $\to$ `TERMINATED`.
  - Tracks transaction timeouts (Timer A, Timer B, Timer F) and retransmissions.
* **Phase-by-Phase Signaling Latency Dissection:**
  - **Post-Dial Delay (PDD):** $T_{\text{first 18x Ringing / Session Progress}} - T_{\text{initial INVITE}}$
  - **Time to Alerting (TTA):** $T_{180\text{ Ringing}} - T_{\text{initial INVITE}}$
  - **Time to Answer (TTOA):** $T_{200\text{ OK}} - T_{180\text{ Ringing}}$
  - **Teardown Duration:** $T_{200\text{ OK (to BYE)}} - T_{\text{initial BYE}}$
  - **Total Session Duration:** $T_{\text{BYE}} - T_{200\text{ OK (to INVITE)}}$
* **Visual Call-Flow Ladder Generator:**
  - Produces structured chronological event ladders:
    $$\text{Asterisk} \xrightarrow{\text{INVITE}} \text{Avaya SBCE} \xrightarrow{\text{100 Trying}} \text{Session Manager} \xrightarrow{\text{180 Ringing}} \text{Endpoint}$$
  - Formats data for interactive Grafana sequence/ladder visual panels.

---

### Workstream 10B: Call Lifecycle & Multi-Leg Correlation
Located in `services/voice/correlation/`:
* **Multi-Leg Session Identifier:**
  - In enterprise environments, an end-to-end call traverses multiple legs:
    $$\text{Leg 1 (Endpoint } \to \text{ CM)} \longleftrightarrow \text{Leg 2 (CM } \to \text{ SM)} \longleftrightarrow \text{Leg 3 (SM } \to \text{ SBCE)} \longleftrightarrow \text{Leg 4 (SBCE } \to \text{ Carrier)}$$
  - Correlates heterogeneous identifiers into a single `CallSession`:
    - SIP `Call-ID` (header)
    - Asterisk `Uniqueid` / `Linkedid` (AMI events)
    - Avaya Session Manager Session ID / Global Call ID (`X-Avaya-Session-ID`)
    - Avaya SBCE Session Index
* **Cause Code & Reason Header Translator:**
  - Translates ITU-T Q.850 release cause codes to clear diagnostic explanations:
    - `Cause 1`: Unallocated (unassigned) number $\to$ Dial plan configuration defect.
    - `Cause 16`: Normal call clearing $\to$ Expected subscriber hangup.
    - `Cause 17`: User busy $\to$ Station occupied (not an infrastructure failure).
    - `Cause 18`: No user responding $\to$ Destination alerting, unanswered.
    - `Cause 19`: No answer from user (user alerted) $\to$ Station ring timeout.
    - `Cause 34`: No circuit/channel available $\to$ SIP trunk or B-channel congestion.
    - `Cause 41`: Temporary failure $\to$ Network routing or proxy failure.
    - `Cause 47`: Resource unavailable $\to$ DSP, media transcoding, or license exhaustion.
    - `Cause 111`: Protocol error, unspecified.
  - Translates Avaya Session Manager diagnostic warnings (e.g. `Warning: 399 SM "User not registered"`).
* **PII & Data Protection Guard:**
  - Sanitizes user and dialed numbers before logging or database persistence.

---

### Workstream 10C: RTP/RTCP & RTCP-XR Media Intelligence
Located in `services/voice/rtp/`:
* **RFC 3611 RTCP-XR VoIP Metrics Block Analyzer:**
  - Extends standard RTCP Sender/Receiver Reports (RFC 3550) with extended report blocks:
    1. **Burst / Gap Loss Model:**
       - Burst Density: Fraction of packets lost/discarded during burst periods.
       - Burst Duration: Average duration of loss bursts in milliseconds.
       - Gap Density: Fraction of packets lost during gap periods.
       - Gap Duration: Average duration of low-loss gaps.
    2. **Loss vs Jitter-Buffer Discard Breakdown:**
       - Distinguishes **network packet loss** (transit network drops, CRC errors, fiber micro-bends) from **jitter buffer discards** (packets arriving too late due to transit jitter).
    3. **Delay Metrics:**
       - Round-Trip Time (RTT), One-Way Network Delay, End System Delay (codec algorithm + buffering delay).
    4. **Signal & Acoustic Quality:**
       - Signal Level, Noise Level, Residual Echo Return Loss (RERL).
* **ITU-T G.107 E-Model Extended MOS Calculation:**
  - Comprehensive transmission rating factor computation:
    $$R = R_0 - I_s - I_d - I_{e,\text{eff}} + A$$
    Where:
    - $R_0 = 93.2$ (Basic signal-to-noise ratio)
    - $I_s$: Simultaneous impairment factor (quantization, loudness)
    - $I_d$: Delay impairment factor (RTT $> 150\text{ ms}$ penalty)
    - $I_{e,\text{eff}}$: Effective equipment impairment factor based on codec (G.711, G.729a, Opus) and burst loss probability
    - $A$: Advantage / expectation factor ($A = 0$ for wireline/VoIP, $A = 5$ for cellular)
  - Mathematical MOS conversion:
    $$\text{MOS} = 1.0 + 0.035 R + R(R - 60)(100 - R) \times 7 \times 10^{-6} \quad (1.0 \le \text{MOS} \le 4.5)$$
* **SDP Offer/Answer Inspector (RFC 3264 / RFC 4566):**
  - Parses media lines (`m=audio <port> RTP/AVP <codecs>`).
  - Detects codec mismatches between offered and answered profiles.
  - Identifies packetization interval discrepancies (e.g. `a=ptime:20` vs `a=ptime:30`).
  - Flags asymmetric RTP media routing.

---

### Workstream 10D: Avaya Aura Platform Intelligence & Service Models
Located in `services/voice/avaya/`:
* **Avaya SBCE 8.1 Service Model:**
  - Telemetry: Active SIP sessions, media channel capacity, TLS encryption status, license concurrency.
  - Fault Signature Mapping: SBCE CPU spikes, license limits reached, cryptographic handshakes rejected.
* **Avaya Session Manager (SM) 8.1.3 Model:**
  - SIP Entity Link state tracking (TLS connections to SBCE, CM, and Asterisk).
  - Routing policy evaluation: detects route group failover and denial rates.
  - Categorization: Strict differentiation between **Station State** (`480 User not registered`, `486 Busy`) and **Infrastructure Failure** (`500 Internal`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`).
* **Avaya Communication Manager (CM) 8.1/10.1 Model:**
  - Trunk group utilization (IP-SIP, ISDN PRI tie-lines).
  - Call Admission Control (CAC) bandwidth ceiling alerts.

---

### Workstream 10E: Kenya Airways Dial Plan & Routing Assurance
Located in `services/voice/dialplan/`:
* **Kenya Airways Enterprise Numbering Plan:**
  - Internal 4-digit Pride Centre HQ extensions: `1000`–`1999`.
  - Internal 4-digit JKIA Terminal 1A operations: `2000`–`2999`.
  - Regional & domestic airport outstations: `4000`–`4999` (e.g. MBA Mombasa, KIS Kisumu, EDL Eldoret).
  - Flight dispatch and crew briefing hunt groups: `3000`–`3999`.
* **National & International E.164 Normalization:**
  - Normalizes Kenyan destination numbers (`0712345678` $\to$ `+254712345678`).
  - Identifies mobile network operators: Safaricom (`+254 7[0-2,9]`), Airtel (`+254 7[3,5,8]`), Telkom (`+254 77`).
* **Carrier Trunk Route Selection Assurance:**
  - Verifies outbound routing preference:
    $$\text{Primary: Safaricom Direct SIP Trunk} \longrightarrow \text{Secondary: Airtel SIP Trunk} \longrightarrow \text{Tertiary: Telkom ISDN PRI}$$
  - Detects suboptimal carrier trunk fallback (e.g. primary trunk silent failure forcing calls to secondary route).
* **Destination Safety Policy Enforcement:**
  - Cryptographic verification that emergency numbers (`999`, `112`, `911`) and premium rate numbers can never be dialed by automated test probes.

---

### Workstream 10F: Voice Service Dependency Correlation (Topological Linkage)
Located in `services/voice/topology_link.py` & `services/assurance/correlator.py`:
* **Path Dissection across Phase 9 Topology:**
  - Connects SIP signaling dialogs and RTP streams to the underlying physical switching and routing graph constructed in Phase 9:
    $$\text{Asterisk Container} \xrightarrow{\text{veth}} \text{Host Switch} \xrightarrow{\text{Trunk}} \text{Cisco Cat9500 (Te1/0/10)} \xrightarrow{\text{Port}} \text{Avaya SBCE (eth0)}$$
* **Root-Cause Disambiguation:**
  - When an endpoint or voice probe observes high jitter or packet loss:
    1. Query Phase 9 `TopologyGraph.get_upstream_path()` for traversed switches and interfaces.
    2. Check `topology_changes` for recent events (`LINK_DOWN`, `UPLINK_FLAP`, `SPEED_CHANGED`).
    3. If an upstream trunk flapped within 900 seconds of an observed RTCP-XR loss burst, synthesize a `CONFIRMED` hypothesis citing the exact physical port and transceiver.

---

### Workstream 10G: Voice Intelligence Dashboards & Visualizations
Located in `docker/grafana/dashboards/nawari_voice_intelligence.json`:
* **Provisioned Grafana Dashboard Panels:**
  1. **SIP Call-Flow Ladder View:** Visual sequence diagram showing phase-by-phase SIP requests, provisional responses, and answer times.
  2. **Signaling Latency Breakdown:** Time-series charts comparing Post-Dial Delay (PDD), Alerting time, and Time to Answer (TTA).
  3. **RTP vs RTCP-XR Media Quality:** Loss burst duration vs gap duration; jitter buffer discard rate vs network drop rate.
  4. **Q.850 & SIP Response Distribution:** Multi-tier breakdown separating normal station states (`180`, `480`, `486`) from true trunk failures (`500`, `503`).
  5. **Carrier Trunk Utilization & Route Selection:** Real-time active channels on Safaricom vs Airtel SIP trunks.
  6. **Topological Hop Health:** Status of physical switch interfaces carrying the voice media path.

---

### Workstream 10H: Consolidated Acceptance & Test Matrix
Located in `scripts/verify_phase10.sh` and `tests/`:
* **Comprehensive Test Suite:**
  - `tests/unit/test_sip_transaction_engine.py`: Parser, state machine, timers, ladder generation.
  - `tests/unit/test_call_lifecycle_correlation.py`: Multi-leg correlation, Q.850 cause codes, PII masking.
  - `tests/unit/test_rtcp_xr_analyzer.py`: RFC 3611 metrics, burst/gap model, extended E-model MOS, SDP inspector.
  - `tests/unit/test_avaya_platform_model.py`: SBCE, Session Manager, Communication Manager service models.
  - `tests/unit/test_dialplan_assurance.py`: Kenya Airways numbering plan, E.164 normalization, carrier routing.
  - `tests/integration/test_voice_topology_assurance.py`: End-to-end voice degradation correlation with Phase 9 topology graph.
* **Regression Guarantee:**
  - 100% pass rate across all 235 existing tests + all new Phase 10 tests ($\ge 265$ total tests).

---

## 4. Modular Directory Layout

```
nawari/
├── services/
│   └── voice/
│       ├── __init__.py
│       ├── models.py                     # Enhanced with Phase 10 models
│       ├── sip/
│       │   ├── __init__.py
│       │   ├── parser.py                 # RFC 3261 streaming SIP message parser
│       │   ├── state_machine.py          # Client/Server transaction state machine
│       │   └── ladder.py                 # Chronological call-flow ladder builder
│       ├── correlation/
│       │   ├── __init__.py
│       │   ├── session_correlator.py     # Multi-leg Call-ID / Uniqueid / Avaya resolver
│       │   ├── cause_codes.py            # Q.850 & Reason header translation dictionary
│       │   └── privacy.py                # PII masking & dialed digit sanitization
│       ├── rtp/
│       │   ├── __init__.py
│       │   ├── rtcp_xr_analyzer.py       # RFC 3611 VoIP Metrics & burst/gap analyzer
│       │   ├── sdp_inspector.py          # RFC 3264/4566 codec & ptime negotiator
│       │   └── extended_emodel.py        # ITU-T G.107 Extended MOS engine
│       ├── avaya/
│       │   ├── __init__.py
│       │   ├── sbce_model.py             # Avaya SBCE 8.1 operational model
│       │   └── session_manager.py        # Avaya Session Manager 8.1.3 model
│       ├── dialplan/
│       │   ├── __init__.py
│       │   ├── number_plan.py            # Kenya Airways extension & E.164 normalizer
│       │   └── routing_assurance.py      # Carrier trunk route validator & safety checks
│       └── topology_link.py              # Bridges Phase 10 Voice with Phase 9 Topology
├── docker/
│   └── grafana/
│       └── dashboards/
│           └── nawari_voice_intelligence.json # Grafana Voice Intelligence Dashboard
├── scripts/
│   └── verify_phase10.sh                 # Consolidated Phase 10 verification script
└── tests/
    ├── unit/
    │   ├── test_sip_transaction_engine.py
    │   ├── test_call_lifecycle_correlation.py
    │   ├── test_rtcp_xr_analyzer.py
    │   ├── test_avaya_platform_model.py
    │   └── test_dialplan_assurance.py
    └── integration/
        └── test_voice_topology_assurance.py
```

---

## 5. Testable Implementation Roadmap & Stage Sequencing

| Stage | Focus Area | Deliverables | Verification Target |
| :---: | :--- | :--- | :--- |
| **10A** | **SIP Transaction Intelligence** | `services/voice/sip/` (parser, state machine, latency dissection, ladders) | Unit tests verifying transaction state transitions, PDD calculations, and ladder JSON. |
| **10B** | **Call Lifecycle & Q.850 Translation**| `services/voice/correlation/` (multi-leg resolver, Q.850 translator, privacy masking) | Unit tests verifying multi-leg mapping, cause code translation, and PII redaction. |
| **10C** | **RTCP-XR & Media Intelligence** | `services/voice/rtp/` (RFC 3611 analyzer, burst/gap model, extended MOS, SDP) | Unit tests validating burst/gap loss breakdown, E-model calculation, and MOS guards. |
| **10D** | **Avaya Platform Models** | `services/voice/avaya/` (SBCE 8.1, Session Manager, station vs trunk state) | Unit tests simulating 480 vs 503 responses and SBCE resource thresholds. |
| **10E** | **Dial Plan & Routing Assurance** | `services/voice/dialplan/` (KQ numbering plan, E.164, carrier trunks, safety) | Unit tests verifying extension mapping, route group validation, and emergency blocks. |
| **10F** | **Topology Dependency Correlation** | `services/voice/topology_link.py` & `services/assurance/correlator.py` | Integration tests verifying topological link failure identification for voice incidents. |
| **10G** | **Visualizations & Dashboard** | `docker/grafana/dashboards/nawari_voice_intelligence.json` | JSON schema validation and dashboard provisioning check. |
| **10H** | **Consolidated Acceptance** | `scripts/verify_phase10.sh`, full regression suite | 235 existing tests + Phase 10 suite passing 100% (zero failures, zero skips). |

---

## 6. Acceptance Criteria for Phase 10 Completion

Phase 10 will be accepted when:
1. **SIP Transaction State Machine:** Correctly parses RFC 3261 messages, models client/server transaction lifecycles, and dissects PDD, alerting, and answer latencies.
2. **Q.850 & Reason Code Mapping:** Accurately translates ITU-T Q.850 cause codes and Avaya warning headers, correctly distinguishing normal station states (`480`, `486`) from true trunk failures (`500`, `503`).
3. **RTCP-XR & E-Model Calculation:** Correctly processes RFC 3611 VoIP metric blocks, separates network loss from jitter buffer discards, and enforces the invariant guard (no MOS when evidence is missing).
4. **SDP Inspection:** Accurately detects codec mismatches, packetization interval disparities, and asymmetric routing.
5. **Kenya Airways Numbering Plan:** Accurately validates and normalizes KQ internal extensions (HQ, JKIA, Outstations) and carrier trunk preferences while strictly blocking emergency numbers.
6. **Topological Integration:** Correlates voice quality degradations with physical switch links and topology changes discovered in Phase 9.
7. **Regression Guarantee:** All 235 existing tests continue to pass 100% with zero regressions.
8. **Working Tree Cleanliness:** Nawari git working tree is clean; Sentra remains untouched.
