# Phase 13.14 — Panel Description Standard & Register

## Standard Purpose

To ensure that Kenya Airways network engineers, voice administrators, and duty managers can immediately understand and act upon dashboard telemetry without ambiguity, all panels adhere to the **8-Field Panel Description Standard**.

---

## 1. The 8 Mandatory Panel Description Fields

Every panel description is structured as follows:

```markdown
1. **Operational Purpose**: What business or infrastructure state is measured?
2. **Underlying Data Source**: Zabbix - Production or PostgreSQL 17.
3. **Item Key / Metric Name**: The exact metric key (e.g. `net.if.in[ifHCInOctets.1]`, `cm.calls.active`).
4. **Physical Engineering Units**: Bits/sec, Milliseconds, MOS (1.0-4.5), Percentage, Count.
5. **Polling Interval / Resolution**: Frequency of data updates (e.g. 60s, 300s).
6. **Telemetry Classification**: PHYSICAL_LIVE, SYNTHETIC_PROBE, or CALCULATED.
7. **Operational Thresholds**: Warning and Critical boundary limits with hysteresis.
8. **Runbook Reference**: Standard Operating Procedure (SOP) link for incident triage.
```

---

## 2. Exemplary Panel Description Implementations

### Example 1: Core Switch Throughput (Network Observability)
> **Operational Purpose**: Measures inbound bits per second on the JKIA Core Switch primary spine uplink to detect network saturation.  
> **Underlying Data Source**: `alexanderzobnin-zabbix-datasource` (Zabbix - Production)  
> **Item Key**: `net.if.in[ifHCInOctets.101]`  
> **Physical Units**: Bits per second (`bps`), 64-bit High-Capacity counter  
> **Polling Interval**: 60 seconds  
> **Classification**: `PHYSICAL_LIVE`  
> **Operational Thresholds**: Warning > 75%, Critical > 90% link capacity sustained for 3m  
> **Runbook**: `docs/runbooks/SOP-NET-01-core-link-congestion.md`

### Example 2: Avaya Extended E-Model Voice MOS (Communication Observability)
> **Operational Purpose**: Tracks synthetic and live ITU-T G.107 listening Mean Opinion Score (MOS) across carrier SIP trunks.  
> **Underlying Data Source**: `alexanderzobnin-zabbix-datasource`  
> **Item Key**: `voice.rtp.mos`  
> **Physical Units**: MOS score (1.0 to 4.5 scale)  
> **Polling Interval**: 60 seconds (synthetic) / per-call (live)  
> **Classification**: `CALCULATED` (Derived from RTT, Jitter, Packet Loss, and Codec Impairment)  
> **Operational Thresholds**: Warning < 4.0, Critical < 3.8 sustained for 3 samples  
> **Runbook**: `docs/runbooks/SOP-VOICE-04-carrier-quality-degradation.md`
