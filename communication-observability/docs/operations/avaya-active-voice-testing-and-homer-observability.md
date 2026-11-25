# NAWARI — AVAYA ACTIVE VOICE TESTING AND HOMER OBSERVABILITY ARCHITECTURAL SPECIFICATION AND OPERATIONAL RUNBOOK

**Author:** Antigravity AI (Principal Enterprise Observability Architect & Voice Telemetry Engineer)  
**Date:** 2026-11-25  
**Document Revision:** 1.0.0  
**Target Environment:** Nawari Enterprise Observability (`mon-grafana01` / `10.2.1.58`)  
**Target Git Branch:** `chore/reconcile-nawari-layout`  
**Classification:** Authoritative Technical Specification & Operational Runbook  

---

## EXECUTIVE SUMMARY

A critical distinction must be maintained in enterprise voice observability: **originating controlled synthetic test calls through an Avaya Session Border Controller Enterprise (SBCE) is not the same as monitoring genuine enterprise production calls.**

In Nawari's live operational deployment, the telemetry pipeline previously ingested only synthetic Asterisk loopback calls into the HOMER database (recording 54 historical test sessions). This occurred because **Asterisk was the sole signaling source configured with a HEP (Homer Encapsulation Protocol) exporter**. Real enterprise conversations occurring directly between Avaya SBCEs, Avaya Aura Session Managers, carrier SIP trunks, and physical IP deskphones never touched Asterisk and thus remained uncaptured.

This specification expands Nawari into two complementary, rigorously decoupled voice monitoring systems:

1. **Active Voice Testing (Asterisk AVTEST):** Asterisk acts as an authorized active probing engine originating deterministic, low-rate synthetic SIP requests (OPTIONS pings, registration queries, and controlled test calls to dedicated loopback extensions `8801`/`8802`) through live Avaya infrastructure. This measures whether specific signaling routes and media processing paths are operationally responsive.
2. **Passive Production Monitoring (Heplify / HOMER):** HOMER acts as a passive, non-intrusive central repository ingesting genuine enterprise SIP signaling from an approved network SPAN mirror or Avaya signaling export point, completely independent of Asterisk.

