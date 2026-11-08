# Phase 13.4 — Migration and Validation Report

## 1. Executive Summary

Nawari Phase 13.4 achieves full transition to **Zabbix-native communication alerting**, provisions declarative Microsoft 365 Exchange Online notification pipelines, and delivers hierarchical service correlation in Nawari.

All 45 communication alert rules previously formulated in Phase 13.3 have been mapped and provisioned as native Zabbix 7.4 template triggers and items. The legacy Python alerting engine has been decommissioned from active runtime duty and assigned the status `PASSIVE_MIGRATED_TO_ZABBIX`.

---

## 2. Complete 45-Rule Migration Matrix

| # | Rule Name | Subsystem | Phase 13.3 Status | Phase 13.4 Zabbix Trigger / Template | Severity |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | `SBCE: Appliance Unreachable` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `icmpping,#3=0` | DISASTER |
| 2 | `SBCE: Management Interface Unreachable` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `net.tcp.service[https,,443]=0` | HIGH |
| 3 | `SBCE: Sustained High SIP Failure Rate` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `sbce.sip.failure_rate,5m>5` | HIGH |
| 4 | `SBCE: Active Session Capacity Warning` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `sbce.calls.active_pct,5m>=80` | WARNING |
| 5 | `SBCE: Active Session Capacity Critical` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `sbce.calls.active_pct,3m>=95` | DISASTER |
| 6 | `SBCE: Interface Error/Discard Elevated` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `sbce.net.error_pct,5m>1` | AVERAGE |
| 7 | `SBCE: Licensed Capacity Limit Approaching` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `sbce.license.utilization_pct>=90` | HIGH |
| 8 | `SBCE: Active Session Telemetry Stale` | Avaya SBCE | MIGRATED_PASSIVE | `nawari_avaya_sbce.yaml` / `nodata(sbce.calls.active,10m)=1` | WARNING |
| 9 | `SM: Session Manager Host Unavailable` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `icmpping,#3=0` | DISASTER |
| 10 | `SM: SIP Entity Down (Communication Manager)` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.sip.entity.cm.state=0` | DISASTER |
| 11 | `SM: SIP Entity Down (Avaya SBCE)` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.sip.entity.sbce.state=0` | DISASTER |
| 12 | `SM: SIP Entity State Partially Up` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.sip.entity.overall.state=1` | AVERAGE |
| 13 | `SM: SIP Entity in Deny New Service` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.sip.entity.overall.state=3` | HIGH |
| 14 | `SM: Synthetic SIP OPTIONS Probe Failure` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.synthetic.options.status,#2=0` | HIGH |
| 15 | `SM: SIP OPTIONS Latency Elevated` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.synthetic.options.latency,5m>250` | WARNING |
| 16 | `SM: Signalling Failure Rate High` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.signalling.failure_rate,5m>5` | HIGH |
| 17 | `SM: Active Alarms Reported` | Session Manager | MIGRATED_PASSIVE | `template_nawari_avaya_sm.yaml` / `sm.alarms.active_count>0` | HIGH |
| 18 | `CM: Communication Manager Processor Unreachable` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `icmpping,#3=0` | DISASTER |
| 19 | `CM: Real-Call Packet Loss High` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `cm.rtcp.packet_loss,15m>1` | HIGH |
| 20 | `CM: Real-Call Peak Jitter High` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `cm.rtcp.jitter,15m>30` | WARNING |
| 21 | `CM: Call Rate Abnormal Drop` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `cm.call.rate_drop_pct>80` | HIGH |
| 22 | `CM: Call Processing CPU Occupancy Critical` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `cm.cpu.occupancy,5m>90` | DISASTER |
| 23 | `CM: Performance Telemetry Stale or Uncollected` | Comm Manager | MIGRATED_PASSIVE | `template_nawari_avaya_cm.yaml` / `nodata(cm.call.rate,15m)=1` | WARNING |
| 24 | `G450: Media Gateway Chassis Unreachable` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `icmpping,#3=0` | HIGH |
| 25 | `G450: Power Supply Unit Failure` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `g450.hardware.psu_status=2` | DISASTER |
| 26 | `G450: Fan Tray Failure` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `g450.hardware.fan_status=2` | HIGH |
| 27 | `G450: Chassis Ambient Temperature Threshold Exceeded` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `g450.hardware.temp,5m>45` | HIGH |
| 28 | `G450: E1/ISDN Primary Trunk Port Down` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `g450.port.e1_isdn_status=2` | HIGH |
| 29 | `G450: Gateway Missing Telemetry or SNMP Timeout` | G450 Gateway | MIGRATED_PASSIVE | `template_nawari_avaya_g450.yaml` / `nodata(g450.hardware.psu_status,10m)=1` | WARNING |
| 30 | `SIP Trunk: Endpoint Unreachable` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `icmpping,#3=0` | DISASTER |
| 31 | `SIP Trunk: Consecutive OPTIONS Probe Failures` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `sip.trunk.options.status,#3=0` | HIGH |
| 32 | `SIP Trunk: High Error Response Rate` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `sip.trunk.error_rate_5xx,5m>10` | HIGH |
| 33 | `SIP Trunk: DNS SRV/A Resolution Failure` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `net.dns[,,SRV]=0` | HIGH |
| 34 | `SIP Trunk: TLS Certificate Expiration Warning` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `sip.trunk.tls_cert_days<=30` | WARNING |
| 35 | `SIP Trunk: TLS Certificate Expiration Critical` | SIP Trunks | MIGRATED_PASSIVE | `template_nawari_sip_trunk.yaml` / `sip.trunk.tls_cert_days<=7` | HIGH |
| 36 | `Synthetic Voice: Call Setup Timeout` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.setup_time,3m>4000` | AVERAGE |
| 37 | `Synthetic Voice: Call Completion Failure / Congestion` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.success_flag=0` | HIGH |
| 38 | `Synthetic Voice: PESQ/POLQA Audio Quality Degradation` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.mos<3.5` | HIGH |
| 39 | `Synthetic Voice: SIP vs AMI Result Mismatch` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.protocol_mismatch=1` | AVERAGE |
| 40 | `Synthetic Voice: Connected Duration Below Criterion` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.duration<5` | AVERAGE |
| 41 | `Synthetic Voice: Consecutive Test Failures` | Synthetic Voice | MIGRATED_PASSIVE | `nawari_voice_synthetic_probe.yaml` / `voice.synthetic.success_flag,#3=0` | HIGH |
| 42 | `Avaya CMS: Queue Service Level Degradation` | Contact Centre | MIGRATED_PASSIVE | `template_nawari_avaya_cms_wfo.yaml` / `cms.queue.service_level,15m<80` | AVERAGE |
| 43 | `Avaya CMS: Real-Time Data Feed Stale or Disconnected` | Contact Centre | MIGRATED_PASSIVE | `template_nawari_avaya_cms_wfo.yaml` / `nodata(cms.agent.logged_in,10m)=1` | WARNING |
| 44 | `WFO: Compliance Voice Recording Pipeline Health Failure` | Voice Recording | MIGRATED_PASSIVE | `template_nawari_avaya_cms_wfo.yaml` / `wfo.recorder.pipeline_status=0` | HIGH |
| 45 | `WFO: Compliance Voice Recording Spool Disk Storage Warning` | Voice Recording | MIGRATED_PASSIVE | `template_nawari_avaya_cms_wfo.yaml` / `wfo.recorder.spool_disk_pct,5m>85` | WARNING |

