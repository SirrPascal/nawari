nc -vz 192.168.1.10 10051# Nawari Technology Compatibility Assessment

**Status:** Proposed decisions; compatibility is not the same as validation  
**Date:** 2026-11-07

## Classification

- **Confirmed:** supported by an official documentation statement or existing Sentra evidence.
- **Validated:** successfully tested in Nawari. None yet; runtime implementation has not started.
- **Unverified:** requires a device, release-specific MIB, network path or local smoke test.
- **Deferred:** intentionally excluded from the initial runtime.

## Decision matrix

| Technology | Decision | Compatibility finding | Current status | Required proof |
|---|---|---|---|---|
| Zabbix 7.4 server | Adopt | Official 7.4 container docs provide PostgreSQL and SNMP-trap deployment paths; versioned image tags are supported. | Confirmed | Compose startup, API login, polling and sender tests |
| PostgreSQL | Adopt | Official Zabbix container variants include PostgreSQL. Use the supported image pairing and a dedicated database/user. | Confirmed | Initialization, restart, backup and restore |
| Zabbix web Nginx/PostgreSQL | Adopt | Official image is listed for PostgreSQL-backed deployments. | Confirmed | Frontend health and API access |
| Zabbix SNMP traps | Adopt | Official flow requires `snmptrapd`, receiver processing, a trap file and shared storage with Zabbix. UDP 162 alone is insufficient. | Confirmed | Generated trap, host matching, fallback item and persistence |
| Grafana | Adopt | Official Zabbix plugin supports dashboards, variables, annotations, problems and API-token authentication. The exact Grafana/plugin pair must be pinned and smoke-tested; do not carry Sentra's 11.5.0 assumption forward. | Confirmed capability; version pair unvalidated | Plugin install/enable, datasource provisioning, dashboard query |
| Grafana Zabbix plugin | Adopt | Plugin documentation requires a full `api_jsonrpc.php` URL and credentials/API token; Zabbix 7.2+ API authentication uses the `Authorization` header. | Confirmed | Provisioned datasource and read-only token |
| Python 3 + FastAPI + Pydantic | Adopt | Fits the required typed modular API and existing Sentra Python expertise. This is an application design choice, not a vendor compatibility claim. | Design decision | Type checks, route tests, API-client contract tests |
| Asterisk 22 | Defer to later profile | Existing Sentra implementation provides a proven reference. AMI is suitable for call control/events, but SIP/TLS/RTP behavior depends on production networking. | Confirmed reference; production path unverified | AMI event correlation, SIP test fixture, authorized network test |
| Zabbix Agent 2 | Defer | Official Zabbix image exists, but endpoint experience needs an explicit measurement design and rollout policy. | Unverified for target estate | Windows/Linux pilot and path probes |
| OpenTelemetry Collector | Defer | Collector architecture supports receiver/processor/exporter pipelines, but no initial source requires it when Zabbix owns monitoring. | Confirmed technology; deferred scope | Reconsider only with a defined telemetry source |
| OpenSearch | Defer | Sentra uses it successfully for event analytics, but adding it would duplicate initial Zabbix history and consume scarce host resources. | Existing reference; deferred | Capacity and data-model decision |
| Data Prepper | Reject initially | No required first-phase responsibility after OpenSearch is deferred. | Deferred/rejected for core | Re-evaluate only with an OpenSearch use case |
| Alertmanager | Reject initially | Zabbix owns primary alerting and problem lifecycle. A second alert engine would duplicate ownership. | Deferred/rejected for core | Re-evaluate only for a documented routing gap |
| TimescaleDB | Defer | Not needed until measured history/trend workload demonstrates a Zabbix-compatible benefit. | Unverified need | Capacity test and official compatibility review |
| Avaya SBCE SNMPv3 | Adopt integration path | Standard MIBs and documented SNMP management support the path; vendor-specific resource OIDs require release-specific validation. | Transport confirmed; OIDs unverified | Authorized polling against actual appliance |
| Avaya Session Manager | Adopt integration path | SNMP/trap/serviceability support depends on deployment and SAL/NMS configuration. | Unverified | Release-specific documentation and trap test |
| Avaya Communication Manager | Adopt integration path | Supported monitoring interfaces and OIDs vary by deployed release. | Unverified | Release-specific MIB and appliance test |

## Official documentation consulted

1. [Zabbix 7.4 container installation](https://www.zabbix.com/documentation/7.4/en/manual/installation/containers) — Docker Compose prerequisites, image variants/tags, PostgreSQL deployment, and shared-volume requirement for traps.
2. [Zabbix 7.4 SNMP traps](https://www.zabbix.com/documentation/7.4/en/manual/config/items/itemtypes/snmptrap) — `snmptrapd` flow, trap file, host-interface matching, trapper items and fallback behavior.
3. [Grafana Zabbix plugin](https://grafana.com/grafana/plugins/alexanderzobnin-zabbix-app/) — dashboards, variables, annotations, problems and installation.
4. [Grafana Zabbix datasource configuration](https://grafana.com/docs/plugins/alexanderzobnin-zabbix-app/latest/configure/) — API URL, API token and Zabbix 7.x authentication behavior.
5. [OpenTelemetry Collector architecture](https://opentelemetry.io/docs/collector/architecture/) — receiver/processor/exporter pipeline model.
6. [Asterisk AMI documentation](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-Manager-Interface-AMI/) — official AMI documentation landing page; detailed event/call behavior remains a Phase 6 validation item.
7. [Asterisk 22 documentation](https://docs.asterisk.org/Asterisk_22_Documentation/) — version-specific reference for the later synthetic-call integration.
8. [Avaya documentation](https://documentation.avaya.com/) — release-specific appliance evidence is still required; a generic landing page does not validate an OID.

## Compatibility conclusions

### Strong foundation

Zabbix 7.4 with PostgreSQL, its Nginx PostgreSQL frontend, SNMP traps and Grafana is a coherent supported foundation. The trap receiver must be implemented according to Zabbix's file-sharing workflow rather than treated as a normal UDP-only service.

### Version pinning rule

Pin full image tags after the first smoke test. Do not use `latest`, and do not assume the previous Grafana 11.5.0 installation is compatible with the selected plugin release. The exact Grafana version, plugin version and Zabbix version form one tested compatibility tuple.

### Architecture constraint

Nawari must not become a second monitoring engine. It should call Zabbix's API, submit only intentional trapper values, and store correlation/workflow data only when Zabbix cannot represent it without duplication.

### Network constraint

macOS can validate containers, provisioning, API contracts and simulated SNMP/SIP flows. It cannot validate production Avaya reachability, firewall policy, UDP 162 delivery, SIP source-IP preservation or RTP.
