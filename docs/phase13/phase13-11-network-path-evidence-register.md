# Phase 13.11 — Network Path Evidence Register

## Validation Evidence Summary

- **Execution Date**: 2026-11-08T19:39:22Z
- **Nawari Revision**: `5f5737f`
- **Sentra Baseline Revision**: `9970404` (Clean & Untouched)
- **Snapshot Manifest**: [`provisioning/zabbix/snapshots/phase13_11_network_path_evidence.json`](file:///Users/madeira/Desktop/Projects/nawari/provisioning/zabbix/snapshots/phase13_11_network_path_evidence.json)
- **Test Suite**: [`tests/unit/test_phase13_11_network_path_observability.py`](file:///Users/madeira/Desktop/Projects/nawari/tests/unit/test_phase13_11_network_path_observability.py) (10/10 PASS)

---

## 1. Verified Path Test Results

| Test Scenario | Test Method | Outcome | Measured Parameter |
| :--- | :--- | :--- | :--- |
| **Paris Traceroute Checksum Invariance** | `test_paris_traceroute_checksum_invariance` | `PASSED` | RFC 1071 Checksum = `0x5432` across sequence variations |
| **CoPP Guard Protection** | `test_copp_guard_intermediate_hop` | `PASSED` | Silent hop 2 classified as `TIMEOUT_COPP`; 0% end-to-end loss |
| **Loss Onset Localization** | `test_loss_onset_localization` | `PASSED` | `loss_onset_hop = 2`; 100% downstream unreachable |
| **Latency Jump Localization** | `test_latency_jump_localization` | `PASSED` | Hop 2 $\Delta\text{RTT} = 56.0\text{ms}$ flagged as latency jump |
| **RFC 4950 MPLS Stack Decoding** | `test_mpls_label_stack_rfc4950` | `PASSED` | Decoded Label 1001 (EXP=5, Voice EF) and Label 2002 (EXP=0, BOS=1) |
| **Path Hashing & Divergence Index** | `test_path_hashing_and_route_churn` | `PASSED` | Hash changed, divergence detected at hop index 2 |
| **Endpoint Probing (DNS, TCP, HTTP)**| `test_endpoint_probes_dns_tcp_http` | `PASSED` | DNS 4.42ms, TCP 0.26ms, HTTP 200 in 45.51ms |
| **Trans-WAN Voice Probe (Optimal)** | `test_trans_wan_voice_prober_optimal` | `PASSED` | MBA circuit: $R=84.5$, $MOS=4.37$, status `OPTIMAL` |
| **Trans-WAN Voice Failover** | `test_trans_wan_voice_prober_degraded_failover`| `PASSED` | KIS degraded circuit: $R<70$, failover recommended |
| **SIP OPTIONS Media Guard** | `test_sip_options_reachability_guard` | `PASSED` | Signaling verified, RTP media claim correctly rejected |

---

## 2. Live Runtime Snapshot Extract

```json
{
  "metadata": {
    "phase": "13.11",
    "title": "Network Path and WAN Observability",
    "status": "VALIDATED_STAGING",
    "hard_production_deny": true
  },
  "paris_traceroute_evidence": {
    "checksum_compensation_verified": true,
    "checksum_sample": "0x5432",
    "flow_hashing_invariant": "RFC 1071 16-bit 1's complement conserved across sequences"
  },
  "hop_analyzer_evidence": {
    "destination_reached": true,
    "total_hops": 4,
    "copp_guard_active": true,
    "copp_hop_index": 2,
    "latency_jump_detected": true,
    "latency_jump_delta_ms": 56.0
  },
  "mpls_label_evidence": {
    "mpls_extracted": true,
    "outer_label": 1001,
    "traffic_class_exp": 5,
    "qos_domain": "Expedited Forwarding (Voice)"
  },
  "route_divergence_evidence": {
    "primary_hash": "c38df34a248ef045dde7560373f54dc1d3af66d57e2ea399d2f0982cdc29b794",
    "alternate_hash": "20c49b339093155dd17760c1fcbe2157590dcb9daa1ddde894085cdbc48084b9",
    "divergent_hop_index": 2,
    "route_changed": true
  },
  "endpoint_probes_evidence": {
    "dns": {"target": "localhost", "status": "NOERROR", "time_ms": 4.42},
    "tcp": {"target": "127.0.0.1:8088", "status": "SUCCESS", "time_ms": 0.26},
    "http": {"target": "http://127.0.0.1:8088", "code": 200, "time_ms": 45.51}
  },
  "trans_wan_outstation_evidence": {
    "station": "MBA-AIRPORT",
    "circuit": "CIRCUIT-MPLS-SAFARICOM-MBA-01",
    "rtt_ms": 38.5,
    "mos": 4.37,
    "status": "OPTIMAL"
  }
}
```