---

## 3. Automated Regression & Verification Gate Results

### Test Suite Execution
- **Command:** `PYTHONPATH=. pytest tests/`
- **Result:** **415 passed, 0 failed, 0 skipped** in 140.61s.
- **Coverage:** Full integration, unit, performance, recovery, and Phase 13.4 native alerting and correlation test suites.

### Verification Gate Summary
- **Phase 10 Verification Gate (`scripts/verify_phase10.sh`):** 9/9 checks PASSED.
- **Phase 13 Verification Gate (`scripts/verify_phase13.sh`):** 12/12 checks PASSED.

---

## 4. Engineering Rigour & Safety Protocol

1. **Production Mutation Lock:** `HARD_PRODUCTION_DENY` is strictly enforced. No physical equipment or network interfaces have been altered.
2. **Telemetry Evidence Integrity:** Zero telemetry points are claimed as `VERIFIED_LIVE`. All integrations are accurately classified as `CONFIGURED_SIMULATED`.
3. **Cross-Repository Isolation:** The Sentra repository (`/Users/madeira/Desktop/Projects/sentra`) remains pristine at commit `9970404` on branch `origin/main`.
4. **Credential Safety:** Microsoft 365 secrets remain unconfigured; media types are safely set to `DISABLED` until customer provisioning.

