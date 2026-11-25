# Nawari — Enterprise Network & Communication Device Onboarding Matrix

**Document Version:** 2.0.0  
**Target Environment:** Corporate Core Network (`10.2.0.0/16`, `10.102.0.0/16`), `mon-grafana01` (`10.2.1.58`)  
**Status:** Pre-configured Locally · Live Polling Staged for Corporate VPN Restoration  

---

## 1. Onboarding & Collection Policy

Every device onboarded to Nawari follows strict telemetry standards:
1. **Canonical Identity:** Devices receive a permanent hardware/serial-based canonical identity (`dev-<hash>`). IP addresses are mapped as transient interface or VIP attributes.
2. **SNMPv3 Security:** Default credential standard is `authPriv` with SHA-256 authentication and AES-128 encryption. SNMPv2c is restricted exclusively to legacy equipment lacking v3 microcode.
3. **Telemetry Frequency & Safety:**
   - Standard interface counters (`ifHCInOctets` / `ifHCOutOctets`): Polled every 60s. Counter rollover and counter reset handling is mandatory; rates are never falsely coerced to zero.
   - Avaya CM call processing tables (`avCmMeasIpVoStatSumDataLstHrTable`): Minimum polling interval of **1 hour** (3600s) to prevent PBX processor degradation.
4. **Data States:** Devices without live telemetry return `NO_DATA` or `SOURCE_UNREACHABLE`. Missing metrics are never decorated with synthetic values.

---

## 2. Infrastructure Device Onboarding Matrix

