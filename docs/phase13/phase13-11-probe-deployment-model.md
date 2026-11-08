# Phase 13.11 — Probe Deployment Model & Topology

## Deployment Topologies & Probing Vectors

Nawari's path observability architecture implements a multi-tier probe deployment model tailored to Kenya Airways' operational environments.

```
       [ Central Core: Pride Centre DC / JKIA ]
                   |            |
       +-----------+            +-----------+
       |                                    |
[ Primary MPLS: Safaricom ]        [ Backup MPLS / DIA: Telkom / BT ]
       |                                    |
       +-----------------+------------------+
                         |
           +-------------+-------------+
           |                           |
   [ Domestic Hubs ]          [ International Hubs ]
   - MBA (Mombasa)            - LHR (London Heathrow)
   - KIS (Kisumu)             - DXB (Dubai)
   - EDL (Eldoret)            - AMS (Amsterdam)
```

---

## 1. Outstation Synthetic Probe Targets

| Outstation ID | Station Name | Primary Circuit | Backup Circuit | Probe Types Active | Target Endpoints |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `MBA-AIRPORT` | Moi International Airport (Mombasa) | Safaricom MPLS 20M | Telkom Kenya DIA 10M | Paris-UDP, ICMP, SIP OPTIONS, Voice-E-Model | `10.2.156.131` (SBC), `10.2.1.254` (Core) |
| `KIS-AIRPORT` | Kisumu International Airport | Telkom Kenya MPLS 10M | Safaricom LTE Backup | Paris-UDP, ICMP, Voice-E-Model | `10.2.156.131` (SBC), `10.2.1.254` (Core) |
| `EDL-AIRPORT` | Eldoret International Airport | Safaricom MPLS 10M | Airtel DIA 5M | Paris-UDP, ICMP, Voice-E-Model | `10.2.156.131` (SBC) |
| `LHR-TERMINAL4`| London Heathrow Terminal 4 | BT Global MPLS 50M | Colt DIA 20M | Paris-UDP, SIP OPTIONS, DNS, HTTP | `10.2.156.131` (SBC), `mon-grafana01` |
| `DXB-TERMINAL1`| Dubai International Terminal 1 | Etisalat MPLS 20M | Du DIA 10M | Paris-UDP, ICMP, SIP OPTIONS | `10.2.156.131` (SBC) |
| `AMS-SCHIPHOL` | Amsterdam Airport Schiphol | KPN MPLS 20M | Ziggo DIA 10M | Paris-UDP, ICMP, SIP OPTIONS | `10.2.156.131` (SBC) |

---

## 2. Probe Specifications

### A. Trans-WAN Voice Probe
- **Engine**: `TransWanVoiceProber`
- **Methodology**: Synthetic periodic voice burst simulating G.711 / G.729 RTP codec streams.
- **Metrics Collected**:
  - Round-Trip Time ($RTT_{ms}$)
  - One-Way Delay estimate ($\frac{RTT}{2}$)
  - Inter-arrival packet jitter ($Jitter_{ms}$)
  - Packet loss rate ($Loss_{\%}$)
  - Calculated Transmission Rating Factor ($R$)
  - Listening Mean Opinion Score ($MOS$)
- **Failover Trigger**:
  - $R < 70.0$ or $MOS < 3.8$ initiates automatic failover recommendation to backup carrier circuit.

### B. SIP OPTIONS Signaling Probe
- **Engine**: `SipOptionsResult`
- **Methodology**: Periodic RFC 3261 `OPTIONS` heartbeat towards edge SBC and remote session managers.
- **Safety Boundary**: Establishes signaling reachability only. Does **not** claim or verify RTP media transmission.

### C. Application Endpoint Probes
- **DNS Probe**: Validates resolution times and record integrity (e.g. `localhost`, `sbc.kenya-airways.com`).
- **TCP Connect Probe**: Measures three-way handshake time ($RTT_{syn}$) against critical listener ports (`8088` Zabbix web, `5038` Asterisk AMI, `5060` SIP).
- **HTTP/HTTPS Probe**: Measures total round-trip time, status codes, and payload response headers.

