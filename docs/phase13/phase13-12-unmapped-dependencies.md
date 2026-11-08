# Phase 13.12 — Unmapped Dependencies & Commissioning Gaps

## Overview

Under `HARD_PRODUCTION_DENY = True`, Phase 13.12 models the complete telecommunications and network service dependency architecture and synchronizes it to the Zabbix 7.4 Service Tree. The following items represent unmapped dependencies, production CMDB interfaces, or external vendor integrations that require production commissioning.

---

## 1. Inventory of Unmapped & Gated Dependencies

| Dependency / Component | Category | Current Status | Commissioning Prerequisite |
| :--- | :--- | :--- | :--- |
| **Enterprise CMDB API** | `EXTERNAL_INTEGRATION` | `MOCKED` in `services.integrations.cmdb_adapter` | Connect Nawari CMDB adapter to Kenya Airways ServiceNow / Jira Assets API with service account credentials. |
| **Carrier BGP Peering Sessions** | `PHYSICAL_ROUTING` | `BLOCKED_ACCESS` (on production edge routers) | Enable BGP MIB / SNMP traps on Safaricom and Telkom CE routers to ingest session state changes into `SVC-WAN-CONNECTIVITY`. |
| **SITA Airport Shared Infrastructure (CUTE/CUSS)** | `THIRD_PARTY_SERVICE` | `CONFIGURED_UNVERIFIED` | SITA manages shared kiosk switches at international stations (LHR, DXB). Ingest SITA status feed into `SVC-DCS-LHR`. |
| **Avaya System Manager (SMGR) LDAP Sync** | `INTERNAL_APPLICATION` | `CONFIGURED_UNVERIFIED` | Map SMGR administrative user synchronization into Zabbix user management. |
| **Verint PCI-DSS Compliance Ingestion** | `SECURITY_AUDIT` | `GATED_METRIC` | Connect PCI-DSS pause/resume audit logs from payment gateways to `SVC-COMPLIANCE-RECORDING`. |

---

## 2. Invariants & Safety Measures

1. **Non-Destructive Zabbix Sync**: The service synchronization script idempotently registers services via `service.create` only when not already present, avoiding disruptive overwrites of manual frontend customizations.
2. **Strict Redundancy Protection**: A single node failure in an HA cluster strictly yields `DEGRADED` status and dispatches to operational specialists (Action 12/14), never generating false executive-level total outage alerts.
3. **Repository Integrity**: The Sentra repository (`/Users/madeira/Desktop/Projects/sentra`) remains untouched on `main` at `9970404`.

