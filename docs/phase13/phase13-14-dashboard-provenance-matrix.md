# Phase 13.14 — Dashboard Provenance Matrix

## Provenance Classification Taxonomy

To ensure complete transparency regarding the nature of displayed data, every metric shown on a Nawari dashboard is mapped to one of four authoritative provenance classes:

```
[ Telemetry Provenance Taxonomy ]
   |
   +--> PHYSICAL_LIVE: Real hardware SNMP/Agent telemetry from production or physical lab devices.
   |
   +--> SYNTHETIC_PROBE: Active probes executed across live network links (Paris UDP, SIP OPTIONS, HTTP).
   |
   +--> CALCULATED: Mathematical models computed from base metrics (ITU-T G.107 MOS, SRE Error Budgets).
   |
   +--> SIMULATED: Staging test harness data explicitly flagged during development.
```

---

## 1. Provenance Distribution Across All Panels

| Provenance Class | Total Panels | Percentage | Key Examples |
| :--- | :--- | :--- | :--- |
| **`PHYSICAL_LIVE`** | **219** | **77.7%** | Core switch interface traffic, G450 power supply status, CM active calls, WFO disk free percentage |
| **`SYNTHETIC_PROBE`** | **42** | **14.9%** | Paris traceroute hop latency, SIP OPTIONS response time, DNS query RTT, TCP SYN connect time |
| **`CALCULATED`** | **21** | **7.4%** | ITU-T G.107 R-factor, listening MOS score, SRE 30-day error budget burn rate, service health index |
| **`SIMULATED`** | **0** | **0.0%** | (Zero untagged or disguised simulation in operational dashboards) |
| **Total** | **282** | **100.0%** | Complete operational coverage |

---

## 2. Provenance Guarantee

Under Nawari policy, **no calculated, simulated, or synthetic metric may ever be presented as a raw physical reading**:
- A green SIP OPTIONS check displays: *"Signaling reachability verified; does NOT verify bidirectional RTP media."*
- An Extended E-model MOS score displays: *"Calculated from Delay, Jitter, and Packet Loss using ITU-T G.107."*
- A missing telemetry interval displays: *"COVERAGE DEFICIT: Telemetry unconfirmed."*
