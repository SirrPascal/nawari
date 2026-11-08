# Nawari Phase 13.3 — Communication Observability Alert Catalogue

**Document Standard:** Nawari Enterprise Observability & Service Assurance  
**Target Environment:** Kenya Airways Telephony Estate & Ground Operations  
**Subsystems Covered:** Avaya SBCE, Session Manager, Communication Manager, G450, SIP Trunks, Synthetic Voice, CMS, WFO  
**Rule Total:** 45 Fully Specified Operational Rules  
**Execution Standard:** Evidence-Classified, Deduplicated, State-Machine Governed Alerting  

---

## 1. Alerting Architecture & Lifecycle Model

Nawari Communication Alerting operates under an explicit finite-state machine designed to prevent alert storms, phantom alerts, and flapping during transient network anomalies:

```
                  +--------------+
                  |   NOMINAL    | <------------------------------------+
                  +--------------+                                      |
                         | (Condition evaluated True)                   |
                         v                                              |
                  +--------------+                                      |
                  |   PENDING    |                                      |
                  +--------------+                                      |
                         |                                              |
      (Condition persists >= pending_duration)                          |
                         v                                              |
                  +--------------+                                      | (3 consecutive
                  |    FIRING    |                                      |  nominal cycles)
                  +--------------+                                      |
                         |                                              |
      (Nominal telemetry observed; 1st cycle)                           |
                         v                                              |
                  +--------------+                                      |
                  |  RECOVERING  | -------------------------------------+
                  +--------------+
```

### Core Alerting Guarantees
1. **Pending Hold Duration:** Alerts must satisfy their configured `pending_duration_seconds` before transitioning to `FIRING` and dispatching external notifications.
2. **Deduplication Key:** Notifications are keyed by `(alert_id, entity_id)` to prevent redundant alerts across identical incidents.
3. **Flapping & Cooldown Protection:** Repeat notifications are suppressed until the cooldown window (default: 1,800 seconds / 30 minutes) elapses.
4. **Three-Cycle Nominal Recovery:** An alert remains in `RECOVERING` until **3 consecutive valid telemetry cycles** confirm the nominal condition.
5. **Strict Telemetry Truth in Recovery:** Missing or null telemetry explicitly resets the nominal cycle counter (`nominal_recovery_cycles = 0`) and holds the alert in `FIRING` or `RECOVERING`. Absence of data can never resolve an incident.
6. **Maintenance Window Suppression:** Suppressed alerts transition through lifecycle states internally but emit zero outbound notifications.

---

## 2. Complete Communication Alert Catalogue (45 Rules)

### 2.1 Avaya SBCE 8.1 (8 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-SBCE-001` | Avaya SBCE Appliance Unreachable | `DISASTER` | `avaya.sbce.reachability == 0` | 60s | `VERIFIED_INTEGRATION` | Check SBCE physical power, hypervisor VM status, and edge firewall rules. |
| `ALERT-SBCE-002` | Avaya SBCE Management Interface Unreachable | `HIGH` | `avaya.sbce.mgmt_reachability == 0` | 120s | `CONFIGURED_UNVERIFIED` | Verify EMS service status and management port 443 connectivity. |
| `ALERT-SBCE-003` | Avaya SBCE Sustained High SIP Failure Rate | `HIGH` | `avaya.sbce.sip_failure_rate_pct > 5.0` | 300s | `VERIFIED_INTEGRATION` | Inspect SIP signaling logs for carrier 503 Service Unavailable or TLS rejections. |
| `ALERT-SBCE-004` | Avaya SBCE Active Session Capacity Warning | `WARNING` | `avaya.sbce.license_utilization_pct >= 80.0` | 180s | `CONFIGURED_UNVERIFIED` | Prepare dynamic license expansion or balance SIP routes across alternate SBC. |
| `ALERT-SBCE-005` | Avaya SBCE Active Session Capacity Critical | `DISASTER` | `avaya.sbce.license_utilization_pct >= 95.0` | 60s | `CONFIGURED_UNVERIFIED` | Critical SIP session saturation; activate secondary SBC failover routing immediately. |
| `ALERT-SBCE-006` | Avaya SBCE Interface Packet Discards / Errors | `AVERAGE` | `avaya.sbce.if_error_rate_pct > 1.0` | 300s | `VERIFIED_INTEGRATION` | Inspect physical Ethernet cabling, SFP optics, and switch port duplex settings. |
| `ALERT-SBCE-007` | Avaya SBCE License Utilization Limit Approached | `HIGH` | `avaya.sbce.allocated_licenses_pct >= 90.0` | 300s | `CONFIGURED_UNVERIFIED` | Engage Avaya licensing administrator to procure additional concurrent sessions. |
| `ALERT-SBCE-008` | Avaya SBCE Telemetry Stale or Loss of Monitoring | `WARNING` | `avaya.sbce.telemetry_age_seconds > 300` | 120s | `VERIFIED_INTEGRATION` | Verify Zabbix SNMP poller health and SBCE SNMP agent daemon status. |

