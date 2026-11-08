# Phase 13.12 — Service Impact & Failure Mode Matrix

## Matrix Overview

This matrix maps technical infrastructure failure modes to Kenya Airways business service impact levels, designated Zabbix notification actions, and affected user operational groups.

---

## 1. Impact Matrix

| Failure Mode | Affected Infrastructure | Redundancy State | Business Service Impact | Causal Classification | Triggered Action ID | Target Recipients |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary SBCE Node Halt** | `avaya-sbce-01` | Secondary SBCE `avaya-sbce-02` active | `SVC-SIP-CARRIER` (DEGRADED) | `REDUNDANCY_FAILOVER` | **Action 12** | Telephony Administrators |
| **Dual SBCE Cluster Outage** | `avaya-sbce-01` & `avaya-sbce-02` | Redundancy completely exhausted | `SVC-SIP-CARRIER` (TOTAL OUTAGE) | `ROOT_CAUSE` | **Action 10** | All 5 Recipients (incl. Service Desk) |
| **Core Switch Uplink Down** | `jkia-core-sw01` (Port-Channel 1) | Secondary core switch carrying traffic | `SVC-ENTERPRISE-NETWORK` (DEGRADED) | `ROOT_CAUSE` | **Action 14** | Network Administrators |
| **Downstream Ping Loss** | `avaya-cm-01`, `avaya-sm-01`, `avaya-g450-01` | Caused by core switch link down | Multiple dependent services | `DOWNSTREAM_SYMPTOM` | *Suppressed* | Attached to Core Switch Incident |
| **Primary WAN MPLS Drop** | `CIR-MPLS-SAFARICOM-01` | Telkom Kenya backup circuit active | `SVC-WAN-CONNECTIVITY` (DEGRADED) | `REDUNDANCY_FAILOVER` | **Action 14** | Network Administrators |
| **Dual WAN Link Cut** | `CIR-MPLS-SAFARICOM-01` & `CIR-MPLS-TELKOM-01` | Complete station isolation | `SVC-WAN-CONNECTIVITY` (TOTAL OUTAGE) | `ROOT_CAUSE` | **Action 10** | All 5 Recipients (incl. Service Desk) |
| **WFO Spool Storage Warning** | `avaya-cms-01` (/var/spool < 15%) | Local disk storage threshold | `SVC-COMPLIANCE-RECORDING` (DEGRADED) | `INDEPENDENT_EVENT` | **Action 12** | Telephony Administrators |
| **Rapid Interface Flap** | `jkia-dist-sw01` (Gi1/0/24) | Flapping $\ge 3$ times in 60s | Local access VLAN | `FLAPPING_DAMPENED` | **Action 13** | Network Administrators |

---

## 2. Notification Action Routing Policy

- **Action 10 (`total_outage`)**: Strictly reserved for events where service impact is `TOTAL_OUTAGE` and redundancy is exhausted. Never dispatched on single member HA failures.
- **Action 11 (`total_outage_recovery`)**: Sent only upon verified restoration of total outages.
- **Action 12 (`telephony_admin`)**: Dispatched for PBX, SBCE, SIP, and voice infrastructure degradations and failovers.
- **Action 13 (`infrastructure_warning`)**: Dispatched for platform capacity, disk warnings, and environmental alerts.
- **Action 14 (`network_reachability`)**: Dispatched for switch link drops, BGP peering drops, and WAN circuit issues.