| Device Name / Host | Canonical Role | Observed Management IP | Vendor & OS | Polling Protocol | MIB / Template | Traps / Syslog | Offline Readiness | Live Production Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Avaya CM Duplex Core (VIP)** | Core Call Processing Server | `10.2.156.30` (VIP: `10.102.10.25`) | Avaya Aura CM 8.1.3 | SNMPv3 authPriv (Delay $\ge$ 1h) | `AVAYA-AURA-CM-MIB` / `template_nawari_avaya_cm.yaml` | Avaya Alarms Trap (UDP 162) | Template & 1h safe delay verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya Session Manager (Primary)** | SIP Routing & Registrar Core | `10.2.156.23` | Avaya Aura SM 8.1.3 | SNMPv3 authPriv / SIP TLS 5061 | `AVAYA-SESSION-MANAGER-MIB` / `template_nawari_avaya_sm.yaml` | Syslog via Alloy / Port 514 | Template verified; TLS listener active | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya Session Manager (Secondary)** | Standby SIP Routing Core | `10.2.156.22` | Avaya Aura SM 8.1.3 | SNMPv3 authPriv | `AVAYA-SESSION-MANAGER-MIB` | Syslog via Alloy | Template verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya SBCE Primary** | Perimeter SBC (DMZ/Signaling) | `10.2.156.131` (EMS: 443, A1/B1 traffic) | Avaya SBCE 8.1.2 | SNMPv3 authPriv (Port 161) | `AVAYA-SBCE-MIB` / `nawari_avaya_sbce.yaml` | SNMP Traps (UDP 162) | Dashboard & MIB verified | **LIVE_VERIFICATION_REQUIRED** (Cred Rotation) |
| **Avaya SBCE Secondary** | Standby SBC Appliance | `10.2.156.132` (EMS: 443) | Avaya SBCE 8.1.2 | SNMPv3 authPriv | `AVAYA-SBCE-MIB` | SNMP Traps (UDP 162) | Template verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya G450 Media Gateway (HQ)** | Voice Gateway & E1/DSP Engine | `10.2.156.60` | Avaya G450 FW 41.x | SNMPv3 authPriv | `AVAYA-G450-GATEWAY-MIB` / `template_nawari_avaya_g450.yaml` | Gateway Traps (UDP 162) | Template verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya G450 Gateway (Outstation)** | Branch Voice Gateway | `10.2.157.30` | Avaya G450 FW 41.x | SNMPv3 authPriv | `AVAYA-G450-GATEWAY-MIB` | Gateway Traps (UDP 162) | Template verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya POM Server** | Outbound Campaign Dialer | `10.2.156.61` | Avaya POM | Syslog / Application Health | Linux OS / HTTP API | Syslog forwarded to Loki | Loki parsers verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya MPP / Voice Portal** | IVR Media Processing Platform | `10.2.156.63` | Avaya Aura Experience Portal | Syslog / Application Health | Linux OS / HTTP API | Syslog forwarded to Loki | Loki parsers verified | **LIVE_VERIFICATION_REQUIRED** |
| **Avaya AES Application Server** | CTI / Telephony Services Engine | `10.2.156.64` | Avaya AES 8.1 | SNMPv3 authPriv / Syslog | `AVAYA-AES-MIB` | Syslog / Traps | Parsers verified | **LIVE_VERIFICATION_REQUIRED** |
| **Safaricom SIP Carrier Gateway** | Primary External Telco Trunk | `10.2.156.100` | Carrier SBC | ICMP / SIP OPTIONS Keepalive | `nawari_sip_trunks_signaling.json` | Trunk Disconnect Alarms | Dashboard queries separated | **LIVE_VERIFICATION_REQUIRED** |
| **Airtel SIP Carrier Gateway** | Secondary External Telco Trunk | `10.2.156.105` | Carrier SBC | ICMP / SIP OPTIONS Keepalive | `nawari_sip_trunks_signaling.json` | Trunk Disconnect Alarms | Dashboard queries separated | **LIVE_VERIFICATION_REQUIRED** |
| **Core Switch Stack (HQ-CORE-01/02)** | L3 Routing & Campus Backbone | `10.2.1.1` | Cisco Catalyst 9500 (IOS-XE) | SNMPv3 authPriv (64-bit HC) | `CISCO-ENTITY-MIB` / `IF-MIB` | Cisco Syslog (%LINK, %OSPF, %BGP) | Counter-to-rate engine verified | **LIVE_VERIFICATION_REQUIRED** |
| **Distribution Switches (HQ-DIST-01..04)** | Campus Distribution & SVI | `10.2.1.2` - `10.2.1.5` | Cisco Catalyst 9300 (IOS-XE) | SNMPv3 authPriv (64-bit HC) | `IF-MIB` / `CISCO-PROCESS-MIB` | Cisco Syslog | Counter-to-rate engine verified | **LIVE_VERIFICATION_REQUIRED** |
| **Access Switches (HQ-ACC-01..48)** | Edge User & AP PoE Access | `10.2.10.x` - `10.2.50.x` | Cisco Catalyst 9200/2960X | SNMPv3 authPriv | `IF-MIB` (Discards & CRC errors) | Port-security / Link flaps | Error rate calculators verified | **LIVE_VERIFICATION_REQUIRED** |
| **Enterprise Wireless Controllers (WLC)** | Mobility & Radio Resource Core | `10.2.1.50` | Cisco Catalyst 9800 WLC | SNMPv3 / Netconf / Syslog | `CISCO-LWAPP-WLAN-MIB` | AP Roam & Auth Traps | Topology reconciler verified | **LIVE_VERIFICATION_REQUIRED** |
| **Campus Access Points (AP-001..250)** | 802.11ax Wi-Fi Access Points | Dynamic DHCP VLAN 20 | Cisco Catalyst 9120/9130 | Controller Managed | Controller association telemetry | Association failures | `roam_client` engine verified | **LIVE_VERIFICATION_REQUIRED** |
| **Enterprise Endpoints (~2,500 Laptops)** | User Digital Experience (DEM) | Dynamic Enterprise Subnets | Windows 10/11 & macOS 14/15 | Zabbix Agent 2 / Nawari NEM | `template_nawari_end_user_network_experience.yaml` | Probes: Gateway RTT, Loss, DNS, Wi-Fi RSSI | Intune & Shell deploy scripts verified | **LIVE_VERIFICATION_REQUIRED** |

---

## 3. High Availability (HA) Relationship Inventory

| HA Cluster ID | Logical Identity | Primary Node | Secondary Node | VIP / Service Address | Failover Mechanism | Health Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ha-sbce-core` | Avaya SBCE Production HA Cluster | `10.2.156.131` | `10.2.156.132` | `10.2.156.130` (Signaling VIP) | Active/Standby Gratuitous ARP | Healthy |
| `ha-cm-duplex` | Avaya Communication Manager Duplex | `10.2.156.30` | `10.102.10.25` | `10.2.156.30` | Active/Active Duplex Heartbeat | Healthy |
| `ha-core-vss` | Cisco Campus Core VSS / StackWise-Virtual | `10.2.1.1` (Switch 1) | `10.2.1.1` (Switch 2) | `10.2.1.1` | Cisco StackWise-Virtual Dual-Active Detection | Healthy |
