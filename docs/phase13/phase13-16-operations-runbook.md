# Phase 13.16 — Operations Runbook & Incident Triage Procedures

## Runbook Purpose

This runbook guides Kenya Airways network engineers, voice administrators, and IT Service Desk duty staff in triaging, investigating, and escalating operational incidents detected by the Nawari platform.

---

## 1. Incident Severity & Escalation Directory

| Incident Classification | Triggered Action ID | Initial Target Group | Escalation SLA | Primary Contacts |
| :--- | :--- | :--- | :--- | :--- |
| **TOTAL OUTAGE (P1)** | **Action 10** | IT Service Desk & All Administrators | **Immediate (< 5m)** | IT Service Desk (`it.servicedesk@kenya-airways.com`) & Major Incident Manager |
| **TELEPHONY FAULT (P2)** | **Action 12** | Telephony Administrators | **< 15 minutes** | John Gacomo (`John.Gacomo@kenya-airways.com`), Robinson Wainaina (`Robinson.Wainaina@kenya-airways.com`) |
| **NETWORK LINK DOWN (P2)** | **Action 14** | Network Administrators | **< 15 minutes** | Pascal Gathungu (`Pascal.Gathungu@kenya-airways.com`) |
| **COMMUNICATIONS WARNING (P3)** | **Action 12** | Communications Administrators | **< 1 hour** | Mercy Vaati (`Mercy.Vaati@kenya-airways.com`) |
| **INFRASTRUCTURE WARNING (P4)** | **Action 13** | Systems Administrators | **< 4 hours** | Duty Systems Engineer |

---

## 2. Standard Operating Procedures (SOPs)

### SOP-01: Carrier SIP Trunk Ingress Total Outage (Action 10)
1. **Verification**:
   - Check Grafana Dashboard: `Communication Observability` $\rightarrow$ `Carrier SIP Trunks & Perimeter Session Routing`.
   - Verify active problem in Zabbix: `SBCE: Both Active/Standby Nodes Offline` or `Carrier Ingress: Dual Safaricom & Airtel Ingress Timeout`.
2. **Immediate Remediation**:
   - Inspect SBCE cluster state via SSH (`10.2.156.131` / `10.2.156.132`):
     ```bash
     ssh admin@10.2.156.131 "sudo systemctl status sbce-signaling"
     ```
   - If primary SBCE hardware failed, verify secondary SBCE status:
     ```bash
     ssh admin@10.2.156.132 "sudo ha_status"
     ```
   - If both nodes unreachable, check upstream switch ports on `jkia-core-sw01` (Interfaces Gi1/0/10 - Gi1/0/12).
   - If carrier IP link is down, initiate carrier escalation ticket with Safaricom / Airtel NOC.
3. **Recovery Verification**:
   - Zabbix Action 11 automatically dispatches recovery notification once SIP OPTIONS and call completion succeed for 180 consecutive seconds.

### SOP-02: Voice Quality Degradation (Action 12)
1. **Verification**:
   - Check Grafana Dashboard: `Communication Observability` $\rightarrow$ `Voice Service Assurance & Media Quality`.
   - Review Extended E-model R-factor ($R < 70.0$) and listening MOS ($MOS < 3.8$).
2. **Path Diagnostics**:
   - Launch Paris Traceroute to local SBC / outstation from `mon-grafana01`:
     ```bash
     PYTHONPATH=. /usr/bin/python3 -c "
     import asyncio
     from services.endpoint.path.traceroute import ParisTraceroute
     tracer = ParisTraceroute()
     res = asyncio.run(tracer.trace('outstation-mba', '10.2.156.131'))
     print('Path Hops:', res.total_hops, 'Latency Onset Hop:', res.latency_onset_hop)
     "
     ```
   - Inspect `loss_onset_hop` and `latency_onset_hop` to determine if degradation originated on local LAN or carrier WAN core.

### SOP-03: Storage Disk Warning on WFO Server (Action 13)
1. **Verification**:
   - Check `recording_wfo_operational_health.json` dashboard.
   - Alert: `WFO: Compliance Voice Recording Spool Disk Storage Warning (< 15%)` on `avaya-cms-01`.
2. **Remediation Playbook**:
   - Execute controlled spool flush script:
     ```bash
     PYTHONPATH=. /usr/bin/python3 -m services.actions.playbooks.spool_flusher --target avaya-cms-01 --dry-run
     ```
   - After dry-run verification, execute with approval flag to archive completed audio records older than 48 hours to long-term storage.
