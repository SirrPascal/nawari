# Nawari Endpoint Agent Security Specification

**Document Version:** 1.0.0  
**Status:** Architectural Baseline for Review  
**Date:** 2026-11-07  
**Classification:** Enterprise Security Baseline

---

## 1. Executive Security Directive & Zero-RCE Mandate

> [!CAUTION]
> **The Zero-Remote-Execution (Zero-RCE) Principle:**
> The Nawari Endpoint Agent **MUST NEVER** accept, execute, or evaluate arbitrary remote commands, shell scripts, or dynamic code under any circumstances. Distributed agents deployed across thousands of employee laptops represent an attractive target for adversaries. A monitoring agent must strictly remain an outbound measurement sensor, never a remote administrative backdoor.

---

## 2. Threat Modeling & Attack Surface Analysis (STRIDE)

| Threat Category | Potential Attack Vector | Nawari Architectural Defense |
|---|---|---|
| **Spoofing (S)** | A malicious entity sends fabricated telemetry claiming an enterprise network outage, or claims `PHYSICAL_PRODUCTION` provenance from a test runner. | 1. Mutual TLS (mTLS) or HMAC-SHA256 token authentication.<br/>2. Authoritative `environment` provenance tagging injected exclusively by the trusted Ingestion Gateway, not by endpoint payloads. |
| **Tampering (T)** | An attacker modifies the probe targets to launch a Distributed Denial of Service (DDoS) against external systems. | 1. Target configurations are validated against a strict, server-enforced CIDR and domain whitelist.<br/>2. Configuration files are digitally signed and integrity-checked via SHA-256 before loading. |
| **Repudiation (R)** | An unverified endpoint denies sending anomalous metric spikes or corrupting time-series trends. | All transmissions require a registered `agent_id` tied to an audit log entry on the Ingestion Gateway with client IP, certificate serial, and nanosecond timestamp. |
| **Information Disclosure (I)** | An adversary intercepts endpoint telemetry to map internal enterprise network topologies, subnets, and routing hops. | All data in transit is encrypted using TLS 1.3. Local disk spools are secured with OS-level permissions (`0600` on Linux, ACL restricted to `LOCAL_SYSTEM` and the service account on Windows). |
| **Denial of Service (D)** | Aggressive probing saturates user Wi-Fi/cellular bandwidth, or an agent flooding the Ingestion Gateway causes central server exhaustion. | 1. Strict rate-limiting on both agent (max 1 probe burst/minute) and Gateway (token bucket algorithm).<br/>2. Circuit breakers halt probing if endpoint CPU exceeds 20% or battery drops below 15%. |
| **Elevation of Privilege (E)** | An attacker exploits agent vulnerability to gain `SYSTEM` (Windows) or `root` (Linux) privileges. | The agent is explicitly designed to run as an **unprivileged user** without requiring Administrator or `root` rights. |

---

## 3. Least Privilege Execution Architecture

### 3.1 Windows 10/11 Architecture (Zero-Admin Operation)
Traditionally, network diagnostic tools on Windows required Administrator rights to open raw sockets (`IPPROTO_IP`).

**Nawari Solution:**
- Windows provides the native, unprivileged IP Helper API: `Iphlpapi.dll`.
- Functions `IcmpCreateFile()`, `IcmpSendEcho()`, and `IcmpCloseHandle()` allow standard, non-administrator user accounts to send ICMP Echo requests and receive responses.
- To execute hop-by-hop traceroute, the agent populates the `IP_OPTION_INFORMATION` structure with varying `Ttl` values (1 through 30).
- TCP connect probing uses standard WinSock `connect()` sockets.
- Wi-Fi metrics (RSSI, BSSID, Channel) are queried via the unprivileged Native Wifi API (`WlanOpenHandle`, `WlanQueryInterface`).
- **Privilege Level:** The agent runs under `NT AUTHORITY\NetworkService` or a standard local service account. Administrator privileges are strictly denied.

### 3.2 Linux Architecture (Zero-Root Operation)
On modern Linux kernels (Ubuntu 20.04+, Debian 11+, RHEL 8+):
- **Unprivileged ICMP:** Linux supports unprivileged ICMP datagram sockets (`socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)`).
- This is controlled by the kernel sysctl `net.ipv4.ping_group_range = 0 2147483647`, which is enabled by default on Ubuntu and Debian distributions.
- Where raw sockets are strictly required for Paris traceroute custom UDP checksum adjustment, the binary is granted a single isolated file capability:
  ```bash
  sudo setcap cap_net_raw+ep /usr/local/bin/nawari-agent
  ```
