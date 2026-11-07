# Nawari Phase 2: Configuration & Device Provisioning Engine Report

## 1. Executive Summary

Phase 2 implements the automated, declarative device provisioning engine for **Nawari**.
In accordance with the foundational architecture directive:
> **"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services."**

The provisioning engine provides a version-controlled, declarative model for defining host groups, network devices, voice infrastructure (Avaya SBCE), interfaces, templates, and macros. It ensures that monitoring configuration is managed entirely as code, with full dry-run plan generation and a strictly verified **idempotency contract**.

---

## 2. Core Architecture of the Provisioning Engine

The engine is located in `services/api/` and consists of five core components:

```text
services/api/
├── client/
│   ├── exceptions.py       # Typed error contracts (ZabbixAPIError, ZabbixAuthError, etc.)
│   ├── models.py           # Strongly typed Zabbix entity models & enums
│   └── zabbix_client.py    # Robust JSON-RPC 2.0 client with retry backoff
├── config.py               # Typed settings & runtime secret reference expansion
├── provisioning/
│   ├── schema.py           # YAML desired-state schema models & directory loader
│   ├── diff.py             # Deterministic state comparison & change report generator
│   └── reconciler.py       # Idempotent apply engine
└── cli.py                  # Operator CLI (status, plan, apply)
```

---

## 3. Key Technical Capabilities

### A. Dynamic Secret Reference Resolution
YAML configurations support dynamic environment variable injection:
- `${VARIABLE_NAME}`
- `${VARIABLE_NAME:-default_value}`
This guarantees that sensitive SNMPv3 authentication passphrases, privacy keys, and API tokens are never written into committed Git files.

### B. Zabbix 7.4 API Client
- Implements strict JSON-RPC 2.0 over HTTP/HTTPS.
- Supports both **Bearer API Token authentication** (preferred in Zabbix 7.4) and standard `user.login` session tokens.
- Handles Zabbix 7.4-specific schema changes: `selectHostGroups` instead of legacy `selectGroups`.
- Includes exponential backoff and retry handling for transient connectivity interruptions.

### C. Deterministic Diff Engine
Before any change is committed to Zabbix, the diff engine fetches current live state and computes:
- Missing host groups to create
- Missing hosts to create
- Property updates (labels, descriptions, status)
- Group membership changes
- Template linkage updates (preventing duplicate item conflicts)
- Interface updates (IP, port, SNMPv2 community, SNMPv3 `authPriv` parameters)
- Macro updates (handling secret macro masking)

### D. Idempotency Contract & Exit Gate Verification
When `nawari apply` is executed:
1. Pass 1 applies the computed changes to Zabbix.
2. Pass 2 immediately re-evaluates the live Zabbix state against the desired state.
3. If Pass 2 detects any changes, the process exits with an error code.
4. **Result:** Achieved **0 changes on secondary pass** across all provisioned entities.

---

## 4. Provisioned Infrastructure State

Using declarative definitions in `provisioning/zabbix/`:
- `provisioning/zabbix/host_groups.yaml`
- `provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml`
- `provisioning/zabbix/hosts/core_network.yaml`

The following objects were provisioned in the live local Zabbix 7.4 instance:

| Entity Type | Technical Identifier | Name / Label | Assigned Groups | Linked Templates |
| :--- | :--- | :--- | :--- | :--- |
| **Host Group** | `Core Network` | Core Network | — | — |
| **Host Group** | `Voice Infrastructure` | Voice Infrastructure | — | — |
| **Host Group** | `Edge SBC` | Edge SBC | — | — |
| **Host Group** | `Communications Applications` | Communications Applications | — | — |
| **Host** | `avaya-sbce-01` | Avaya SBCE Primary (HQ-DMZ) | Voice Infrastructure, Edge SBC | Network Generic Device by SNMP |
| **Host** | `core-gw-01` | Core Distribution Gateway 01 | Core Network | Network Generic Device by SNMP |

---

## 5. Automated Verification Results

All unit and integration tests passed:

```text
pytest tests/ -v
============================== 24 passed in 3.29s ==============================

./scripts/verify_phase2.sh
======================================================================
NAWARI PHASE 2 ACCEPTANCE VERIFICATION
======================================================================
[TEST] Unit Tests (Schema, Diff Engine, Secret Expansion) ... PASS
[TEST] Zabbix API Client Status & Connectivity ... PASS
[TEST] Declarative Desired-State Plan (Dry-Run) ... PASS
[TEST] Idempotent Reconciliation (Exit Gate: 0 changes on pass 2) ... PASS
[TEST] Live Provisioning Idempotency Test Suite ... PASS
======================================================================
RESULTS: 5 passed, 0 failed
>> ALL 5 PHASE 2 ACCEPTANCE CRITERIA MET SUCCESSFULLY! <<
```

---

## 6. Addressing Governance & Production Reality Gates

In response to the architecture review, the following production reality gates are formalized:

1. **Credential Sanitization:** All hardcoded credentials have been stripped from documentation, integration tests, and scripts. Credentials exist strictly in `.env`.
2. **Resource Consumption:** The ~309 MiB memory measurement is classified as a local Mac baseline. Sizing on `mon-grafana01` will be re-benchmarked under simulated polling loads on Ubuntu.
3. **Version Pinning & Upgrades:** `zabbix/zabbix-server-pgsql:alpine-7.4-latest` pulls patch releases along the stable 7.4 branch (currently `7.4.16`). Minor patch upgrades follow semantic versioning without breaking schema changes.
4. **SNMP Traps Network Gate:** Local test traps validate container spooling; cross-network UDP transport, firewall validation, and Avaya enterprise MIB resolution remain gated for production staging.
5. **Production Readiness:** `docker/compose.prod.yaml` is documented as an initial configuration baseline, not proof of deployment.
