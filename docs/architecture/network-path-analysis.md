# Nawari Network Path Analysis Specification

**Document Version:** 1.0.0  
**Status:** Architectural Baseline for Review  
**Date:** 2026-11-07  
**Design Reference:** ThousandEyes-Style Directional Network Path Trace

---

## 1. Executive Summary & Design Goals

Traditional monitoring tools treat the network between the user and the application as an opaque black box. When voice quality degrades, engineers often dispute whether the issue is caused by the Wi-Fi access point, the corporate WAN provider, transit peering, or the destination Session Border Controller (SBCE).

**Nawari Network Path Analysis** decomposes the network path into discrete, measurable hops between the user's endpoint and the enterprise voice gateway. It visualizes:
1. Every intermediate layer-3 router traversed.
2. Latency incurred across each individual physical link ($\Delta RTT$).
3. Packet loss localization (pinpointing the exact hop where drops begin).
4. Route changes and asymmetric path shifts over time.
5. Distinction between intermediate router CPU rate-limiting and true end-to-end loss.

---

## 2. Probing Protocols & Paris Traceroute Methodology

### 2.1 The Multi-Protocol Probing Problem
In modern enterprise networks, different protocols experience radically different routing policies and firewall behaviors:
- **ICMP Echo:** Universally supported internally, but frequently dropped or rate-limited by transit ISPs and enterprise perimeter firewalls.
- **UDP Probing:** Standard for classic Unix traceroute, but heavily filtered at firewalls unless directed at specific SIP/RTP media port ranges.
- **TCP SYN Probing:** Sends TCP SYN packets toward destination services (e.g., Avaya SBCE SIP TLS on port 5061, or Web services on port 443). Firewalls permit TCP SYN packets because they appear as legitimate client connection attempts. Intermediate routers generate ICMP Time Exceeded (Type 11), while the destination returns a TCP SYN-ACK or RST.

**Nawari Probe Protocol Matrix:**
```
+-------------------------------------------------------------------------------------------------+
| Target Type          | Primary Probe Protocol | Secondary / Fallback    | Target Port           |
+----------------------+------------------------+-------------------------+-----------------------+
| Avaya SBCE SIP/TLS   | TCP SYN                | ICMP Echo               | 5061 (TCP) / ICMP     |
| Avaya SBCE SIP/UDP   | UDP (Paris)            | ICMP Echo               | 5060 (UDP) / ICMP     |
| Enterprise Gateway   | ICMP Echo              | TCP SYN                 | ICMP / 443 (TCP)      |
| Internal DNS Server  | UDP (DNS query)        | ICMP Echo               | 53 (UDP) / ICMP       |
| Cloud SaaS (Webex)   | TCP SYN                | ICMP Echo               | 443 (TCP)             |
+-------------------------------------------------------------------------------------------------+
```

---

### 2.2 Paris Traceroute: Eliminating ECMP Phantom Route Flapping

#### The Flaw of Classic Traceroute:
Modern enterprise WANs and carrier backbones rely heavily on **Equal-Cost Multi-Path (ECMP)** load balancing. ECMP routers calculate a hash of the IP 5-tuple:
$$\text{Hash}(\text{SrcIP}, \text{DstIP}, \text{Protocol}, \text{SrcPort}, \text{DstPort})$$
Classic traceroute increments the UDP destination port with every single probe (e.g. 33434, 33435, 33436). This alters the 5-tuple hash for every probe, causing packets destined for the same hop distance to take different physical paths. This creates artificial route flapping, incorrect hop sequences, and phantom packet loss.

#### The Paris Traceroute Solution:
Nawari implements the **Paris Traceroute algorithm** (RFC-aligned):
- The probe keeps the 5-tuple strictly constant for all probes across the entire path trace.
- For UDP probes, the destination port is held constant (e.g., 5060), and the probe identifier / sequence number is embedded inside the payload while adjusting the UDP checksum field to maintain a constant overall checksum.
- For ICMP probes, the ICMP Identifier and Sequence number are manipulated such that the IP/ICMP payload hash remains identical across all TTL iterations.
- **Result:** Every probe packet in a single path trace traverses the exact same physical link sequence, providing deterministic, repeatable hop measurements.

