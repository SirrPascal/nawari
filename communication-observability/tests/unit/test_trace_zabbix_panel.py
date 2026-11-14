"""Deterministic A01 API and data-frame fixtures. No network or live credentials."""

from http.client import HTTPException

import pytest

from scripts.trace_zabbix_panel import DATASOURCE_TYPE, trace

NOW = 1_800_000_000
SAMPLE_TIME = NOW - 60


@pytest.fixture
def evidence():
    host = {"hostid": "10001", "host": "lab-switch", "name": "Lab Switch (1)", "status": "0",
            "hostgroups": [{"name": "Core Network"}]}
    item = {
        "itemid": "90001", "key_": "icmppingsec", "name": "ICMP response time",
        "value_type": "0", "units": "s", "status": "0", "state": "0", "error": "",
        "lastvalue": "0.012", "lastclock": str(SAMPLE_TIME), "delay": "1m",
    }
    target = {
        "refId": "A", "mode": 0, "host": {"filter": host["name"]}, "item": {"filter": item["name"]},
        "group": {"filter": "Core Network"}, "datasource": {"uid": "local-zabbix"},
    }
    panel = {
        "id": 4, "type": "stat", "targets": [target], "fieldConfig": {"defaults": {"unit": "s"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }
    dashboard = {"uid": "test-dashboard", "panels": [panel]}
    datasource = {"uid": "local-zabbix", "type": DATASOURCE_TYPE, "access": "proxy",
                  "url": "http://zabbix-web:8080/api_jsonrpc.php"}
    field = {
        "type": "number", "name": "Value", "labels": {"item_key": item["key_"], "host": host["name"]},
        "config": {"custom": {"units": "s", "scopedVars": {"__zbx_host_id": {"value": host["hostid"]}}}},
    }
    frame = {
        "schema": {"fields": [{"type": "time"}, field]},
        "data": {"values": [[SAMPLE_TIME * 1000, (SAMPLE_TIME + 1) * 1000], [0.012, None]]},
    }
    return host, item, target, panel, dashboard, datasource, field, frame


@pytest.fixture
def run(evidence):
    host, item, _, _, dashboard, datasource, _, frame = evidence
    calls = []

    def zabbix(method, params):
        assert params["hostids"] == ["10001"]
        calls.append((method, params))
        if method == "host.get":
            return [host]
        assert method == "item.get"
        assert params["filter"] == {"key_": "icmppingsec"}
        return [item]

    def grafana(path, payload=None):
        calls.append((path, payload))
        if path == "/api/dashboards/uid/test-dashboard":
            return {"dashboard": dashboard}
        if path == "/api/datasources/uid/local-zabbix":
            if not datasource:
                raise HTTPException("Access denied; sensitive detail")
            return datasource
        assert path == "/api/ds/query"
        return {"results": {"A": frame if "error" in frame else {"status": 200, "frames": [frame]}}}

    def execute(**options):
        return trace(
            zabbix, grafana, host_id="10001", technical_host="lab-switch", item_key="icmppingsec",
            dashboard_uid="test-dashboard", panel_id=4, now=NOW, fixture_target=True, **options,
        )

    return execute, calls


@pytest.mark.parametrize("sample", [0.012, 0])
def test_recent_measurement_including_measured_zero(evidence, run, sample):
    _, item, _, _, _, _, _, frame = evidence
    item["lastvalue"] = str(sample)
    frame["data"]["values"][1][0] = sample
    execute, calls = run
    report = execute()
    assert report["first_broken_link"] is None
    assert report["zabbix_item"]["sample_value"] == sample
    assert report["panel_result"]["value"] == sample
    assert report["panel_result"]["rendered"] is False
    assert report["provenance"] == "lab-simulation"
    assert report["freshness"] == {"interval_seconds": 60, "max_age_seconds": 900, "age_seconds": 60}
    assert calls[-1][1]["to"] == str(SAMPLE_TIME * 1000 + 999)


@pytest.mark.parametrize(
    ("changes", "stage"),
    [
        ({"lastclock": str(NOW - 901)}, "sample_stale"),
        ({"state": "1", "error": "sensitive collector details"}, "item_unsupported"),
        ({"lastclock": "0", "lastvalue": "0"}, "sample_never_collected"),
    ],
)
def test_collection_failures_stop_before_grafana(evidence, run, changes, stage):
    evidence[1].update(changes)
    execute, calls = run
    report = execute()
    assert report["first_broken_link"]["stage"] == stage
    assert [method for method, _ in calls] == ["host.get", "item.get"]
    assert "sensitive collector details" not in str(report)
    if stage == "sample_never_collected":
        assert report["zabbix_item"]["sample_value"] is None
        assert report["zabbix_item"]["sample_timestamp"] is None


@pytest.mark.parametrize("selector", ["host", "item"])
def test_missing_selector(evidence, run, selector):
    evidence[2].pop(selector)
    execute, _ = run
    assert execute()["first_broken_link"]["stage"] == f"{selector}_selector"


def test_technical_name_is_not_used_as_visible_selector(evidence, run):
    evidence[2]["host"]["filter"] = evidence[0]["host"]
    execute, _ = run
    assert execute()["first_broken_link"]["stage"] == "host_selector"


def test_inaccessible_datasource(evidence, run):
    evidence[5].clear()
    execute, _ = run
    report = execute()
    assert report["first_broken_link"]["stage"] == "datasource"
    assert report["evidence_classification"] == "BLOCKED"
    assert "sensitive detail" not in str(report)


def test_missing_datasource_uid(evidence, run):
    evidence[2].pop("datasource")
    execute, _ = run
    assert execute()["first_broken_link"]["stage"] == "datasource"


def test_unresolved_template_variable(evidence, run):
    evidence[2]["host"]["filter"] = "$missing"
    execute, _ = run
    assert execute()["first_broken_link"]["stage"] == "variable_resolution"


def test_panel_variables_and_unit_override(evidence, run):
    _, _, target, panel, dashboard, _, _, _ = evidence
    target["host"]["filter"] = "$selected_host"
    target["item"]["filter"] = "${item}"
    dashboard["templating"] = {"list": [
        {"name": "selected_host", "current": {"value": "Other host"}},
        {"name": "item", "current": {"value": "ICMP response time"}},
    ]}
    panel["fieldConfig"] = {
        "defaults": {"unit": "ms"},
        "overrides": [{"matcher": {"id": "byName", "options": "Value"},
                       "properties": [{"id": "unit", "value": "s"}]}],
    }
    execute, calls = run
    report = execute(variable_overrides={"selected_host": "Lab Switch (1)"})
    assert report["first_broken_link"] is None
    assert report["resolved_selectors"]["host"] == "Lab Switch (1)"
    assert calls[-1][1]["queries"][0]["host"]["filter"] == r"/^Lab Switch \(1\)$/"
    assert report["panel_result"]["unit"] == "s"


def test_datasource_query_error(evidence, run):
    evidence[-1]["error"] = "sensitive query details"
    execute, _ = run
    report = execute()
    assert report["first_broken_link"]["stage"] == "datasource_query"
    assert "sensitive query details" not in str(report)


@pytest.mark.parametrize(
    ("problem", "stage"),
    [("value", "panel_measurement"), ("timestamp", "panel_measurement"), ("unit", "panel_unit"),
     ("stat_override", "panel_unit"), ("identity", "series_identity")],
)
def test_successful_query_with_inconsistent_evidence(evidence, run, problem, stage):
    _, _, _, panel, _, _, field, frame = evidence
    if problem == "value":
        frame["data"]["values"][1][0] = 120
    elif problem == "timestamp":
        frame["data"]["values"][0][0] -= 1000
    elif problem == "unit":
        field["config"]["custom"]["units"] = "ms"
    elif problem == "stat_override":
        panel["fieldConfig"]["overrides"] = [
            {"matcher": {"id": "byName", "options": "Value"}, "properties": [{"id": "unit", "value": "ms"}]},
        ]
    else:
        field["labels"]["item_key"] = "icmpping"
    execute, _ = run
    report = execute()
    assert report["first_broken_link"]["stage"] == stage
    assert report["datasource_result"]["status"] == 200
    assert report["panel_result"] is None


def test_effective_interval_required_for_custom_schedule(evidence, run):
    evidence[1]["delay"] = "{$INTERVAL}"
    execute, _ = run
    assert execute()["first_broken_link"]["stage"] == "freshness_policy"
    report = execute(interval_override=600)
    assert report["first_broken_link"] is None
    assert report["freshness"]["max_age_seconds"] == 1800
