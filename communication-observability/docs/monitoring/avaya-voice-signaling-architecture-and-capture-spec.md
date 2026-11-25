# Avaya Voice Signaling Architecture & Production Capture Specification

## 1. Enterprise Voice Topology & Entity Register

The enterprise Avaya telephony deployment separates management and call signaling planes. Telemetry collection must trace each entity, interface, logical role, and monitoring mechanism.

| Entity / Node | Hostname / Visible Name | Role / Function | Interface Plane | IP Address | Signaling Transport / Ports | Monitored Status in Nawari |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Avaya SBCE Primary** | `HQ-SBCE01` | Perimeter Session Border Controller (Active) | External (WAN/SIP Trunk)<br>Internal (Core DMZ)<br>Management | `10.2.156.131`<br>`VIP: 10.2.156.130` | SIP/5060 UDP/TCP<br>SIPS/5061 TLS | **SNMP + ICMP Active**<br>*(SIP: Not Commissioned)* |
| **Avaya SBCE Secondary** | `HQ-SBCE02` | Perimeter Session Border Controller (Standby) | External (WAN/SIP Trunk)<br>Internal (Core DMZ)<br>Management | `10.2.156.132`<br>`VIP: 10.2.156.130` | SIP/5060 UDP/TCP<br>SIPS/5061 TLS | **SNMP + ICMP Active**<br>*(SIP: Not Commissioned)* |
| **Avaya Session Manager 01** | `HQ-ASM01` | SIP Core Proxy & Routing Engine | Signaling Core<br>Management | `10.2.156.22` | SIP/5060 TCP/UDP<br>SIPS/5061 TLS | **SNMP + ICMP Active** |
| **Avaya Session Manager 02** | `HQ-ASM02` | SIP Core Proxy & Routing Engine | Signaling Core<br>Management | `10.2.156.23` | SIP/5060 TCP/UDP<br>SIPS/5061 TLS | **SNMP + ICMP Active** |
| **Avaya Session Manager DR** | `DR-ASM01` | Disaster Recovery SIP Proxy | Signaling Core (DR)<br>Management | `10.2.156.28` | SIP/5060 TCP/UDP<br>SIPS/5061 TLS | **SNMP + ICMP Active** |
| **Communication Manager PE** | `HQ-CM01-PE` | Processor Ethernet (Call Processing Engine) | Signaling Plane | `10.102.10.25` | H.323 / SIP 5060 / 5061 | **ICMP Active** |
| **Communication Manager Mgt** | `HQ-CM01-MGT` | Server Duplex Pair Management | Management Plane | `10.2.156.30` | Web, SSH, SNMP | **SNMP + ICMP Active** |
| **Avaya G450 Gateway** | `HQ-G450-GW01` | Media Gateway & TDM/PSTN DSP Appliance | VoIP / DSP Plane<br>Management | `10.2.156.60` | H.248 / RTP / RTCP | **SNMP + ICMP Active** |
| **Asterisk AVTEST Probe** | `nawari-asterisk` | Synthetic Loopback & Diagnostic Caller | Isolated Lab Docker | `10.2.5.148` (Host)<br>`127.0.0.1` (Internal) | SIP/5060 UDP/TCP | **VERIFIED SYNTHETIC** |

---

## 2. Technical Evaluation of Production Capture Options

```
                              ┌────────────────────────────────────────┐
                              │            CARRIER SIP TRUNKS          │
                              └───────────────────┬────────────────────┘
                                                  │ WAN SIP (5060/5061)
                                                  ▼
                                      ┌───────────────────────┐
                                      │   Avaya SBCE Cluster  │
                                      │  (10.2.156.130 VIP)   │
                                      └───┬───────────────┬───┘
                                          │               │
       [OPTION 1: Native Export / Intermediary]           │ [OPTION 2: SPAN / Port Mirror]
       (RTCP-XR / IPFIX / Diagnostic Tap)                │ (Internal Core DMZ vSwitch)
                                          │               ▼
                                          │     ┌───────────────────┐
                                          │     │ vNIC: ens224      │
                                          │     │ (Unnumbered/SPAN) │
                                          │     └─────────┬─────────┘
                                          │               │
                                          ▼               ▼
                              ┌───────────────────────────────────────┐
                              │     nawari-heplify Capture Agent      │
                              │     (Host or Intermediary Parser)     │
                              └───────────────────┬───────────────────┘
                                                  │ HEPv3 (UDP 9060)
                                                  ▼
                              ┌───────────────────────────────────────┐
                              │        nawari-heplify Server          │
                              │       (PostgreSQL: homer_data)        │
                              └───────────────────────────────────────┘
```

