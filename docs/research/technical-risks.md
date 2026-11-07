# Nawari Technical Risks and Validation Gates

## Risk and gate table

| Risk | Why it matters | Gate before dependent work | Evidence required |
|---|---|---|---|
| Small production host capacity | The prior audit identified approximately 2 vCPU, 7.8 GiB RAM and limited free disk. Zabbix, PostgreSQL and Grafana must be budgeted before optional services. | Resource gate | Measured container RSS/CPU, disk-growth estimate and limits |
| Zabbix image/version drift | Floating tags can silently change database or frontend behavior. | Image gate | Full tags recorded and image architectures inspected |
| SNMP trap wiring | UDP 162 exposure without `snmptrapd`, receiver parsing and shared trap storage produces no usable Zabbix trap item. | Trap gate | Synthetic trap matched to a host/item and survives restart |
| Grafana plugin mismatch | The plugin is an app that must be installed and enabled; API authentication behavior differs across Zabbix versions. | Dashboard gate | Provisioned datasource, read-only token, successful query and panel |
| Avaya release-specific OIDs | Generic or old MIBs can create false monitoring. | Vendor-MIB gate | MIB name, OID, datatype, units, appliance release and live response |
| Session Manager/SAL topology | Alarm forwarding may depend on serviceability configuration outside Nawari. | Avaya alarm gate | Authorized trap path and documented deployment configuration |
| Docker network/source IP | Container startup says nothing about enterprise routing or source address preservation. | Production network gate | Firewall approval, route evidence and packet capture from target host |
| SIP/RTP false health | SIP 200 alone does not prove answer, media or correct hangup. | Voice gate | Call-ID/ActionID/Uniqueid correlation, answer event, media interval and hangup |
| Secret leakage | SNMPv3, API, database and SIP credentials are high-impact secrets. | Secret gate | Secret scan, redacted logs, protected runtime injection |
| Configuration duplication | Manual GUI edits diverge from version-controlled intent. | Reconciliation gate | Two identical provisioning runs with zero duplicate objects |
| Alert ownership duplication | Zabbix and another alert engine can produce conflicting incidents. | Alert gate | Documented ownership and one end-to-end notification test |
| Overbuilding early | OpenSearch, OTel and microservices increase resource and operational cost without a first-phase requirement. | Scope gate | Core profile runs without deferred services |

## Status vocabulary

Every implementation report must classify results as `confirmed`, `validated`, `unverified` or `deferred`. A passing local simulation must not be reported as production network validation.

## Non-negotiable safety conditions

- No live calls by default.
- No production credential values in Git, fixtures or logs.
- No Avaya configuration writes.
- No fabricated metric values.
- No public PostgreSQL or AMI exposure.
- No production deployment from a local-only test result.
