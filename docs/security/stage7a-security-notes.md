# Nawari Stage 7A: Endpoint Agent Security Implementation Notes

**Document Version:** 1.0.0  
**Status:** Implemented & Verified Baseline  
**Date:** 2026-11-07  
**Security Classification:** Enterprise Agent Baseline

---

## 1. Zero-Remote-Execution (Zero-RCE) Enforcement

The Nawari Endpoint Agent is strictly engineered to prevent arbitrary remote command execution:

1. **Purely Outbound Sensor:** The agent does not open any inbound listening TCP/UDP ports. It initiates outbound connections exclusively.
2. **Rejection of Shell Metacharacters:** In `TargetPolicy`, destination addresses and target identifiers are validated against `DANGEROUS_CHARS_REGEX`:
   ```python
   DANGEROUS_CHARS_REGEX = re.compile(r"[;`$&|<>\\\n\r\t\"']")
   ```
   Any target containing shell separators or metacharacters raises an immediate `ConfigurationError`.
3. **Destination Whitelist Policy:** The configuration validates target destinations against `allowed_subnets` (CIDR notation) and `allowed_domains` (e.g. `*.kq.internal`, `*.local`, `localhost`). Targets outside approved boundaries are rejected at startup.
4. **No Dynamic Execution Primitives:** The codebase contains zero instances of `eval()`, `exec()`, `os.system()`, or `subprocess.Popen(shell=True)`. All network interactions utilize native standard library socket APIs or sanitized argument vectors (`shell=False`).

---

## 2. Least Privilege Operation & Capability Reporting

The agent executes with minimal user-space privileges across all supported platforms:

- **Windows 10/11:** Utilizes Microsoft IP Helper API (`Iphlpapi.dll`), which executes user-mode ICMP echo and traceroute without requiring local Administrator privileges.
- **Linux:** Operates as an unprivileged service user (`nawari-agent`). Standard user-mode ICMP datagram sockets (`net.ipv4.ping_group_range`) are supported natively by modern Linux kernels.
- **macOS:** Runs as a standard non-root user, wrapping the setuid `/sbin/ping` binary with strict input sanitization.
- **Capability Honesty:** The agent queries its operating environment at startup and returns a `PlatformCapabilities` object. If raw socket capabilities are absent, it reports `supports_raw_icmp: false` and degrades gracefully.

---

## 3. Data Privacy & Credential Sanitization

1. **Automatic Log Sanitization:** `SanitizingFormatter` in `services/endpoint/core/logger.py` scrubs sensitive authorization tokens (`api_token=***REDACTED***`) and masks agent UUIDs (`e4b3****-****-****-****-****9abc`) across all log streams.
2. **Local Spool Protection:** Telemetry stored on local disk is restricted to owner read/write permissions (`0600`).
3. **Zero Payload Inspection:** The agent captures solely layer-3/4 transport metrics (RTT, packet loss, interface status, Wi-Fi link quality). It never inspects user files, browser history, or packet payloads.
