# Nawari — Voice Quality Measurement, Evidence Hierarchy & Validity

**Standard:** Nawari Phase 13.1 Communications Assurance  
**Target Architecture:** Multi-Site Enterprise Telephony & Synthetic Call Engine  
**Evidence Standard:** ITU-T G.107 (E-Model), RFC 3611 (RTCP-XR), and Avaya CM IP Voice MIB  

---

## 1. Communications Quality Evidence Hierarchy

To ensure NOC operators and airline executives never misdiagnose communications performance, Nawari enforces a strict four-tier hierarchy of voice quality evidence:

```
+===================================================================================================+
|                              COMMUNICATIONS QUALITY EVIDENCE HIERARCHY                            |
+===================================================================================================+
|  TIER 1: SIP Signaling Health                                                                     |
|  - SIP REGISTER / 200 OK                                                                          |
|  - SIP OPTIONS Keepalives & Response Latency (ms)                                                 |
|  - SIP Response Distribution (1xx, 2xx, 4xx, 5xx)                                                 |
|  - Carrier Trunk Operational State                                                                |
|  --> EVIDENCE: Proves layer-5 signaling reachability ONLY.                                         |
|  --> RULE: Never proves that audio flowed or that voice quality was acceptable.                   |
+---------------------------------------------------------------------------------------------------+
|  TIER 2: Call Processing & Outcome Telemetry                                                      |
|  - Call Attempts, Call Completion Rate, Busy / Fast-Busy Counts                                   |
|  - Q.850 Disconnect Cause Codes                                                                   |
|  - Post-Dial Delay (PDD), Time-to-Alerting (TTA), Call Setup Latency                              |
|  --> EVIDENCE: Proves call routing and teardown outcomes.                                         |
|  --> RULE: Does not measure acoustic clarity, voice clipping, or acoustic delay.                 |
+---------------------------------------------------------------------------------------------------+
|  TIER 3: Transport & Media Stream Telemetry                                                       |
|  - Real-call packet loss %, peak jitter (ms), peak delay (ms) via Avaya CM MIB                   |
|  - RTCP packet loss & jitter reports from endpoints                                               |
|  - Voice Codec (G.711u, G.711a, G.729, Opus, G.722) and packetization interval                    |
|  --> EVIDENCE: Quantifies physical audio packet delivery across IP networks.                      |
|  --> RULE: Hourly aggregated in Avaya CM; requires live RTCP for per-call metrics.               |
+---------------------------------------------------------------------------------------------------+
|  TIER 4: Perceived Voice Quality (MOS & R-Factor)                                                 |
|  - Mean Opinion Score (1.0 to 4.5) & R-Factor (0 to 100) calculated via ITU-T G.107 E-Model       |
|  --> EVIDENCE: Perceived acoustic quality experienced by human listeners.                         |
|  --> RULE: Must be computed from actual media evidence (loss, jitter, delay, codec).               |
|  --> MANDATORY ENFORCEMENT: If valid media telemetry is absent, MOS must show N/A.                |
|      Never calculate MOS from SIP OPTIONS or interface utilization.                               |
+===================================================================================================+
```

---

## 2. Real-Call vs. Synthetic Probe Separation

### 2.1 Real-Call Voice Telemetry
1. **Avaya CM IP Voice Tables:**
   - Table `avCmMeasIpVoStatSumDataLstHrTable` (`1.3.6.1.4.1.6889.2.73.8.1.77`): Reports packet loss %, peak jitter, peak delay, and codec for real completed subscriber calls over the preceding 1-hour interval.
   - Table `avCmMeasIpVoStatHrJitterTable` (`1.3.6.1.4.1.6889.2.73.8.1.66`): Reports average jitter and call counts.
   - *Limitation:* Historical hourly summary; not instantaneous per-call streaming telemetry.
2. **Real-Call MOS:**
   - Real-call MOS is available **ONLY** when genuine RFC 3611 RTCP-XR (Block 7) telemetry is emitted by physical endpoints/gateways or when a dedicated passive packet analyzer (e.g. VoIP sniffer/VoIP probe) taps the media stream.
   - *Current Estate Status:* Until RFC 3611 endpoints or media sniffers are physical commissioned in Phase 8.2, Real-Call MOS is honestly displayed as:
     `Real-Call MOS [NOT INSTRUMENTED — RTCP XR REQUIRED]` with value `N/A`.

### 2.2 Synthetic Voice Probes (Asterisk Engine)
- Nawari deploys synthetic Asterisk call probes to generate controlled, end-to-end test calls across network paths.
- Synthetic probes collect exact Post-Dial Delay (PDD), SIP response codes, RTP packet loss %, jitter (ms), and compute ITU-T G.107 MOS.
- *Mandatory Rule:* All synthetic panels are visibly labeled with `[SYNTHETIC — ASTERISK]`. Synthetic metrics must **NEVER** be merged with production customer call statistics.

---

## 3. Telemetry Freshness & Stale Data Policy

To prevent operators from trusting outdated data during network outages:
- Every visualization panel documents its expected collection interval.
- When telemetry ceases to arrive:
  - Dashboards configure `spanNulls: False` to render gaps.
  - Stat panels display `"No Data"` or `"Stale"` after $2\times$ the polling interval.
  - A device with no incoming data is flagged as `Unreachable / Stale`, never `Healthy`.