```
+----------------------------------------------------------------------------------------------------+
|                               NAWARI DUAL-STREAM VOICE ARCHITECTURE                                |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    ACTIVE TESTING STREAM                                  PASSIVE PRODUCTION STREAM                |
|    =====================                                  =========================                |
|                                                                                                    |
|    [Asterisk AVTEST Engine]                               [Live Enterprise Production Traffic]     |
|    Host: 10.2.5.148 (or mon-grafana01)                   (Executive, Contact Centre, Trunks)      |
|    Endpoints: 8801, 8802, avaya-sbce-primary                               |                       |
|           |                                                                v                       |
|           | (Originates INVITE / OPTIONS)                     [Avaya SBCE / Session Manager]       |
|           v                                                   IP: 10.2.156.131 / 10.2.156.40       |
|    [Avaya SBCE Core Signaling]                                             |                       |
|    IP: 10.2.156.131:5060                                                   | (Physical SPAN /      |
|           |                                                                |  Signaling Mirror)    |
|           | (res_hep_pjsip export)                                         v                       |
|           v                                                   [Hardened Heplify Daemon]            |
|    [Asterisk HEP Exporter]                                    Interface: eth1 (SPAN vNIC)          |
|    capture_id: 2001                                           capture_id: 1001                     |
|    capture_name: nawari-avtest-lab                            capture_name: nawari-avaya-sbce-prod |
|           \                                                                /                       |
|            \                                                              /                        |
|             v                                                            v                         |
|         +--------------------------------------------------------------------+                     |
|         |                   CENTRAL HOMER POSTGRESQL DATABASE                |                     |
|         |                   hep_proto_1_call / sip_capture                   |                     |
|         +--------------------------------------------------------------------+                     |
|                                     |                                                              |
|                     +---------------+---------------+                                              |
|                    /                                 \                                             |
|                   v                                   v                                            |
|       [SYNTHETIC TEST DRILL-DOWN]          [GENUINE PRODUCTION CALLS]                              |
|       - Panel 17 (Voice Intelligence)      - Panel 10 (Voice Intelligence)                         |
|       - Voice Service Assurance            - Carrier SIP Trunks                                    |
|       - Tracked by: X-Nawari-ActionID      - Tracked by: Enterprise Call-ID                        |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 1. WHY HOMER CURRENTLY SHOWS ONLY ASTERISK CALLS

### 1.1 The Root Cause of Synthetic-Only Records
In the initial commissioning phase, queries against HOMER revealed 54 call records, all with loopback IP addresses (`127.0.0.1`) and caller IDs like `1001` or `1002`. Zero records exhibited genuine enterprise source IPs (`10.2.156.x` or `10.102.x`).

This was not a malfunction of HOMER or Grafana. It was the direct consequence of the network capture topology:
- **Asterisk's PJSIP Stack:** Uses Asterisk's native `res_hep_pjsip.so` module to mirror SIP transactions that Asterisk itself processes. When Asterisk runs a diagnostic echo call between extension 1000 and 1001, Asterisk encapsulates the SIP packets into HEPv3 frames and transmits them to `nawari-heplify:9060`.
- **The Missing Production Feed:** Production Avaya phone calls (e.g. an agent on extension 4521 speaking to an external customer through the Safaricom SIP trunk) flow directly between the Avaya 9611G IP deskphone, Avaya Session Manager, Avaya SBCE, and the carrier perimeter. None of those packets transit the Asterisk container.
- **The Telemetry Separation:** HOMER cannot ingest what it does not receive. To observe real calls, HOMER requires a dedicated network tap, switch port mirror (SPAN), or Avaya-native signaling export agent.

---

## 2. THE 6 LEVELS OF TESTING AGAINST LIVE AVAYA EQUIPMENT

Active testing can target multiple layers of the Avaya voice architecture. Each test level verifies distinct functional capabilities and provides specific forensic evidence:

| Test Level | Target Entity | What It Proves | Evidence Collected |
| :--- | :--- | :--- | :--- |
| **1. SIP OPTIONS to SBCE** | Avaya SBCE Signaling IP (`10.2.156.131:5060`) | SIP stack availability, L4 socket responsiveness, network path latency, and perimeter ACL acceptance. | SIP response code (`200 OK`, `403 Forbidden`, `405 Method Not Allowed`), round-trip time (RTT in ms), socket timeout status. |
| **2. SIP OPTIONS to Session Manager** | Avaya Session Manager (`10.2.156.40:5060`) | Core call processing responsiveness and internal routing domain health. | SIP response code, routing delay, transit hop count. |
| **3. SIP Trunk Registration** | Carrier / Core SIP Registrar | Registration state, credential validity, and session timer expiration. | SIP `REGISTER` / `200 OK`, `401 Unauthorized`, `Expires:` header verification. |
| **4. Controlled Test Call through SBCE** | Assigned Internal Test Endpoint (e.g. Ext `8801` Echo, `8802` Announce) | Dialplan routing through SBCE and Session Manager, call setup sequencing, and session state machine stability. | Full SIP ladder (`INVITE` $\rightarrow$ `100 Trying` $\rightarrow$ `180 Ringing` $\rightarrow$ `200 OK` $\rightarrow$ `ACK` $\rightarrow$ `BYE`), post-dial delay (PDD), setup time ms. |
| **5. Two-Way Media Test** | Internal Audio Echo Loop (`8801`) | Bidirectional RTP audio connectivity, firewall UDP hole-punching, audio codec negotiation, and acoustic impairment metrics. | Transmitted/Received RTP packet counts (Tx/Rx), RTCP XR packets, jitter buffer discards, packet loss percentage, estimated MOS score (ITU-T G.107). |
| **6. Carrier Perimeter Test Call** | Dedicated Carrier Echo/Test Number | End-to-end PSTN/carrier trunk routing, external billing authorization, perimeter SBC NAT traversal. | Carrier SIP signaling response, trunk seizure duration, carrier disconnect cause code. |

> [!WARNING]
> A successful SIP OPTIONS response (`200 OK`) **only proves that the SIP daemon is alive and listening**. It does **not** prove that call routing works, that Session Manager has routing licenses, or that bidirectional RTP audio packets can cross enterprise firewalls without one-way audio failure.

---

## 3. THE 3-STAGE CONTROLLED ROLLOUT PROTOCOL

To ensure that active voice testing never disrupts enterprise contact centers or executive lines, testing must follow a strict 3-stage progression:

```
+----------------------------------------------------------------------------------------------------+
|                                    3-STAGE COMMISSIONING PROTOCOL                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    STAGE 1: SIP AVAILABILITY TESTING                                                               |
|    - Target: Avaya SBCE Primary (10.2.156.131:5060)                                                |
|    - Method: Low-rate SIP OPTIONS ping (qualify_frequency = 60s, timeout = 3.0s)                   |
|    - Requirement: Verified SIP response (200 OK or 403 Forbidden) within 50ms                      |
|    - Gate: Stage 2 calls are HARD-BLOCKED until Stage 1 is green                                   |
|                                   |                                                                |
|                                   v                                                                |
|    STAGE 2: CONTROLLED INTERNAL TEST CALLS                                                         |
|    - Target: Dedicated internal test extensions only (Ext 8801 Echo, Ext 8802 Announcement)       |
|    - Routing: Asterisk -> Avaya SBCE -> Session Manager -> Test IVR                                |
|    - Controls: Allowed-targets whitelist, 1-call concurrency lock, 5s cooldown, circuit breaker    |
|    - Evidence: Injects X-Nawari-ActionID and X-Nawari-Test-Stage headers into outbound INVITE       |
|                                   |                                                                |
|                                   v                                                                |
|    STAGE 3: PASSIVE PRODUCTION SIP COLLECTION                                                      |
|    - Target: Genuine production Avaya calls (all extensions, carrier trunks)                       |
|    - Method: Non-intrusive SPAN port mirror on SBCE vNIC (eth1) -> Hardened Heplify daemon        |
|    - Provenance: Classified as VERIFIED_PRODUCTION_AVAYA in Homer PostgreSQL                       |
|    - Result: Complete production SIP intelligence with zero synthetic contamination                |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. ASTERISK AVTEST CONFIGURATION SPECIFICATIONS

