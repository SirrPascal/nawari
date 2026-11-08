# Phase 13.8B Implementation Evidence Register

**Author:** Antigravity Engineering (pair programming with User)  
**Date:** 2026-11-08  
**Status:** Approved & Implemented in Staging  
**Platform:** Zabbix 7.4.4 / PostgreSQL Engine on `mon-grafana01`  
**Baseline Snapshot:** `provisioning/zabbix/snapshots/phase13_8b_pre_mutation_baseline.json`  
**Change Manifest:** `provisioning/zabbix/snapshots/phase13_8b_change_manifest.json`  
**Runtime Results:** `provisioning/zabbix/snapshots/phase13_8b_runtime_hysteresis_results.json`

---

## 1. Executive Implementation Summary

Phase 13.8B has implemented the **Nawari Trigger and Alert Threshold Standard** across all 11 monitoring templates in Zabbix 7.4. Every eligible metric trigger now enforces dual-expression recovery hysteresis (`recovery_mode: 1`), minimum persistence evaluation windows, and anti-flapping deadbands. Furthermore, LLD trigger prototypes for network interfaces now propagate `notification_class` tags to all 54 discovered interface triggers on mock lab hosts.

### Consolidated Implementation Ledger
| Category | Total Inventory | Recovery Mode 1 | Recovery Mode 0 (Exceptions) | Tagged with `notification_class` | Implementation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Template Triggers** | 68 | 67 (98.5%) | 1 (1.5% — EX-01) | 68 (100.0%) | **VERIFIED** |
| **Trigger Prototypes** | 11 | 11 (100.0%) | 0 (0.0%) | 11 (100.0%) | **VERIFIED** |
| **Discovered Host Triggers** | 54 | 54 (100.0%) | 0 (0.0%) | 54 (100.0%) | **VERIFIED** |
| **Total Managed Triggers** | **133** | **132** | **1** | **133 (100.0%)** | **ALL PASSED** |

---

## 2. Batch-by-Batch Implementation Evidence

