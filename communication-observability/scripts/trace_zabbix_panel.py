"""A01 local trace for a single, untransformed Grafana-Zabbix numeric stat."""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
from urllib.parse import quote

DATASOURCE_TYPE = "alexanderzobnin-zabbix-datasource"
SELECTORS = ("group", "host", "item", "application", "itemTag", "tags", "proxy", "trigger")
VARIABLE = re.compile(r"\$\{([a-zA-Z_]\w*)\}|\$([a-zA-Z_]\w*)")
REGEX_SPECIAL = re.compile(r"[\\^$*+?.()|\[\]{}/]")
SIMPLE_INTERVAL = re.compile(r"([1-9][0-9]*)([smhdw]?)")
ZABBIX_METHODS = {"host.get", "item.get"}


class TraceStop(Exception):
    """An expected failure with a safe description for the evidence report."""

    def __init__(self, link, reason, classification="VERIFIED"):
        super().__init__(reason)
        self.link = link
        self.classification = classification


def require(condition, link, reason, classification="VERIFIED"):
    if not condition:
        raise TraceStop(link, reason, classification)


def local_json(port, token, path, payload=None):
    # No redirects, proxy environment, implicit credentials, or external destinations.
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "GET" if payload is None else "POST",
            path,
            body=None if payload is None else json.dumps(payload),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise HTTPException(f"HTTP {response.status}")
        return json.load(response)
    finally:
        connection.close()


