# Endpoint deployment decision

Status: accepted for pilot implementation

## Decision

Employee laptops have one primary monitoring service: Netdata Child. Nawari
network digital-experience measurements run as a compiled Netdata external
collector whose lifecycle is supervised by Netdata. Endpoint metrics stream to
Netdata Parents through the authenticated Netdata streaming connection.

Nawari remains a central platform responsible for service catalogues,
correlation, storage selection, dashboards, incident workflows, and qualified
diagnosis. Zabbix and SolarWinds retain their infrastructure responsibilities.

## Packaging

- Windows: one Intune Win32 application containing the approved Netdata MSI,
  the signed Nawari collector, approved collector configuration, authenticated
  stream configuration, detection, rollback, and uninstall scripts.
- macOS: the approved Netdata installation plus the signed/notarized collector
  in Netdata's plugin directory, delivered as one managed endpoint package.
- The vendor Netdata package is not rebuilt or modified.
- `communication-observability/packaging/windows` is an experimental fallback,
  not the default fleet deployment.

## Telemetry boundary

The default collector configuration is metrics-only:

```json
"structured_evidence_enabled": false
```

DNS/connect/TLS/TTFB/total durations and request outcome are emitted using the
Netdata external-plugin protocol and travel through child-to-Parent streaming.
The collector does not require a Nawari token or direct endpoint intake in this
mode.

Structured path histories and selected diagnostic events do not fit naturally
into time-series chart dimensions. Any future endpoint evidence channel for
those records requires a separate privacy, security, retention, and operational
decision. It must not be enabled implicitly by the endpoint package.

## Acceptance gates

The source and macOS pilot do not establish Windows production readiness. A
managed Windows 10/11 device must demonstrate:

1. Netdata supervision and restart behavior for `nawari.plugin.exe`.
2. Native resolver, gateway, interface, Wi-Fi, VPN, and proxy observations.
3. DNS, TCP, TLS, HTTP, ICMP, and bounded path behavior permitted by policy.
4. Authenticated child-to-Parent streaming and certificate verification.
5. Parent and Grafana visibility with stable device and service labels.
6. Sleep/wake, roaming, VPN transition, offline recovery, upgrade, rollback,
   removal, CPU, memory, battery, bandwidth, and disk limits.

Until these pass, Windows status is build-feasible and runtime-pending.