### BATCH 01: Nawari Generic SNMP Base
- **Template ID:** `10784`
- **Template Name:** `Nawari Generic SNMP Base`
- **Monitored Scope:** Base ICMP reachability, packet loss, round-trip time, SNMP daemon responsiveness, and uptime reboot detection.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32573` | Device has just been restarted | Warn | `last(/Nawari Generic SNMP Base/system.uptime[sysUpTime.0])<10m and last(...)>0` | `last(/Nawari Generic SNMP Base/system.uptime[sysUpTime.0])>=10m` | `1` | `informational` | VERIFIED |
| `32574` | SNMP agent is not responding | High | `max(/Nawari Generic SNMP Base/zabbix[host,snmp,available],#3)=0` | `min(/Nawari Generic SNMP Base/zabbix[host,snmp,available],#3)=1` | `1` | `monitoring_failure` | VERIFIED |
| `32575` | High ICMP ping loss | Warn | `min(/Nawari Generic SNMP Base/icmppingloss,5m)>20` | `max(/Nawari Generic SNMP Base/icmppingloss,5m)<5` | `1` | `degradation` | VERIFIED |
| `32576` | High ICMP response time | Warn | `avg(/Nawari Generic SNMP Base/icmppingsec,5m)>0.15` | `avg(/Nawari Generic SNMP Base/icmppingsec,5m)<0.10` | `1` | `degradation` | VERIFIED |

---

### BATCH 02: Nawari Network Device by SNMP
- **Template ID:** `10786`
- **Template Name:** `Nawari Network Device by SNMP`
- **Monitored Scope:** Interface LLD Discovery Prototypes on core switches and edge routers.

| Prototype ID | Prototype Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Discovered Resolved | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32585` | Interface {#IFNAME}: Link down | Avg | `{$IFCONTROL:"{#IFNAME}"}=1 and last(/Nawari Network Device by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=2` | `last(/Nawari Network Device by SNMP/net.if.status[ifOperStatus.{#SNMPINDEX}])=1` | `1` | `component_failure` | 18 interface triggers | VERIFIED |
| `32586` | Interface {#IFNAME}: High bandwidth utilization (> {$IF_UTIL_MAX}%) | Warn | `(last(net.if.in) > (speed*80/100) or last(net.if.out) > (speed*80/100))` | `(last(net.if.in) < (speed*60/100) and last(net.if.out) < (speed*60/100))` | `1` | `degradation` | 18 interface triggers | VERIFIED |
| `32587` | Interface {#IFNAME}: High error rate (> {$IF_ERRORS_WARN} err/s) | Warn | `(min(net.if.in.errors,5m)>{$IF_ERRORS_WARN} or min(net.if.out.errors,5m)>{$IF_ERRORS_WARN})` | `(max(net.if.in.errors,5m)<1 and max(net.if.out.errors,5m)<1)` | `1` | `degradation` | 18 interface triggers | VERIFIED |

---

### BATCH 03: Template Nawari Endpoint Probe by Zabbix Trapper
- **Template ID:** `10792`
- **Template Name:** `Template Nawari Endpoint Probe by Zabbix Trapper`
- **Monitored Scope:** Edge endpoint agent telemetry, gateway reachability, and trans-WAN round-trip times.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32691` | Endpoint probe telemetry is stale (>15m) | Warn | `nodata(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.info,15m)=1` | `last(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.info)<>""` | `1` | `monitoring_failure` | VERIFIED |
| `32692` | High packet loss to default gateway (>20%) | Avg | `min(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.loss,5m)>20` | `max(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.loss,5m)<5` | `1` | `degradation` | VERIFIED |
| `32693` | High default gateway latency (>50ms) | Warn | `min(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.rtt,5m)>0.05` | `max(/Template Nawari Endpoint Probe by Zabbix Trapper/endpoint.network.gateway.rtt,5m)<0.02` | `1` | `degradation` | VERIFIED |

---

### BATCH 04: Nawari Avaya SBCE by SNMP
- **Template ID:** `10788`
- **Template Name:** `Nawari Avaya SBCE by SNMP`
- **Monitored Scope:** SBC appliance CPU, RAM, root disk, active sessions, license limits, SIP failure rates, and interface health.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32626` | Avaya SBCE: High CPU utilization (> {$CPU.UTIL.WARN}%) | Warn | `min(/Nawari Avaya SBCE by SNMP/system.cpu.util,5m)>85` | `max(/Nawari Avaya SBCE by SNMP/system.cpu.util,5m)<70` | `1` | `degradation` | VERIFIED |
| `32627` | Avaya SBCE: High memory utilization (> {$MEMORY.UTIL.WARN}%) | Warn | `min(/Nawari Avaya SBCE by SNMP/vm.memory.util,5m)>90` | `max(/Nawari Avaya SBCE by SNMP/vm.memory.util,5m)<80` | `1` | `degradation` | VERIFIED |
| `32628` | Avaya SBCE: High root filesystem disk usage (> {$DISK.UTIL.WARN}%) | Warn | `min(/Nawari Avaya SBCE by SNMP/vfs.fs.used.percent[/],5m)>85` | `max(/Nawari Avaya SBCE by SNMP/vfs.fs.used.percent[/],5m)<75` | `1` | `degradation` | VERIFIED |
| `32701` | Avaya SBCE: Telemetry Stale or Loss of Monitoring | High | `nodata(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.active_calls,15m)=1` | `last(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.active_calls)>=0` | `1` | `monitoring_failure` | VERIFIED |
| `32702` | Avaya SBCE: Active Session Capacity Warning (>= 80%) | Warn | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,5m)>=80` | `max(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,5m)<70` | `1` | `degradation` | VERIFIED |
| `32703` | Avaya SBCE: Active Session Capacity Critical (>= 95%) | High | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,3m)>=95` | `max(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct,3m)<85` | `1` | `service_outage` | VERIFIED |
| `32704` | Avaya SBCE: Management Interface Unreachable | High | `count(/Nawari Avaya SBCE by SNMP/net.tcp.service[https,10.2.156.131,443],#2,"eq",0)>=2` | `last(/Nawari Avaya SBCE by SNMP/net.tcp.service[https,10.2.156.131,443])=1` | `1` | `monitoring_failure` | VERIFIED |
| `32705` | Avaya SBCE: Sustained High SIP Failure Rate (> 5%) | Avg | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.sip_failure_rate_pct,5m)>5` | `max(/Nawari Avaya SBCE by SNMP/avaya.sbce.sip_failure_rate_pct,5m)<2` | `1` | `degradation` | VERIFIED |
| `32706` | Avaya SBCE: License Utilization Limit Approached (>= 90%) | High | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.allocated_licenses_pct,5m)>=90` | `max(/Nawari Avaya SBCE by SNMP/avaya.sbce.allocated_licenses_pct,5m)<80` | `1` | `degradation` | VERIFIED |
| `32707` | Avaya SBCE: Interface Packet Discards / Errors Elevated (> 1%) | Warn | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.if_error_rate_pct,5m)>1` | `max(/Nawari Avaya SBCE by SNMP/avaya.sbce.if_error_rate_pct,5m)<0.2` | `1` | `degradation` | VERIFIED |
| `32708` | Avaya SBCE: Appliance Unreachable | Dis | `max(/Nawari Avaya SBCE by SNMP/icmpping[10.2.156.131],#3)=0` | `min(/Nawari Avaya SBCE by SNMP/icmpping[10.2.156.131],#3)=1` | `1` | `service_outage` | VERIFIED |

---

### BATCH 05: Nawari Voice Synthetic Probe by Zabbix Trapper
- **Template ID:** `10790`
- **Template Name:** `Nawari Voice Synthetic Probe by Zabbix Trapper`
- **Monitored Scope:** Synthetic call tests, setup times, one-way audio, synthetic MOS (G.107), and AMI result consistency.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32679` | Synthetic voice test failed or congested | High | `last(...)="FAILED" or last(...)="CONGESTION"` | `last(...)="ANSWERED" or last(...)="SUCCESS"` | `1` | `synthetic_failure` | VERIFIED |
| `32680` | Synthetic Voice: Call Setup Timeout (> 4000 ms) | Avg | `min(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.setup_time,#2)>4000` | `max(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.setup_time,#2)<2500` | `1` | `synthetic_failure` | VERIFIED |
| `32681` | One-way audio detected on synthetic voice test | High | `last(...)="TRANSMIT_ONLY" or last(...)="RECEIVE_ONLY"` | `last(...)="BIDIRECTIONAL"` | `1` | `synthetic_failure` | VERIFIED |
| `32682` | Degraded voice quality on synthetic probe (MOS < 3.8) | Warn | `max(voice.synthetic.mos,#2)<3.8 and last(voice.synthetic.mos)>0` | `min(voice.synthetic.mos,#2)>=4.0` | `1` | `synthetic_failure` | VERIFIED |
| `32683` | Unacceptable voice quality on synthetic probe (MOS < 3.5) | Avg | `max(voice.synthetic.mos,#2)<3.5 and last(voice.synthetic.mos)>0` | `min(voice.synthetic.mos,#2)>=3.8` | `1` | `synthetic_failure` | VERIFIED |
| `32689` | Synthetic voice probe telemetry is stale (>15m) | Warn | `nodata(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome,15m)=1` | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.outcome)<>""` | `1` | `monitoring_failure` | VERIFIED |
| `32725` | Synthetic Voice: Connected Duration Below Criterion (< 5s) | Warn | `last(voice.synthetic.duration)<5 and last(voice.synthetic.duration)>=0` | `last(voice.synthetic.duration)>=5` | `1` | `synthetic_failure` | VERIFIED |
| `32726` | Synthetic Voice: SIP vs AMI Result Mismatch | Warn | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.sip_ami_mismatch)=1` | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.sip_ami_mismatch)=0` | `1` | `synthetic_failure` | VERIFIED |
| `32727` | Synthetic Voice: Consecutive Test Failures (3 Consecutive) | High | `count(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.call_success,#3,"eq",0)=3` | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.call_success)=1` | `1` | `synthetic_failure` | VERIFIED |

---

### BATCH 06: Nawari Avaya Communication Manager by SNMP
- **Template ID:** `10793`
- **Template Name:** `Nawari Avaya Communication Manager by SNMP`
- **Monitored Scope:** Real-call aggregate loss, jitter, active telephony alarms, completed call rates, and chassis reachability.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32694` | Avaya CM: Real-Call Packet Loss High (> 2.5% in Last Hour) | Avg | `min(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.loss_pct,1h)>2.5` | `max(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.loss_pct,1h)<1.0` | `1` | `degradation` | VERIFIED |
| `32695` | Avaya CM: Real-Call Peak Jitter High (> 30 ms) | Warn | `min(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.peak_jitter,1h)>30` | `max(/Nawari Avaya Communication Manager by SNMP/avaya.cm.ip_voice.peak_jitter,1h)<20` | `1` | `degradation` | VERIFIED |
| `32696` | Avaya CM: Active Telephony Alarms Present | Avg | `last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.alarms.active_count)>0` | `last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.alarms.active_count)=0` | `1` | `degradation` | VERIFIED |
| `32731` | Avaya CM: Call Rate Abnormal Drop (< 10 calls/hr) | Warn | `last(avaya.cm.call_rate.completed)<10 and last(avaya.cm.call_rate.completed)>=0` | `last(avaya.cm.call_rate.completed)>=25` | `1` | `degradation` | VERIFIED |
| `32732` | Avaya CM: Call Volume Telemetry Missing (> 2h) | Warn | `nodata(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed,2h)=1` | `last(/Nawari Avaya Communication Manager by SNMP/avaya.cm.call_rate.completed)>=0` | `1` | `monitoring_failure` | VERIFIED |
| `32733` | Avaya CM: Communication Manager Host Unreachable | Dis | `max(/Nawari Avaya Communication Manager by SNMP/icmpping[10.102.10.25],#3)=0` | `min(/Nawari Avaya Communication Manager by SNMP/icmpping[10.102.10.25],#3)=1` | `1` | `service_outage` | VERIFIED |

---

### BATCH 07: Nawari Avaya G450 Media Gateway by SNMP
- **Template ID:** `10794`
- **Template Name:** `Nawari Avaya G450 Media Gateway by SNMP`
- **Monitored Scope:** Media Gateway registration, ambient temperature, PSU redundancy, fan trays, E1 PRI trunk ports, and chassis reachability.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32697` | Avaya G450: Media Gateway Unregistered from CM | High | `last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.cm_registration_state)<>1` | `last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.cm_registration_state)=1` | `1` | `service_outage` | VERIFIED |
| `32730` | Avaya G450: Chassis Ambient Temperature Threshold Exceeded | Warn | `min(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.temperature,5m)>=2` | `max(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.temperature,5m)=1` | `1` | `degradation` | VERIFIED |
| `32738` | Avaya G450: Media Gateway Telemetry Missing (> 10m) | Warn | `nodata(/Nawari Avaya G450 Media Gateway by SNMP/system.uptime,10m)=1` | `last(/Nawari Avaya G450 Media Gateway by SNMP/system.uptime)>=0` | `1` | `monitoring_failure` | VERIFIED |
| `32739` | Avaya G450: Power Supply Unit Failure | Avg | `last(avaya.g450.psu.status.1)=2 or last(avaya.g450.psu.status.2)=2` | `last(avaya.g450.psu.status.1)=1 and last(avaya.g450.psu.status.2)=1` | `1` | `component_failure` | VERIFIED |
| `32740` | Avaya G450: Fan Tray Failure | Avg | `last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.fan_tray.status)=2` | `last(/Nawari Avaya G450 Media Gateway by SNMP/avaya.g450.fan_tray.status)=1` | `1` | `component_failure` | VERIFIED |
| `32741` | Avaya G450: E1/ISDN Primary Trunk Port Down | High | `last(/Nawari Avaya G450 Media Gateway by SNMP/ifOperStatus.e1.1)=2` | `last(/Nawari Avaya G450 Media Gateway by SNMP/ifOperStatus.e1.1)=1` | `1` | `service_outage` | VERIFIED |
| `32742` | Avaya G450: Media Gateway Chassis Unreachable | Dis | `max(/Nawari Avaya G450 Media Gateway by SNMP/icmpping[10.2.156.60],#3)=0` | `min(/Nawari Avaya G450 Media Gateway by SNMP/icmpping[10.2.156.60],#3)=1` | `1` | `service_outage` | VERIFIED |

---

### BATCH 08: Nawari Avaya Session Manager by SNMP
- **Template ID:** `10795`
- **Template Name:** `Nawari Avaya Session Manager by SNMP`
- **Monitored Scope:** Session Manager routing states, SIP Entity down/partially-up/deny-new-service, OPTIONS latency, and signaling failure rates.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32698` | Avaya SM: SIP Entity Down (Communication Manager) | High | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=3` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1` | `1` | `service_outage` | VERIFIED |
| `32699` | Avaya SM: SIP Entity Down (Avaya SBCE) | High | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=3` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1` | `1` | `service_outage` | VERIFIED |
| `32743` | Avaya SM: Management Telemetry Stale or Loss of Monitoring | High | `nodata(/Nawari Avaya Session Manager by SNMP/system.uptime,10m)=1` | `last(/Nawari Avaya Session Manager by SNMP/system.uptime)>=0` | `1` | `monitoring_failure` | VERIFIED |
| `32744` | Avaya SM: SIP Entity PARTIALLY UP (Communication Manager) | Avg | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=2` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1` | `1` | `degradation` | VERIFIED |
| `32745` | Avaya SM: SIP Entity DENY NEW SERVICE (Communication Manager) | High | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=4` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.cm)=1` | `1` | `service_outage` | VERIFIED |
| `32746` | Avaya SM: SIP Entity PARTIALLY UP (Avaya SBCE) | Avg | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=2` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1` | `1` | `degradation` | VERIFIED |
| `32747` | Avaya SM: SIP Entity DENY NEW SERVICE (Avaya SBCE) | High | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=4` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.status.sbce)=1` | `1` | `service_outage` | VERIFIED |
| `32748` | Avaya SM: SIP OPTIONS Latency Elevated (> 250ms) | Warn | `min(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.rtt.cm,5m)>250` | `max(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_entity.rtt.cm,5m)<100` | `1` | `degradation` | VERIFIED |
| `32749` | Avaya SM: Synthetic SIP OPTIONS Probe Failure | High | `count(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_options_status,#2,"eq",0)>=2` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.sip_options_status)=1` | `1` | `service_outage` | VERIFIED |
| `32750` | Avaya SM: Session Manager Signalling Failure Rate High (> 5%) | Avg | `min(/Nawari Avaya Session Manager by SNMP/avaya.sm.signalling_failure_pct,5m)>5` | `max(/Nawari Avaya Session Manager by SNMP/avaya.sm.signalling_failure_pct,5m)<2` | `1` | `degradation` | VERIFIED |
| `32751` | Avaya SM: Critical Enterprise Alarm Reported | High | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.alarms.active_count)>0` | `last(/Nawari Avaya Session Manager by SNMP/avaya.sm.alarms.active_count)=0` | `1` | `degradation` | VERIFIED |
| `32752` | Avaya SM: Session Manager Host Unavailable | Dis | `max(/Nawari Avaya Session Manager by SNMP/icmpping[10.2.156.22],#3)=0` | `min(/Nawari Avaya Session Manager by SNMP/icmpping[10.2.156.22],#3)=1` | `1` | `service_outage` | VERIFIED |

---

### BATCH 09: Nawari SIP Trunk by Trapper
- **Template ID:** `10797`
- **Template Name:** `Nawari SIP Trunk by Trapper`
- **Monitored Scope:** Safaricom SIP carrier interconnect, consecutive OPTIONS failures, 5xx error rates, DNS resolution, and TLS certificate expiration.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32753` | SIP Trunk: Endpoint Unreachable | Dis | `max(/Nawari SIP Trunk by Trapper/icmpping[10.2.156.100],#3)=0` | `min(/Nawari SIP Trunk by Trapper/icmpping[10.2.156.100],#3)=1` | `1` | `service_outage` | VERIFIED |
| `32754` | SIP Trunk: Consecutive OPTIONS Probe Failures | High | `count(/Nawari SIP Trunk by Trapper/sip.trunk.options_status,#4,"eq",0)>=3` | `min(/Nawari SIP Trunk by Trapper/sip.trunk.options_status,#2)=1` | `1` | `service_outage` | VERIFIED |
| `32755` | SIP Trunk: High Error Response Rate (5xx/4xx > 10%) | Avg | `min(/Nawari SIP Trunk by Trapper/sip.trunk.error_rate_pct,5m)>10` | `max(/Nawari SIP Trunk by Trapper/sip.trunk.error_rate_pct,5m)<3` | `1` | `degradation` | VERIFIED |
| `32756` | SIP Trunk: DNS SRV/A Resolution Failure | High | `count(/Nawari SIP Trunk by Trapper/sip.trunk.dns_resolved,#2,"eq",0)>=2` | `last(/Nawari SIP Trunk by Trapper/sip.trunk.dns_resolved)=1` | `1` | `service_outage` | VERIFIED |
| `32757` | SIP Trunk: TLS Certificate Expiration Warning (<= 30 days) | Warn | `last(sip.trunk.tls_cert_expiry_days)<=30 and last(...)>7` | `last(sip.trunk.tls_cert_expiry_days)>30` | `1` | `degradation` | VERIFIED |
| `32758` | SIP Trunk: TLS Certificate Expiration Critical (<= 7 days) | High | `last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)<=7` | `last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_expiry_days)>7` | `1` | `service_outage` | VERIFIED |

---

### BATCH 10: Nawari Avaya CMS and WFO by Trapper
- **Template ID:** `10796`
- **Template Name:** `Nawari Avaya CMS and WFO by Trapper`
- **Monitored Scope:** Contact center queue SLAs, telemetry freshness, compliance voice recording pipeline health, and disk spool capacity.

| Trigger ID | Description | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `32734` | Avaya CMS: Queue Service Level Degradation (< 80%) | Warn | `min(avaya.cms.sla_pct,15m)<80 and last(...)>=0` | `min(avaya.cms.sla_pct,15m)>=85` | `1` | `degradation` | VERIFIED |
| `32735` | Avaya CMS: Telemetry Data Stale (> 45m) | Warn | `nodata(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct,45m)=1` | `last(/Nawari Avaya CMS and WFO by Trapper/avaya.cms.sla_pct)>=0` | `1` | `monitoring_failure` | VERIFIED |
| `32736` | WFO: Compliance Voice Recording Pipeline Health Failure | High | `last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.pipeline_status)=0` | `last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.pipeline_status)=1` | `1` | `service_outage` | VERIFIED |
| `32737` | WFO: Compliance Voice Recording Spool Disk Storage Warning (< 15%) | Warn | `last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.disk_free_pct)<15` | `last(/Nawari Avaya CMS and WFO by Trapper/wfo.recording.disk_free_pct)>20` | `1` | `degradation` | VERIFIED |

---

### BATCH 11: Network Generic Device by SNMP & Prototypes
- **Template ID:** `10226`
- **Template Name:** `Network Generic Device by SNMP`
- **Monitored Scope:** Standard RFC 1213 network switch triggers and LLD interface prototypes.

| Trigger / Proto ID | Description | Type | Sev | Problem Expression | Recovery Expression | Mode | Notification Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `21709` | Unavailable by ICMP ping | Trigger | Dis | `max(/Network Generic Device by SNMP/icmpping,#3)=0` | `min(/Network Generic Device by SNMP/icmpping,#3)=1` | `1` | `service_outage` | VERIFIED |
| `21710` | High ICMP ping loss | Trigger | Warn | `min(/Network Generic Device by SNMP/icmppingloss,5m)>20` | `max(/Network Generic Device by SNMP/icmppingloss,5m)<5` | `1` | `degradation` | VERIFIED |
| `21711` | High ICMP ping response time | Trigger | Warn | `avg(/Network Generic Device by SNMP/icmppingsec,5m)>0.15` | `avg(/Network Generic Device by SNMP/icmppingsec,5m)<0.10` | `1` | `degradation` | VERIFIED |
| `21712` | System name has changed | Trigger | Info | `last(system.name,#1)<>last(system.name,#2) and length(...)>0` | *Single-Expression Event (EX-01)* | `0` | `informational` | VERIFIED |
| `21713` | Host has been restarted | Trigger | Warn | `(last(net.uptime)<10m and last(...)>0) or (last(net.uptime)=0 and last(hw.uptime)<10m)` | `last(net.uptime)>=10m or last(hw.uptime)>=10m` | `1` | `informational` | VERIFIED |
| `21714` | No SNMP data collection | Trigger | Warn | `max(/Network Generic Device by SNMP/zabbix[host,snmp,available],#3)=0` | `min(/Network Generic Device by SNMP/zabbix[host,snmp,available],#3)=1` | `1` | `monitoring_failure` | VERIFIED |
| `29741` | Interface {#IFNAME}({#IFALIAS}): Speed changed | Proto | Info | `(last(net.if.speed)>0 and last(net.if.speed)<last(net.if.speed,#2))` | `last(net.if.speed)>=last(net.if.speed,#2)` | `1` | `informational` | VERIFIED |
| `29742` | Interface {#IFNAME}({#IFALIAS}): High bandwidth usage | Proto | Warn | `(min(net.if.in,15m)>(speed*80/100) or min(net.if.out,15m)>(speed*80/100))` | `(max(net.if.in,15m)<(speed*60/100) and max(net.if.out,15m)<(speed*60/100))` | `1` | `degradation` | VERIFIED |
| `29743` | Interface {#IFNAME}({#IFALIAS}): High error rate | Proto | Warn | `(min(net.if.in.errors,5m)>{$IF_ERRORS_WARN} or min(net.if.out.errors,5m)>{$IF_ERRORS_WARN})` | `(max(net.if.in.errors,5m)<1 and max(net.if.out.errors,5m)<1)` | `1` | `degradation` | VERIFIED |
| `29744` | Interface {#IFNAME}({#IFALIAS}): Link down | Proto | Avg | `{$IFCONTROL:"{#IFNAME}"}=1 and last(net.if.status)=2` | `last(net.if.status)=1` | `1` | `component_failure` | VERIFIED |
| `29745` | Interface {#IFNAME}({#IFALIAS}): In half-duplex mode | Proto | Warn | `last(net.if.duplex)=2` | `last(net.if.duplex)=3` | `1` | `degradation` | VERIFIED |

---

## 3. Empirical Verification Summary

1. **Automated Unit & Staging Test:** `tests/unit/test_phase13_8b_threshold_implementation.py` (9/9 Passed in 0.48s).
2. **Master Regression Suites:**
   - `test_phase13_8a_threshold_rationalisation.py` (14/14 Passed)
   - `test_phase13_8_runtime_verification_and_service_semantics.py` (10/10 Passed)
   - `test_phase6_1_hardening.py` (7/7 Passed)
   - `test_provisioning_idempotency.py` (2/2 Passed)
   - `scripts/verify_phase10.sh` (9/9 Passed)
   - `scripts/verify_phase13.sh` (12/12 Passed)
3. **Change Manifest & Snapshot Verification:** Change manifest committed at `provisioning/zabbix/snapshots/phase13_8b_change_manifest.json` confirms 79 records processed across 11 batches with zero errors.

