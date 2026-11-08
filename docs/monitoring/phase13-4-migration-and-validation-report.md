# Phase 13.4 — Migration, Runtime Investigation & Validation Report

## 1. Executive Summary & Critical Investigation Resolution

### Investigation Finding: Why Templates Were Initially Unlinked
During earlier iterations of Phase 13.4, all 7 communication templates and their 59 triggers were successfully imported into Zabbix 7.4. However, they were initially classified as unlinked because:
1. The Zabbix host definitions in `provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml` only defined `avaya-sbce-01`.
2. The remaining Avaya and communication monitoring targets (`avaya-sm-01`, `avaya-cm-01`, `avaya-g450-01`, `sip-trunk-carrier-01`, `avaya-cms-01`) had not yet been declared in host inventory.
3. In Zabbix architecture, templates and triggers exist in **Data collection -> Templates**, but their triggers are only evaluated when linked to active hosts.

### Remediation & Live Provisioning
1. **Host Infrastructure Provisioned:** All 5 missing communication hosts were declared in `provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml` and applied via `Reconciler.apply()`.
2. **Template Linkage Completed:** Every communication template is now linked to its respective host in the live Zabbix instance.
3. **Four Designated Administrators Provisioned:** Created user group `Nawari Avaya & Communications Administrators` and provisioned all four administrators with enabled 24x7 email media in Zabbix.
4. **Authoritative Action Created:** Provisioned action `Nawari Avaya & Communication Alerting` (ID: 7) targeting the group with step escalations (1800s cooldown repeat) and maintenance suppression.
5. **Python Engine Decommissioned:** Confirmed `CommunicationAlertEngine` is decoupled and set to `PASSIVE_MIGRATED_TO_ZABBIX`.

---

## 2. Live Zabbix Environment Details

- **Zabbix Server Version:** Zabbix 7.4.16 (`zabbix/zabbix-server-pgsql:alpine-7.4-latest`)
- **Zabbix Web Frontend:** `http://localhost:8088` (API endpoint: `http://localhost:8088/api_jsonrpc.php`)
- **Database Engine:** PostgreSQL 17 (`postgres:17-alpine`) on port 5433
- **Total Monitored Hosts in Zabbix:** 11 hosts
- **Total Communication Triggers Active on Hosts:** 59 triggers (45 communication catalogue triggers + appliance/SNMP base triggers)

---

## 3. Four Designated Administrators & User Group

**Zabbix User Group:** `Nawari Avaya & Communications Administrators` (ID: `14`)

| Administrator Name | Username | User ID | Destination Email Address | Configured Media ID | Active Period | Severities | Verification State |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **John Gacomo** | `john.gacomo` | 3 | `John.Gacomo@kenya-airways.com` | Media 1 (Type 1) | `1-7,00:00-24:00` | 63 (All) | `CONFIGURED_UNVERIFIED` |
| **Robinson Wainaina**| `robinson.wainaina`| 4 | `Robinson.Wainaina@kenya-airways.com` | Media 2 (Type 1) | `1-7,00:00-24:00` | 63 (All) | `CONFIGURED_UNVERIFIED` |
| **Pascal Gathungu** | `pascal.gathungu` | 5 | `Pascal.Gathungu@kenya-airways.com` | Media 3 (Type 1) | `1-7,00:00-24:00` | 63 (All) | `CONFIGURED_UNVERIFIED` |
| **Mercy Vaati** | `mercy.vaati` | 6 | `Mercy.Vaati@kenya-airways.com` | Media 4 (Type 1) | `1-7,00:00-24:00` | 63 (All) | `CONFIGURED_UNVERIFIED` |

---

## 4. Complete 45-Trigger Runtime Verification Matrix

*Directly reconciled and verified via the live Zabbix 7.4 JSON-RPC API:*