---

### 2.2 Avaya Aura Session Manager (9 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-ASM-001` | Avaya Session Manager Host Down | `DISASTER` | `avaya.sm.reachability == 0` | 60s | `VERIFIED_INTEGRATION` | Check physical server power, VMware ESXi status, and management network gateway. |
| `ALERT-ASM-002` | Session Manager SIP Entity DOWN | `DISASTER` | `avaya.sm.entity_status == 'DOWN'` | 60s | `CONFIGURED_UNVERIFIED` | Check target SIP Entity (CM, SBCE, or PSTN Gateway) reachability and TLS certs. |
| `ALERT-ASM-003` | Session Manager SIP Entity PARTIALLY UP | `AVERAGE` | `avaya.sm.entity_status == 'PARTIALLY_UP'` | 120s | `CONFIGURED_UNVERIFIED` | Investigate redundant link connectivity or partial listener degradation. |
| `ALERT-ASM-004` | Session Manager SIP Entity DENY NEW SERVICE | `HIGH` | `avaya.sm.entity_status == 'DENY_NEW_SERVICE'` | 60s | `CONFIGURED_UNVERIFIED` | Verify maintenance mode in SMGR; remove administrative lockout if unintentional. |
| `ALERT-ASM-005` | Synthetic SIP OPTIONS Probe Failure | `HIGH` | `avaya.sm.sip_options_status == 0` | 60s | `VERIFIED_INTEGRATION` | Validate Session Manager SIP signaling port 5060/5061 listener and TLS trust. |
| `ALERT-ASM-006` | Session Manager SIP OPTIONS RTT Elevated | `WARNING` | `avaya.sm.sip_options_rtt_ms > 250.0` | 180s | `VERIFIED_INTEGRATION` | Investigate network core latency and ASM processor load spikes. |
| `ALERT-ASM-007` | Session Manager Signalling Failure Rate High | `HIGH` | `avaya.sm.signalling_failure_pct > 5.0` | 180s | `CONFIGURED_UNVERIFIED` | Check routing policies, dial patterns, and downstream SIP entity responses. |
| `ALERT-ASM-008` | Session Manager Critical Alarm Reported | `HIGH` | `avaya.sm.active_alarms_count > 0` | 60s | `VERIFIED_INTEGRATION` | Log into SMGR and review active ASM maintenance alarms. |
| `ALERT-ASM-009` | Session Manager Management Telemetry Stale | `WARNING` | `avaya.sm.telemetry_age_seconds > 300` | 120s | `CONFIGURED_UNVERIFIED` | Verify SM CLI trapper script execution and Zabbix sender connectivity. |

---