def zabbix_read(token, method, params):
    if method not in ZABBIX_METHODS:
        raise ValueError("Method is outside the A01 read scope")
    response = local_json(
        8088, token, "/api_jsonrpc.php",
        {"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
    )
    if "error" in response:
        raise HTTPException("Zabbix rejected the read")
    return response["result"]


def read(link, operation, *args):
    try:
        return operation(*args)
    except (OSError, HTTPException, ValueError, KeyError, TypeError):
        raise TraceStop(link, "API response unavailable or unreadable; check scoped access.", "BLOCKED") from None


def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def collection_interval(delay, override):
    match = SIMPLE_INTERVAL.fullmatch(delay)
    if match:
        count, suffix = match.groups()
        return int(count) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[suffix]
    require(override, "freshness_policy", "Provide the verified effective interval for this schedule.", "UNKNOWN")
    return override


def resolve_literal(expression, variables, link):
    def substitute(match):
        value = variables.get(match.group(1) or match.group(2))
        require(
            isinstance(value, str) and value and not value.startswith(("$", "/")),
            "variable_resolution", "A referenced variable needs a single literal selection.", "UNKNOWN",
        )
        return value

    result = VARIABLE.sub(substitute, expression)
    require("$" not in result, "variable_resolution", "Unsupported variable syntax.", "UNKNOWN")
    require(not result.startswith("/"), link, "Regex selectors are outside the single-item trace.", "UNKNOWN")
    return result


def backend_selector(expression, variables):
    if not VARIABLE.search(expression):
        return expression
    # The 6.10.2 plugin escapes variable values and anchors interpolated filters.
    def escape_variable(match):
        value = variables[match.group(1) or match.group(2)]
        return REGEX_SPECIAL.sub(lambda char: "\\" + char[0], value)

    escaped = VARIABLE.sub(escape_variable, expression)
    return f"/^{escaped}$/"


def resolve_panel(panel, variables, report):
    targets = [target for target in panel.get("targets", []) if not target.get("hide")]
    require(len(targets) == 1, "panel_model", "Expected exactly one visible target.", "UNKNOWN")
    target = targets[0].copy()
    require(
        target.get("mode", 0) == 0 and target.get("resultFormat", "time_series") == "time_series"
        and not target.get("functions") and not target.get("itemids")
        and target.get("options", {}).get("useTrends") not in (True, "true"),
        "panel_model", "Expected a numeric time-series target without query functions.", "UNKNOWN",
    )
    require(
        panel.get("type") == "stat" and not panel.get("transformations")
        and not panel.get("timeFrom") and not panel.get("timeShift")
        and panel.get("options", {}).get("textMode", "auto") in {"auto", "value"}
        and panel.get("options", {}).get("reduceOptions") == {
            "calcs": ["lastNotNull"], "fields": "", "values": False,
        },
        "panel_model", "Expected an untransformed lastNotNull stat with the trace time range.", "UNKNOWN",
    )

    selectors = {}
    report["resolved_selectors"] = selectors
    for name in SELECTORS:
        selector = target.get(name, {}).get("filter", "")
        link = f"{name}_selector"
        require(selector or name not in {"host", "item"}, link, f"Missing {name} selector.")
        selectors[name] = resolve_literal(selector, variables, link)
        if VARIABLE.search(selector):
            require(not REGEX_SPECIAL.search(VARIABLE.sub("", selector)), "variable_resolution",
                    "Interpolation with regex-significant static text is outside this trace.", "UNKNOWN")
        target[name] = {"filter": backend_selector(selector, variables)}

    require(
        not any(selectors[name] for name in SELECTORS[3:]),
        "panel_model", "Additional selector filters are outside this trace.", "UNKNOWN",
    )
    datasource = target.get("datasource") or panel.get("datasource") or {}
    require(isinstance(datasource, dict), "datasource", "Expected a datasource UID.")
    uid = resolve_literal(datasource.get("uid", ""), variables, "datasource")
    require(uid, "datasource", "Missing datasource UID.")
    report["grafana"]["datasource_uid"] = uid
    target["datasource"] = {"type": DATASOURCE_TYPE, "uid": uid}
    return target


def verify_frame(result, report):
    query = report["datasource_result"]
    query["status"] = result.get("status")
    require(not result.get("error") and query["status"] in (None, 200), "datasource_query", "Grafana rejected the query.")
    frames = result.get("frames", [])
    query["frame_count"] = len(frames)
    require(len(frames) == 1, "datasource_query", "Expected one returned series.")
    frame = frames[0]
    fields = frame.get("schema", {}).get("fields", [])
    columns = frame.get("data", {}).get("values", [])
    require(
        len(fields) == len(columns) == 2 and {field.get("type") for field in fields} == {"time", "number"},
        "datasource_query", "Expected one timestamp field and one numeric value field.",
    )
    time_index = next(i for i, field in enumerate(fields) if field["type"] == "time")
    times, values = columns[time_index], columns[1 - time_index]
    require(len(times) == len(values), "datasource_query", "Time and value fields have different lengths.")
    samples = [(stamp, value) for stamp, value in zip(times, values) if value is not None]
    require(
        samples and all(isinstance(stamp, int) and type(value) in (int, float)
                        and math.isfinite(value) for stamp, value in samples),
        "datasource_query", "No usable numeric time series was returned.",
    )
    require(
        all(left[0] < right[0] for left, right in zip(samples, samples[1:])),
        "datasource_query", "Sample timestamps are unordered or ambiguous.",
    )
    field = fields[1 - time_index]
    labels = field.get("labels", {})
    custom = field.get("config", {}).get("custom", {})
    host_id = custom.get("scopedVars", {}).get("__zbx_host_id", {}).get("value")
    item = report["zabbix_item"]
    stamp, value = samples[-1]
    query.update({"timestamp_ms": stamp, "value": value, "unit": custom.get("units")})
    require(
        str(host_id) == report["zabbix_host"]["hostid"] and labels.get("item_key") == item["key_"],
        "series_identity", "Returned series lacks the expected host ID and item key.",
    )
    expected_value = item["sample_value"]
    value_matches = value == expected_value if item["value_type"] == "3" else math.isclose(
        value, expected_value, rel_tol=1e-12, abs_tol=0,
    )
    require(
        stamp // 1000 == int(item["lastclock"]) and value_matches,
        "panel_measurement", "Latest datasource timestamp or value differs from the Zabbix snapshot.",
    )
    require(query["unit"] == item["units"], "panel_unit", "Datasource unit differs from the Zabbix unit.")
    return value, field


def verify_panel_unit(panel, field, expected):
    config = panel.get("fieldConfig", {})
    unit = config.get("defaults", {}).get("unit", "")
    require(
        not config.get("defaults", {}).get("mappings") and not field.get("config", {}).get("mappings"),
        "panel_model", "Value mappings are outside the supported stat.", "UNKNOWN",
    )
    for override in config.get("overrides", []):
        matcher = override.get("matcher", {})
        require(matcher.get("id") == "byName", "panel_model", "Unsupported field override matcher.", "UNKNOWN")
        if matcher.get("options") in {field.get("name"), field.get("config", {}).get("displayNameFromDS")}:
            for prop in override.get("properties", []):
                require(prop.get("id") == "unit", "panel_model", "Unsupported matching field override.", "UNKNOWN")
                unit = prop.get("value")
    require(
        unit == expected or (not expected and unit in {"", "none"}),
        "panel_unit", "Effective stat unit differs from the source unit.",
    )
    return unit


def trace(zabbix, grafana, *, host_id, technical_host, item_key, dashboard_uid, panel_id,
          now, variable_overrides=None, interval_override=None, fixture_target=False):
    report = {
        "environment": "local-development",
        "provenance": "lab-simulation" if fixture_target else "physical provenance unverified",
        "observation_timestamp": utc(now),
        "zabbix_host": {"hostid": host_id, "host": technical_host},
        "zabbix_item": {"key_": item_key},
        "grafana": {"dashboard_uid": dashboard_uid, "panel_id": panel_id, "datasource_uid": None},
        "freshness": None,
        "resolved_selectors": None,
        "datasource_result": None,
        "panel_result": None,
        "first_broken_link": None,
        "evidence_classification": "VERIFIED",
        "limitations": ["The stat is evaluated from the authenticated query and saved model. Browser rendering is unverified."],
    }
    try:
        hosts = read("zabbix_host_access", zabbix, "host.get", {
            "hostids": [host_id], "output": ["hostid", "host", "name", "status"],
            "selectHostGroups": ["name"],
        })
        require(
            len(hosts) == 1 and hosts[0]["hostid"] == host_id and hosts[0]["host"] == technical_host,
            "zabbix_host", "Host ID and technical name did not identify the same host.",
        )
        host = hosts[0]
        report["zabbix_host"].update({key: host[key] for key in ("name", "status")})
        require(host["status"] == "0", "zabbix_host", "Host is disabled.")
        items = read("zabbix_item_access", zabbix, "item.get", {
            "hostids": [host_id], "filter": {"key_": item_key},
            "output": ["itemid", "key_", "name", "value_type", "units", "status", "state",
                       "error", "lastvalue", "lastclock", "delay"],
        })
        require(len(items) == 1 and items[0]["key_"] == item_key, "zabbix_item", "Item key is missing or ambiguous.")
        item = {key: items[0][key] for key in ("itemid", "key_", "name", "value_type", "units",
                                                "status", "state", "lastclock", "delay")}
        # Device/API error text can include credentials or sensitive endpoint details.
        item["collection_error"] = "present (redacted)" if items[0].get("error") else None
        clock = int(item["lastclock"])
        sample = items[0].get("lastvalue") if clock else None
        item.update({"sample_value": None, "sample_timestamp": utc(clock) if clock else None})
        report["zabbix_item"] = item
        if clock and item["value_type"] in {"0", "3"} and sample is not None:
            try:
                value = int(sample) if item["value_type"] == "3" else float(sample)
                if math.isfinite(value):
                    item["sample_value"] = value
            except (ValueError, TypeError, OverflowError):
                pass
        require(item["status"] == "0", "item_disabled", "Item is disabled.")
        require(item["state"] == "0", "item_unsupported", "Item is unsupported; this does not establish device health.")
        require(clock > 0, "sample_never_collected", "No last sample timestamp.")
        require(item["sample_value"] is not None, "sample_invalid", "Expected a finite numeric sample.")
        # A standard interval is authoritative. Overrides are for schedules this tool cannot resolve.
        interval = collection_interval(item["delay"], interval_override)
        max_age = max(900, 3 * interval)
        report["freshness"] = {"interval_seconds": interval, "max_age_seconds": max_age, "age_seconds": now - clock}
        require(clock <= now, "sample_clock_skew", "Zabbix timestamp is ahead of the observation time.")
        require(now - clock <= max_age, "sample_stale", "Sample is older than the freshness policy allows.")

        dashboard = read("dashboard_access", grafana, f"/api/dashboards/uid/{quote(dashboard_uid, safe='')}")["dashboard"]
        require(dashboard.get("uid") == dashboard_uid, "dashboard", "Returned dashboard UID differs.")
        panels = [panel for panel in dashboard.get("panels", []) if panel.get("id") == panel_id]
        require(len(panels) == 1, "panel", "Expected one top-level panel with the supplied ID.")
        panel = panels[0]
        variables = {
            entry["name"]: entry.get("current", {}).get("value")
            for entry in dashboard.get("templating", {}).get("list", [])
            if not entry.get("multi") and not entry.get("includeAll")
        }
        overrides = variable_overrides or {}
        require(overrides.keys() <= variables.keys(), "variable_resolution", "Override is unknown or is not scalar.", "UNKNOWN")
        target = resolve_panel(panel, variables | overrides, report)
        selectors = report["resolved_selectors"]
        require(selectors["host"] == host["name"], "host_selector", "Grafana-Zabbix matches the visible host name; selector differs.")
        require(selectors["item"] == item["name"], "item_selector", "Selector differs from the intended item name.")
        require(
            not selectors["group"] or selectors["group"] in {group["name"] for group in host["hostgroups"]},
            "group_selector", "Selected group excludes the intended host.",
        )
        uid = target["datasource"]["uid"]
        datasource = read("datasource", grafana, f"/api/datasources/uid/{quote(uid, safe='')}")
        require(
            datasource.get("uid") == uid and datasource.get("type") == DATASOURCE_TYPE
            and datasource.get("access") == "proxy"
            and datasource.get("url") == "http://zabbix-web:8080/api_jsonrpc.php"
            and not datasource.get("jsonData", {}).get("dbConnectionEnable"),
            "datasource", "Datasource UID, plugin, endpoint, or access mode differs from the local provisioning.",
        )
        report["grafana"]["datasource_type"] = datasource["type"]
        report["grafana"]["query_filters"] = {name: target[name]["filter"] for name in SELECTORS}
        report["datasource_result"] = {}
        # End in the snapshot second so a subsequent collection does not race this comparison.
        payload = {
            "from": str(max(0, clock - 900) * 1000),
            "to": str(clock * 1000 + 999),
            "queries": [{**target, "maxDataPoints": 10000, "intervalMs": 1000}],
        }
        response = read("datasource_query", grafana, "/api/ds/query", payload)
        value, field = verify_frame(response.get("results", {}).get(target["refId"], {}), report)
        unit = verify_panel_unit(panel, field, item["units"])
        report["panel_result"] = {"value": value, "unit": unit, "verification": "stat model and datasource", "rendered": False}
    except TraceStop as stop:
        report["first_broken_link"] = {"stage": stop.link, "reason": str(stop)}
        report["evidence_classification"] = stop.classification
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        report["first_broken_link"] = {"stage": "response_schema", "reason": "Unexpected model or response shape."}
        report["evidence_classification"] = "UNKNOWN"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--technical-host", required=True)
    parser.add_argument("--item-key", required=True)
    parser.add_argument("--dashboard-uid", required=True)
    parser.add_argument("--panel-id", type=int, required=True)
    parser.add_argument("--variable", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--effective-interval", type=int, metavar="SECONDS")
    args = parser.parse_args()
    if args.effective_interval is not None and args.effective_interval <= 0:
        parser.error("--effective-interval must be positive")
    variables = {}
    for assignment in args.variable:
        name, separator, value = assignment.partition("=")
        if not separator or not name or not value or name in variables:
            parser.error("Each variable must have one unique NAME=VALUE assignment")
        variables[name] = value

    def zabbix(method, params):
        return zabbix_read(os.environ["ZBX_API_TOKEN"], method, params)

    def grafana(path, payload=None):
        return local_json(3001, os.environ["GRAFANA_API_TOKEN"], path, payload)

    report = trace(
        zabbix, grafana, host_id=args.host_id, technical_host=args.technical_host,
        item_key=args.item_key, dashboard_uid=args.dashboard_uid, panel_id=args.panel_id,
        now=int(datetime.now(timezone.utc).timestamp()), variable_overrides=variables,
        interval_override=args.effective_interval, fixture_target=args.technical_host == "mock-core-switch-01",
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["first_broken_link"] is not None)


if __name__ == "__main__":
    sys.exit(main())
