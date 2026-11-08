# Nawari — Recording & Workforce Optimisation (WFO) Observability Architecture

**Standard:** Nawari Phase 13.1 Compliance & Operational Observability  
**Scope:** Telephony Voice Recording, Archival Storage & Operational Health  
**Data Policy:** Strictly Operational Metadata (Audio Payload Excluded)  

---

## 1. Product Identification Requirement

"Workforce Optimisation" (WFO) and "Recording" describe broad enterprise product categories rather than specific, integrable software products. Kenya Airways may deploy:
- **Verint Workforce Engagement / WFO (v15.x)**
- **NICE Engage / Interaction Management**
- **Geomant Contact Expert Recording**
- **Avaya Workforce Optimization Select (AWOS)**
- **Avaya Aura Media Server (AMS) native recording**

### Integration Prerequisite Gate
Before generating device-specific polling templates or deploying custom API collectors:
1. Identify the exact vendor, software edition, and patch release deployed at Kenya Airways.
2. Verify the server roles in the cluster (e.g., Central Application Server, Recording Ingestion Server, Archival/Storage Server, Speech Analytics Node).
3. Review official vendor Serviceability / SNMP / REST API documentation for the confirmed version.
4. Until this confirmation is established, the platform monitors standard host resources and generic recording service availability, displaying unverified vendor-specific metrics as `Not available — requires vendor/product confirmation`.

---

## 2. Supported Operational Observability Model

Nawari monitors the **operational availability, throughput, and capacity** of the recording estate. Nawari does **NOT** collect, process, or store voice audio recordings or customer personal data.

### 2.1 Server Infrastructure Health
- Server CPU utilization, 1-minute load average, physical RAM consumption.
- Operating system uptime and reboot detection.
- Network interface throughput, packet drops, and transmission errors.

### 2.2 Recording Service Availability & Throughput
- **Recording Service Process State:** Daemon availability (e.g. `recording-daemon`, `capture-service`).
- **Active Recording Sessions:** Count of concurrent telephone conversations currently being captured.
- **Recording Ingestion Rate:** Audio files or metadata records ingested per minute.
- **Recording Failure Count:** Calls marked for recording where audio capture failed or timed out.
- **Recording Ingestion Queue Depth:** Number of recorded call payloads buffered in memory or staging disk awaiting archiving.

### 2.3 Storage Capacity & Retention Compliance
- **Storage Partition Utilization:** Capacity utilization on recording storage volumes (SAN, NAS, or local arrays).
- **Projected Days-to-Full (TTE):** Linear regression forecasting the remaining days before storage capacity reaches 90% and 100% saturation.
- **Archive Status:** Rate of successful daily transfers to long-term immutable archives (e.g. S3/Blob or optical archive).

### 2.4 Telephony CTI Connectivity
- **Recorder-to-Communication-Manager CTI Link:** Health of the TSAPI / CSTA / DMCC link between Avaya CM and the recording cluster. Loss of CTI link halts call event signaling, causing recordings to miss metadata (agent ID, calling party, call direction).

---

## 3. Data Protection & Privacy Boundary

> [!CAUTION]
> **Audio Content Exclusion:** Nawari is an operational observability platform. Under Kenya Data Protection Act 2019 and airline regulatory compliance policies, customer audio recordings, customer PII, and credit card / CVV data must **NEVER** be ingested, stored, or visualized in Nawari or Grafana.