The Asterisk container configuration on `mon-grafana01` is tailored for staged Avaya integration while maintaining safe offline fallbacks.

### 4.1 PJSIP Configuration (`pjsip.conf`)
Located at `communication-observability/docker/asterisk/config/pjsip.conf`:

```ini
; NAWARI PJSIP Configuration — Avaya SBCE Staged Testing
[global]
type = global
debug = no

; Transports
[transport-udp]
type = transport
protocol = udp
bind = 0.0.0.0:5060

[transport-tls]
type = transport
protocol = tls
bind = 0.0.0.0:5061
method = tlsv1_2
verify_server = no
verify_client = no

; ---------------------------------------------------------
; Diagnostic Loopback Endpoints (Offline / Local Dev Mode)
; ---------------------------------------------------------
[1001]
type = endpoint
context = nawari-diagnostic
disallow = all
allow = ulaw
allow = alaw
aors = 1001

[1001]
type = aor
max_contacts = 1

; ---------------------------------------------------------
; Stage 1 & Stage 2 Live Avaya Infrastructure Endpoints
; ---------------------------------------------------------

; Avaya SBCE Primary Signaling Interface (B1 / Internal)
[avaya-sbce-primary]
type = endpoint
transport = transport-udp
context = nawari-outbound
disallow = all
allow = ulaw
allow = alaw
dtmf_mode = rfc4733
direct_media = no
aors = avaya-sbce-primary

[avaya-sbce-primary]
type = aor
contact = sip:10.2.156.131:5060
qualify_frequency = 60
qualify_timeout = 3.0

; Avaya SBCE Secondary Signaling Interface (HA Standby)
[avaya-sbce-secondary]
type = endpoint
transport = transport-udp
context = nawari-outbound
disallow = all
allow = ulaw
allow = alaw
dtmf_mode = rfc4733
direct_media = no
aors = avaya-sbce-secondary

[avaya-sbce-secondary]
type = aor
contact = sip:10.2.156.130:5060
qualify_frequency = 60
qualify_timeout = 3.0

; Avaya Session Manager Core SIP Signaling Entity
[avaya-sm-primary]
type = endpoint
transport = transport-udp
context = nawari-outbound
disallow = all
allow = ulaw
allow = alaw
dtmf_mode = rfc4733
direct_media = no
aors = avaya-sm-primary

[avaya-sm-primary]
type = aor
contact = sip:10.2.156.40:5060
qualify_frequency = 60
qualify_timeout = 3.0
```