| # | Alert ID & Rule Name | Source Template | Zabbix Trigger ID | Trigger Expression | Linked Host(s) | Status | State | Provisioning Result |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `ALERT-SBCE-001` SBCE Appliance Unreachable | `Nawari Avaya SBCE by SNMP` | 32708 | `last(/Nawari Avaya SBCE by SNMP/icmpping[10.2.156.131])=0` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 2 | `ALERT-SBCE-002` SBCE Management Interface Unreachable | `Nawari Avaya SBCE by SNMP` | 32704 | `last(/Nawari Avaya SBCE by SNMP/net.tcp.service[https,10.2.156.131,443])=0` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 3 | `ALERT-SBCE-003` SBCE Sustained High SIP Failure Rate | `Nawari Avaya SBCE by SNMP` | 32705 | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.sip_failure_rate_pct,5m)>5` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 4 | `ALERT-SBCE-004` SBCE Active Session Capacity Warning | `Nawari Avaya SBCE by SNMP` | 32702 | `last(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct)>=80` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 5 | `ALERT-SBCE-005` SBCE Active Session Capacity Critical | `Nawari Avaya SBCE by SNMP` | 32703 | `last(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.license_utilization_pct)>=95` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 6 | `ALERT-SBCE-006` SBCE Interface Discards/Errors Elevated | `Nawari Avaya SBCE by SNMP` | 32707 | `min(/Nawari Avaya SBCE by SNMP/avaya.sbce.if_error_rate_pct,5m)>1` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 7 | `ALERT-SBCE-007` SBCE License Utilization Limit Approached | `Nawari Avaya SBCE by SNMP` | 32706 | `last(/Nawari Avaya SBCE by SNMP/avaya.sbce.allocated_licenses_pct)>=90` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 8 | `ALERT-SBCE-008` SBCE Telemetry Stale or Loss of Monitoring | `Nawari Avaya SBCE by SNMP` | 32701 | `nodata(/Nawari Avaya SBCE by SNMP/avaya.sbce.ems.active_calls,5m)=1` | `avaya-sbce-01`, `mock-avaya-sbce-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 9 | `ALERT-ASM-001` Session Manager Host Unavailable | `Nawari Avaya Session Manager by SNMP` | 32752 | `last(/Nawari Avaya Session Manager by SNMP/icmpping[10.2.156.22])=0` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 10 | `ALERT-ASM-002` Session Manager SIP Entity DOWN (CM) | `Nawari Avaya Session Manager by SNMP` | 32698 | `last(/Nawari Avaya Session Manager by SNMP/sm.sip.entity.cm.state)=0` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 11 | `ALERT-ASM-003` Session Manager SIP Entity DOWN (SBCE) | `Nawari Avaya Session Manager by SNMP` | 32699 | `last(/Nawari Avaya Session Manager by SNMP/sm.sip.entity.sbce.state)=0` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 12 | `ALERT-ASM-004` Session Manager SIP Entity PARTIALLY UP | `Nawari Avaya Session Manager by SNMP` | 32744 | `last(/Nawari Avaya Session Manager by SNMP/sm.sip.entity.cm.state)=1` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 13 | `ALERT-ASM-005` Session Manager SIP Entity DENY NEW SERVICE | `Nawari Avaya Session Manager by SNMP` | 32745 | `last(/Nawari Avaya Session Manager by SNMP/sm.sip.entity.cm.state)=3` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 14 | `ALERT-ASM-006` Synthetic SIP OPTIONS Probe Failure | `Nawari Avaya Session Manager by SNMP` | 32749 | `max(/Nawari Avaya Session Manager by SNMP/sm.synthetic.options.status,#2)=0` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 15 | `ALERT-ASM-007` Session Manager OPTIONS Latency Elevated | `Nawari Avaya Session Manager by SNMP` | 32748 | `min(/Nawari Avaya Session Manager by SNMP/sm.synthetic.options.latency,5m)>250`| `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 16 | `ALERT-ASM-008` Session Manager Signalling Failure Rate High | `Nawari Avaya Session Manager by SNMP` | 32750 | `min(/Nawari Avaya Session Manager by SNMP/sm.signalling.failure_rate,5m)>5` | `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 17 | `ALERT-ASM-009` Session Manager Management Telemetry Stale | `Nawari Avaya Session Manager by SNMP` | 32743 | `nodata(/Nawari Avaya Session Manager by SNMP/system.uptime[sysUpTime.0],15m)=1`| `avaya-sm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 18 | `ALERT-CM-001` Communication Manager Processor Unreachable | `Nawari Avaya Communication Manager by SNMP` | 32733 | `last(/Nawari Avaya Communication Manager by SNMP/icmpping[10.102.10.25])=0` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 19 | `ALERT-CM-002` Communication Manager Active Telephony Alarms | `Nawari Avaya Communication Manager by SNMP` | 32696 | `last(/Nawari Avaya Communication Manager by SNMP/cm.alarms.active_count)>0` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 20 | `ALERT-CM-003` Communication Manager Real-Call Packet Loss High| `Nawari Avaya Communication Manager by SNMP` | 32694 | `min(/Nawari Avaya Communication Manager by SNMP/cm.rtcp.packet_loss,15m)>2.5` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 21 | `ALERT-CM-004` Communication Manager Real-Call Peak Jitter High| `Nawari Avaya Communication Manager by SNMP` | 32695 | `min(/Nawari Avaya Communication Manager by SNMP/cm.rtcp.jitter,15m)>30` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 22 | `ALERT-CM-005` Communication Manager Call Rate Abnormal Drop | `Nawari Avaya Communication Manager by SNMP` | 32731 | `last(/Nawari Avaya Communication Manager by SNMP/cm.call.rate_drop_pct)>80` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 23 | `ALERT-CM-006` Communication Manager Telemetry Stale | `Nawari Avaya Communication Manager by SNMP` | 32732 | `nodata(/Nawari Avaya Communication Manager by SNMP/cm.call.rate,15m)=1` | `avaya-cm-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 24 | `ALERT-G450-001` G450 Media Gateway Chassis Unreachable | `Nawari Avaya G450 Media Gateway by SNMP` | 32742 | `last(/Nawari Avaya G450 Media Gateway by SNMP/icmpping[10.2.156.60])=0` | `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 25 | `ALERT-G450-002` G450 Ambient Temperature Threshold Exceeded | `Nawari Avaya G450 Media Gateway by SNMP` | 32700 | `min(/Nawari Avaya G450 Media Gateway by SNMP/g450.hardware.temp,5m)>45` | `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 26 | `ALERT-G450-003` G450 Power Supply Unit Failure | `Nawari Avaya G450 Media Gateway by SNMP` | 32739 | `last(/Nawari Avaya G450 Media Gateway by SNMP/g450.hardware.psu_status)=2` | `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 27 | `ALERT-G450-004` G450 Fan Tray Failure | `Nawari Avaya G450 Media Gateway by SNMP` | 32740 | `last(/Nawari Avaya G450 Media Gateway by SNMP/g450.hardware.fan_status)=2` | `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 28 | `ALERT-G450-005` G450 E1/ISDN Primary Trunk Port Down | `Nawari Avaya G450 Media Gateway by SNMP` | 32741 | `last(/Nawari Avaya G450 Media Gateway by SNMP/g450.port.e1_isdn_status)=2` | `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 29 | `ALERT-G450-006` G450 Media Gateway Telemetry Missing | `Nawari Avaya G450 Media Gateway by SNMP` | 32738 | `nodata(/Nawari Avaya G450 Media Gateway by SNMP/g450.hardware.psu_status,10m)=1`| `avaya-g450-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 30 | `ALERT-SIP-001` SIP Trunk Endpoint Unreachable | `Nawari SIP Trunk by Trapper` | 32753 | `max(/Nawari SIP Trunk by Trapper/icmpping,#3)=0` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 31 | `ALERT-SIP-002` SIP Trunk Consecutive OPTIONS Probe Failures | `Nawari SIP Trunk by Trapper` | 32754 | `max(/Nawari SIP Trunk by Trapper/sip.trunk.options.status,#3)=0` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 32 | `ALERT-SIP-003` SIP Trunk High Error Response Rate (5xx/4xx) | `Nawari SIP Trunk by Trapper` | 32755 | `min(/Nawari SIP Trunk by Trapper/sip.trunk.error_rate_5xx,5m)>10` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 33 | `ALERT-SIP-004` SIP Trunk DNS SRV/A Resolution Failure | `Nawari SIP Trunk by Trapper` | 32756 | `last(/Nawari SIP Trunk by Trapper/net.dns[,,SRV])=0` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 34 | `ALERT-SIP-005` SIP TLS Certificate Expiration Warning | `Nawari SIP Trunk by Trapper` | 32757 | `last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_days)<=30` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 35 | `ALERT-SIP-006` SIP TLS Certificate Expiration Critical | `Nawari SIP Trunk by Trapper` | 32758 | `last(/Nawari SIP Trunk by Trapper/sip.trunk.tls_cert_days)<=7` | `sip-trunk-carrier-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 36 | `ALERT-SYNTH-001` Synthetic Voice Scheduled Test Missed | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32689 | `nodata(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.success_flag,15m)=1`| `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 37 | `ALERT-SYNTH-002` Synthetic Voice Call Test Failed | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32679 | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.success_flag)=0` | `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 38 | `ALERT-SYNTH-003` Synthetic Voice Call Setup Timeout | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32680 | `min(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.setup_time,3m)>4000` | `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 39 | `ALERT-SYNTH-004` Synthetic Voice SIP vs AMI Mismatch | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32726 | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.protocol_mismatch)=1`| `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 40 | `ALERT-SYNTH-005` Synthetic Voice Connected Duration Short | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32725 | `last(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.duration)<5` | `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 41 | `ALERT-SYNTH-006` Synthetic Voice Consecutive Test Failures | `Nawari Voice Synthetic Probe by Zabbix Trapper` | 32727 | `max(/Nawari Voice Synthetic Probe by Zabbix Trapper/voice.synthetic.success_flag,#3)=0`| `nawari-voice-probe-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 42 | `ALERT-CMS-001` Avaya CMS Queue Service Level Degradation | `Nawari Avaya CMS and WFO by Trapper` | 32734 | `min(/Nawari Avaya CMS and WFO by Trapper/cms.queue.service_level,15m)<80` | `avaya-cms-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 43 | `ALERT-CMS-002` Avaya CMS Telemetry Data Stale | `Nawari Avaya CMS and WFO by Trapper` | 32735 | `nodata(/Nawari Avaya CMS and WFO by Trapper/cms.agent.logged_in,10m)=1` | `avaya-cms-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 44 | `ALERT-WFO-001` Voice Recording Pipeline Health Failure | `Nawari Avaya CMS and WFO by Trapper` | 32736 | `last(/Nawari Avaya CMS and WFO by Trapper/wfo.recorder.pipeline_status)=0` | `avaya-cms-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |
| 45 | `ALERT-WFO-002` Voice Recording Spool Disk Storage Warning | `Nawari Avaya CMS and WFO by Trapper` | 32737 | `min(/Nawari Avaya CMS and WFO by Trapper/wfo.recorder.spool_disk_pct,5m)>85` | `avaya-cms-01` | ENABLED | NORMAL | `IMPORTED_AND_LINKED` |

