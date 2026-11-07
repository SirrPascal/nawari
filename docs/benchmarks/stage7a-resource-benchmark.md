# Nawari Stage 7A: Endpoint Agent Resource Benchmark Report

**Document Version:** 1.0.0  
**Status:** Empirical Measurement Baseline  
**Date:** 2026-11-07  
**Test Host:** macOS Darwin 27.0.1 (arm64, Apple Silicon)  
**Python Runtime:** Python 3.13.15 64-bit  
**Measurement Script:** [`scripts/benchmark_endpoint_agent.py`](file:///Users/madeira/Desktop/Projects/nawari/scripts/benchmark_endpoint_agent.py)

---

## 1. Executive Summary

In response to the Phase 7 architectural review, this benchmark provides **actual measured runtime resource consumption** for the Nawari Endpoint Agent Core (Stage 7A). 

Rather than relying on theoretical estimates (such as the earlier 85 MiB projection for central ingestion), these measurements demonstrate that the standalone Python endpoint agent is exceptionally lightweight, initializing in **under 1 millisecond** and operating with a memory footprint of **under 30 MiB**.

---

## 2. Empirical Benchmark Results

| Metric | Measured Value | Architectural Budget Limit | Status | Notes |
|---|---|---|---|---|
| **Cold Process Execution (CLI)** | **120.0 ms** | < 500.0 ms | **PASS** | Complete shell command invocation from cold python3 launch to process exit |
| **Agent Internal Init Latency** | **0.93 ms** | < 100.0 ms | **EXCEEDED (100x Faster)** | In-process time to parse config, load identity, initialize platform adapter and scheduler |
| **Idle Memory RSS** | **28.70 MiB** | < 45.0 MiB | **PASS (36% Headroom)** | Baseline Resident Set Size after initialization |
| **Active Probing Memory RSS** | **29.55 MiB** | < 50.0 MiB | **PASS (40% Headroom)** | Memory RSS during active gateway ping and mock target execution |
| **Active CPU Utilization** | **0.39% of 1 core** | < 5.0% of 1 core | **EXCEEDED (12x Lower)** | Average CPU utilization across 5 continuous diagnostic cycles |
| **Active Thread Count** | **1 thread** | < 5 threads | **PASS** | Pure asyncio event loop execution |
| **5 Diagnostic Cycles Duration** | **10.19 s** | < 30.0 s | **PASS** | Workload: 5 consecutive cycles of 3x gateway ICMP pings + loopback reachability checks |
| **Logging Overhead (1,000 lines)** | **15.34 ms** | < 100.0 ms | **PASS** | 15.34 microseconds per sanitized log line |
| **Local Spool Footprint** | **5 records (~3.8 KB)** | < 10 MB | **PASS** | Standard JSONL append-only format |

---

## 3. Analysis & Key Findings

1. **Memory Efficiency:**
   The entire Python agent runtime, including UUID identity management, asyncio scheduler, platform adapter, and disk spooler, occupies only **29.55 MiB RSS**. This leaves virtually zero impact on modern employee laptops (which typically possess 8 GiB to 32 GiB of RAM).
2. **Negligible CPU Footprint:**
   At **0.39% CPU utilization**, the agent executes unobtrusively in the background without causing battery drain or thermal throttling on user laptops.
3. **Sub-Millisecond Startup:**
   With an initialization latency of **0.93 ms**, the agent can be executed as a transient single-shot CLI probe (`nawari-agent run-once`) via cron/Task Scheduler or as a standing daemon with equal efficiency.
