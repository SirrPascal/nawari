# Phase 13.4 — Communication Trigger Catalogue (Zabbix 7.4 Native)

## Overview

This catalogue documents all **45 communication monitoring triggers** provisioned in native Zabbix 7.4 YAML templates under `provisioning/zabbix/templates/`. Each trigger defines native expression syntax, evaluation criteria, severity mapping, recovery expressions, and tag attributes.

---

## 1. Avaya SBCE Triggers (8 Rules)
**Template:** `provisioning/zabbix/templates/nawari_avaya_sbce.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `SBCE: Appliance Unreachable (ICMP Ping Down)` | DISASTER | `max(/Avaya SBCE by SNMP/icmpping,#3)=0` | SBCE appliance failed 3 consecutive ICMP probes. Recovery: ping returns 1. | `component: sbce-core`, `scope: availability` |
| 2 | `SBCE: Management Interface Unreachable` | HIGH | `last(/Avaya SBCE by SNMP/net.tcp.service[https,,443])=0` | SBCE EMS management web interface is unreachable on port 443. | `component: sbce-mgmt`, `scope: availability` |
| 3 | `SBCE: Sustained High SIP Failure Rate (>5%)` | HIGH | `min(/Avaya SBCE by SNMP/sbce.sip.failure_rate,5m)>5` | SIP client/server error responses (4xx/5xx) exceed 5% over 5 minutes. | `component: sbce-sip`, `scope: performance` |
| 4 | `SBCE: Active Session Capacity Warning (>=80%)` | WARNING | `min(/Avaya SBCE by SNMP/sbce.calls.active_pct,5m)>=80` | Concurrent call sessions exceed 80% of configured system capacity. | `component: sbce-capacity`, `scope: performance` |
| 5 | `SBCE: Active Session Capacity Critical (>=95%)` | DISASTER | `min(/Avaya SBCE by SNMP/sbce.calls.active_pct,3m)>=95` | Concurrent call sessions exceed 95% capacity; risk of call dropping. | `component: sbce-capacity`, `scope: availability` |
| 6 | `SBCE: Interface Error or Discard Rate Elevated (>1%)` | AVERAGE | `min(/Avaya SBCE by SNMP/sbce.net.error_pct,5m)>1` | Media interface packet discards/errors exceed 1% over 5m window. | `component: sbce-network`, `scope: performance` |
| 7 | `SBCE: Licensed Capacity Limit Approaching (>=90%)` | HIGH | `last(/Avaya SBCE by SNMP/sbce.license.utilization_pct)>=90` | Active license pool consumption exceeds 90% of installed capacity. | `component: sbce-license`, `scope: performance` |
| 8 | `SBCE: Active Session Telemetry Stale or Missing` | WARNING | `nodata(/Avaya SBCE by SNMP/sbce.calls.active,10m)=1` | No active session telemetry received from SBCE for over 10 minutes. | `component: sbce-telemetry`, `scope: performance` |

---

## 2. Avaya Session Manager Triggers (9 Rules)
**Template:** `provisioning/zabbix/templates/template_nawari_avaya_sm.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 9 | `SM: Session Manager Host Unavailable (ICMP Ping Down)` | DISASTER | `max(/Avaya Session Manager by SNMP/icmpping,#3)=0` | Session Manager host failed 3 consecutive ICMP pings. | `component: sm-core`, `scope: availability` |
| 10 | `SM: SIP Entity Down (Communication Manager)` | DISASTER | `last(/Avaya Session Manager by SNMP/sm.sip.entity.cm.state)=0` | SIP link to core Communication Manager is out of service. | `component: sm-sip-link`, `scope: availability` |
| 11 | `SM: SIP Entity Down (Avaya SBCE)` | DISASTER | `last(/Avaya Session Manager by SNMP/sm.sip.entity.sbce.state)=0` | SIP link to perimeter Session Border Controller is down. | `component: sm-sip-link`, `scope: availability` |
| 12 | `SM: SIP Entity State Partially Up (One or more links degraded)` | AVERAGE | `last(/Avaya Session Manager by SNMP/sm.sip.entity.overall.state)=1` | One or more redundant SIP entity links are offline. | `component: sm-sip-link`, `scope: performance` |
| 13 | `SM: SIP Entity in Deny New Service Maintenance State` | HIGH | `last(/Avaya Session Manager by SNMP/sm.sip.entity.overall.state)=3` | SIP entity is marked in Deny New Service (draining/maintenance). | `component: sm-admin`, `scope: availability` |
| 14 | `SM: Synthetic SIP OPTIONS Probe Failure` | HIGH | `max(/Avaya Session Manager by SNMP/sm.synthetic.options.status,#2)=0` | Synthetic SIP OPTIONS ping to SM failed twice consecutively. | `component: sm-options`, `scope: availability` |
| 15 | `SM: SIP OPTIONS Latency Elevated (>250ms)` | WARNING | `min(/Avaya Session Manager by SNMP/sm.synthetic.options.latency,5m)>250` | SIP OPTIONS round-trip response time exceeds 250ms over 5m. | `component: sm-options`, `scope: performance` |
| 16 | `SM: Signalling Failure Rate High (>5% in 5m)` | HIGH | `min(/Avaya Session Manager by SNMP/sm.signalling.failure_rate,5m)>5` | SIP transaction failure rate exceeds 5% across entity routes. | `component: sm-sip`, `scope: performance` |
| 17 | `SM: Active Alarms Reported by Appliance Agent` | HIGH | `last(/Avaya Session Manager by SNMP/sm.alarms.active_count)>0` | Session Manager appliance reported active SNMP alarms. | `component: sm-alarms`, `scope: performance` |

---

## 3. Avaya Communication Manager Triggers (6 Rules)
**Template:** `provisioning/zabbix/templates/template_nawari_avaya_cm.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 18 | `CM: Communication Manager Processor Unreachable (ICMP Down)` | DISASTER | `max(/Avaya Communication Manager by SNMP/icmpping,#3)=0` | CM Main/Duplex processor unreachable via ICMP ping. | `component: cm-core`, `scope: availability` |
| 19 | `CM: Real-Call Packet Loss High (>1% over 15m window)` | HIGH | `min(/Avaya Communication Manager by SNMP/cm.rtcp.packet_loss,15m)>1` | RTCP-XR packet loss reported on active trunks exceeds 1%. | `component: cm-voice-quality`, `scope: performance` |
| 20 | `CM: Real-Call Peak Jitter High (>30ms over 15m window)` | WARNING | `min(/Avaya Communication Manager by SNMP/cm.rtcp.jitter,15m)>30` | Real-call RTCP-XR packet jitter exceeds 30 milliseconds. | `component: cm-voice-quality`, `scope: performance` |
| 21 | `CM: Call Rate Abnormal Drop (>80% drop vs baseline)` | HIGH | `last(/Avaya Communication Manager by SNMP/cm.call.rate_drop_pct)>80` | Sudden abnormal drop in completed call volume during peak hours. | `component: cm-traffic`, `scope: performance` |
| 22 | `CM: Call Processing CPU Occupancy Critical (>90%)` | DISASTER | `min(/Avaya Communication Manager by SNMP/cm.cpu.occupancy,5m)>90` | CM server processor occupancy exceeds 90% over 5m. | `component: cm-capacity`, `scope: performance` |
| 23 | `CM: Performance Telemetry Stale or Uncollected (>15m)` | WARNING | `nodata(/Avaya Communication Manager by SNMP/cm.call.rate,15m)=1` | CM CDR/RTCP metrics not received for more than 15 minutes. | `component: cm-telemetry`, `scope: performance` |

---

## 4. Avaya G450 Media Gateway Triggers (6 Rules)
**Template:** `provisioning/zabbix/templates/template_nawari_avaya_g450.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 24 | `G450: Media Gateway Chassis Unreachable (ICMP Ping Down)` | HIGH | `max(/Avaya G450 Media Gateway by SNMP/icmpping,#3)=0` | Gateway chassis fails 3 consecutive ICMP echo requests. | `component: g450-gateway`, `scope: availability` |
| 25 | `G450: Power Supply Unit Failure (Redundant PSU Fault)` | DISASTER | `last(/Avaya G450 Media Gateway by SNMP/g450.hardware.psu_status)=2` | Gateway reports failure or removal of redundant power supply. | `component: g450-hardware`, `scope: availability` |
| 26 | `G450: Fan Tray Failure or RPM Critical Degradation` | HIGH | `last(/Avaya G450 Media Gateway by SNMP/g450.hardware.fan_status)=2` | Gateway cooling fan tray failure detected. | `component: g450-hardware`, `scope: performance` |
| 27 | `G450: Chassis Ambient Temperature Threshold Exceeded (>45C)` | HIGH | `min(/Avaya G450 Media Gateway by SNMP/g450.hardware.temp,5m)>45` | Internal chassis temperature sensor exceeds 45°C. | `component: g450-environmental`, `scope: performance` |
| 28 | `G450: E1/ISDN Primary Trunk Port Down` | HIGH | `last(/Avaya G450 Media Gateway by SNMP/g450.port.e1_isdn_status)=2` | E1/PRI circuit port operational status is down (LOS/LOF). | `component: g450-trunk`, `scope: availability` |
| 29 | `G450: Gateway Missing Telemetry or SNMP Timeout` | WARNING | `nodata(/Avaya G450 Media Gateway by SNMP/g450.hardware.psu_status,10m)=1` | No SNMP responses received from G450 gateway for 10 minutes. | `component: g450-telemetry`, `scope: performance` |

---

## 5. External SIP Carrier Trunks (6 Rules)
**Template:** `provisioning/zabbix/templates/template_nawari_sip_trunk.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 30 | `SIP Trunk: Endpoint Unreachable (ICMP Down)` | DISASTER | `max(/SIP Trunk Carrier Monitoring/icmpping,#3)=0` | Primary carrier SBC IP address is completely unreachable. | `component: sip-trunk`, `scope: availability` |
| 31 | `SIP Trunk: Consecutive OPTIONS Probe Failures` | HIGH | `max(/SIP Trunk Carrier Monitoring/sip.trunk.options.status,#3)=0` | Carrier fails 3 consecutive SIP OPTIONS heartbeat transactions. | `component: sip-trunk`, `scope: availability` |
| 32 | `SIP Trunk: High Error Response Rate (>10% 5xx in 5m)` | HIGH | `min(/SIP Trunk Carrier Monitoring/sip.trunk.error_rate_5xx,5m)>10` | Carrier returning 500/503 Service Unavailable on > 10% of attempts. | `component: sip-trunk`, `scope: performance` |
| 33 | `SIP Trunk: DNS SRV/A Resolution Failure for Carrier FQDN` | HIGH | `last(/SIP Trunk Carrier Monitoring/net.dns[,,SRV])=0` | DNS resolution failure for carrier SIP proxy domain name. | `component: sip-trunk-dns`, `scope: availability` |
| 34 | `SIP Trunk: TLS Certificate Expiration Warning (<= 30 days)` | WARNING | `last(/SIP Trunk Carrier Monitoring/sip.trunk.tls_cert_days)<=30` | Mutual-TLS / SIP-TLS certificate expires within 30 days. | `component: sip-trunk-cert`, `scope: performance` |
| 35 | `SIP Trunk: TLS Certificate Expiration Critical (<= 7 days)` | HIGH | `last(/SIP Trunk Carrier Monitoring/sip.trunk.tls_cert_days)<=7` | Mutual-TLS certificate expires within 7 days; immediate renew required. | `component: sip-trunk-cert`, `scope: availability` |

---

## 6. Synthetic Voice Probes (6 Rules)
**Template:** `provisioning/zabbix/templates/nawari_voice_synthetic_probe.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 36 | `Synthetic Voice: Call Setup Timeout (>4000ms)` | AVERAGE | `min(/Asterisk Synthetic Voice Probe/voice.synthetic.setup_time,3m)>4000` | Automated test call takes over 4 seconds to receive 180 Ringing. | `component: voice-probe`, `scope: performance` |
| 37 | `Synthetic Voice: Call Completion Failure / Congestion` | HIGH | `last(/Asterisk Synthetic Voice Probe/voice.synthetic.success_flag)=0` | Synthetic test call failed or received congested SIP code. | `component: voice-probe`, `scope: availability` |
| 38 | `Synthetic Voice: PESQ/POLQA Audio Quality Degradation (MOS < 3.5)` | HIGH | `last(/Asterisk Synthetic Voice Probe/voice.synthetic.mos)<3.5` | Synthesized RTP audio loopback PESQ MOS score dropped below 3.5. | `component: voice-probe-quality`, `scope: performance` |
| 39 | `Synthetic Voice: SIP vs AMI Result Mismatch` | AVERAGE | `last(/Asterisk Synthetic Voice Probe/voice.synthetic.protocol_mismatch)=1` | SIP signalling indicates call success but Asterisk AMI reports failure. | `component: voice-probe-audit`, `scope: performance` |
| 40 | `Synthetic Voice: Connected Duration Below Criterion (<5s)` | AVERAGE | `last(/Asterisk Synthetic Voice Probe/voice.synthetic.duration)<5` | Synthetic call disconnected prematurely before media playback ended. | `component: voice-probe`, `scope: performance` |
| 41 | `Synthetic Voice: Consecutive Test Failures (3 runs failed)` | HIGH | `max(/Asterisk Synthetic Voice Probe/voice.synthetic.success_flag,#3)=0` | 3 consecutive automated test calls have failed across the route. | `component: voice-probe`, `scope: availability` |

---

## 7. Contact Centre & Voice Recording (4 Rules)
**Template:** `provisioning/zabbix/templates/template_nawari_avaya_cms_wfo.yaml`

| # | Trigger Name | Severity | Expression | Description & Recovery | Tags |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 42 | `Avaya CMS: Queue Service Level Degradation (<80% in 20s)` | AVERAGE | `min(/Avaya CMS and WFO Monitoring/cms.queue.service_level,15m)<80` | Contact centre ACD call answer rate dropped below 80% SLA. | `component: contact-centre`, `scope: performance` |
| 43 | `Avaya CMS: Real-Time Data Feed Stale or Disconnected` | WARNING | `nodata(/Avaya CMS and WFO Monitoring/cms.agent.logged_in,10m)=1` | CMS RTCL / OpenLink socket feed inactive for over 10 minutes. | `component: contact-centre-telemetry`, `scope: performance` |
| 44 | `WFO: Compliance Voice Recording Pipeline Health Failure` | HIGH | `last(/Avaya CMS and WFO Monitoring/wfo.recorder.pipeline_status)=0` | Verint / WFO compliance voice recording stream dropped. | `component: call-recording`, `scope: availability` |
| 45 | `WFO: Compliance Voice Recording Spool Disk Storage Warning (>85%)`| WARNING | `min(/Avaya CMS and WFO Monitoring/wfo.recorder.spool_disk_pct,5m)>85` | Compliance audio spool storage partition exceeds 85% utilization. | `component: call-recording-storage`, `scope: performance` |

---

## Summary Statistics
- **Total Provisioned Triggers:** 45
- **DISASTER:** 8
- **HIGH:** 21
- **AVERAGE:** 8
- **WARNING:** 8
- **INFORMATION:** 0

