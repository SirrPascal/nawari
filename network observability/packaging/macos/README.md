# Nawari Netdata macOS package

This package installs the signed `nawari.plugin` as a Netdata external plugin.
Netdata remains the only supervisor; no Nawari launch daemon or second intake
service is installed. Existing Netdata configuration, machine identity, claim
credentials and streaming settings are preserved.

## Build

```sh
./packaging/macos/build.sh 0.3.1
```

The output is `artifacts/packages/<version>/Nawari-Netdata-macOS-<arch>-<version>.pkg`
with a SHA-256 file and a signing manifest. Set `NAWARI_ARCH=amd64` to build the
Intel package. Without `APPLICATION_IDENTITY`, `INSTALLER_IDENTITY`, and
`NOTARY_PROFILE`, the result is explicitly an unsigned development artifact.
Set `REQUIRE_SIGNING=1` for a production build; it fails closed.

## Install and verify

Install the package by double-clicking it or with `installer -pkg ... -target /`.
The postinstall script detects Homebrew and official Netdata layouts dynamically
and requires pinned Netdata 2.12.3; it never downloads or executes a remote
script. Review and replace the generated `nawari-collector.json` with approved
targets and enrollment settings, then restart the existing Netdata service.

```sh
./packaging/macos/verify.sh
```

Verification requires native CPU, memory and network charts plus at least one
Nawari chart with recent numeric samples. Chart existence without samples is a
failure. `health-check.sh` is a smaller local probe for operational checks.

Netdata's native `net.<interface>`, `net_errors.<interface>`, and
`net_drops.<interface>` charts remain the source of per-interface traffic and
fault measurements. Nawari's context chart additionally publishes
`interface_wifi`, `interface_ethernet`, and `interface_tunnel` for the active
default route. The destination route and default transport are tracked
separately, so a loopback pilot target cannot be mistaken for the Mac's active
Wi-Fi or Ethernet channel. Nawari does not automatically probe every observed
service; passive traffic discovery and active approved-target diagnostics are
separate policies.

Passive application discovery is opt-in in the collector configuration:

```json
{
  "application_discovery_enabled": true,
  "application_discovery_interval_ms": 60000,
  "application_discovery_max_apps": 12,
  "dns_observation_path": "/var/run/nawari/dns-observations.ndjson",
  "dns_slow_threshold_ms": 1000
}
```

When enabled on macOS, the bounded inventory reads established TCP sockets,
associates them with processes and route interfaces, emits one aggregate
`nawari.application_network` chart, and writes the local
`nawari-application-catalog.json` catalog with mode `0600`. It records
connection counts and interface association, not application page timing.
Browser or application instrumentation is still required for true operation
latency.

The DNS path is an approved telemetry input, not a DNS interceptor. Each
newline-delimited record must contain `domain`, `addresses`, `observed_at`,
`duration_ms`, and `status`; optional `resolver`, `ttl`, `cname_chain`, and
`process` fields improve evidence. The file must be regular,
non-group/world-writable, no larger
than 1 MiB, and is bounded to 256 observations per collection. Without this
managed resolver source, service classification remains unknown rather than
being inferred from reverse DNS or synthetic probes.

## Upgrade, rollback and uninstall

Install a newer package over the existing one. The plugin and configuration are
backed up under Netdata's configuration directory before replacement. Remove
only the plugin with `uninstall.sh`; configuration, queue and rollback copies are
intentionally retained for explicit retirement and review.

Clean-machine installation requires an operator-installed, approved Netdata
version. The package does not silently replace Netdata or claim credentials.
Validate both Homebrew and official Netdata layouts on a clean supported Mac
before calling a release production-ready.
