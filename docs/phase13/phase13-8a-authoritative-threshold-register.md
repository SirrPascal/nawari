# Phase 13.8A Authoritative Threshold Register

**Status:** Authoritative Engineering Register  
**Date:** 2026-11-08  
**Scope:** Complete Inventory of Nawari Triggers across Templates and Monitored Hosts  
**Governance:** Kenya Airways Telephony & Network Operational SLAs  

---

## 1. Register Schema Definition

Every entry in this register documents the full operational lifecycle of a trigger using the following 16 standardized metadata fields:

| Field Index | Field Name | Description | Example |
|:---:|:---|:---|:---|
| 1 | `Trigger ID` | Authoritative Zabbix Trigger ID (Template or Host level) | `32797`, `32708`, `32682` |
| 2 | `Trigger Name` | Operational human-readable incident description | `Avaya SBCE: Appliance Unreachable` |
| 3 | `Host / Template` | Associated Zabbix template or specific monitored host | `Nawari Avaya SBCE by SNMP` |
| 4 | `Metric Key` | Exact item key or calculated formula evaluated | `icmpping[10.2.156.131]` |
| 5 | `Unit` | Physical or logical measurement unit | `%`, `ms`, `calls/s`, `errors/s`, `uptime` |
| 6 | `Warning Threshold` | Value or condition indicating initial operational deterioration | `> 80%`, `count(#2, 0, "eq") >= 2` |
| 7 | `High Threshold` | Value or condition indicating significant operational risk | `> 90%`, `count(#4, 0, "eq") >= 4` |
| 8 | `Disaster Threshold` | Value or condition indicating confirmed critical service outage | `count(#3, 0, "eq") = 3` (loss of primary) |
| 9 | `Problem Duration` | Required persistence window to confirm problem state | `min(10m)`, `5m`, `3 consecutive checks` |
| 10 | `Recovery Condition` | Mathematical expression required to clear the problem | `max(5m) < 80%`, `count(#2, 1, "eq") = 2` |
| 11 | `Recovery Duration` | Time period condition must remain healthy before recovery | `5m`, `60s` |
| 12 | `Severity` | Zabbix severity level (Information, Warning, Average, High, Disaster) | `Disaster (5)`, `High (4)`, `Warning (2)` |
| 13 | `Notification Class` | Tag-based classification (`total_outage`, `service_outage`, etc.) | `service_outage`, `total_outage`, `degradation` |
| 14 | `Data Provenance` | Measurement source: Real, Synthetic, Calculated, or Event-Derived | `Real (SNMP)`, `Synthetic (Probe)`, `Calculated` |
| 15 | `Threshold Rationale` | Technical, RFC, vendor, or operational SLA justification | Avaya SBCE HA pair failover tolerance |
| 16 | `Validation Status` | Lifecycle state: Proposed, Tested, Approved, or Verified | `Verified (Staging)`, `Approved (Design)` |

---

## 2. Core Network Infrastructure & Distribution Gateways

Target Hosts: `mock-core-switch-01`, `core-gw-01`  
Templates: `Nawari Network Device by SNMP` (10786), `Network Generic Device by SNMP` (10226)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32797** | Core Switch: Total Network Core Transport Failure | `mock-core-switch-01` | `core.switch.total_outage_state` | state | — | — | `= 1` | Immediate (`last()=1`) | `= 0` | 5s | Disaster (5) | `total_outage` | Event-Derived | Primary core switch transport down; isolates campus voice and data networks. | Tested (Live Staging) |
| **21709** | Network Generic Device: Unavailable by ICMP ping | `Network Generic Device by SNMP` | `icmpping` | state | — | — | `= 0` for 3 checks | 3 consecutive (90s) | `count(#2, 1, "eq") = 2` | 60s | High (4) / Disaster | `total_outage` | Real (ICMP) | Default distribution gateway unresponsive; WAN connectivity severed. | Tested (Live Staging) |
| **32583** | Nawari Generic SNMP Base: High ICMP ping loss | `Nawari Network Device by SNMP` | `icmppingloss` | % | `> 1%` | `> 3%` | `> 5%` | `min(5m)` | `max(5m) < 0.5%` | 5m | Warning (2) | `degradation` | Real (ICMP) | Packet drop across network core impairs real-time voice codecs (G.711/G.729). | Approved |
| **32584** | Nawari Generic SNMP Base: High ICMP response time | `Nawari Network Device by SNMP` | `icmppingsec` | s | `> 0.02s` (20ms) | `> 0.05s` (50ms) | `> 0.10s` (100ms) | `min(5m)` | `max(5m) < 0.015s` | 5m | Warning (2) | `degradation` | Real (ICMP) | LAN baseline is <5ms. 20ms indicates queue congestion or duplex mismatch. | Approved |
| **32582** | Nawari Generic SNMP Base: SNMP agent is not responding | `Nawari Network Device by SNMP` | `zabbix[host,snmp,available]` | state | — | `= 0` for 5m | — | 5m continuous | `= 1` for 2 checks | 2m | High (4) | `monitoring_failure` | Event-Derived | SNMP daemon unresponsive; underlying switch may remain operational. | Tested (Live Staging) |
| **32581** | Nawari Generic SNMP Base: Device has just been restarted | `Nawari Network Device by SNMP` | `system.uptime[sysUpTime.0]` | uptime | `< 10m` | — | — | `< 10m` post-boot | `> 10m` | 10m | Warning (2) | `informational` | Real (SNMP) | Device reloaded. Informational event; zero external notification. | Tested (Live Staging) |

