# Nawari Voice Telemetry Specification (v1.0)

**Document Reference:** NAWARI-SPEC-VOICE-TELEMETRY-01  
**Status:** APPROVED FOR PHASE 6.1  
**Scope:** Canonical Voice Telemetry, Metrics Inventory, Units, Invariants, and Validity Contracts.

---

## 1. Metric Inventory & Validity Contracts

Every quality metric ingested, stored in Zabbix, and visualized in Grafana adheres to the strict contract defined below.

| Metric Key | Description | Source | Unit | Value Type | Validity Condition | Null / Fallback Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `voice.synthetic.outcome` | Transactional call outcome | AMI `Hangup` / Asterisk Dialplan | String | Character | Always valid upon call completion | Mandatory (`ANSWERED`, `BUSY`, `CONGESTION`, `TIMEOUT`, `FAILED`, `SAFETY_BLOCKED`, `DRY_RUN`) |
| `voice.synthetic.sip_status` | SIP response status code | PJSIP Channel / AMI `VarSet` | Code | Unsigned Integer | Present if SIP transaction reached progress or answer | `None` if aborted before SIP response |
| `voice.synthetic.setup_time` | Signaling establishment latency | Millisecond difference between `Newchannel` and `Answer` | ms | Float | $\Delta t > 0$ and call was answered or progressed | `0.0` or `None` if uncompleted |
| `voice.synthetic.duration` | Active connected duration | Millisecond difference between `Answer` and `Hangup` | s | Float | Call reached answered state | `0.0` if unanswered |
| `voice.synthetic.media_status`| Media verification level | RTP packet counters ($Tx, Rx$) | String | Character | Validated across 7-stage media lifecycle | Mandatory (`BIDIRECTIONAL`, `TRANSMIT_ONLY`, `RECEIVE_ONLY`, `NO_MEDIA`, `UNVERIFIED`) |
| `voice.synthetic.mos` | Estimated Mean Opinion Score | ITU-T G.107 E-model computation | Score (1.00 - 4.50) | Float | **Strict:** Requires `media_status == BIDIRECTIONAL` AND valid RTCP reports ($Tx \ge 1, Rx \ge 1$) | **MANDATORY NULL (`None`):** Never fabricated or assumed healthy |
| `voice.synthetic.r_factor` | Transmission rating factor $R$ | ITU-T G.107 E-model ($R = R_0 - I_s - I_d - I_e + A$) | Score (0.0 - 100.0) | Float | Requires valid RTCP and bidirectional media | `None` if RTCP missing or media unidirectional |
| `voice.synthetic.jitter` | Interarrival packet jitter | RTCP Receiver/Sender Report | ms | Float | Measured RTCP jitter $\ge 0$ | `None` if no RTCP reports captured |
| `voice.synthetic.packet_loss` | RTP packet loss percentage | RTCP fraction lost / RTP sequence delta | % (0.0 - 100.0) | Float | Requires $Rx > 0$ or confirmed lost packets | `None` if 0 packets sent/received (not 0.0%) |
| `voice.synthetic.rtt` | RTCP round-trip time | RTCP Delay Since Last SR (DLSR) | ms | Float | Measured RTT $> 0$ | `None` if DLSR cannot be calculated |
| `voice.synthetic.one_way_delay`| Mouth-to-ear one-way delay | Calculated: $\frac{\text{RTT}}{2} + 2J + 20\text{ ms}$ | ms | Float | Estimated from measured RTT and jitter | `None` if RTT or jitter is missing |
| `voice.synthetic.environment` | Telemetry provenance | Runner configuration | String | Character | Identifies producer environment | `MOCK_SIMULATED` vs `PHYSICAL_PRODUCTION` |

---

## 2. Invariants & Rules

### Invariant 1: Delay Distinction (Estimated vs. Measured)
- **Estimated One-Way Delay (`estimated_one_way_delay_ms`):** Inferred algorithmically via $d = \frac{\text{RTT}}{2} + 2 \cdot J + T_p$ ($T_p = 20\text{ ms}$). This is an operational estimate assuming symmetric network routing.
- **Measured One-Way Delay (`measured_one_way_delay_ms`):** Inferred from high-precision synchronized endpoint clocks (PTP/IEEE 1588 or NTP stratum 1) or RTCP Extended Reports (RFC 3611 VoIP Metrics). When unsynchronized, this field MUST remain `None`.

### Invariant 2: Absence of RTCP
- When RTCP sender or receiver reports are absent, `is_valid` MUST evaluate to `False`.
- `estimated_mos` and `r_factor` MUST remain `None`.
- Healthy MOS values (e.g. 4.3 or 4.5) MUST NEVER be defaulted, assumed, or guessed.

### Invariant 3: Zero Packets Received is NOT Zero Packet Loss
- If a channel is answered but 0 RTP packets are received ($Rx = 0$), packet loss cannot be claimed as $0.0\%$.
- If $Tx > 0$ and $Rx = 0$, the stream is classified as `TRANSMIT_ONLY` (One-Way Audio).
- If $Tx = 0$ and $Rx = 0$, the stream is classified as `NO_MEDIA`.

### Invariant 4: Telemetry Staleness
- Any voice telemetry older than 15 minutes without subsequent refreshes is classified as `STALE`.
- A stale synthetic probe does not imply a healthy service; the assurance engine marks the service health as `UNKNOWN` or `DEGRADED`.
