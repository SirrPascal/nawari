# Stage 7B: Endpoint Connectivity, DNS, and Service Probing Engine

## 1. Executive Summary

Stage 7B of the Nawari platform expands the endpoint agent (established in Stage 7A) with multi-protocol connectivity and service probing capabilities. The agent can now continuously evaluate edge reachability, domain name resolution, transport layer health, cryptographic session establishment, and application responsiveness to critical enterprise services (such as Avaya Session Border Controllers, SIP proxies, web portals, and database infrastructure).

Following Nawari's architectural principles, all probing operations are strictly **unprivileged** (no root, no administrative capabilities required), operate under declarative whitelist policies, and enforce **Zero-RCE** (zero invocation of operating system shell primitives).

---

## 2. Core Probing Engines

### 2.1 DNS Probing Engine (`services/endpoint/probes/dns.py`)
- **Direct Wire Protocol**: Implements an unprivileged, non-blocking RFC 1035 UDP DNS packet builder and parser alongside platform resolver fallbacks (`getaddrinfo`).
- **RFC 1035 Truncation Fallback**: Automatically inspects the `TC` (Truncation) header bit on UDP responses. If `TC=1` (indicating payload exceeded 512 bytes), the engine immediately reconnects over TCP port 53 with a 2-byte length prefix.
- **Granular Classification**: Classifies outcomes into RFC 1035 RCODEs and operational states:
  - `NOERROR`: Successful resolution with matching record payloads.
  - `NOERROR_EMPTY`: Query resolved successfully, but the zone contains no matching records for the queried RR type.
  - `NXDOMAIN`: Non-existent domain.
  - `SERVFAIL`: Name server failure.
  - `REFUSED`: Name server policy refusal.
  - `TIMEOUT`: Unresponsive resolver.
  - `ERROR`: Network or malformed packet errors.
- **Latency Resolution**: Sub-millisecond timing tracking DNS resolution time.

### 2.2 TCP 3-Way Handshake Engine (`services/endpoint/probes/tcp.py`)
- **SYN-to-SYN-ACK Measurement**: Uses non-blocking socket connect (`select.select` / `asyncio`) to measure exact round-trip transport handshake latency.
- **Transport Failure Mapping**: Maps POSIX socket errors to deterministic states:
  - `SUCCESS`: Handshake complete.
  - `CONNECTION_REFUSED`: Target host actively rejected connection (`RST`).
  - `TIMEOUT`: SYN packet dropped or blackholed without response.
  - `HOST_UNREACHABLE` / `NETWORK_UNREACHABLE`: Routing failure / ICMP destination unreachable.
  - `CONNECTION_RESET`: Connection reset during handshake.
- **Voice Invariant (Port 5061)**:
  > **Architectural Invariant**: A successful TCP 3-way handshake to port 5061 (or 5060) proves only that the host's transport stack is listening. It does **not** prove SIP registration status, call processing capability, or RTP media health.

### 2.3 TLS Handshake Engine (`services/endpoint/probes/tls.py`)
- **Cryptographic Session Inspection**: Establishes TLS handshakes to determine negotiated TLS version (`TLSv1.2`, `TLSv1.3`), negotiated cipher suite, and handshake completion time.
- **Certificate Health**: Extracts peer X.509 certificate validity dates (`notAfter`), calculates days remaining until expiration, and detects impending expiration.
- **Default Verification Invariant**:
  > **Security Invariant**: `verify_certificates=True` is the default. Verification is never silently disabled. Untrusted certificates, expired certificates, and hostname mismatches are explicitly flagged and categorized (`CERTIFICATE_EXPIRED`, `CERTIFICATE_UNTRUSTED`, `HOSTNAME_MISMATCH`).

### 2.4 HTTP/HTTPS Decomposed Latency Engine (`services/endpoint/probes/http.py`)
- **Decomposed Latency Breakdown**:
  - `dns_lookup_time_ms`: Resolution duration.
  - `tcp_connect_time_ms`: Transport handshake duration.
  - `tls_handshake_time_ms`: Cryptographic handshake duration (HTTPS only).
  - `http_ttfb_ms`: Time to First Byte (from request dispatch to first byte received).
  - `http_total_time_ms`: Total end-to-end request duration.
- **Outcome Classification**: Maps HTTP response codes to structured states (`SUCCESS`, `CLIENT_ERROR_4XX`, `SERVER_ERROR_5XX`, `REDIRECT_3XX`, `TIMEOUT`, `CONNECTION_FAILED`).
- **Privacy & Security Invariant**:
  > **Data Privacy Invariant**: The agent collects **only** connection metrics, timing breakdowns, response byte size, and status codes. It **never** logs or stores HTTP cookies, authorization headers, request bodies, or user browsing history.

---

## 3. Integration with Endpoint Agent Coordinator (`runner.py`)

The `EndpointAgentRunner` coordinates all Stage 7A and Stage 7B diagnostic collectors into unified reporting:
1. **Local Network Health**: Default gateway reachability, interface state, MTU, Wi-Fi link speed, and SSID.
2. **DNS Diagnostics**: Probing configured local and corporate DNS resolvers.
3. **Service Connectivity**: Multi-target probing dispatched according to configured `ServiceProtocol`:
   - `TCP` $\to$ `TcpProbe`
   - `TLS` $\to$ `TlsProbe`
   - `HTTP` / `HTTPS` $\to$ `HttpProbe`
   - `ICMP` $\to$ Platform ping adapter
4. **Target Security Whitelist**: Targets that do not match `allowed_ip_ranges` or `allowed_domains` are rejected by policy before execution.
5. **Local Spooling**: Reports are committed atomically to SQLite/disk spooler prior to network transmission, ensuring offline resilience.

---

## 4. Verification Evidence

### 4.1 Unit Test Suite (`tests/unit/test_stage7b_probes.py`)
- **DNS tests**: Validated localhost `NOERROR`, reserved domain `NXDOMAIN`, RFC 1035 QNAME encoding, and UDP `TC=1` truncation fallback to TCP port 53.
- **TCP tests**: Validated `CONNECTION_REFUSED` on closed ports, `TIMEOUT` on blackhole IPs, and port 5061 reachability mapping.
- **TLS tests**: Validated `CONNECTION_FAILED`, default verification enforcement, and `CERTIFICATE_EXPIRED` / `HOSTNAME_MISMATCH` mapping.
- **HTTP tests**: Validated live container probing, 404 client error classification, and scheme validation.
- **Result**: 13/13 unit tests passed in 0.35s.

### 4.2 Integration Test Suite (`tests/integration/test_stage7b_connectivity.py`)
- Probed live Docker environment:
  - `nawari-asterisk` (Port 5061): TCP handshake verified in 0.28 ms.
  - `nawari-zabbix-web` (Port 8088): Decomposed HTTP timing verified (DNS: 0.03 ms, TCP: 0.18 ms, TTFB: 33.36 ms, Total: 33.73 ms, 3,982 bytes).
  - `nawari-postgres` (Port 5433): TCP handshake verified in 0.31 ms.
- Layer independence verified: 404 URL confirms transport healthy while application layer reports client error.
- Full agent cycle verified: `run_once()` generated `nawari.endpoint.telemetry.v1` report and safely persisted to spooler.
- **Result**: 5/5 integration tests passed in 6.33s.