- **Privilege Level:** The agent runs as dedicated system user `nawari-agent` (`UID 985`, `GID 985`) with `NoNewPrivileges=yes` and `ProtectSystem=strict` enforced in its systemd unit.

---

## 4. Configuration Integrity & Whitelisting Framework

The endpoint agent receives its probing policy via an immutable, declarative specification delivered over TLS from the Nawari Gateway.

### 4.1 Strict Whitelist Enforcement Schema
```json
{
  "$schema": "https://nawari.internal/schemas/endpoint-policy-v1.json",
  "policy_version": "2026.11.07.1",
  "signature": "MEUCIQDx...",
  "max_concurrent_probes": 2,
  "probe_cooldown_seconds": 60,
  "allowed_domains": [
    "*.kq.internal",
    "*.kenya-airways.com",
    "voice.nawari.local"
  ],
  "allowed_subnets": [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16"
  ],
  "allowed_ports": [53, 80, 443, 5060, 5061],
  "targets": [
    {
      "target_id": "avaya-sbce-sig-a1",
      "destination": "10.250.1.10",
      "port": 5061,
      "protocol": "TCP",
      "traceroute_enabled": true
    }
  ]
}
```

### 4.2 Security Constraints on Targets:
1. **No External Arbitrary Probing:** Probes directed to arbitrary public internet IP addresses outside enterprise voice and cloud services are rejected.
2. **Port Restrictions:** Destination ports are restricted to well-known service ports (DNS: 53, HTTP: 80, HTTPS: 443, SIP: 5060, SIP-TLS: 5061). Probing arbitrary high ports is blocked.
3. **No Dynamic Code / Shell Execution:** The agent does not use `os.system()`, `subprocess.call(shell=True)`, `eval()`, or `exec()`. All network operations are invoked via native Python standard library socket/TLS primitives or Ctypes bindings.

---

## 5. Agent Identity, Enrollment & Revocation

```mermaid
sequenceDiagram
    autonumber
    participant Admin as Nawari Security Admin
    participant Gateway as Nawari Ingestion Gateway
    participant Agent as New Endpoint Agent
    participant Vault as Agent Secure Storage (Credential Vault)

    Admin->>Gateway: Generate One-Time Registration Token (OTRT)
    Admin->>Agent: Deploy Agent with OTRT & Gateway URL
    Agent->>Gateway: POST /api/v1/agent/enroll (OTRT, Hostname, OS Fingerprint)
    Note over Gateway: 1. Validate OTRT (One-time, unexpired)<br/>2. Generate Agent UUID v4<br/>3. Issue mTLS Client Cert or HMAC Token
    Gateway-->>Agent: 201 Created (Agent UUID, Client Cert, Ingestion Key, Policy)
    Agent->>Vault: Store Ingestion Key in OS Secure Vault (DPAPI / SecretService)
    Agent->>Agent: Purge OTRT from memory and disk
    
    loop Every Scheduled Interval (e.g. 60s)
        Agent->>Gateway: POST /api/v1/telemetry/endpoint (Signed with Ingestion Key)
        alt Agent Key Revoked by Admin
            Gateway-->>Agent: 401 Unauthorized (REVOKED)
            Agent->>Agent: Transition to HALTED state; disable probing
        else Key Valid
            Gateway-->>Agent: 200 OK (Accepted)
        end
    end
```

---

## 6. Telemetry Privacy & Data Minimization

The Nawari agent strictly adheres to data minimization principles:
1. **Zero Packet Capture (No PCAP):** The agent never captures, inspects, or buffers raw packet payloads. It records only transport-layer metrics (SYN-ACK latency, ICMP RTT, loss percentage, HTTP status code).
2. **Zero User Data Inspection:** The agent does not read user files, browser history, keystrokes, camera/microphone streams, or active application windows.
3. **Sanitized Hostname & User Identity:** Telemetry is associated only with the machine hostname and unique Agent UUID. Operating system username is stripped prior to transmission.
4. **Local Spool Protection:** If network connectivity to the Gateway is interrupted, metrics spooled to local disk are saved in an encrypted SQLite database or restricted JSONL file (`chmod 0600`) owned exclusively by the service account.