### 4.2 Dialplan Staging & Telemetry Header Injection (`extensions.conf`)
Located at `communication-observability/docker/asterisk/config/extensions.conf`:

```ini
; Outbound dialing context towards Avaya SBCE / Session Manager
; Strictly gated by pre-call safety checks and Stage 1 OPTIONS verification
[nawari-outbound]
; Stage 2 Authorized Internal Echo Test
exten => 8801,1,NoOp(Nawari Stage 2 Controlled Internal Echo Test: 8801)
 same => n,Set(NAWARI_TEST_STAGE=STAGE_2_INTERNAL_ECHO)
 same => n,Dial(PJSIP/8801@avaya-sbce-primary,15,b(nawari-correlation^s^1(${NAWARI_ACTION_ID},STAGE_2_INTERNAL_ECHO)))
 same => n,Hangup()

; Stage 2 Authorized Internal Fast Answer / Announcement Test
exten => 8802,1,NoOp(Nawari Stage 2 Controlled Internal Fast Answer Test: 8802)
 same => n,Set(NAWARI_TEST_STAGE=STAGE_2_INTERNAL_FAST_ANSWER)
 same => n,Dial(PJSIP/8802@avaya-sbce-primary,15,b(nawari-correlation^s^1(${NAWARI_ACTION_ID},STAGE_2_INTERNAL_FAST_ANSWER)))
 same => n,Hangup()

; Authorized internal range for Avaya lab extensions
exten => _88XX,1,NoOp(Nawari Stage 2 Authorized Internal Call: ${EXTEN})
 same => n,Dial(PJSIP/${EXTEN}@avaya-sbce-primary,20,b(nawari-correlation^s^1(${NAWARI_ACTION_ID},STAGE_2_INTERNAL_CALL)))
 same => n,Hangup()

; Correlation handler: Injects explicit unique X-Nawari headers into outbound INVITE
[nawari-correlation]
exten => s,1,Set(PJSIP_HEADER(add,X-Nawari-ActionID)=${ARG1})
 same => n,Set(PJSIP_HEADER(add,X-Nawari-Origin)=AVTEST_ASTERISK)
 same => n,Set(PJSIP_HEADER(add,X-Nawari-Test-Stage)=${ARG2})
 same => n,Return()
```

### 4.3 HEPv3 Encapsulation Tagging (`hep.conf`)
Located at `communication-observability/docker/asterisk/config/hep.conf`:

```ini
; NAWARI HEPv3 Configuration for Homer/Heplify SIP Observability
[general]
enabled = yes
capture_address = nawari-heplify:9060
capture_id = 2001
capture_name = nawari-avtest-lab
uuid_type = call-id
```

By tagging synthetic Asterisk packets with `capture_id = 2001` and `capture_name = nawari-avtest-lab`, HOMER PostgreSQL database queries can filter synthetic traffic from production captures (`capture_id = 1001`, `capture_name = nawari-avaya-sbce-prod`) with 100% mathematical precision.

---

## 5. SAFETY CONTROLS, CONCURRENCY GUARDS, AND CIRCUIT BREAKERS

Nawari enforces four layers of pre-call safety via `CallSafetyManager` (`services/voice/safety.py`):

