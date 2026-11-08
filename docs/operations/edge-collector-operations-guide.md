# Nawari Edge Collector Operations Guide

**Scope:** Nawari Trans-WAN Edge Telemetry and Voice Probe Architecture  
**Target Infrastructure:** Remote Station Edge Nodes (e.g. MBA, KIS, LHR, CDG, DXB, JNB)  
**Security & Commissioning Status:** Simulation & Staging Active — Physical Production Gated pending Phase 8.2  

---

## 1. Overview & Architecture

The Nawari Edge Collector daemon (`services.multisite.edge_forwarder`) provides autonomous outstation telemetry collection and store-and-forward buffering. It is engineered to maintain operational resilience during WAN severance, satellite latency spikes, and link degradation between outstations and the primary JKIA Datacenter hub.

```
+-------------------------------------------------------------------------+
|                        Remote Station Edge Node                         |
|                                                                         |
|  +--------------------+   +-------------------+   +------------------+  |
|  | Local Telemetry    |   | Edge Voice Probe  |   | System Monitors  |  |
|  | (SNMP / Syslog)    |   | (SIP / RTP Media) |   | (CPU / Disk / IF)|  |
|  +---------+----------+   +---------+---------+   +--------+---------+  |
|            |                        |                      |            |
|            +------------------------+----------------------+            |
|                                     |                                   |
|                                     v                                   |
|                     +-------------------------------+                   |
|                     | Priority-Aware Spool Manager  |                   |
|                     | (/var/spool/nawari/edge.db)   |                   |
|                     | - Hard Limit: 50 MB           |                   |
|                     | - Critical Alerts: Protected  |                   |
|                     | - Diagnostic Telemetry: Pruned|                   |
|                     +---------------+---------------+                   |
|                                     |                                   |
|                                     v                                   |
|                     +-------------------------------+                   |
|                     | Edge Forwarder Transmitter    |                   |
|                     | - Exponential Backoff / Jitter|                   |
|                     | - Clock Drift Offset Tracking |                   |
|                     +---------------+---------------+                   |
+-------------------------------------|-----------------------------------+
                                      | Trans-WAN Link
                                      v
+-------------------------------------------------------------------------+
|                         Central JKIA Hub Gateway                        |
|                                                                         |
|  +-------------------------------------------------------------------+  |
|  | Central Telemetry Receiver (services.multisite.edge_forwarder)    |  |
|  | - Stream Segregation: Live vs Replayed (is_replayed=True)         |  |
|  | - Replay Discard Guard: Replayed data never closes live incidents |  |
|  | - Duplicate ID Rejection: (record_uuid deduplication)             |  |
|  | - Backpressure Throttling: Replay rate limited to protect live bus|  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

---

## 2. Store-and-Forward Spool Operations

### 2.1 Storage Specifications
- **Database Engine:** Embedded SQLite with Write-Ahead Logging (`WAL` mode).
- **Default Database Path:** `/var/spool/nawari/edge.db`
- **Maximum Spool Size:** 50 MB (`52,428,800` bytes).
- **Pruning Trigger:** Spool utilization $\ge 90\%$ (or exceeding maximum record threshold).

### 2.2 Priority-Aware Pruning Scheme
When spool storage approaches capacity, the spool engine enforces priority-ordered pruning:
1. **Priority 2 (Diagnostic Telemetry):** Pruned first on FIFO basis.
2. **Priority 1 (Standard Operational Telemetry):** Pruned next on FIFO basis.
3. **Priority 0 (Critical Alerts & Audit Events):** **Strictly protected.** Under no circumstance will critical P1 alerts or tamper-evident audit records be dropped to accommodate routine metrics.

### 2.3 Quarantine of Corrupted Records
If an unparseable or corrupted payload is detected during read operations:
- The record is flagged as `CORRUPTED`.
- The payload is moved to the quarantine table (`spool_quarantine`).
- A high-priority system telemetry event is generated to alert the NOC of local SQLite tampering or disk corruption.

---

## 3. Trans-WAN Voice Synthetic Probing

The edge daemon executes periodic voice probing across WAN circuits (`services.multisite.wan_voice_probes`).

### 3.1 Signaling Reachability vs Media Path Quality
The probe engine strictly distinguishes between SIP signaling reachability and voice media transmission:

| Probe Type | Mechanism | Capabilities & Limitations | Metric Produced |
| :--- | :--- | :--- | :--- |
| **SIP OPTIONS Ping** | SIP OPTIONS transaction to Avaya SBCE / SM | Verifies SIP stack responsiveness and trunk reachability. **Does NOT guarantee voice call quality.** | `reachability`, `rtt_ms` |
| **Synthetic Media Call** | SIP INVITE + Bidirectional RTP/RTCP | Measures latency, jitter, packet loss, and codec degradation under real network load. | `mos`, `rtt_ms`, `jitter_ms`, `loss_pct` |

> [!WARNING]
> An E-model Mean Opinion Score (MOS) calculation is **strictly invalid** if bidirectional media streams are not present. A SIP OPTIONS ping yielding 0 ms packet loss must never be reported as MOS 4.40; it must be recorded as `signaling_only: true` with MOS `null`.

### 3.2 ITU-T G.107 E-Model Computation
For valid media probes, the R-factor and MOS are computed via standard G.107 equipment impairment algorithms:
$$R = R_0 - I_s - I_d - I_e + A$$
$$\text{MOS} = 1.0 + 0.035 R + 7 \times 10^{-6} R (R - 60)(100 - R)$$

---

## 4. Transmission, Backoff & Central Ingestion

### 4.1 Exponential Backoff with Jitter
During WAN outages, transmission attempts to JKIA central receiver back off exponentially to avoid thundering-herd saturation upon link restoration:
- Initial Interval: 2.0 seconds.
- Multiplier: 2.0x.
- Jitter: Uniform random $\pm 25\%$.
- Maximum Backoff: 300.0 seconds.

### 4.2 Stream Segregation & Replay Guards
Upon reconnection, the receiver partitions incoming telemetry into two distinct streams:
- **Live Stream (`is_replayed=False`):** Ingested with primary scheduling priority; drives real-time SLI metrics and NOC alerts.
- **Replayed Stream (`is_replayed=True`):** Ingested via throttled worker queues for historical baseline building and auditing.

> [!IMPORTANT]
> **Operational Rule:** Replayed telemetry arriving from an outstation buffer **cannot close or resolve active NOC incidents**. Incident closure requires fresh, real-time verification observations.

---

## 5. Systemd Service Configuration

On Linux edge appliances (e.g. Dell PowerEdge / Raspberry Pi Industrial at outstations), the daemon is supervised by `systemd`:

```ini
# /etc/systemd/system/nawari-edge-collector.service
[Unit]
Description=Nawari Outstation Edge Collector Daemon
After=network.target local-fs.target
Wants=network-online.target

[Service]
Type=simple
User=nawari
Group=nawari
WorkingDirectory=/opt/nawari
Environment=PYTHONPATH=/opt/nawari
Environment=NAWARI_STATION_ID=MBA-STATION
Environment=NAWARI_SPOOL_DIR=/var/spool/nawari
Environment=NAWARI_HUB_ENDPOINT=https://hub.nawari.kenya-airways.com:8443
ExecStart=/opt/nawari/.venv/bin/python3 -m services.multisite.edge_forwarder --station MBA-STATION
Restart=always
RestartSec=5s
MemoryMax=128M
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

To control the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nawari-edge-collector
sudo systemctl status nawari-edge-collector
```