---

## 3. Network Interfaces & LLD Discovery Prototypes

Template: `Nawari Network Device by SNMP` (10786)  
Applies to interfaces: `eth0`, `ge-0-0-1`, `ge-0-0-2`, `sbc-ext0`, `sbc-int0`, `M1`, `M2`, `A1`, `B1`

| ID | Trigger Name Prototype | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32585** | Interface {#IFNAME}: Link down | `Nawari Network Device by SNMP` | `net.if.status[ifOperStatus.{#SNMPINDEX}]` | state | — | `= 2` (down) | — | 30s | `= 1` (up) | 30s | Average (3) | `component_failure` | Real (SNMP) | Physical link down. Handled as component failure when LACP/HA redundancy exists. | Tested (Live Staging) |
| **32586** | Interface {#IFNAME}: High bandwidth utilization (> {$IF_UTIL_MAX}%) | `Nawari Network Device by SNMP` | Calculated: `rate(ifHCInOctets)*8/ifSpeed*100` | % | `> 80%` | `> 90%` | `> 95%` (with drops) | `min(10m)` (Warn); `min(5m)` (High) | `max(5m) < 75%` | 5m | Warning (2) / Average (3) | `degradation` | Calculated (SNMP Rate) | Sustained interface saturation causes buffer bloat and packet drops. | Tested (Live Staging) |
| **32587** | Interface {#IFNAME}: High error rate (> {$IF_ERRORS_WARN} err/s) | `Nawari Network Device by SNMP` | `rate(ifInErrors.{#SNMPINDEX})` | errors/s | `> 5 err/s` | `> 25 err/s` | `> 100 err/s` | `min(5m)` | `max(5m) < 1 err/s` | 5m | Warning (2) | `degradation` | Calculated (SNMP Rate) | Physical layer CRC errors, bad cabling, or faulty SFP optics. | Tested (Live Staging) |
| **29743** | Interface {#IFNAME}: High discard rate (> {$IF_DISCARDS_WARN} discards/s) | `Nawari Network Device by SNMP` | `rate(ifInDiscards.{#SNMPINDEX})` | discards/s | `> 10 discards/s` | `> 50 discards/s` | `> 200 discards/s` | `min(5m)` | `max(5m) < 2 discards/s` | 5m | Warning (2) | `degradation` | Calculated (SNMP Rate) | Interface buffer overflow resulting in dropped ingress packets. | Proposed (Phase 13.8B) |

---

## 4. Avaya Session Border Controller Enterprise (SBCE)

Target Hosts: `avaya-sbce-01`, `mock-avaya-sbce-01`  
Template: `Nawari Avaya SBCE by SNMP` (10788)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32708** | Avaya SBCE: Appliance Unreachable | `Nawari Avaya SBCE by SNMP` | `icmpping[10.2.156.131]` | state | — | — | `= 0` for 3 checks | 90s | `count(#2, 1, "eq") = 2` | 60s | Disaster (5) | `service_outage` | Real (ICMP) | Primary SBCE host unreachable. HA failover engages; voice engineers paged. | Tested (Live Staging) |
| **32704** | Avaya SBCE: Management Interface Unreachable | `Nawari Avaya SBCE by SNMP` | `net.tcp.service[https,10.2.156.131,443]` | state | — | `= 0` for 2m | — | 2m | `= 1` for 1m | 1m | High (4) | `degradation` | Real (TCP) | SBCE EMS/GUI management port unreachable; call processing may continue. | Tested (Live Staging) |
| **32705** | Avaya SBCE: Sustained High SIP Failure Rate (> 5%) | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.sip_failure_rate_pct` | % | `> 2%` | `> 5%` | `> 15%` | `min(5m)` | `max(5m) < 1%` | 5m | High (4) | `degradation` | Real / Trapper | Spike in 4xx/5xx responses on SIP signaling interfaces. | Tested (Live Staging) |
| **32702** | Avaya SBCE: Active Session Capacity Warning (>= 80%) | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.ems.license_utilization_pct` | % | `>= 80%` | — | — | `min(10m)` | `max(5m) < 70%` | 5m | Warning (2) | `degradation` | Real (EMS) | Licensed concurrent session limit nearing exhaustion. | Tested (Live Staging) |
| **32706** | Avaya SBCE: License Utilization Limit Approached (>= 90%) | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.allocated_licenses_pct` | % | — | `>= 90%` | — | `min(5m)` | `max(5m) < 80%` | 5m | High (4) | `degradation` | Real (EMS) | Severe risk of incoming/outgoing call rejection. | Tested (Live Staging) |
| **32703** | Avaya SBCE: Active Session Capacity Critical (>= 95%) | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.ems.license_utilization_pct` | % | — | — | `>= 95%` | `min(3m)` | `max(5m) < 85%` | 5m | High (4) | `degradation` | Real (EMS) | Imminent call blocking on enterprise boundary. | Tested (Live Staging) |
| **32707** | Avaya SBCE: Interface Packet Discards / Errors Elevated (> 1%) | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.if_error_rate_pct` | % | `> 0.5%` | `> 1.0%` | `> 3.0%` | `min(5m)` | `max(5m) < 0.2%` | 5m | Average (3) | `degradation` | Real (SNMP) | Network interface saturation on media/signaling VLANs. | Tested (Live Staging) |
| **32626** | Avaya SBCE: High CPU utilization (> {$CPU.UTIL.WARN}%) | `Nawari Avaya SBCE by SNMP` | `system.cpu.util` | % | `> 80%` | `> 90%` | — | `min(10m)` | `max(5m) < 70%` | 5m | Warning (2) | `degradation` | Real (SNMP) | CPU load on Linux appliance kernel. | Tested (Live Staging) |
| **32627** | Avaya SBCE: High memory utilization (> {$MEMORY.UTIL.WARN}%) | `Nawari Avaya SBCE by SNMP` | `vm.memory.util` | % | `> 85%` | `> 95%` | — | `min(10m)` | `max(5m) < 80%` | 5m | Warning (2) | `degradation` | Real (SNMP) | Memory exhaustion risk on proxy/transcoding daemons. | Tested (Live Staging) |
| **32628** | Avaya SBCE: High root filesystem disk usage (> {$DISK.UTIL.WARN}%) | `Nawari Avaya SBCE by SNMP` | `vfs.fs.used.percent[/]` | % | `> 80%` | `> 90%` | `> 95%` | `last() > 80%` | `last() < 75%` | 5m | Warning (2) | `degradation` | Real (SNMP) | Log accumulation in `/var/log` or trace directories. | Tested (Live Staging) |
| **32701** | Avaya SBCE: Telemetry Stale or Loss of Monitoring | `Nawari Avaya SBCE by SNMP` | `avaya.sbce.ems.active_calls` | calls | — | Stale > 15m | — | 15m | Fresh data received | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | Poller unable to refresh call count table. | Tested (Live Staging) |

---

## 5. Avaya Session Manager (SM)

Target Host: `avaya-sm-01`  
Template: `Nawari Avaya Session Manager by SNMP` (10795)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32752** | Avaya SM: Session Manager Host Unavailable | `Nawari Avaya Session Manager by SNMP` | `icmpping[10.2.156.22]` | state | — | — | `= 0` for 3 checks | 90s | `count(#2, 1, "eq") = 2` | 60s | Disaster (5) | `service_outage` | Real (ICMP) | Session Manager host down. Redundant SM node carries routing; voice admins paged. | Tested (Live Staging) |
| **32698** | Avaya SM: SIP Entity Down (Communication Manager) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.cm` | state | — | — | `= 2` (Down) | 60s | `= 1` (Up) | 60s | Disaster (5) | `service_outage` | Real (SNMP) | Core link between Session Manager and CM duplex processor severed. | Tested (Live Staging) |
| **32699** | Avaya SM: SIP Entity Down (Avaya SBCE) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.sbce` | state | — | — | `= 2` (Down) | 60s | `= 1` (Up) | 60s | Disaster (5) | `service_outage` | Real (SNMP) | Internal SIP trunk from SM to perimeter SBCE severed. | Tested (Live Staging) |
| **32745** | Avaya SM: SIP Entity DENY NEW SERVICE (Communication Manager) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.cm` | state | — | `= 4` (Deny) | — | 30s | `= 1` (Up) | 30s | High (4) | `service_outage` | Real (SNMP) | Entity in maintenance or rejecting new call dialogs. | Tested (Live Staging) |
| **32747** | Avaya SM: SIP Entity DENY NEW SERVICE (Avaya SBCE) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.sbce` | state | — | `= 4` (Deny) | — | 30s | `= 1` (Up) | 30s | High (4) | `service_outage` | Real (SNMP) | Perimeter SBC refusing new routing invitations. | Tested (Live Staging) |
| **32744** | Avaya SM: SIP Entity PARTIALLY UP (Communication Manager) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.cm` | state | `= 3` (Partial) | — | — | 60s | `= 1` (Up) | 60s | Average (3) | `degradation` | Real (SNMP) | One of multiple links in entity group degraded. | Tested (Live Staging) |
| **32746** | Avaya SM: SIP Entity PARTIALLY UP (Avaya SBCE) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.status.sbce` | state | `= 3` (Partial) | — | — | 60s | `= 1` (Up) | 60s | Average (3) | `degradation` | Real (SNMP) | Redundant SBC path link down. | Tested (Live Staging) |
| **32748** | Avaya SM: SIP OPTIONS Latency Elevated (> 250ms) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_entity.rtt.cm` | ms | `> 150ms` | `> 250ms` | `> 500ms` | `min(5m)` | `max(5m) < 100ms` | 5m | Warning (2) | `degradation` | Real (SNMP) | SIP heartbeats between SM and CM experiencing transmission delay. | Tested (Live Staging) |
| **32749** | Avaya SM: Synthetic SIP OPTIONS Probe Failure | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.sip_options_status` | state | — | `= 0` for 2 checks | — | 60s | `= 1` for 2 checks | 60s | High (4) | `monitoring_failure` | Synthetic (Probe) | Synthetic SIP options poller failed to elicit 200 OK from SM. | Tested (Live Staging) |
| **32750** | Avaya SM: Session Manager Signalling Failure Rate High (> 5%) | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.signalling_failure_pct` | % | `> 2%` | `> 5%` | `> 15%` | `min(5m)` | `max(5m) < 1%` | 5m | High (4) | `degradation` | Real / Trapper | Call routing errors (e.g. SIP 503 Service Unavailable). | Tested (Live Staging) |
| **32751** | Avaya SM: Critical Enterprise Alarm Reported | `Nawari Avaya Session Manager by SNMP` | `avaya.sm.alarms.active_count` | alarms | — | `> 0` | — | Immediate | `= 0` | 60s | High (4) | `component_failure` | Real (SNMP) | Avaya internal system management daemon logged critical alarm. | Tested (Live Staging) |
| **32743** | Avaya SM: Management Telemetry Stale or Loss of Monitoring | `Nawari Avaya Session Manager by SNMP` | `system.uptime` | uptime | — | Stale > 10m | — | 10m | Fresh data received | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | Telemetry collection timeout. | Tested (Live Staging) |

---

## 6. Avaya Communication Manager (CM Duplex Core)

Target Host: `avaya-cm-01`  
Template: `Nawari Avaya Communication Manager by SNMP` (10793)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32733** | Avaya CM: Communication Manager Processor Unreachable | `Nawari Avaya Communication Manager by SNMP` | `icmpping[10.102.10.25]` | state | — | — | `= 0` for 3 checks | 90s | `count(#2, 1, "eq") = 2` | 60s | Disaster (5) | `service_outage` | Real (ICMP) | Active duplex server unreachable. Standby server assumes active role; voice admins paged. | Tested (Live Staging) |
| **32694** | Avaya CM: Real-Call Packet Loss High (> 2.5% in Last Hour) | `Nawari Avaya Communication Manager by SNMP` | `avaya.cm.ip_voice.loss_pct` | % | `> 1.0%` | `> 2.5%` | `> 5.0%` | 1 hour summary | `< 0.8%` in next hour | 1h | Warning (2) | `degradation` | Real (Hourly MIB) | Aggregated QoS statistics across completed IP voice calls (`avCmMeasIpVoStatHrData`). | Tested (Live Staging) |
| **32695** | Avaya CM: Real-Call Peak Jitter High (> 30 ms) | `Nawari Avaya Communication Manager by SNMP` | `avaya.cm.ip_voice.peak_jitter` | ms | `> 20 ms` | `> 30 ms` | `> 50 ms` | 1 hour summary | `< 15 ms` in next hour | 1h | Warning (2) | `degradation` | Real (Hourly MIB) | Worst-case jitter experienced on IP phone / softphone media streams. | Tested (Live Staging) |
| **32731** | Avaya CM: Call Rate Abnormal Drop (< 10 calls/hr) | `Nawari Avaya Communication Manager by SNMP` | `avaya.cm.call_rate.completed` | calls | `< 25 calls/hr` | `< 10 calls/hr` | — | 1 hour during business hours | `> 30 calls/hr` | 1h | High (4) | `degradation` | Real (Calculated) | Detects silent carrier or routing blackout during peak enterprise hours. | Tested (Live Staging) |
| **32696** | Avaya CM: Active Telephony Alarms Present | `Nawari Avaya Communication Manager by SNMP` | `avaya.cm.alarms.active_count` | alarms | `> 0` | — | — | Immediate | `= 0` | 60s | Average (3) | `component_failure` | Real (SNMP) | Hardware, synchronization, or dial plan alarms present in CM core. | Tested (Live Staging) |
| **32732** | Avaya CM: Performance Telemetry Stale (> 2h) | `Nawari Avaya Communication Manager by SNMP` | `avaya.cm.call_rate.completed` | calls | — | Stale > 2h | — | 2h | Fresh hourly data | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | MIB table poller stalled. | Tested (Live Staging) |

---

## 7. Avaya G450 Media Gateway Fleet

Target Host: `avaya-g450-01`  
Template: `Nawari Avaya G450 Media Gateway by SNMP` (10794)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32742** | Avaya G450: Media Gateway Chassis Unreachable | `Nawari Avaya G450 Media Gateway by SNMP` | `icmpping[10.2.156.60]` | state | — | — | `= 0` for 3 checks | 90s | `count(#2, 1, "eq") = 2` | 60s | High (4) / Disaster | `service_outage` | Real (ICMP) | Media gateway chassis unreachable. Analog lines and PRI trunks affected. | Tested (Live Staging) |
| **32697** | Avaya G450: Media Gateway Unregistered from Communication Manager | `Nawari Avaya G450 Media Gateway by SNMP` | `avaya.g450.cm_registration_state` | state | — | `<> 1` (Unregistered) | — | 60s | `= 1` (Registered) | 60s | High (4) | `service_outage` | Real (SNMP) | Gateway loses H.248 registration to CM core; cannot process TDM/IP calls. | Tested (Live Staging) |
| **32739** | Avaya G450: Power Supply Unit Failure | `Nawari Avaya G450 Media Gateway by SNMP` | `avaya.g450.psu.status.1`, `avaya.g450.psu.status.2` | state | — | One PSU `= 2` (Fault) | Both PSUs `= 2` | Immediate | Both PSUs `= 1` (OK) | 60s | Average (3) / High (4) | `component_failure` | Real (SNMP) | Redundant PSU loss. Chassis continues on survivor. | Tested (Live Staging) |
| **32740** | Avaya G450: Fan Tray Failure | `Nawari Avaya G450 Media Gateway by SNMP` | `avaya.g450.fan_tray.status` | state | — | `= 2` (Fault) | — | Immediate | `= 1` (OK) | 60s | High (4) | `component_failure` | Real (SNMP) | Cooling failure threatens hardware shutdown. | Tested (Live Staging) |
| **32700** | Avaya G450: Chassis Ambient Temperature Threshold Exceeded (Warning) | `Nawari Avaya G450 Media Gateway by SNMP` | `avaya.g450.temperature` | state | `= 2` (Warning) | `= 3` (Critical) | — | 5m | `= 1` (Normal) | 5m | High (4) | `component_failure` | Real (SNMP) | Equipment room HVAC deterioration. | Tested (Live Staging) |
| **32741** | Avaya G450: E1/ISDN Primary Trunk Port Down | `Nawari Avaya G450 Media Gateway by SNMP` | `ifOperStatus.e1.1` | state | — | `= 2` (Down) | — | 30s | `= 1` (Up) | 30s | High (4) | `component_failure` | Real (SNMP) | Local PSTN E1 link failure. | Tested (Live Staging) |
| **32738** | Avaya G450: Media Gateway Telemetry Missing (> 10m) | `Nawari Avaya G450 Media Gateway by SNMP` | `system.uptime` | uptime | — | Stale > 10m | — | 10m | Fresh data received | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | Poller unable to refresh gateway uptime. | Tested (Live Staging) |

---

## 8. Carrier SIP Trunks (Safaricom & Airtel)

Target Host: `sip-trunk-carrier-01`  
Template: `Nawari SIP Trunk by Trapper` (10797)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32753** | SIP Trunk: Endpoint Unreachable | `Nawari SIP Trunk by Trapper` | `icmpping[10.2.156.100]` | state | — | — | `= 0` for 3 checks | 90s | `count(#2, 1, "eq") = 2` | 60s | Disaster (5) | `service_outage` | Real (ICMP) | Carrier SBC boundary IP unreachable. Route pattern diverts calls to secondary trunk. | Tested (Live Staging) |
| **32754** | SIP Trunk: Consecutive OPTIONS Probe Failures | `Nawari SIP Trunk by Trapper` | `sip.trunk.options_status` | state | 2 failed (60s) | 4 failed (120s) | 6 failed (180s) | 120s (`count(#4, 0, "eq") >= 3`) | 3 consecutive 200 OK | 90s | High (4) | `service_outage` | Real (SIP Trapper) | Carrier SIP signaling interface unresponsive. Trunk marked busy. | Tested (Live Staging) |
| **32755** | SIP Trunk: High Error Response Rate (5xx/4xx > 10%) | `Nawari SIP Trunk by Trapper` | `sip.trunk.error_rate_pct` | % | `> 5%` | `> 10%` | `> 25%` | `min(5m)` | `max(5m) < 2%` | 5m | High (4) | `degradation` | Real (SIP Trapper) | Carrier network congestion or circuit failure (SIP 500/503/404). | Tested (Live Staging) |
| **32756** | SIP Trunk: DNS SRV/A Resolution Failure | `Nawari SIP Trunk by Trapper` | `sip.trunk.dns_resolved` | state | — | `= 0` for 2m | — | 2m | `= 1` for 1m | 1m | High (4) | `service_outage` | Real (DNS Trapper) | FQDN resolution failed for carrier SBC realm. | Tested (Live Staging) |
| **32757** | SIP Trunk: TLS Certificate Expiration Warning (<= 30 days) | `Nawari SIP Trunk by Trapper` | `sip.trunk.tls_cert_expiry_days` | days | `<= 30 days` | — | — | Immediate | `> 30 days` | Immediate | Warning (2) | `informational` | Real (Trapper) | Proactive renewal window for SIP/TLS mutual authentication certificate. | Tested (Live Staging) |
| **32758** | SIP Trunk: TLS Certificate Expiration Critical (<= 7 days) | `Nawari SIP Trunk by Trapper` | `sip.trunk.tls_cert_expiry_days` | days | — | `<= 7 days` | — | Immediate | `> 7 days` | Immediate | High (4) | `degradation` | Real (Trapper) | Urgent renewal required to prevent SIP-TLS connection drops. | Tested (Live Staging) |

---

## 9. Communications Applications (CMS & WFO)

Target Host: `avaya-cms-01`  
Template: `Nawari Avaya CMS and WFO by Trapper` (10796)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32736** | WFO: Compliance Voice Recording Pipeline Health Failure | `Nawari Avaya CMS and WFO by Trapper` | `wfo.recording.pipeline_status` | state | — | `= 0` (Fail) | — | 60s | `= 1` (OK) | 60s | High (4) | `service_outage` | Real (Trapper) | Contact center legal call recording pipeline halted. Regulatory compliance risk. | Tested (Live Staging) |
| **32737** | WFO: Compliance Voice Recording Spool Disk Storage Warning (< 15%) | `Nawari Avaya CMS and WFO by Trapper` | `wfo.recording.disk_free_pct` | % | `< 15%` free | `< 5%` free | — | `last() < 15%` | `last() > 20%` | 5m | Warning (2) | `degradation` | Real (Trapper) | Audio buffer partition nearing capacity. | Tested (Live Staging) |
| **32734** | Avaya CMS: Queue Service Level Degradation (< 80%) | `Nawari Avaya CMS and WFO by Trapper` | `avaya.cms.sla_pct` | % | `< 80%` | `< 65%` | — | `min(15m)` | `max(15m) > 85%` | 15m | Average (3) | `degradation` | Real (Trapper) | Contact center ACD queue abandon rate elevated. Operational SLA impacted. | Tested (Live Staging) |
| **32735** | Avaya CMS: Telemetry Data Stale (> 45m) | `Nawari Avaya CMS and WFO by Trapper` | `avaya.cms.sla_pct` | % | — | Stale > 45m | — | 45m | Fresh data received | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | CMS ODBC/export pipeline stalled. | Tested (Live Staging) |

---

## 10. Synthetic Voice & Endpoint Quality Probes

Target Hosts: `nawari-voice-probe-01`, `endpoint-probe-01`  
Templates: `Nawari Voice Synthetic Probe by Zabbix Trapper` (10790), `Template Nawari Endpoint Probe by Zabbix Trapper` (10792)

| ID | Trigger Name | Host / Template | Metric Key | Unit | Warning | High | Disaster | Problem Duration | Recovery Condition | Recovery Duration | Severity | Notification Class | Provenance | Threshold Rationale | Validation Status |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|:---:|
| **32683** | Unacceptable voice quality on synthetic probe (MOS < 3.5) | `Nawari Voice Synthetic Probe` | `voice.synthetic.mos` | MOS | — | `< 3.5` | `< 3.0` | 2 consecutive tests | `> 3.8` | 1 test | High (4) | `synthetic_failure` | Synthetic (E-Model) | Simulated call probe detected severe audio distortion. ITU-T G.107 standard. | Tested (Live Staging) |
| **32682** | Degraded voice quality on synthetic probe (MOS < 3.8) | `Nawari Voice Synthetic Probe` | `voice.synthetic.mos` | MOS | `< 3.8` | — | — | 2 consecutive tests | `> 4.0` | 1 test | Warning (2) | `synthetic_failure` | Synthetic (E-Model) | Early indication of packet jitter or network queuing affecting voice. | Tested (Live Staging) |
| **32681** | One-way audio detected on synthetic voice test | `Nawari Voice Synthetic Probe` | `voice.synthetic.media_status` | state | — | `= 2` (One-way) | — | Immediate | `= 1` (Bidirectional)| 1 test | High (4) | `synthetic_failure` | Synthetic (RTP Analysis) | RTP audio packets missing in inbound or outbound path during test call. | Tested (Live Staging) |
| **32679** | Synthetic voice test failed or congested | `Nawari Voice Synthetic Probe` | `voice.synthetic.outcome` | state | — | `= 2` (Fail) | — | Immediate | `= 1` (Pass) | 1 test | High (4) | `synthetic_failure` | Synthetic (Full Lifecycle) | Test call failed to complete or was rejected with SIP error. | Tested (Live Staging) |
| **32727** | Synthetic Voice: Consecutive Test Failures (3 Consecutive) | `Nawari Voice Synthetic Probe` | `voice.synthetic.call_success` | state | — | 2 fails | 3 consecutive fails (`count(#3, 0, "eq") = 3`) | 3 tests (15m) | 2 consecutive passes | 10m | High (4) | `synthetic_failure` | Synthetic (Lifecycle) | Persistent failure across test window proves genuine telephony impairment. | Tested (Live Staging) |
| **32680** | Synthetic Voice: Call Setup Timeout (> 4000 ms) | `Nawari Voice Synthetic Probe` | `voice.synthetic.setup_time` | ms | `> 3000 ms` | `> 4000 ms` | `> 8000 ms` | 2 consecutive tests | `< 2500 ms` | 1 test | Average (3) | `synthetic_failure` | Synthetic (AMI/SIP) | Post-dial delay elevated. Measures time from INVITE to 200 OK / Answer. | Tested (Live Staging) |
| **32725** | Synthetic Voice: Connected Duration Below Criterion (< 5s) | `Nawari Voice Synthetic Probe` | `voice.synthetic.duration` | s | `< 5s` | `< 2s` | — | Immediate | `> 10s` | 1 test | Average (3) | `synthetic_failure` | Synthetic (Call Length) | Premature call drops or unexpected BYE sent during test audio phase. | Tested (Live Staging) |
| **32726** | Synthetic Voice: SIP vs AMI Result Mismatch | `Nawari Voice Synthetic Probe` | `voice.synthetic.sip_ami_mismatch` | state | — | `= 1` (Mismatch) | — | Immediate | `= 0` (Match) | 1 test | Average (3) | `monitoring_failure` | Synthetic (Audit) | SIP signaling reported call answered, but AMI recorded channel failure. | Tested (Live Staging) |
| **32689** | Synthetic voice probe telemetry is stale (>15m) | `Nawari Voice Synthetic Probe` | `voice.synthetic.outcome` | state | — | Stale > 15m | — | 15m | Fresh data received | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | Probe scheduler paused or unable to send trapper data. | Tested (Live Staging) |
| **32692** | High packet loss to default gateway (>20%) | `Template Nawari Endpoint Probe` | `endpoint.network.gateway.loss` | % | `> 5%` | `> 20%` | — | `min(5m)` | `max(5m) < 2%` | 5m | Average (3) | `degradation` | Real (Endpoint Ping) | Local LAN packet loss from edge user location. | Tested (Live Staging) |
| **32693** | High default gateway latency (>50ms) | `Template Nawari Endpoint Probe` | `endpoint.network.gateway.rtt` | ms | `> 25 ms` | `> 50 ms` | — | `min(5m)` | `max(5m) < 15 ms` | 5m | Warning (2) | `degradation` | Real (Endpoint Ping) | Local edge access layer switch congestion. | Tested (Live Staging) |
| **32691** | Endpoint probe telemetry is stale (>15m) | `Template Nawari Endpoint Probe` | `endpoint.info` | state | — | Stale > 15m | — | 15m | Fresh heartbeat | Immediate | Warning (2) | `monitoring_failure` | Event-Derived | Edge probe agent stopped reporting. | Tested (Live Staging) |

---

## 11. Gated & Deferred Telemetry Register

Metrics that **must not** have active alerts in production until physical hardware and collection pipelines are commissioned:

| Gated Telemetry Item | Proposed Metric Name | Intended Unit | Desired Threshold | Reason for Gating | Required Commissioning Step | Target Phase |
|:---|:---|:---:|:---|:---|:---|:---:|
| **G450 DSP Pool Utilization** | `avaya.g450.dsp_utilization_pct` | % | Warn > 80%, High > 95% | Physical MP120 / MP160 child DSP cards must be confirmed installed in chassis slots V2–V4. | Hardware chassis audit on-site. | Phase 8.2 |
| **Real-Time Per-Call RTCP Jitter** | `avaya.cm.live_call.rtcp_jitter` | ms | Warn > 20ms, High > 35ms | CM does not expose per-second RTCP via SNMP; requires dedicated VoIP packet sniffer (Homer/HEP). | Deploy dedicated network TAP/sniffer. | Phase 8.2 |
| **Avaya SBCE Transcoding Session Depth** | `avaya.sbce.transcoding_sessions` | calls | Warn > 80% capacity | Requires live EMS authenticated REST API or licensed DSP transcoding feature active. | Configure authenticated EMS API token. | Phase 8.2 |
| **Session Manager Internal Trace Buffer Overflow** | `avaya.sm.trace_buffer_dropped` | packets | > 0 dropped | SM restricts trace buffer metrics to local CLI `traceSM` daemon. | Authorize SSH/local agent collector. | Phase 8.2 |
