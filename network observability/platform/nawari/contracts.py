"""Signal validation and trusted retention decisions, independent of transport."""

import datetime as dt
import math
import re
from urllib.parse import urlsplit

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
OUTCOMES = {"complete", "partial", "unsupported", "permission_denied", "collection_error"}
RESULTS = {"success", "dns_failure", "connectivity_failure", "tls_failure", "timeout", "bad_status", "bad_content"}
SIGNALS = {"service_test", "network_context", "path", "selected_event"}
RETENTION = {"service_test": 7 * 86400, "network_context": 7 * 86400, "path": 7 * 86400, "selected_event": 6 * 86400}


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid_identifier")
    return value


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid_timestamp")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.timestamp()


def number(value, minimum=0, maximum=86400000):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("invalid_number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("number_out_of_range")
    return value


def operation(value):
    for field in ("service_id", "operation_id", "config_version"):
        identifier(value.get(field))
    for field in ("name", "owner", "comparison_point_id", "execution_context"):
        if not isinstance(value.get(field), str) or not 1 <= len(value[field]) <= 160:
            raise ValueError("missing_operation_field")
    target = urlsplit(value.get("url", ""))
    if target.scheme not in {"http", "https"} or not target.hostname or target.username or target.password or target.fragment:
        raise ValueError("invalid_operation_target")
    if value.get("method") not in {"GET", "HEAD"}:
        raise ValueError("unsafe_operation_method")
    for field in ("applicable_sites", "os_versions", "network_contexts"):
        if not isinstance(value.get(field), list) or not value[field]:
            raise ValueError("missing_operation_context")
    number(value.get("interval_ms"), 1000, 3600000)
    number(value.get("timeout_ms"), 100, 30000)
    number(value.get("jitter_ms"), 0, value["interval_ms"])
    number(value.get("objective_ms"), 1, 30000)
    if value.get("concurrency") != 1 or value.get("retry_limit") != 0:
        raise ValueError("slice_requires_single_request_without_retries")
    if value["timeout_ms"] > value["interval_ms"]:
        raise ValueError("timeout_exceeds_interval")
    statuses = value.get("expected_statuses")
    if not isinstance(statuses, list) or not statuses or any(type(x) is not int or not 100 <= x <= 599 for x in statuses):
        raise ValueError("invalid_expected_statuses")
    if value.get("retention_seconds") != RETENTION["service_test"]:
        raise ValueError("invalid_retention_policy")
    for field in ("description", "proves", "cannot_prove", "authentication_requirements", "regional_comparison_profile"):
        if field in value and (not isinstance(value[field], str) or not 1 <= len(value[field]) <= 500):
            raise ValueError("invalid_operation_coverage")
    if "baseline_group" in value:
        identifier(value["baseline_group"])
    if "network_dependencies" in value and (not isinstance(value["network_dependencies"], list)
                                               or len(value["network_dependencies"]) > 20
                                               or any(not isinstance(item, str) or len(item) > 120 for item in value["network_dependencies"])):
        raise ValueError("invalid_network_dependencies")
    if "data_policy" in value and (not isinstance(value["data_policy"], dict)
                                    or value["data_policy"].get("retention_seconds") != RETENTION["service_test"]):
        raise ValueError("invalid_operation_data_policy")
    return value


def validate(record):
    if not isinstance(record, dict) or record.get("schema_version") != "1":
        raise ValueError("unsupported_schema")
    for field in ("record_id", "producer_id", "enrollment_id", "observation_point_id", "config_version"):
        identifier(record.get(field))
    kind = record.get("payload_type")
    if kind not in SIGNALS or record.get("collection_outcome") not in OUTCOMES:
        raise ValueError("invalid_signal_or_outcome")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    if kind == "service_test":
        for field in ("service_id", "operation_id", "run_id"):
            identifier(record.get(field))
        if record.get("execution_context") not in {"system", "fixture"}:
            raise ValueError("unsupported_execution_context")
        number(record.get("collection_interval_ms"), 1000, 3600000)
        if payload.get("test_result") not in RESULTS | {"unknown"}:
            raise ValueError("invalid_test_result")
        if record["collection_outcome"] != "complete" and payload["test_result"] != "unknown":
            raise ValueError("incomplete_collection_cannot_assert_test_result")
        if payload.get("total_ms") is not None:
            number(payload["total_ms"])
        phases = payload.get("phases", {})
        if not isinstance(phases, dict) or set(phases) - {"dns", "connect", "tls", "ttfb"}:
            raise ValueError("invalid_phases")
        for phase in phases.values():
            if phase.get("state") not in {"performed", "not_performed", "failed"}:
                raise ValueError("invalid_phase_state")
            if phase["state"] == "not_performed" and phase.get("duration_ms") is not None:
                raise ValueError("unperformed_phase_has_duration")
            if phase["state"] == "performed":
                number(phase.get("duration_ms"))
    elif kind == "network_context":
        identifier(payload.get("context_kind"))
        timestamp(payload.get("effective_from"))
        timestamp(payload.get("effective_until"))
        if timestamp(payload["effective_until"]) <= timestamp(payload["effective_from"]):
            raise ValueError("invalid_context_interval")
    elif kind == "path":
        identifier(payload.get("destination_id"))
        identifier(payload.get("diagnostic_method"))
        hops = payload.get("hops")
        if not isinstance(hops, list) or len(hops) > 16:
            raise ValueError("invalid_path")
    else:
        identifier(payload.get("source_kind"))
        identifier(payload.get("source_record_id"))
        identifier(payload.get("event_class"))
        # Initial slice accepts an explicit event vocabulary, with no free-text logs.
        if set(payload) - {"source_kind", "source_record_id", "event_class", "severity", "parser_version"}:
            raise ValueError("unapproved_event_fields")
    return record


def retention(record, received):
    """Unknown occurrence age is rejected until a trusted replay proof is implemented."""
    observed = timestamp(record.get("observed_at"))
    if observed > received + 120:
        raise ValueError("untrusted_future_timestamp")
    basis = min(observed, received)
    expiry = basis + RETENTION[record["payload_type"]]
    if record.get("upstream_expires_at"):
        expiry = min(expiry, timestamp(record["upstream_expires_at"]))
    return observed, basis, expiry, "skewed" if observed > received else "validated"


def freshness(record, at):
    if record["timestamp_quality"] != "validated":
        return "unknown"
    body = record.get("record") or {}
    interval = body.get("collection_interval_ms")
    if interval is None:
        return "event"
    age = at - record["observed_at"]
    return "fresh" if 0 <= age <= interval / 500 + 30 else "stale"
