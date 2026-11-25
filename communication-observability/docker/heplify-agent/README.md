# Nawari Voice Capture Agent — Deployment & Security Architecture

## 1. Overview & Architecture

The `nawari-heplify-agent` service provides passive packet sniffing of SIP signaling frames (`UDP/TCP` ports `5060` and `5061`) traversing mirrored enterprise voice trunks. Captured signaling is encapsulated into **HEPv3 (Homer Encapsulation Protocol)** and forwarded to the central Homer ingestion server (`nawari-heplify` listening on UDP `10.2.1.58:9060`), which stores the parsed SIP dialogs in PostgreSQL (`homer_data`).

```
[Avaya SBCE / Core Switch] 
       │ (Port Mirror / SPAN)
       ▼
[Dedicated vNIC: ens224] (Passive, Unnumbered, Promiscuous Port Group)
       │
[nawari-heplify-agent] (Pinned OCI, CAP_NET_RAW/ADMIN, Non-Privileged, Read-Only)
       │ (HEPv3 UDP :9060)
       ▼
[nawari-heplify server] ──> [PostgreSQL homer_data] ──> [Nawari Core API] ──> [Grafana]
```

---

## 2. Security Hardening & Least-Privilege Posture

In initial testing, an ad-hoc container was started with `--privileged --net=host` on `ens192`. **This has been audited and removed.**

This production deployment specification adheres to zero-trust monitoring standards:
1. **Pinned Digest:** Uses `sipcapture/heplify@sha256:aa6dc20006f8bdd13dd62f1d54789e885843284280224d2ee2f8489d88dffd0e`.
2. **Non-Privileged:** `privileged: false`. The container runs without arbitrary host root privileges.
3. **Dropped Capabilities:** `cap_drop: [ALL]`.
4. **Minimal Linux Capabilities:** `cap_add: [NET_RAW, NET_ADMIN]`. Only the raw packet socket opening (`AF_PACKET`) and BPF filter configuration (`SO_ATTACH_FILTER`) privileges are granted.
5. **Security Options:** `security_opt: [no-new-privileges:true]`. Prevents privilege escalation via setuid binaries.
6. **Immutable Rootfs:** `read_only: true` with a small in-memory `/tmp` mount (`tmpfs: 10MB`).
7. **Resource Caps:** Bounded to `cpus: 0.50` and `mem_limit: 256m` to prevent noisy-neighbor starvation of Zabbix and PostgreSQL.
8. **Explicit Interface Binding:** Bound exclusively to the dedicated SPAN interface (`HEPLIFY_CAPTURE_IFACE`, default `ens224`). It must **never** be attached to the management interface `ens192`.

---

## 3. Infrastructure Prerequisites

Before starting this container, the following infrastructure actions must be completed:
1. **VMware vSphere Virtual Switch Configuration:**
   - Create a dedicated Port Group on the Virtual Distributed Switch (VDS) or Standard vSwitch (VSS): `PG-VOICE-SPAN`.
   - Security Policy: Set **Promiscuous Mode = Accept**, **MAC Address Changes = Accept**, **Forged Transmits = Reject**.
   - Mirroring: Configure a Port Mirroring session (Encapsulated Remote SPAN or Local VDS SPAN) sourcing Avaya SBCE interfaces and destination set to `PG-VOICE-SPAN`.
2. **VM Virtual Machine vNIC:**
   - Add a second network adapter (`vNIC 2`, vmxnet3) to `mon-grafana01` attached to `PG-VOICE-SPAN`.
   - On the Linux OS, this interface appears as `ens224` (or similar).
   - In Linux: Bring the interface up in unnumbered promiscuous mode without assigning an IP:
     ```bash
     ip link set dev ens224 up promisc on arp off
     ```

---

## 4. Change-Control Authorization Gate

**STATUS: GATED**

Do not activate `compose.heplify-agent.yaml` without signed approval from:
- **Voice Operations:** Approval to mirror Avaya SBCE / ASM signaling ports.
- **Network Engineering:** Approval of physical switch / vSwitch SPAN bandwidth impact.
- **Cybersecurity & Compliance:** Authorization for passive packet inspection on voice networks.
