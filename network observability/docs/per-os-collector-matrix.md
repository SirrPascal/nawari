# Endpoint collector feasibility matrix

`Source verified` means the pinned code or installed binary was inspected. `Runtime verified` means the behavior was exercised on the named laptop. Windows remains a source-level feasibility assessment.

| Observation | Implementation owner | macOS status | Windows status | Remaining acceptance |
| --- | --- | --- | --- | --- |
| Host and interface counters | Netdata platform collector | Runtime verified for interface traffic/errors/drops | Native Netdata Windows build reports a Windows platform plugin, runtime pending | Counter reset semantics and resource impact per supported OS |
| Approved reachability | Netdata `ping` | Installed configuration exists; job runtime pending | Collector source/package availability pending | Socket privilege, blocked ICMP and target policy |
| Explicit-resolver DNS | Netdata `dns_query` | Installed configuration exists; job runtime pending | Collector source/package availability pending | Resolver/protocol semantics and secure-DNS boundary |
| TCP connection | Netdata `portcheck` | Installed configuration exists; job runtime pending | Collector source/package availability pending | Timeout classification and permissions |
| HTTP outcome and total duration | Netdata `httpcheck` | Controlled 200, delayed and 503 runtime verified | Source/package feasibility pending | Redirect, proxy, trust and employee-session behavior |
| DNS/connect/TLS/TTFB/total phases | Compiled `nawari.plugin` | Netdata-supervised fixture charts verified in metrics-only mode | Windows AMD64 executable and test binary cross-compile; runtime pending | Signed package, proxy policy and production target |
| Structured service evidence | Optional collector extension, disabled in the primary endpoint policy | Queue/receipt mechanics tested previously; primary package now disables direct intake | Build-only artifact produced; runtime pending | Separate privacy, retention and transport approval before any enablement |
| Resolver/gateway/route context | Compiled OS integration | Loopback context delivered; opt-in live test observed the laptop's actual tunnel route and resolver inventory without inventing a gateway | Interface derivation implemented; resolver/gateway APIs pending | Permission denial, physical next-hop correlation and network-transition handling |
| Wi-Fi/VPN/proxy context | Compiled OS integration | VPN and system-proxy state collected; Wi-Fi honestly unavailable on loopback run; SSID is hashed | Explicit unknown states; native APIs and runtime pending | Wi-Fi transition test, privacy review and employee-session fidelity |
| Destination path | Future bounded integrated diagnostic | Typed transport and UI fixture implemented | Source/runtime pending | Permission, hop cap, frequency and hidden-hop behavior |
| Selected OS events | Future integrated reader/sender | Typed allowlisted event intake implemented; OS source pending | Windows event-channel access pending | Permitted channels, redaction and seven-day deletion |

The compiled service collector creates a new connection for each request. A phase absent from the request appears as `not_performed` with no duration. Metrics never encode an absent phase as zero. DNS/connect/TLS callbacks can overlap and are displayed individually rather than summed.