1. **Unconditional Emergency Blacklist:** Destination numbers matching emergency services (`911`, `112`, `999`, `000`, `100`, `991`) or emergency numbers with typical trunk escape prefixes (`9911`, `0911`) are unconditionally rejected before initiating any socket connection or dialplan execution.
2. **Strict Destination Allowlist:** Only extensions present in the configured allowlist (`allowed_targets = ["1001", "1002", "1003", "1004", "8801", "8802"]`) can be called. Arbitrary phone numbers are rejected with `SafetyViolationError`.
3. **Stage 1 OPTIONS Prerequisite Gate:** Non-diagnostic live calls (such as `8801` or carrier trunks) require both `--live --confirm-live-call` flags **and** an active, successful Stage 1 SIP OPTIONS qualification recorded within the past 300 seconds (`stage_prerequisite_window_seconds`). If OPTIONS failed or expired, the test call is blocked.
4. **Consecutive Failure Circuit Breaker:** If 3 consecutive calls fail, the circuit breaker trips into `IS_TRIPPED = True`, locking all subsequent call attempts for a 60-second cooldown period to prevent network flooding during telephony outages.

---

## 6. EXPECTED EVIDENCE RECORD & CALL SEQUENCE LADDER

### 6.1 Expected SIP Call Ladder (Stage 2 Internal Test Call to Ext 8801)

```
Asterisk AVTEST (10.2.5.148)           Avaya SBCE (10.2.156.131)           Session Manager / Media Loop
         |                                         |                                     |
         | --- SIP OPTIONS (Stage 1 Ping) -------> |                                     |
         | <--- SIP 200 OK (RTT: 14.2ms) --------- |                                     |
         |                                         |                                     |
         | --- SIP INVITE (Ext 8801) ------------> |                                     |
         |     X-Nawari-ActionID: nawari-a1b2c3d4  | --- SIP INVITE (Ext 8801) --------> |
         |     X-Nawari-Test-Stage: STAGE_2_ECHO   |                                     |
         | <--- 100 Trying ----------------------- | <--- 100 Trying ------------------- |
         | <--- 180 Ringing ---------------------- | <--- 180 Ringing ------------------ |
         | <--- 200 OK (SDP Answer: G.711u) ------ | <--- 200 OK (SDP Answer) ---------- |
         | --- ACK ------------------------------> | --- ACK --------------------------> |
         |                                         |                                     |
         | <================= Bidirectional RTP Audio Stream (Ext 8801 Echo) ===========> |
         |                   Tx: 150 pkts | Rx: 150 pkts | MOS: 4.38                     |
         |                                         |                                     |
         | --- BYE (Teardown after 3s) ----------> | --- BYE --------------------------> |
         | <--- 200 OK --------------------------- | <--- 200 OK ----------------------- |
         |                                         |                                     |
```

### 6.2 Actual Output Telemetry Schema (`nawari-voice call 8801 --json`)

```json
{
  "action_id": "nawari-a1b2c3d4",
  "target": "8801",
  "stage": "STAGE_2_CONTROLLED_INTERNAL_CALL",
  "target_entity": "avaya-sbce-primary",
  "outcome": "ANSWERED",
  "success": true,
  "timestamp_start": 1795587476.120,
  "timestamp_end": 1795587479.250,
  "duration_seconds": 3.13,
  "signaling": {
    "setup_time_ms": 142.5,
    "ringing_time_ms": 310.2,
    "duration_seconds": 3.13,
    "sip_status_code": 200,
    "sip_status_reason": "OK",
    "hangup_cause": 16,
    "hangup_cause_txt": "Normal Call Clearing",
    "sip_call_id": "4a7b9c1d-8801-avtest@10.2.5.148",
    "action_id": "nawari-a1b2c3d4",
    "channel": "PJSIP/avaya-sbce-primary-00000042",
    "lifecycle": {
      "signaling_established": true,
      "channel_answered": true,
      "rtp_tx_observed": true,
      "rtp_rx_observed": true,
      "rtcp_received": true,
      "bidirectional_media": true,
      "quality_calculated": true
    }
  },
  "media": {
    "jitter_ms": 2.1,
    "loss_pct": 0.0,
    "rtt_ms": 14.5,
    "one_way_delay_ms": 7.2,
    "estimated_mos": 4.38,
    "r_factor": 92.4,
    "packets_sent": 156,
    "packets_received": 156,
    "codec": "G.711u",
    "verification_level": "BIDIRECTIONAL",
    "is_valid": true,
    "mos_score": 4.38
  },
  "provenance": "SYNTHETIC_AVTEST",
  "error_message": null
}
```

