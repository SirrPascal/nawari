"""Bounded server-side adapter for the pinned Netdata Agent/Parent APIs."""

from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class NetdataError(RuntimeError):
    pass


def metric_id(node, chart, dimension):
    return hashlib.sha256(f"{node}|{chart}|{dimension}".encode()).hexdigest()[:24]


def section(context):
    prefix = context.split(".", 1)[0]
    if prefix in {"app", "apps", "user", "usergroup"}:
        return "applications"
    if prefix in {"net", "ipv4", "ipv6", "dns_query", "portcheck"}:
        return "network"
    if prefix in {"nawari", "httpcheck"}:
        return "services"
    if prefix in {"system", "mem", "disk", "disk_space", "powersupply", "macos", "nvme", "sensors"}:
        return "system"
    return "other"


class NetdataAdapter:
    def __init__(self, base_url, timeout=5, node_guid=None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"}:
            raise ValueError("invalid_netdata_url")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.node_guid = node_guid

    def _path(self, path, node_guid=None):
        node_guid = node_guid or self.node_guid
        if node_guid and path.startswith("/api/v1/"):
            return f"/host/{node_guid}{path}"
        return path

    def _json(self, path, limit=8 * 1024 * 1024, accept_error_body=False):
        request = Request(self.base_url + self._path(path), headers={"Accept": "application/json", "User-Agent": "Nawari-Netdata-Adapter/0.1"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise NetdataError(f"netdata_http_{response.status}")
                content = response.read(limit + 1)
        except HTTPError as error:
            if not accept_error_body:
                raise NetdataError(f"netdata_http_{error.code}") from error
            content = error.read(limit + 1)
        except (OSError, TimeoutError) as error:
            raise NetdataError("netdata_unavailable") from error
        if len(content) > limit:
            raise NetdataError("netdata_response_too_large")
        try:
            return json.loads(content)
        except (ValueError, UnicodeError) as error:
            raise NetdataError("netdata_invalid_json") from error

    def discover(self, now=None):
        now = time.time() if now is None else now
        if self.node_guid:
            charts = self._json("/api/v1/charts", 8 * 1024 * 1024)
            functions = self._json("/api/v1/functions", 512 * 1024).get("functions", {})
            normalized = []
            for chart_id, chart in sorted((charts.get("charts") or {}).items()):
                context_id = chart.get("context") or chart_id
                last = float(chart.get("last_entry") or 0)
                first = float(chart.get("first_entry") or last)
                update = max(1, int(chart.get("update_every") or 1))
                available = now - last <= max(30, update * 3)
                for dimension_id, dimension in sorted((chart.get("dimensions") or {}).items()):
                    normalized.append({
                        "metric_id": metric_id(self.node_guid, chart_id, dimension_id),
                        "context_id": context_id, "chart_id": chart_id, "dimension_id": dimension_id,
                        "display_name": dimension.get("name") or dimension_id,
                        "description": chart.get("title") or context_id,
                        "units": chart.get("units") or "unknown", "semantics": "netdata_dimension",
                        "plugin": chart.get("plugin") or (chart.get("chart_labels") or {}).get("_collect_plugin") or "unknown",
                        "module": chart.get("module") or (chart.get("chart_labels") or {}).get("_collect_module") or "unknown",
                        "update_every": update, "first_seen": first, "last_observed": last,
                        "collection_outcome": "complete" if available else "stale",
                        "timestamp_quality": "agent_reported",
                        "availability": "available" if available else "historical",
                        "retention_start": first, "retention_end": last,
                        "source_api": "parent_host_v1_charts", "section": section(context_id),
                        "catalogue_version": str(charts.get("version") or "unknown"),
                    })
            connection_function = "topology:network-connections" in functions
            return {
                "node_guid": self.node_guid,
                "node_name": charts.get("hostname") or "unknown",
                "agent_version": charts.get("version") or "unknown",
                "os_name": charts.get("os") or "unknown", "api_generation": 1,
                "discovered_at": now, "last_seen": max((m["last_observed"] for m in normalized), default=now),
                "status": "available",
                "capabilities": {
                    "network_connections": {"registered": connection_function, "access": "not_probed", "evidence": "function_preflight"},
                    "catalogue": {"contexts": len({m["context_id"] for m in normalized}), "charts": len(charts.get("charts") or {}), "dimensions": len(normalized)},
                },
            }, normalized
        info = self._json("/api/v3/info", 1024 * 1024)
        contexts = self._json("/api/v3/contexts", 4 * 1024 * 1024)
        # v2.12.3 exposes v3 context metadata but does not include chart and
        # dimension instances in that response. Use its compatibility endpoint
        # only to enrich the v3-authoritative context inventory.
        charts = self._json("/api/v1/charts", 8 * 1024 * 1024)
        functions = self._json("/api/v1/functions", 512 * 1024).get("functions", {})
        agent = (info.get("agents") or [{}])[0]
        application = agent.get("application") or {}
        package = application.get("package") or {}
        os_data = application.get("os") or {}
        node_guid = agent.get("mg") or (contexts.get("nodes") or [{}])[0].get("mg")
        if not isinstance(node_guid, str) or not node_guid:
            raise NetdataError("netdata_node_identity_missing")
        context_values = contexts.get("contexts") or {}
        catalogue_version = str((contexts.get("versions") or {}).get("contexts_hard_hash", "unknown"))
        normalized = []
        for chart_id, chart in sorted((charts.get("charts") or {}).items()):
            context_id = chart.get("context") or chart_id
            authoritative = context_values.get(context_id)
            if not authoritative:
                continue
            last = float(authoritative.get("last_entry") or chart.get("last_entry") or 0)
            first = float(authoritative.get("first_entry") or chart.get("first_entry") or last)
            update = max(1, int(chart.get("update_every") or 1))
            available = bool(authoritative.get("live")) and now - last <= max(30, update * 3)
            for dimension_id, dimension in sorted((chart.get("dimensions") or {}).items()):
                normalized.append({
                    "metric_id": metric_id(node_guid, chart_id, dimension_id),
                    "context_id": context_id,
                    "chart_id": chart_id,
                    "dimension_id": dimension_id,
                    "display_name": dimension.get("name") or dimension_id,
                    "description": chart.get("title") or context_id,
                    "units": chart.get("units") or authoritative.get("units") or "unknown",
                    "semantics": "netdata_dimension",
                    "plugin": chart.get("plugin") or (chart.get("chart_labels") or {}).get("_collect_plugin") or "unknown",
                    "module": chart.get("module") or (chart.get("chart_labels") or {}).get("_collect_module") or "unknown",
                    "update_every": update,
                    "first_seen": first,
                    "last_observed": last,
                    "collection_outcome": "complete" if available else "stale",
                    "timestamp_quality": "agent_reported",
                    "availability": "available" if available else "historical",
                    "retention_start": first,
                    "retention_end": last,
                    "source_api": "v3_contexts+v1_chart_enrichment",
                    "section": section(context_id),
                    "catalogue_version": catalogue_version,
                })
        connection_function = "topology:network-connections" in functions
        access = "not_registered"
        if connection_function:
            result = self._json("/api/v3/function?" + urlencode({"function": "topology:network-connections info"}), 512 * 1024, True)
            access = "available" if result.get("status", 200) == 200 else f"denied_{result.get('status', 'unknown')}"
        node = {
            "node_guid": node_guid,
            "node_name": agent.get("nm") or "unknown",
            "agent_version": package.get("version") or charts.get("version") or "unknown",
            "os_name": os_data.get("os") or charts.get("os") or "unknown",
            "api_generation": int(contexts.get("api") or 0),
            "discovered_at": now,
            "last_seen": float(agent.get("now") or now),
            "status": "available",
            "capabilities": {
                "network_connections": {"registered": connection_function, "access": access, "evidence": "function_preflight"},
                "catalogue": {"contexts": len(context_values), "charts": len(charts.get("charts") or {}), "dimensions": len(normalized)},
            },
        }
        return node, normalized

    def query(self, metric, start, end, points):
        if not 1 <= points <= 600 or start >= end or end - start > 7 * 86400:
            raise ValueError("invalid_metric_query")
        if metric["source_api"] == "parent_host_v1_charts":
            parameters = {
                "chart": metric["chart_id"], "dimensions": metric["dimension_id"],
                "after": int(start), "before": int(end), "points": points,
                "group": "average", "format": "json",
            }
            value = self._json_for_node("/api/v1/data?" + urlencode(parameters), metric["node_guid"], 2 * 1024 * 1024)
            labels = value.get("labels") or []
            if len(labels) < 2:
                raise NetdataError("metric_dimension_unavailable")
            samples = [{"time": row[0], "value": row[1]} for row in value.get("data") or []]
            return {"metric": metric, "samples": samples, "sample_count": len(samples),
                    "aggregation": "arithmetic_mean_per_time_bucket", "after": start, "before": end,
                    "retention_start": metric["retention_start"], "retention_end": metric["retention_end"],
                    "source_api": "parent_host_v1_data", "partial": False}
        parameters = {
            "contexts": metric["context_id"], "instances": metric["chart_id"], "dimensions": metric["dimension_id"],
            "after": int(start), "before": int(end), "points": points, "group_by": "dimension", "time_group": "average",
        }
        value = self._json("/api/v3/data?" + urlencode(parameters), 2 * 1024 * 1024)
        result = value.get("result") or {}
        labels = result.get("labels") or []
        if metric["dimension_id"] not in labels:
            raise NetdataError("metric_dimension_unavailable")
        index = labels.index(metric["dimension_id"])
        samples = []
        for row in result.get("data") or []:
            item = row[index]
            measured = item[0] if isinstance(item, list) else item
            samples.append({"time": row[0], "value": measured})
        view = value.get("view") or {}
        database = value.get("db") or {}
        return {
            "metric": metric,
            "samples": samples,
            "sample_count": len(samples),
            "aggregation": "arithmetic_mean_per_time_bucket",
            "after": view.get("after", start), "before": view.get("before", end),
            "retention_start": database.get("first_entry", metric["retention_start"]),
            "retention_end": database.get("last_entry", metric["retention_end"]),
            "source_api": "v3_data", "partial": False,
        }

    def _json_for_node(self, path, node_guid, limit):
        previous = self.node_guid
        try:
            self.node_guid = node_guid
            return self._json(path, limit)
        finally:
            self.node_guid = previous
