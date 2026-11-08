# Phase 13.13 — Service Level Indicators (SLI) & Objectives (SLO) Standard

## Executive Summary

Phase 13.13 defines the formal mathematical standards, evaluation methods, and operational thresholds for Service Level Indicators (SLIs) and Service Level Objectives (SLOs) across Kenya Airways' mission-critical network and communications services.

Following Google Site Reliability Engineering (SRE) principles, Nawari decouples **SLI measurement** from **SLO targets** and **SLA contractual commitments**. Furthermore, Nawari enforces a strict **Telemetry Integrity Guard**: missing or unconfirmed telemetry is explicitly tracked as an operational defect (`unknown_minutes`) that reduces availability and flags coverage deficits, completely eliminating false 100% availability claims.

---

## 1. Authoritative SLO Register (30-Day Rolling Window)

| Service ID | Service Name | Criticality Tier | Target SLO | Contractual SLA | Allowed Monthly Downtime (30-day budget) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SVC-ENTERPRISE-NETWORK` | Enterprise Network Core | Tier 1 | **99.99%** | 99.95% | **4.32 minutes** (259.2 seconds) |
| `SVC-WAN-CONNECTIVITY` | WAN & Outstation Connectivity | Tier 1 | **99.95%** | 99.90% | **21.60 minutes** |
| `SVC-SIP-CARRIER` | Carrier Ingress & SIP Trunking | Tier 1 | **99.99%** | 99.95% | **4.32 minutes** |
| `SVC-CORP-TELEPHONY` | Corporate Telephony Core | Tier 1 | **99.95%** | 99.90% | **21.60 minutes** |
| `SVC-CONTACT-CENTER-INBOUND` | Inbound Contact Center | Tier 1 | **99.90%** | 99.80% | **43.20 minutes** |
| `SVC-IVR-SELFSERVICE` | Interactive Voice Response | Tier 2 | **99.80%** | 99.50% | **86.40 minutes** |
| `SVC-MONITORING-PLATFORM` | Observability & Monitoring Platform | Tier 1 | **99.95%** | 99.90% | **21.60 minutes** |

---

## 2. Multi-Dimensional SLI Formulation

Unlike simplistic ping-uptime metrics, Nawari evaluates four independent dimensions of service reliability:

### A. Availability SLI
$$\text{Availability SLI} = \frac{\text{Good Operational Minutes (Reachable \& Responding)}}{\text{Total Valid Operational Minutes}} \times 100\%$$
Where:
$$\text{Total Valid Minutes} = \text{Good Minutes} + \text{Degraded Minutes} + \text{Outage Minutes} + \text{Unknown Minutes}$$

### B. Latency / Performance SLI
$$\text{Performance SLI} = \frac{\sum \text{Transactions meeting Latency Threshold}}{\sum \text{Total Valid Transactions}} \times 100\%$$
- **SIP INVITE Post-Dial Delay (PDD)**: $\le 500\text{ms}$
- **Core Switch Transit Delta RTT**: $\le 15\text{ms}$
- **Zabbix Web UI HTTP Connect**: $\le 200\text{ms}$

### C. Voice Quality SLI
$$\text{Quality SLI} = \frac{\sum \text{Voice Call Intervals with } R \ge 80 \text{ and } MOS \ge 4.0}{\sum \text{Total Measured Bidirectional Voice Intervals}} \times 100\%$$

### D. Coverage SLI
$$\text{Coverage SLI} = \frac{\text{Minutes with Fresh, Trustworthy Telemetry}}{\text{Total Expected Operational Minutes}} \times 100\%$$
- If $\text{Coverage} < 80\%$, the engine automatically flags `COVERAGE_DEFICIT`, clamps availability, and prohibits claiming green compliance.