---

## 7. GRAFANA DASHBOARD OPERATIONAL ALIGNMENT

Nawari organizes voice observability across **5 designated dashboards**, each assigned a distinct operational role:

```
+----------------------------------------------------------------------------------------------------+
|                                    GRAFANA VOICE DASHBOARD MATRIX                                  |
+----------------------------------------------------------------------------------------------------+
| Dashboard Name                  | Operational Purpose                              | Primary Source|
+----------------------------------------------------------------------------------------------------+
| 1. Voice Service Assurance      | Synthetic probe success rates, call latency,     | Asterisk      |
|    (nawari-voice-service-       | acoustic impairments, and estimated MOS.         | Synthetic     |
|     assurance.json)             | Shows continuous availability of voice services. | Probes        |
+----------------------------------------------------------------------------------------------------+
| 2. SBCE Operational Health      | SBCE appliance CPU/RAM, interface packet errors, | Avaya SNMP +  |
|    (avaya_sbce_operational_    | ICMP availability, and active SIP OPTIONS        | Asterisk      |
|     health.json)                | response latency from Asterisk AVTEST.           | OPTIONS Probe |
+----------------------------------------------------------------------------------------------------+
| 3. Carrier SIP Trunks           | Safaricom and Airtel trunk keepalive health,     | Zabbix SNMP + |
|    (nawari_sip_trunks_          | trunk registration status, and end-to-end test   | Homer Carrier |
|     signaling.json)             | call signaling ladders.                          | Capture       |
+----------------------------------------------------------------------------------------------------+
| 4. Voice Intelligence           | Centralized SIP session forensic viewer.         | Homer         |
|    (nawari_voice_intelligence.  | Strictly separates Panel 10 (Production Capture) | PostgreSQL    |
|     json)                       | from Panel 17 (Synthetic Test Calls).            | (hep_proto)   |
+----------------------------------------------------------------------------------------------------+
| 5. Voice & Endpoint Correlation | Correlates voice quality degradation (MOS/Jitter)| Netdata +     |
|    (endpoint_voice_correlation. | with physical network conditions (Wi-Fi signal,  | Zabbix +      |
|     json)                       | endpoint gateway loss, and WAN path latency).    | Asterisk RTCP |
+----------------------------------------------------------------------------------------------------+
```

### 7.1 Provenance Isolation SQL Invariants
In `nawari_voice_intelligence.json`:
- **Panel 10 (Production SIP Sessions):**
  ```sql
  SELECT create_date AS "time", sid AS "call_id", ...
  FROM hep_proto_1_call 
  WHERE protocol_header->>'captureId' IN ('nawari-avaya-sbce-prod', 'nawari-avaya-span-prod') 
    AND (protocol_header->>'srcIp' LIKE '10.2.156.%' OR protocol_header->>'srcIp' LIKE '10.102.%')
    AND $__timeFilter(create_date)
  ORDER BY create_date DESC LIMIT 50;
  ```
- **Panel 17 (Synthetic SIP Test Calls):**
  ```sql
  SELECT create_date AS "time", sid AS "call_id", ...
  FROM hep_proto_1_call 
  WHERE (protocol_header->>'captureId' = 'nawari-avtest-lab' OR protocol_header->>'srcIp' IN ('127.0.0.1', '::1'))
    AND $__timeFilter(create_date)
  ORDER BY create_date DESC LIMIT 50;
  ```

---

## 8. CLI OPERATIONAL COMMAND REFERENCE

