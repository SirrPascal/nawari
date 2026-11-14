# Network observability pilot

This project pilots network digital user experience from a macOS laptop, starting with the installed Netdata Agent. Code, templates and local evidence live in this folder. Existing Nawari services continue to use their established paths.

The first controlled endpoint-to-operator slice now lives under `platform/` and the compiled Netdata-managed extension under `collectors/nawari/`. The extension has been launched and supervised by the local Homebrew Netdata `2.12.3` fixture installation; this does not establish Parent or fleet integration. See [local development](docs/local-development.md), the [baseline and milestone register](docs/baseline-and-milestone-status.md), and the [per-OS coverage matrix](docs/per-os-collector-matrix.md). Server artifacts under `server/platform/` are prepared for later inspection and deployment review; they have not been deployed.

The [server deployment guide](server/README.md) covers the locally built Parent bundle,
SSH deployment to `admin.comms@10.2.1.58`, IP-based TLS certificates and Mac enrollment.

## First pilot

Run commands from this folder. Python scripts use the standard library.

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability"
python3 scripts/audit_agent.py
python3 -m unittest discover -s tests -v
```

The audit queries the agent at `http://127.0.0.1:19999`. It writes `evidence/agent-capabilities.json` with version, chart counts and freshness by capability. Evidence is ignored by Git. The report omits hostnames, interface names, URLs, process data and log contents. An unavailable API exits with status 1 and an explicit unavailable report.

`observed_fresh` describes chart availability. A healthy business service requires test outcomes and target-level evidence. `not_observed` means the capability has no matching charts in the queried inventory. Collector support and activation still need checking. `partially_fresh`, stale and unknown timestamps remain visible.

## Controlled HTTP experience test

Start the local fixture in a separate terminal and keep it running.

```sh
python3 scripts/fixture_service.py
```

| Path | Expected response | Interpretation |
| --- | --- | --- |
| `/healthy` | HTTP 200, prompt response | Available local reference |
| `/slow` | HTTP 200 after approximately one second | Controlled service-response delay |
| `/unavailable` | HTTP 503 | Controlled unsuccessful service response |

These checks exercise HTTP response classification on loopback. The local fixture holds the network observation point constant while response behavior changes. Later tests must exercise real gateway, DNS and service-path conditions.

To activate the provided HTTP jobs in the installed Homebrew agent, first check whether its configuration file already exists.

```sh
NETDATA_PILOT_CONFIG="$(brew --prefix)/etc/netdata/go.d/httpcheck.conf"
ls -l "$NETDATA_PILOT_CONFIG"
```

If the file exists, merge the three uniquely named `pilot_fixture_*` jobs into its existing `jobs` list. Otherwise copy the template.

```sh
cp -n config/netdata/go.d/httpcheck.conf.example "$NETDATA_PILOT_CONFIG"
brew services restart netdata
```

After at least two 15-second collection intervals, rerun `python3 scripts/audit_agent.py` and open `http://localhost:19999`. Look for `httpcheck` charts and the three job names. Expect the slow target to have elevated response time and the unavailable target to report `bad_status`. The template's accepted status remains 200 for all jobs. Verify both the configuration and actual charts if no HTTP capability appears.

When finished, remove only the three pilot jobs. If the file was created exclusively for this pilot, remove that file, then restart Netdata. Stop the fixture with Ctrl+C. This project creates configuration examples and queries the running agent. Activation commands are an operator step.

## Build upon the pilot

| Stage | Deliverable | Acceptance evidence |
| --- | --- | --- |
| Agent baseline | Installed version, interface metrics and explicit capability gaps | Timestamped capability report |
| Service response | Three local HTTP jobs | Healthy, delayed and 503 results distinguishable on the same observation point |
| Network experience | Approved gateway, DNS resolver and reference-service targets | Independent DNS, connection and service outcomes with fresh timestamps |
| Context | Stable endpoint/site IDs, Wi-Fi/Ethernet and VPN context | Correct identities across reconnect and network changes |
| Central metrics | Native agent streams to a Linux Parent, selected export to self-hosted metrics backend and Grafana | Source identity, timestamps, outage/replay behavior and freshness visible centrally |
| Selected logs | macOS collector, authenticated central intake and log store | Redaction, bounded queue, seven-day deletion and restart/restore checks |
| Fault-domain assessment | Compare matched service/site/time windows | Network, DNS, destination-specific and application-response hypotheses supported by evidence |

The service catalogue in `config/services.example.json` records pilot identities and the evidence contract to build. Later business-service targets need explicit expected status/content, schedule and network context. Netdata's basic HTTP collector provides total response time and result categories. Detailed DNS/TCP/TLS/first-byte phases require verified collector coverage or an additional focused probe. Local response delay alone cannot establish the cause of a remote incident.

## Source references

Homebrew setup and service commands follow the [Netdata macOS guide](https://learn.netdata.cloud/docs/netdata-agent/installation/macos).

The local jobs follow the [HTTP collector reference](https://learn.netdata.cloud/docs/collecting-metrics/collectors/synthetic-testing/http-endpoints). Future gateway and DNS checks use the [ping](https://learn.netdata.cloud/docs/collecting-metrics/collectors/synthetic-testing/ping) and [DNS query](https://learn.netdata.cloud/docs/collecting-metrics/collectors/synthetic-testing/dns-query) collector references. These targets need configuration and observed results.