### 2.3 Avaya Aura Communication Manager (6 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-CM-001` | Communication Manager Processor Unreachable | `DISASTER` | `avaya.cm.reachability == 0` | 60s | `VERIFIED_INTEGRATION` | Check CM duplicated server pair (Main/Standby) status and server hardware. |
| `ALERT-CM-002` | Communication Manager Active Alarms Present | `AVERAGE` | `avaya.cm.alarms.active > 0` | 300s | `VERIFIED_INTEGRATION` | Connect to CM via SAT and run `display alarms` to identify degraded hardware. |
| `ALERT-CM-003` | Communication Manager Real-Call Packet Loss High | `WARNING` | `avaya.cm.ip_voice.loss_pct > 2.0` | 3600s | `VERIFIED_INTEGRATION` | Check WAN QoS remarking, circuit congestion, and IP network region boundaries. |
| `ALERT-CM-004` | Communication Manager Real-Call Peak Jitter High | `WARNING` | `avaya.cm.ip_voice.peak_jitter_ms > 30.0`| 3600s | `VERIFIED_INTEGRATION` | Review edge switch buffer drops and WAN carrier latency variations. |
| `ALERT-CM-005` | Communication Manager Call Rate Abnormal Drop | `HIGH` | `avaya.cm.call_rate.completed < 10` | 900s | `VERIFIED_INTEGRATION` | Check trunk signaling state; verify inbound airline reservation call paths. |
| `ALERT-CM-006` | Communication Manager Telemetry Stale | `WARNING` | `avaya.cm.telemetry_age_seconds > 7200` | 300s | `VERIFIED_INTEGRATION` | Verify SNMP daemon status on CM Linux base; note 1-hour vendor polling delay. |

---

### 2.4 Avaya G450 Media Gateway (6 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-G450-001` | G450 Media Gateway Chassis Unreachable | `HIGH` | `avaya.g450.reachability == 0` | 60s | `VERIFIED_INTEGRATION` | Verify branch rack power and local LAN switchport connectivity. |
| `ALERT-G450-002` | G450 Ambient Temperature Threshold Exceeded | `HIGH` | `avaya.g450.temperature == 2` | 60s | `CONFIGURED_UNVERIFIED` | Inspect branch comms room air conditioning; clear chassis air filters. |
| `ALERT-G450-003` | G450 Power Supply Unit Failure | `DISASTER` | `avaya.g450.psu_status == 0` | 60s | `CONFIGURED_UNVERIFIED` | Dispatch field engineer to replace failed redundant power supply unit. |
| `ALERT-G450-004` | G450 Fan Tray Failure | `HIGH` | `avaya.g450.fan_status == 0` | 60s | `CONFIGURED_UNVERIFIED` | Check fan tray assembly; replace blower unit before thermal shutdown occurs. |
| `ALERT-G450-005` | G450 E1/ISDN Primary Trunk Port Down | `HIGH` | `avaya.g450.e1_status == 'DOWN'` | 60s | `VERIFIED_INTEGRATION` | Inspect telco E1/PRI circuit, CSU/DSU cable, and carrier sync. |
| `ALERT-G450-006` | G450 Media Gateway Telemetry Missing | `WARNING` | `avaya.g450.telemetry_age_seconds > 600` | 180s | `VERIFIED_INTEGRATION` | Check SNMP community and WAN reachability to branch gateway. |

---