---

## 5. Automated Regression & Verification Gate Results

### Test Suite Execution
- **Command:** `PYTHONPATH=. pytest tests/`
- **Result:** **418 passed, 0 failed, 0 skipped** across all unit, integration, and performance suites.
- **Phase 13.4 Native Suite:** **10 / 10 passed** (`tests/unit/test_phase13_4_zabbix_native_alerting_and_correlation.py`).
- **Provisioning Idempotency:** **2 / 2 passed** (`tests/integration/test_provisioning_idempotency.py`).

### Verification Gate Summary
- **Phase 10 Verification Gate (`scripts/verify_phase10.sh`):** 9 / 9 checks PASSED.
- **Phase 13 Verification Gate (`scripts/verify_phase13.sh`):** 12 / 12 checks PASSED.

---

## 6. Engineering Rigour & Safety Protocol

1. **Production Mutation Lock:** `HARD_PRODUCTION_DENY` is strictly enforced. No physical equipment or production network interfaces have been altered.
2. **Telemetry Evidence Integrity:** Zero telemetry points are claimed as `VERIFIED_LIVE`. All integrations are accurately classified as `CONFIGURED_SIMULATED`.
3. **Cross-Repository Isolation:** The Sentra repository (`/Users/madeira/Desktop/Projects/sentra`) remains pristine at commit `9970404` on branch `origin/main`.
4. **Credential Safety:** Microsoft 365 secrets remain unconfigured; media types are safely set to `DISABLED` until customer provisioning.
5. **No Unsolicited Live Notifications:** Zero test emails dispatched to `@kenya-airways.com` recipients during local testing.