### Option 1: Native Avaya SBCE Signaling Export / Intermediary
- **Mechanism:** Avaya SBCE provides internal call tracing and RTCP monitoring options (such as traceSBC, syslog event forwarding, or RTCP-XR exporter). If enabled, SBCE can stream diagnostic signaling to a designated receiver.
- **Feasibility:** High fidelity, zero network SPAN overhead. Does not require promiscuous virtual switches.
- **Limitations:** Requires Avaya administrative privileges and configuration changes within the SBCE EMS (Element Management System).

### Option 2: VMware vSwitch Dedicated Port Mirror (SPAN)
- **Mechanism:** The VMware administrator configures a Port Mirror session on the vSphere Distributed Switch (VDS) sourcing the vNICs of `HQ-SBCE01`, `HQ-SBCE02`, and `HQ-ASM01`. The destination is a dedicated port group (`PG-VOICE-SPAN`). A second vNIC (`ens224`) on `mon-grafana01` is attached to this port group in unnumbered promiscuous mode.
- **Feasibility:** Independent of Avaya software configuration. Captures exact over-the-wire signaling.
- **Limitations:** Requires vSphere Enterprise Plus licensing for VDS Port Mirroring, physical host switch trunk capacity, and an explicit network change window.

### Option 3: Existing Syslog / Diagnostic Export
- **Mechanism:** Ingesting Avaya Session Manager and SBCE security/event logs into Grafana-Loki via Vector/Alloy.
- **Feasibility:** Currently active for Cisco switches via SolarWinds.
- **Limitations:** Syslog only provides summarized call disposition (Call Start/End, Q.850 release cause). It **cannot** reconstruct millisecond-accurate SIP signaling ladders (INVITE $\rightarrow$ 100 Trying $\rightarrow$ 180 Ringing $\rightarrow$ 200 OK $\rightarrow$ ACK).

---

## 3. SIP/TLS Encryption Constraints & Security Boundary

Enterprise Avaya topologies commonly mandate **SIPS over TLS (port 5061)** between external perimeter carriers, the SBCE, and internal Session Managers.

1. **The TLS Barrier:** If SIP signaling is encrypted using TLS, passive network sniffing (Option 2) captures only the TCP stream and TLS Record Layer frames (`Application Data`). The SIP INVITE headers, Call-ID, URIs, and SDP codecs remain cryptographically opaque.
2. **Strict Cryptographic Constraint:**
   - Under no circumstances will Nawari attempt to decrypt production TLS traffic via insecure interception, private key extraction, or downgrade attacks.
   - Doing so violates corporate security policy and data protection regulations.
3. **Approved Engineering Solution for TLS Voice Networks:**
   - **Internal Unencrypted B2BUA Leg:** Avaya SBCE operates as a Back-to-Back User Agent (B2BUA). Often, the external carrier leg is TLS (port 5061), while the internal core signaling to Session Manager within the secured Core DMZ operates on port 5060 (TCP/UDP). Capturing the internal leg provides complete, unencrypted signaling ladders.
   - **Native Application-Layer Export:** Using SBCE EMS / ASM diagnostic export (Option 1) which emits HEP or RTCP-XR payloads after internal decryption.

---

## 4. Production Change-Control Authorization Gate

```
┌────────────────────────────────────────────────────────────────────────┐
│                   PRODUCTION VOICE CAPTURE GATE                        │
│                 GATED — REQUIRES FORMAL SIGN-OFF                       │
├────────────────────────────┬─────────────────────────────┬─────────────┤
│ Domain                     │ Approving Authority         │ Status      │
├────────────────────────────┼─────────────────────────────┼─────────────┤
│ Voice Infrastructure       │ Telecoms / Voice Operations │ PENDING     │
│ Network Infrastructure     │ Core Network Engineering    │ PENDING     │
│ Information Security       │ SOC / CISO Office           │ PENDING     │
└────────────────────────────┴─────────────────────────────┴─────────────┘
```

### Action Items to Clear the Gate:
1. **Network Engineering:** Provision `PG-VOICE-SPAN` on vSphere and map second vNIC `ens224` on `mon-grafana01`.
2. **Voice Operations:** Confirm whether SBCE internal signaling leg (Core DMZ) uses unencrypted SIP/5060 or TLS/5061.
3. **Security:** Authorize packet sniffing restricted exclusively to UDP/TCP 5060/5061 on `ens224`.
