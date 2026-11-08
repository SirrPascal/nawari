# Phase 13.10 — Voice Assurance Architecture & Call-Flow Specification

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Architecture Implemented & Staging Verified  
**Target Environment:** Kenya Airways Telephony Core, Contact Center & Outstations  
**Standards Conformance:** RFC 3261 (SIP), RFC 3550 (RTP), RFC 3611 (RTCP-XR), ITU-T G.107 (E-model), ITU-T Q.850

---

## 1. Executive Summary

Phase 13.10 establishes an authoritative, end-to-end **Voice Assurance Architecture** for Kenya Airways.

In modern telecommunications observability, distinguishing between **signaling reachability** (SIP handshakes) and **media transport quality** (bidirectional RTP/RTCP delivery) is paramount. A phone system can successfully negotiate a SIP `200 OK` while delivering dead air, one-way audio, or severe jitter-induced degradation.

Nawari's voice assurance engine solves this by establishing:
1. A multi-stage call-flow model spanning carrier trunks, border controllers, session managers, communication managers, and automatic call distribution (ACD) queues.
2. Complete architectural separation between signaling paths and media anchoring paths.
3. Deterministic cross-protocol correlation binding SIP `Call-ID`, Asterisk AMI `Uniqueid`, and Avaya session identifiers.
4. Defensible ITU-T G.107 E-model estimated MOS ratings with strict missing-media guards.
5. Absolute operational and privacy isolation: zero audio recording and caller number masking.

---

## 2. End-to-End Enterprise Call-Flow Model

```
+-------------------------------------------------------------------------------------------------------------------------+
|                                    KENYA AIRWAYS END-TO-END TELEPHONY TOPOLOGY                                          |
+-------------------------------------------------------------------------------------------------------------------------+

 [Safaricom / Airtel SIP Trunk]
               |
               v (SIP UDP/TLS 5060/5061 + SRTP / RTP Audio)
    +----------------------+
    |   Avaya SBCE 8.1     | <--- DMZ Border Security & Topology Hiding
    |  (10.2.156.131/.132) |      Media Anchoring: Translates External Carrier RTP -> Internal Voice VLAN
    +----------------------+
               |
               v (SIP TCP 5060 Core Signaling)
    +----------------------+
    | Avaya Session Manager| <--- Central SIP Routing & Dial Plan Policy
    |  (10.2.156.22/.23)   |      Evaluates Location, Route Groups & Emergency Policies
    +----------------------+
               |
               v (SIP Proprietary Evolution / H.323 Core)
    +----------------------+
    | Avaya CM Duplex Pair | <--- Enterprise PBX Feature Engine & ACD Hunting
    |  (10.102.10.25/.26)  |      Call Center Skills, IVR Routing, Vector Directory Numbers (VDNs)
    +----------------------+
               |
        +------+---------------------------------+
        |                                        |
        v (H.248 Control)                        v (Direct RTP Audio)
 +---------------+                       +---------------+
 | Avaya G450 GW |                       |  Agent IP Soft |
 | (10.2.156.60) |                       |  or Deskphone  |
 | E1 PRI Backup |                       |  (VLAN 156)    |
 +---------------+                       +---------------+
```

### Signaling vs. Media Path Separation
- **Signaling Path:** Traverses `Carrier -> SBCE -> Session Manager -> Communication Manager -> Station`.
- **Media Path:** To minimize delay and latency jitter, media is anchored at the SBCE border and directed straight to the agent endpoint or G450 gateway via Voice VLAN 156 (`Direct IP-to-IP Audio`), bypassing the Session Manager.
- **Transcoding:** Required only when the carrier negotiates G.711A (PCMA) while remote outstations or mobile clients negotiate G.729 or Opus. Transcoding is performed on G450 DSP daughterboards.

---

## 3. Call Lifecycle State Machine & Latency Decomposition

Nawari decomposes call setup time into discrete, auditable latency intervals:

```
[TIME T0]  INVITE Sent / Received (State: CALLING)
    |
    |----> Post-Dial Delay (PDD): T1 - T0 (Target: < 500ms)
    |
[TIME T1]  180 Ringing / 183 Session Progress (State: PROCEEDING)
    |
    |----> Ringing / Alerting Duration: T2 - T1 (Caller heard ringback)
    |
[TIME T2]  200 OK Received / Answered (State: CONNECTED)
    |
    |----> Total Call Setup Time: T2 - T0 (Target: < 2500ms)
    |----> Active Connected Call Duration: T3 - T2
    |
[TIME T3]  BYE Received / Call Cleared (State: TERMINATED)
```

### Distinction Between Transport Latency and Call Setup Time
- **SIP Transport Latency:** The round-trip transmission delay of a single SIP transaction (e.g. `OPTIONS -> 200 OK` round-trip in 15–35ms).
- **Call Setup Time:** The complete end-to-end elapsed time from initial digit transmission (`INVITE`) until the destination device responds with alerting (`180 Ringing`) or connect (`200 OK`). Typically ranges from 400ms to 2500ms.
- Nawari strictly reports these metrics in dedicated panels to prevent engineers from confusing network transit time with PSTN signaling delays.

---

## 4. Operational Failure vs. Station State Classification

Calls terminate for many reasons; not all terminations represent infrastructure failures:

```
+------------+-------------------------------+-----------------------+-------------------------+------------------------+
| Final Code | Q.850 Standard Cause          | Operational Meaning   | Failure Classification  | Action / Alert Route   |
+------------+-------------------------------+-----------------------+-------------------------+------------------------+
| 200 OK     | Cause 16: Normal Clearing     | Call finished nominal | SUCCESS                 | Zero alert (Nominal)   |
| 486 Busy   | Cause 17: User Busy           | Callee already on call| STATION_STATE (User)    | Zero alert (Not infra) |
| 480 Unavail| Cause 18: No user responding  | Endpoint unplugged    | STATION_STATE (Device)  | Optional desk warning  |
| 503 Unavail| Cause 34: No circuit/channel  | Carrier trunk maxed   | TRUNK_CONGESTION        | Action 11 (Comm Alert) |
| 504 Timeout| Cause 41: Temporary failure   | Signaling node down   | INFRASTRUCTURE_FAILURE  | Action 11 (Comm Alert) |
| 404 Not Fnd| Cause 1: Unallocated number   | Misdialed phone number| DIALPLAN_DEFECT (User)  | Zero alert (Audit log) |
+------------+-------------------------------+-----------------------+-------------------------+------------------------+
```

---

## 5. Security, Privacy & Compliance Safeguards

In compliance with Kenya Airways SecOps and global telecommunications privacy regulations:
1. **Zero Audio Payload Storage:** Nawari captures packet headers, RTCP reports, and SIP transaction metadata. **No voice payloads, RTP packet bodies, or audio files are recorded or stored.**
2. **Caller ID Pseudonymization:** All customer and passenger phone numbers are masked upon ingestion (`+254 722 123 456` $\to$ `+2547****456`).
3. **No PII Retention:** Passenger names, ticket numbers, and credit card credentials are never parsed, indexed, or stored.