---

## 3. Hop Classification & Anomaly Detection Algorithms

### 3.1 Differentiating Control Plane Policing (CoPP) from True Loss

The most frequent error in automated path analysis is declaring a network outage because an intermediate router displays 100% packet loss (`* * *`).

Most enterprise core routers (Cisco, Juniper, Arista) implement **Control Plane Policing (CoPP)**. When an IP TTL expires, the packet is punted from the hardware forwarding plane (ASIC) to the router's main CPU. To prevent Denial of Service (DoS) attacks, the CPU aggressively rate-limits or entirely disables generating ICMP Time Exceeded (Type 11, Code 0) packets.

```
       Hop 1          Hop 2              Hop 3              Hop 4          Destination
     [ Gateway ]--->[ WAN Edge ]------>[ Transit Core ]--->[ Aggregation ]--->[ Avaya SBCE ]
RTT:   1.2 ms         8.4 ms             * * * (Timeout)     22.1 ms          24.5 ms
Loss:  0.0%           0.0%               100.0% (CoPP)       0.0%             0.0%
                                                 ^
                                                 |
                       [ NOT AN OUTAGE: Downstream hops are healthy ]
```

#### The Nawari Loss Evaluation Algorithm:
Let $L(k)$ be the packet loss percentage observed at Hop $k \in \{1, \dots, N\}$, and let $L(\text{Dest})$ be the packet loss observed at the final destination.

1. **Non-Responsive Hop / CoPP Classification:**
   If $L(k) = 100\%$ AND $L(k+1) < \text{LossThreshold}$ AND $L(\text{Dest}) < \text{LossThreshold}$:
   - Hop $k$ status is classified as `TIMEOUT_COPP`.
   - Hop $k$ packet loss is marked as non-impairing; no incident alarm is raised.
   - Hop $k$ RTT is recorded as `None` (omitted from average latency calculations).

2. **Genuine Loss Onset Hop:**
   Hop $k$ is classified as the **Loss Onset Hop** if and only if:
   $$L(k) \ge \text{LossThreshold} \quad \land \quad L(m) \ge \text{LossThreshold} \quad \forall m \in [k, N]$$
   and $L(k-1) < \text{LossThreshold}$.
   - An alert is raised pointing to the physical link between Hop $k-1$ and Hop $k$.

---

### 3.2 Latency Jump Localization ($\Delta RTT$)

End-to-end latency increases are localized to the specific physical span where the delay was introduced:
$$\Delta RTT_k = \overline{RTT}_k - \overline{RTT}_{k-1}$$

- If $\Delta RTT_k > 40\text{ ms}$:
  - Hop $k$ is flagged as the **Latency Onset Hop**.
  - Possible causes: WAN link bufferbloat, long-distance geographical transit (e.g. undersea cable or satellite link), or queue saturation on the egress interface of router $k-1$.

---

### 3.3 Asymmetric Routing & Directionality Limitations

A fundamental constraint of traceroute is that it measures **Round-Trip Time (RTT)**, but routing across IP networks is asymmetric:
- Forward Path: Endpoint $\to R_1 \to R_2 \to R_3 \to \text{Destination}$.
- Reverse Path: Destination $\to R_A \to R_B \to \text{Endpoint}$.

When router $R_2$ sends an ICMP Time Exceeded packet back to the endpoint, that ICMP packet traverses the reverse path from $R_2$. Therefore:
$$\text{Observed } RTT(R_2) = T_{\text{forward}}(\text{Endpoint} \to R_2) + T_{\text{reverse}}(R_2 \to \text{Endpoint})$$

**Nawari Operational Rule:** A latency jump observed at Hop $k$ proves that round-trip delay has increased, but does not guarantee the delay is exclusively on the forward link. The Correlator marks the latency increase as `PROBABLE Forward Link Queue or Reverse Link Transit`.