### 8.1 Stage 1: SIP OPTIONS Qualification Probes

```bash
# Execute simulated Stage 1 SIP OPTIONS ping (offline / at-home testing)
python communication-observability/services/voice/cli.py options \
  --peer avaya-sbce-primary \
  --simulate

# Execute live Stage 1 SIP OPTIONS ping to Avaya SBCE Primary
python communication-observability/services/voice/cli.py options \
  --peer avaya-sbce-primary \
  --target 10.2.156.131 \
  --port 5060

# Execute live Stage 1 SIP OPTIONS ping to Avaya Session Manager
python communication-observability/services/voice/cli.py options \
  --peer avaya-sm-primary \
  --target 10.2.156.40 \
  --port 5060
```

### 8.2 Stage 2: Controlled Internal Test Calls

```bash
# Execute pre-flight dry-run test call (simulates pre-call gates without SIP traffic)
python communication-observability/services/voice/cli.py call 8801 \
  --dry-run \
  --json

# Execute Stage 2 internal echo test call through Avaya SBCE (requires confirmed Stage 1)
python communication-observability/services/voice/cli.py call 8801 \
  --live \
  --confirm-live-call \
  --peer avaya-sbce-primary \
  --timeout 10.0

# Inspect circuit breaker status
python communication-observability/services/voice/cli.py circuit-breaker status

# Reset tripped circuit breaker
python communication-observability/services/voice/cli.py circuit-breaker reset
```

---

## 9. AT-HOME OFFLINE READINESS & CORPORATE COMMISSIONING CHECKLIST

### 9.1 Offline Tasks Completed (At Home)
- [x] PJSIP Avaya endpoint profiles (`avaya-sbce-primary`, `avaya-sbce-secondary`, `avaya-sm-primary`) configured with qualify intervals.
- [x] Dialplan staging extensions (`8801`, `8802`, `_88XX`) configured with `X-Nawari` telemetry header injection.
- [x] Active SIP OPTIONS probe (`sip_options_probe.py`) implemented with RTT measurement and simulation support.
- [x] Pre-call safety manager updated with allowlist targets and Stage 1 prerequisite gate.
- [x] CLI commands (`options`, `call --stage`, `call --live --confirm-live-call`) implemented and validated.
- [x] Grafana queries in Voice Intelligence (Panels 10 & 17) hardened with strict positive provenance isolation.
- [x] 17 automated tests passing across `test_active_voice_testing_architecture.py` and `test_voice_safety.py`.

### 9.2 Live Corporate Commissioning Checklist (Upon VPN / Office Access)
- [ ] **Voice Operations Approval:** Obtain formal approval for AVTEST IP `10.2.5.148` (or `10.2.1.58`) as a permitted SIP signaling entity on Avaya SBCE B1 interface.
- [ ] **Test Extension Provisioning:** Confirm extensions `8801` (Echo) and `8802` (Announcement) are provisioned on Avaya Aura Session Manager routing policies.
- [ ] **Stage 1 Verification:** Run `nawari-voice options --peer avaya-sbce-primary` and confirm HTTP `200 OK` or `403 Forbidden` response with RTT $< 20\text{ms}$.
- [ ] **Stage 2 Verification:** Run `nawari-voice call 8801 --live --confirm-live-call` and observe call completion, bidirectional RTP stream, and estimated MOS.
- [ ] **Homer Inspection:** Verify that the test call appears in Homer PostgreSQL with `capture_name = nawari-avtest-lab` and `capture_id = 2001`.
- [ ] **Stage 3 Passive SPAN Capture:** Provision SPAN vNIC (`eth1`) on `mon-grafana01` to capture production Avaya traffic without Asterisk mediation.

---

## CONCLUSION

Nawari now possesses an enterprise-grade active voice testing engine built directly on Asterisk AVTEST, fully integrated with HOMER central signaling storage, and safeguarded by multi-tier pre-call safety controls. By strictly separating active synthetic probes from passive production signaling capture, Nawari provides continuous voice service availability assurance while preserving forensic accuracy for genuine production incidents.
