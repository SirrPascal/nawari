# Phase 13.9 — Telemetry Gaps, Physical Blockers & Commissioning Action Plan

**Author:** Antigravity Engineering (pair programming with Kenya Airways Project Team)  
**Date:** 2026-11-08  
**Status:** Documented Operational Register  
**Platform:** Zabbix 7.4.16 / PostgreSQL Engine on `mon-grafana01`  
**Purpose:** Formal identification of physical telemetry blockers, missing network dependencies, and uncommissioned metrics.

---

## 1. Executive Summary

In strict accordance with the programme principles (**Dependency-Aware Execution** and **No Fabricated Completion**), Phase 13.9 identifies and registers all physical connectivity limitations, gated hardware metrics, and external integration dependencies.

Rather than synthesizing mock numbers or claiming complete physical commissioning prematurely, this register provides an actionable, dependency-aware gap analysis for Kenya Airways engineering leadership.

---

## 2. Blocked Physical Access Targets Ledger

The following production hardware addresses reside on Kenya Airways internal private RFC 1918 subnets (`10.2.156.0/24`, `10.2.1.0/24`, `10.102.10.0/24`) and are currently unreachable from the standalone staging server:

```
+----+----------------------------------+------------------+-------+-------------------+---------------------------------------------+
| ID | Production Appliance Description | Target IP        | Port  | Physical Location | Required Networking Prerequisite            |
+----+----------------------------------+------------------+-------+-------------------+---------------------------------------------+
| 01 | Core Distribution Gateway 01     | 10.2.1.1         | 161/u | Pride Center DC   | Provision L3 static route or IPsec tunnel   |
| 02 | Avaya SBCE Secondary (Standby)   | 10.2.156.132     | 161/u | Pride Center DMZ  | Add secondary node route to monitoring VLAN |
| 03 | Avaya SBCE DR (Airport Gateway)  | 10.2.156.45      | 161/u | JKIA Terminal 1A  | Establish trans-WAN route across MPLS       |
| 04 | Avaya Session Manager Primary    | 10.2.156.22      | 5060/t| Pride Center Core | Open SIP TCP port 5060 on core firewall     |
| 05 | Avaya Session Manager Secondary  | 10.2.156.23      | 5060/t| Pride Center Core | Open SIP TCP port 5060 on core firewall     |
| 06 | Avaya Session Manager DR         | 10.2.156.28      | 5060/t| JKIA Terminal 1A  | Open SIP TCP port 5060 across airport link  |
| 07 | Avaya CM Duplex Server           | 10.102.10.25     | 161/u | Pride Center Core | Route DC voice management VLAN              |
| 08 | Avaya CM Standby Server          | 10.2.156.27      | 161/u | Pride Center Core | Route standby server management IP          |
| 09 | Avaya CM Cluster VIP             | 10.2.156.30      | 161/u | Pride Center Core | Route CM active cluster VIP interface       |
| 10 | Avaya G450 Media Gateway HQ      | 10.2.156.60      | 161/u | Pride Center Core | Route gateway management VLAN               |
+----+----------------------------------+------------------+-------+-------------------+---------------------------------------------+
```

---

## 3. Gated Hardware & Integration Telemetry Register

```
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| ID | Metric Key              | Subsystem & Domain                | Technical Blocker & Commissioning Requirement                   |
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| 01 | avaya.g450.dsp_util     | G450 Transcoding DSP Utilization  | Physical audit required to identify installed MP20/80/120/160   |
|    |                         |                                   | childboards; requires MGP CLI script or vendor MIB upgrade.     |
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| 02 | avaya.cm.live_rtcp      | Continuous Real-Call RTCP Jitter  | CM MIB table .67 is an hourly aggregated bucket; continuous     |
|    |                         |                                   | real-call RTCP requires deploying an eBPF/sFlow packet pipeline.|
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| 03 | ems.sip.server_errors   | SBCE Granular 4xx/5xx Error Rates | Requires REST API token authentication on SBCE EMS appliance;   |
|    |                         |                                   | basic SNMP host metrics are active, deep API uncommissioned.    |
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| 04 | wfo.verint.pipeline     | Verint Contact Center Ingestion   | Third-party Verint recording API uncommissioned; partition disk |
|    |                         |                                   | checks active; vendor integration agreement pending.            |
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
| 05 | carrier.deep.sla_pct    | Safaricom Carrier SLA Commitment  | Direct carrier SLA API uncommissioned; live SIP OPTIONS probe  |
|    |                         |                                   | is active and provides genuine transport reachability.          |
+----+-------------------------+-----------------------------------+-----------------------------------------------------------------+
```

---

## 4. Commissioning Action Plan

```
+---------------------------------------------------------------------------------------------------+
|                                 TELEMETRY COMMISSIONING ROADMAP                                   |
+-------------------+-----------------------------------+-------------------+-----------------------+
| Milestone         | Action Required                   | Responsible Team  | Target Phase          |
+-------------------+-----------------------------------+-------------------+-----------------------+
| Phase 13.9 (Now)  | Audit & gate unverified telemetry | Antigravity / KQ  | COMPLETED (Audited)   |
| Phase 13.10       | Implement genuine voice assurance | Antigravity / KQ  | NEXT (In-flight)      |
| Network L3 Window | Configure IPsec / static routing  | KQ Network Ops    | Post-Phase 13.15      |
| SNMPv3 Cutover    | Apply Admin_sha256 to appliances  | KQ Voice Ops      | Production Gate 8.2   |
| EMS API Token     | Provision SBCE EMS API account    | KQ Telecoms Admin | Production Gate 8.2   |
+-------------------+-----------------------------------+-------------------+-----------------------+
```