### 2.5 SIP Trunks & External Connectivity (6 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-SIP-001` | SIP Trunk Endpoint Unreachable | `DISASTER` | `sip.trunk.reachability == 0` | 60s | `VERIFIED_INTEGRATION` | Contact Telco SIP provider (e.g. Safaricom/Airtel); check WAN termination. |
| `ALERT-SIP-002` | SIP Trunk Consecutive OPTIONS Probe Failures | `HIGH` | `sip.trunk.options_failure_count >= 3` | 60s | `VERIFIED_INTEGRATION` | Verify SIP proxy signaling, carrier firewall ACLs, and NAT traversal on SBCE. |
| `ALERT-SIP-003` | SIP Trunk High Error Response Rate (5xx/4xx) | `HIGH` | `sip.trunk.error_rate_pct > 10.0` | 180s | `VERIFIED_INTEGRATION` | Carrier returning error responses; review SIP response codes (e.g. 503/486). |
| `ALERT-SIP-004` | SIP Trunk DNS SRV/A Resolution Failure | `HIGH` | `sip.trunk.dns_resolved == 0` | 60s | `VERIFIED_INTEGRATION` | Check DNS server health, domain registrar forwarding, and SRV lookups. |
| `ALERT-SIP-005` | SIP TLS Certificate Expiration Warning | `WARNING` | `sip.trunk.tls_cert_expiry_days <= 30` | 3600s | `CONFIGURED_UNVERIFIED` | Schedule TLS certificate renewal and import onto SBCE/Session Manager. |
| `ALERT-SIP-006` | SIP TLS Certificate Expiration Critical | `HIGH` | `sip.trunk.tls_cert_expiry_days <= 7` | 3600s | `CONFIGURED_UNVERIFIED` | Emergency TLS renewal required; certificate expiration will drop all trunks. |

---

### 2.6 Synthetic Voice Assurance (6 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-SYNTH-001` | Synthetic Voice Scheduled Test Missed | `AVERAGE` | `synthetic.voice.test_missed == 1` | 300s | `SYNTHETIC` | Verify Asterisk synthetic test daemon and cron scheduler health. |
| `ALERT-SYNTH-002` | Synthetic Voice Call Test Failed | `HIGH` | `synthetic.voice.call_success == 0` | 60s | `SYNTHETIC` | Synthetic test call failed to complete; inspect end-to-end PBX routing. |
| `ALERT-SYNTH-003` | Synthetic Voice Call Setup Timeout | `AVERAGE` | `synthetic.voice.setup_time_ms > 4000.0`| 120s | `SYNTHETIC` | High Post-Dial Delay (PDD) detected on synthetic call probe. |
| `ALERT-SYNTH-004` | Synthetic Voice SIP vs AMI Mismatch | `AVERAGE` | `synthetic.voice.sip_ami_mismatch == 1` | 60s | `SYNTHETIC` | Signaling succeeded but Asterisk media channel failed to answer. |
| `ALERT-SYNTH-005` | Synthetic Voice Connected Duration Short | `AVERAGE` | `synthetic.voice.duration_seconds < 5.0`| 60s | `SYNTHETIC` | Test call dropped prematurely; investigate RTP media timeout. |
| `ALERT-SYNTH-006` | Synthetic Voice Consecutive Test Failures | `HIGH` | `synthetic.voice.consecutive_failures >= 3`| 180s | `SYNTHETIC` | Multiple test call probe failures confirm broad telephony degradation. |

---

### 2.7 Contact Centre CMS & WFO/Recording (4 Rules)

| Alert ID | Name | Severity | Metric Key & Trigger Condition | Pending | Evidence Class | Runbook Action |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| `ALERT-CMS-001` | Avaya CMS Queue Service Level Degradation | `AVERAGE` | `avaya.cms.sla_pct < 80.0` | 900s | `CONFIGURED_UNVERIFIED` | Airline contact centre queue SLA below 80%; alert duty shift supervisor. |
| `ALERT-CMS-002` | Avaya CMS Telemetry Data Stale | `WARNING` | `avaya.cms.telemetry_age_seconds > 1800` | 300s | `CONFIGURED_UNVERIFIED` | Check read-only Informix ODBC connector and CMS database connectivity. |
| `ALERT-WFO-001` | Compliance Recording Pipeline Failure | `HIGH` | `wfo.recording.pipeline_status == 0` | 120s | `CONFIGURED_UNVERIFIED` | Call recording service failed; airline regulatory compliance risk. |
| `ALERT-WFO-002` | Recording Spool Disk Storage Warning | `WARNING` | `wfo.recording.disk_free_pct < 15.0` | 600s | `CONFIGURED_UNVERIFIED` | Voice recording storage volume reaching capacity; verify archiving to NAS. |