---

### 3.4 Route Change & Churn Detection

Nawari computes a deterministic cryptographic hash of the responsive hop IP sequence for every path measurement:
$$\text{PathHash} = \text{SHA256}(IP_1 + \text{":"} + IP_2 + \dots + IP_N)$$
- If $\text{PathHash}_t \ne \text{PathHash}_{t-1}$:
  - Metric `endpoint.path.route_changed` is set to `1`.
  - The Ingestion Gateway computes the diff:
    $$\text{Divergent Hop Distance } k = \min \{ i \mid IP_i(t) \ne IP_i(t-1) \}$$
  - An event is dispatched to Zabbix noting the old IP and new IP at hop $k$.

---

## 4. Network Boundary & Encapsulation Visibility

### 4.1 NAT (Network Address Translation) Boundaries
- When probes cross an enterprise NAT gateway (RFC 1918 $\to$ Public IP):
  - Hops prior to the NAT gateway reflect internal RFC 1918 addresses (`10.x.x.x`, `172.16.x.x`, `192.168.x.x`).
  - Hops after the NAT gateway reflect public routable or carrier-grade NAT (CGNAT) addresses (`100.64.x.x`).
- **Nawari Interpretation:** Nawari labels hops with RFC 1918 addresses as `INTERNAL_ENTERPRISE_HOP` and public addresses as `PUBLIC_TRANSIT_HOP`.

### 4.2 MPLS (Multi-Protocol Label Switching) Visibility
Enterprise WAN providers often carry traffic inside an MPLS core.
- **RFC 4950 Support:** If intermediate MPLS Label Switch Routers (LSRs) support RFC 4950 ("ICMP Extensions for Multi-Protocol Label Switching"), the ICMP Time Exceeded packet includes an extension payload carrying the MPLS Label Stack:
  - Label value (20 bits)
  - Traffic Class / Experimental bits (EXP, 3 bits - indicating QoS class)
  - Bottom of Stack (S, 1 bit)
  - Inward TTL (8 bits)
- **Opaque MPLS Core:** If LSRs do not support RFC 4950 or disable ICMP tunneling, the entire MPLS core appears as a sequence of timeouts (`* * *`) or as a single hop between the Provider Edge (PE) routers.
- **Nawari Parser:** The endpoint agent parses RFC 4950 ICMP extension structures when present, recording `mpls_labels` in the hop telemetry.

---

## 5. Autonomous System (ASN) Attribution & BGP Integration

To provide ThousandEyes-style organizational attribution, Nawari maps public IP addresses to their originating Autonomous System Number (ASN) and AS Organization name (e.g., AS36940 Kenya Airways, AS37061 Safaricom, AS1299 Arelion).

### Evaluation of Resolution Approaches:
1. **Air-Gapped / Local Offline Database (Recommended Baseline):**
   - Ingestion Gateway bundles an offline MaxMind GeoLite2-ASN database (or IP2Location ASN database).
   - Lookups are local in-memory binary trie queries ($< 5\mu\text{s}$ per lookup).
   - Zero outbound DNS or WHOIS requests; completely functional in secure air-gapped enterprise environments.
2. **DNS-Based Team Cymru Lookup (`origin.asn.cymru.com`):**
   - Query format: Reverse IP format `2.1.200.10.origin.asn.cymru.com` TXT record.
   - Returns: `ASN | Prefix | CC | Registry | Allocated`.
   - Requires outbound DNS resolution to public root servers.
3. **Architectural Decision:**
   - **Local Verification / Development:** Mock ASN dictionary containing Kenya Airways ASN (`AS36940`), regional carriers, and local RFC 1918 identifiers (`INTERNAL`).
   - **Production Deployment:** Ingestion Gateway utilizes a locally mounted MaxMind GeoLite2-ASN database file, updated monthly. Endpoint agents NEVER perform ASN lookups directly.
