# Phase 13.11 — Limitations, Boundary Gaps & Blockers

## Overview

Under `HARD_PRODUCTION_DENY = True`, Phase 13.11 establishes algorithmic validation and synthetic simulation of the complete network path and WAN observability architecture. The following limitations, operational gaps, and commissioning prerequisites must be addressed during production site cutovers.

---

## 1. Physical Infrastructure Constraints & Gaps

| Limitation / Gap | Classification | Description | Remediation / Commissioning Step |
| :--- | :--- | :--- | :--- |
| **Physical Outstation Probers** | `CONFIGURED_UNVERIFIED` | Outstation synthetic probing currently models MBA, KIS, and LHR endpoints via staging probers. Physical micro-appliances / probe agents are not yet shipped to outstations. | Deploy Raspberry Pi / containerized probe agents to airport LANs during physical outstation rollout. |
| **Raw Socket Privileges** | `ENVIRONMENTAL_RESTRICTION`| In production Linux environments, Paris Traceroute raw socket creation requires `CAP_NET_RAW` or root privileges. | Configure Linux systemd service with `AmbientCapabilities=CAP_NET_RAW` and avoid running as root. |
| **Carrier MPLS ICMP Extensions** | `CARRIER_DEPENDENCY` | Certain transit providers disable RFC 4950 MPLS ICMP extensions on their core P routers (`no mpls ip icmp` in Cisco/Juniper syntax). | Formalize carrier SLA requirement with Safaricom, Telkom, and BT to enable ICMP tunnel extension reporting. |
| **Asymmetric Return Path Blindness** | `PROTOCOL_LIMITATION` | Forward path probing does not measure return path routing unless reciprocal probers are deployed at remote outstations. | Deploy bidirectional pairing between `mon-grafana01` and remote station probe daemons. |

---

## 2. Safety Compliance Invariants

1. **Zero External Flooding**: Probe packet rates are capped at $\le 5$ packets per second per destination.
2. **Zero Inbound Modification**: Traceroute and synthetic probing remain strictly read-only diagnostics; no router routing tables or interface policies are modified.
3. **Sentra Repository Isolation**: The adjacent repository (`/Users/madeira/Desktop/Projects/sentra`) remains untouched on `main` at `9970404`.

