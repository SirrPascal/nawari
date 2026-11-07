# Nawari Phase 8.2 Controlled Production Commissioning Specification
## Enterprise Infrastructure, Telephony, Identity & Fleet Rollout Protocol

**Document Version:** 1.0.0  
**Status:** Approved Master Commissioning Protocol  
**Date:** 2026-11-08  
**Software Baseline:** Commit [`e5f23d4`](file:///Users/madeira/Desktop/Projects/nawari) (Phase 8 Complete, Phase 8.1 Audit Passed, 215 Passing Tests)  
**Target Environment:** Kenya Airways Production Host `mon-grafana01` (`10.2.1.58`), Pride Centre Data Centre, Nairobi, Kenya  
**Operational Scope:** Authorised On-Site Deployment & Enterprise System Commissioning  
**Core Architectural Directive:**  
> *"Zabbix monitors. Grafana visualizes. Nawari correlates and assures services. Asterisk provides controlled synthetic voice testing in a separately gated deployment profile."*

---

## 1. Executive Summary & Commissioning Mandate

Phases 1 through 8.1 successfully developed, hardened, and verified the complete Nawari software stack in isolated development and simulated container environments. All 215 automated unit, integration, performance, and recovery tests pass with zero failures and zero skipped tests.

However, in accordance with Kenyan aviation and Kenya Airways corporate information security policies, **software-level verification does not constitute production commissioning on the live enterprise network**.

**Phase 8.2 defines the authoritative, step-by-step commissioning protocol** to transition Nawari from **`Conditionally Ready`** to **`Production Ready`**. It establishes strict operational boundaries, security prerequisites, execution steps, verification criteria, and rollback procedures across seven commissioning workstreams:

```
+----------------------------------------------------------------------------------------------------+
|                         PHASE 8.2: CONTROLLED PRODUCTION COMMISSIONING                              |
|                                                                                                    |
|  [ 8.2.1: Host OS & Docker ] ─────► [ 8.2.2: Secrets & SSO ] ──────► [ 8.2.3: Core Switch SNMP ]   |
|              │                                     │                                    │          |
|              ▼                                     ▼                                    ▼          |
|  [ 8.2.4: Avaya SBCE / PBX ] ─────► [ 8.2.5: Endpoint MDM ] ──────► [ 8.2.6: Off-Host Backup ]    |
|                                                    │                                               |
|                                                    ▼                                               |
|                                  [ 8.2.7: ITSM & NOC Handover ]                                    |
|                                                    │                                               |
|                                                    ▼                                               |
|                                    FINAL PRODUCTION ACCEPTANCE                                     |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Strict Operational Boundaries & Safety Principles

1. **Explicit Separation of Development vs Physical Commissioning:**
   Local testing, mock containers (`nawari-mock-snmp`, `nawari-asterisk`), and synthetic scripts remain active for continuous regression testing. Live physical infrastructure (`10.2.156.45`, `10.2.156.60`, corporate PBX) must **never** be probed until authorised on-site access is granted.
2. **Zero Modification to Network Device Configurations:**
   All network and voice monitoring is strictly **read-only** (SNMPv3 GET/GETBULK). Zero SNMP SET commands or automated CLI configuration pushes are permitted.
3. **Synthetic Voice Testing Gating:**
   Synthetic call testing against corporate PBX trunks requires explicit, active operator confirmation, adherence to the Kenya Airways dialed number allowlist, and total cryptographic blocking of emergency numbers (`999`, `112`, `911`).
4. **Repository Isolation:**
   All work is performed strictly within `nawari/`. The `sentra/` repository remains 100% clean and untouched.

---

## 3. Detailed Workstream Execution Plans

### Workstream 8.2.1: Production Host OS, Docker & Network Infrastructure
* **Target Host:** `mon-grafana01` (10.2.1.58), Pride Centre Data Centre Rack-04-U12.
* **Hardware Baseline:** VMware ESXi Virtual Machine, 2 vCPUs, 7.8 GiB RAM, 4 GiB Swap, ~17 GB free root disk (`/dev/sda1`).
* **Execution Checklist:**
  1. [ ] **OS Validation:** Verify Ubuntu Server 24.04.4 LTS (kernel `6.8.0-xx-generic`).
  2. [ ] **Time Synchronization:** Configure `systemd-timesyncd` pointing to corporate NTP servers:
     ```ini
     # /etc/systemd/timesyncd.conf
     [Time]
     NTP=time.kenya-airways.com 10.2.1.10
     FallbackNTP=0.africa.pool.ntp.org
     ```
     Verify max clock offset $\le 10\text{ ms}$ (`timedatectl timesync-status`).
  3. [ ] **Kernel Tuning:** Apply [`docker/security/sysctl-hardening.conf`](file:///Users/madeira/Desktop/Projects/nawari/docker/security/sysctl-hardening.conf) to `/etc/sysctl.d/99-nawari.conf`. Verify:
     - `vm.swappiness = 10`
     - `vm.max_map_count = 262144`
     - `fs.file-max = 2097152`
     - `net.core.somaxconn = 4096`
  4. [ ] **Firewall Activation:** Execute [`docker/security/ufw-rules.sh`](file:///Users/madeira/Desktop/Projects/nawari/docker/security/ufw-rules.sh). Verify policy:
     - Inbound default: `DENY`
     - Outbound default: `ALLOW`
     - SSH (22): Restricted to jump subnet (`10.100.0.0/16`)
     - Grafana (443): Permitted from NOC / Corporate subnet (`10.0.0.0/8`)
     - Ingestion Gateway (8443): Permitted from endpoint subnets (`10.0.0.0/8`)
     - SNMP Traps (UDP 162): Restricted strictly to core switches (`10.2.156.0/24`)
     - Zabbix Web (8080): Restricted to monitoring admins (`10.2.0.0/16`)
  5. [ ] **Resource Ceiling Verification:** Confirm total memory reservations $\le 950\text{ MiB}$ and limits $\le 1,900\text{ MiB}$, preserving $\ge 5.8\text{ GiB}$ for host kernel and page cache.

---

### Workstream 8.2.2: Enterprise Security, Secrets Management & SSO Federation
* **Execution Checklist:**
  1. [ ] **Docker Secrets Transition:** Eliminate `.env` passwords. Mount production secrets at `/run/secrets/` with permissions `0400`:
     - `nawari_postgres_prod_pass`
     - `nawari_zabbix_api_token`
     - `nawari_gateway_hmac_secret`
     - `nawari_snmpv3_auth_key`
     - `nawari_snmpv3_priv_key`
  2. [ ] **Enterprise PKI Certificates:** Deploy corporate wildcard TLS certificates:
     - Certificate: `/etc/ssl/certs/nawari.kenya-airways.com.crt`
     - Private Key: `/etc/ssl/private/nawari.kenya-airways.com.key` (mode `0400`)
     - Chain: Kenya Airways Enterprise Root & Intermediate CA bundle.
  3. [ ] **Single Sign-On (SSO) Federation:** Configure Grafana and Zabbix against Microsoft Entra ID (Azure AD):
     ```ini
     # /etc/grafana/grafana.ini [auth.generic_oauth]
     enabled = true
     name = Kenya Airways Single Sign-On
     allow_sign_up = false
     client_id = $ENTRA_CLIENT_ID
     client_secret = $ENTRA_CLIENT_SECRET
     scopes = openid email profile
     auth_url = https://login.microsoftonline.com/kenya-airways.com/oauth2/v2.0/authorize
     token_url = https://login.microsoftonline.com/kenya-airways.com/oauth2/v2.0/token
     api_url = https://graph.microsoft.com/v1.0/me
     role_attribute_path = contains(groups[*], 'Nawari-Admins') && 'Admin' || contains(groups[*], 'Nawari-Engineers') && 'Editor' || 'Viewer'
     ```
  4. [ ] **Break-Glass Emergency Protocol:** Local break-glass admin accounts provisioned with 20-character random passwords stored in corporate CyberArk / 1Password vault, protected by TOTP MFA.

---

### Workstream 8.2.3: Physical Network Switch SNMPv3 & Trap Commissioning
* **Target Switch:** Cisco Catalyst 9500-48Y4C Core Switch (`10.2.156.45`).
* **Execution Checklist:**
  1. [ ] **SNMPv3 Connectivity Verification:** Execute non-intrusive query using production credentials:
     ```bash
     snmpget -v3 -l authPriv -u nawari_snmp_user \
         -a SHA-256 -A "$SNMP_AUTH_KEY" \
         -x AES-128 -X "$SNMP_PRIV_KEY" \
         10.2.156.45 sysDescr.0
     ```
     Verify device identification string: `Cisco IOS-XE Software, Catalyst L3 Switch Software`.
  2. [ ] **LLD Interface Enumeration:** Trigger Zabbix discovery rule (`net.if.discovery`). Confirm all 52 physical interfaces (48x 25GE SFP28 + 4x 100GE QSFP28) and active SVIs are provisioned with:
     - 64-bit high-speed counters (`ifHCInOctets`, `ifHCOutOctets`)
     - Operational status (`ifOperStatus`)
     - Interface aliases (`ifAlias`)
  3. [ ] **Physical Trap Forwarding Verification:** Verify Cisco core switch configuration:
     ```cisco
     snmp-server host 10.2.1.58 version 3 authPriv nawari_snmp_user
     snmp-server enable traps link-status
     snmp-server enable traps bgp
     ```
     Simulate test trap; verify receipt in `/var/lib/zabbix/snmptraps/snmptraps.log` and dashboard problem feed within 2 seconds.

---

### Workstream 8.2.4: Avaya SBCE 8.1 & PBX Telephony Commissioning
* **Target Appliance:** Avaya Session Border Controller Enterprise (SBCE 8.1) @ `10.2.156.60`.
* **Execution Checklist:**
  1. [ ] **Dual SNMPv3 Profile Verification:** Test primary Modern profile (`SHA-256 / AES-128`) and legacy fallback profile (`SHA-1 / DES`) against management interface.
  2. [ ] **VoIP Signaling Telemetry:** Verify Avaya MIB items active:
     - Active SIP Sessions (`avSbceActiveSessions`)
     - Session Registration State (`avSbceRegistrationStatus`)
     - Media Channel Utilization (`avSbceMediaUtilization`)
     - License Concurrency (`avSbceLicenseCurrentUsage`)
  3. [ ] **Controlled Synthetic Call Rehearsal:**
     - Profile: Launch `asterisk` container under `synthetic-voice` profile.
     - Destination: Kenya Airways internal diagnostic echo test extension (`1001`).
     - Safety Gate Verification: Verify destination is present in `voice_destination_allowlist.json`; verify call duration limited to 15 seconds; verify cooldown delay enforced.
     - RTCP / MOS Validation: Inspect generated RTCP packet report; confirm calculated MOS ($R$-factor conversion), jitter, and packet loss persist to Zabbix trapper.

---

### Workstream 8.2.5: Endpoint Agent Fleet MDM Packaging & Pilot Deployment
* **Target Fleet:** Kenya Airways Workstations (Windows 11 Enterprise & macOS Sequoia 15.x).
* **Execution Checklist:**
  1. [ ] **Code Signing:**
     - Windows: Sign `nawari-agent-setup.msi` with Kenya Airways Enterprise Authenticode Certificate using `signtool.exe`.
     - macOS: Sign `nawari-agent.pkg` with Apple Developer ID Installer certificate and notarize via Apple notary service.
  2. [ ] **MDM Profile Creation:**
     - Microsoft Intune: Deploy MSI with command line:
       ```cmd
       msiexec /i nawari-agent-setup.msi /qn GATEWAY_URL="https://10.2.1.58:8443" ENROLLMENT_TOKEN="$TOKEN"
       ```
     - Jamf Pro: Deploy PKG with post-install configuration placing `/etc/nawari/agent.json` (mode `0600`).
  3. [ ] **Phased Rollout Schedule:**
     - **Canary (Day 1):** 5 laptops in Network Engineering lab.
     - **Pilot (Day 3):** 25 workstations across Airport Terminal 1A operations and check-in desks.
     - **General Availability (Day 7):** 250 enterprise workstations across Pride Centre HQ and outstations.
  4. [ ] **Fleet Health Verification:** Confirm all enrolled endpoints appear on `nawari-endpoint-fleet` Grafana dashboard with correct server-stamped `PHYSICAL_PRODUCTION` provenance and active heartbeats.

---

### Workstream 8.2.6: Backup Hardening & Off-Host Replication
* **Execution Checklist:**
  1. [ ] **Off-Host Storage Mount:** Mount secondary backup volume from dedicated Kenya Airways backup server:
     ```bash
     # /etc/fstab
     backup-nas.kenya-airways.com:/vol/nawari_backups /var/backups/nawari nfs4 rw,sync,hard,intr 0 0
     ```
  2. [ ] **GPG Encryption at Rest:** Configure automated GPG public-key encryption in `scripts/backup/backup_nawari.sh`:
     ```bash
     export NAWARI_BACKUP_GPG_RECIPIENT="secops-backup@kenya-airways.com"
     ```
  3. [ ] **Automated Cron Schedule:**
     ```cron
     # /etc/cron.d/nawari-backup
     0 */6 * * * nawari /opt/nawari/scripts/backup/backup_nawari.sh >> /var/log/nawari/backup.log 2>&1
     ```
  4. [ ] **Scheduled Restoration Drill:** Schedule monthly cold restoration exercise into isolated staging VM (`mon-grafana02`) using [`scripts/backup/restore_nawari.sh`](file:///Users/madeira/Desktop/Projects/nawari/scripts/backup/restore_nawari.sh).

---

### Workstream 8.2.7: Operations, ITSM & NOC Handover
* **Execution Checklist:**
  1. [ ] **ServiceNow / Jira API Integration:** Configure live enterprise credentials in `services/integrations/itsm_adapter.py`. Verify automated ticket creation on synthetic fault injection and automatic resolution on telemetry recovery.
  2. [ ] **Corporate SMTP Dispatch:** Configure production relay `mail.kenya-airways.com:587` with STARTTLS and sender address `nawari-alerts@kenya-airways.com`. Verify secret masking of credentials.
  3. [ ] **SMS Paging Gateway:** Configure Kenya Airways telecom aggregator HTTP SMS gateway for CRITICAL P1 alerts.
  4. [ ] **NOC Training & Documentation:** Deliver [`disaster-recovery-runbook.md`](file:///Users/madeira/Desktop/Projects/nawari/docs/operations/disaster-recovery-runbook.md) and dashboard walkthrough to Tier-1/Tier-2 Network Operations Center engineers.

---

## 4. Commissioning Gating & Sign-off Matrix

Every workstream requires explicit sign-off from designated stakeholders before Nawari transitions to full **`Production Ready`**:

| Workstream | Stakeholder Role | Verification Evidence Required | Sign-off Status |
| :--- | :--- | :--- | :---: |
| **8.2.1 Host Infrastructure** | Linux Systems Admin | UFW active, sysctl applied, memory ceiling verified. | [ ] Pending On-Site |
| **8.2.2 Security & SSO** | SecOps Lead | TLS valid, Entra ID SSO working, break-glass secured. | [ ] Pending On-Site |
| **8.2.3 Core Network Switch** | Lead Network Engineer | SNMPv3 polling active, interfaces discovered, traps firing. | [ ] Pending On-Site |
| **8.2.4 Telephony & PBX** | Voice Telephony Engineer| SBCE SNMP telemetry active, test call MOS recorded. | [ ] Pending On-Site |
| **8.2.5 Endpoint Fleet** | End-User Computing Lead | Signed MSI/PKG deployed via MDM, 25 canary agents healthy. | [ ] Pending On-Site |
| **8.2.6 Backup & DR** | IT Infrastructure Manager| Off-host NFS mounted, GPG encrypted, restore drill logged. | [ ] Pending On-Site |
| **8.2.7 ITSM & NOC Handover** | Service Delivery Manager| ServiceNow tickets opening/closing, NOC team trained. | [ ] Pending On-Site |

---

## 5. Rollback & Emergency Contingency Procedures

In the event of an unforeseen operational conflict during commissioning:
1. **Network Switch Rollback:** Remove SNMP trap destination from Cisco core switch: `no snmp-server host 10.2.1.58`. Switch operations remain 100% unaffected.
2. **Endpoint Agent Rollback:** Distribute Intune/Jamf uninstall policy: `msiexec /x nawari-agent-setup.msi /qn`. Endpoint agents shut down cleanly without leaving background hooks.
3. **Platform Service Isolation:** Stop all ingress containers: `docker compose stop zabbix-snmptraps nawari-gateway`. Restores host to dormant state.
