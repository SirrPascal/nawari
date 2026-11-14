# A01 local item-to-panel trace

Local execution is recorded in the [Release A evidence summary](../operations/release-a-local-evidence.md). See the [enterprise observability plan](../architecture/enterprise-observability-plan.md).

The initial worktree was on `feat/github-actions-cicd-pipeline` at `782e504`. The modified export workflow and exporter, untracked export CSV/JSON, and untracked architecture plan were already present. A01 adds this runbook, the [trace command](../../scripts/trace_zabbix_panel.py), and the [unit fixtures](../../tests/unit/test_trace_zabbix_panel.py).

## Candidate and evidence boundaries

The first candidate is the existing **ICMP Latency** stat in dashboard `nawari-net-overview`, panel **4**. Source provisioning associates the technical host `mock-core-switch-01` with a simulated core switch and the linked network template provides `icmppingsec` in seconds. This is a lab infrastructure fixture. The original selector used the technical name, which failed against the visible host name required by Grafana-Zabbix 6.10.2. The corrected target uses `Simulated Core Switch 01 (Lab)` and preserves the raw sample timestamp by disabling query alignment. A physical target can be supplied after an authorized operator identifies an existing compatible panel and matching local item.

Evidence sources: [dashboard model](../../docker/grafana/dashboards/network_observability/network_infrastructure_overview.json), [host manifest](../../provisioning/zabbix/hosts/mock_network_device.yaml), [item template](../../provisioning/zabbix/templates/nawari_generic_snmp.yaml), [datasource provisioning](../../docker/grafana/provisioning/datasources/zabbix.yaml), [plugin selector implementation](https://github.com/grafana/grafana-zabbix/blob/v6.10.2/pkg/zabbix/methods.go).

## Repeat local EXECUTE

Use the existing dev listeners on loopback, Zabbix on TCP 8088 and Grafana on TCP 3001. Obtain the stable host ID from an approved local read-only Zabbix inventory or the local Zabbix UI. Supply `ZBX_API_TOKEN` scoped to host/item reads and `GRAFANA_API_TOKEN` scoped to reading the saved dashboard and datasource and querying the datasource. Inject credentials through the approved local secret mechanism. Check that the listeners and datasource resolve to the intended development stack. No credential values belong in shell arguments or trace output.

```sh
python3 scripts/trace_zabbix_panel.py \
  --host-id "$LOCAL_ZABBIX_HOST_ID" \
  --technical-host mock-core-switch-01 \
  --item-key icmppingsec \
  --dashboard-uid nawari-net-overview --panel-id 4 \
  > /tmp/nawari-a01-trace.json
```

The trace writes one JSON object even for expected runtime or access failures. Exit status 0 means the model and datasource evidence matched. Exit status 1 means the trace stopped and recorded the first failure or evidence boundary. The report includes the sampled value and timestamp, source and Grafana identities, resolved selectors, freshness policy, datasource result summary, model-level stat result, evidence classification, and limitations. A successful report still has `rendered: false` because browser rendering requires independent evidence. Protect the report as operational inventory. Collection errors are represented by presence and redacted before output, as API error text can contain sensitive details.

Freshness is the greater of three collection intervals and 900 seconds. For macros and custom schedules, supply `--effective-interval SECONDS` only after verifying the effective local schedule. For supported scalar dashboard variables, an explicit `--variable NAME=VALUE` overrides the persisted selection. The tool reproduces the plugin's anchored interpolation for its supported filter forms. Use only non-sensitive monitoring selectors. The fixed history request spans the 15 minutes ending in the recorded Zabbix sample second, so newer samples in later seconds do not race the comparison. The Zabbix `lastclock` comparison has second precision. If plugin alignment changes the reported timestamp or value, investigate the difference before interpreting it as a source defect. For ICMP response time specifically, interpret a numeric zero using the item contract and its companion availability measurement.

The runtime check supports one top-level numeric `lastNotNull` stat and one target on the local proxy-mode Grafana-Zabbix datasource. Regex selectors, multi-value variables, panel transformations and other nontrivial frontend features stop at the applicable evidence boundary. Where supported, a matching field-name unit override takes precedence over the panel default. The verification covers the raw value and declared unit. Grafana can scale the displayed unit, and an authenticated backend query alone cannot establish the exact text rendered in the UI.

## TEST after EXECUTE and ANALYZE

```sh
python3 -m pytest tests/unit/test_trace_zabbix_panel.py
```

Fixtures cover non-zero, measured zero, stale, unsupported and never-collected values, missing or incorrect selectors, inaccessible datasource, unresolved variables, API query errors, and inconsistent timestamps/values/units or series identity. The tests construct API responses in memory. Expected results include a valid model-level value of zero with a nonzero timestamp, a null sample for `lastclock=0`, and a separately classified blocked datasource when scoped access is unavailable.

## Rollback

Remove the three A01 additions after preserving any trace evidence required by the owner. The script reads Zabbix and Grafana models and submits a read-only datasource query. There is no dashboard, item, datasource, service, or data migration to reverse. Dispose of temporary trace files under the project evidence policy.
