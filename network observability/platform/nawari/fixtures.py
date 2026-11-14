"""Labeled, isolated investigation data. No production service operations."""

import datetime as dt
import json
import os
from pathlib import Path
import secrets
import uuid


def iso(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def service(service_id="fixture-portal", operation_id="page", name="Fixture employee portal", path="healthy", objective=500):
    return {"service_id": service_id, "operation_id": operation_id, "name": name,
            "owner": "Local validation", "description": "Controlled loopback operation used only for isolated validation.",
            "proves": "The named HTTP operation completed with the configured result and timing.",
            "cannot_prove": "Employee authentication, application sessions, media quality and complete service health.",
            "url": f"http://127.0.0.1:18080/{path}", "method": "GET",
            "expected_statuses": [200], "config_version": "fixture-v1", "execution_context": "fixture",
            "applicable_sites": ["fixture-site"], "os_versions": ["fixture"], "network_contexts": ["loopback"],
            "comparison_point_id": "fixture-regional", "interval_ms": 15000, "jitter_ms": 1000,
            "timeout_ms": 3000, "concurrency": 1, "retry_limit": 0, "objective_ms": objective,
            "retention_seconds": 604800, "baseline_group": f"{service_id}-{operation_id}-loopback",
            "authentication_requirements": "None; controlled fixture only.",
            "network_dependencies": ["loopback"], "proxy_dependency": "not_applicable", "vpn_dependency": "not_applicable",
            "regional_comparison_profile": "fixture-regional", "data_policy": {"payloads": "none", "retention_seconds": 604800}}


def catalogue():
    return [
        service(),
        service("fixture-collaboration", "front-door", "Fixture collaboration front door"),
        service("fixture-collaboration", "auth-dependency", "Fixture authentication dependency"),
        service("fixture-collaboration", "media-coverage", "Fixture meeting/media coverage"),
        service("fixture-reference", "homepage", "Independent fixture reference"),
    ]


def record(now, enrollment="fixture-endpoint", result="success", total=12, kind="service_test",
           service_id="fixture-portal", operation_id="page", outcome="complete"):
    identifier = str(uuid.uuid4())
    value = {"schema_version": "1", "payload_type": kind, "record_id": identifier,
             "producer_id": "nawari-plugin", "enrollment_id": enrollment,
             "observation_point_id": enrollment, "observed_at": iso(now), "config_version": "fixture-v1",
             "collection_outcome": outcome, "origin": "controlled_fixture"}
    if kind == "service_test":
        value.update(service_id=service_id, operation_id=operation_id, run_id=identifier,
                     execution_context="fixture", collection_interval_ms=15000,
                     payload={"test_result": result, "total_ms": total if outcome == "complete" else None,
                              "phases": {"dns": {"state": "not_performed", "duration_ms": None}}})
    elif kind == "network_context":
        value["payload"] = {"context_kind": "fixture_network", "effective_from": iso(now - 1800),
                            "effective_until": iso(now + 1800), "interface": "loopback-fixture",
                            "gateway": "fixture-gateway", "vpn": "fixture-disconnected",
                            "execution_context": "fixture", "relationship_kind": "inferred"}
    elif kind == "path":
        value["payload"] = {"destination_id": "fixture-portal", "diagnostic_method": "fixture",
                            "hops": [{"node": "fixture-endpoint", "kind": "observed_l3"},
                                     {"node": "fixture-gateway", "kind": "inferred"},
                                     {"node": "fixture-portal", "kind": "observed_l3"}]}
    else:
        value["payload"] = {"source_kind": "controller_fixture", "source_record_id": identifier,
                            "event_class": "client_reassociated", "severity": "info", "parser_version": "fixture-v1"}
    return value


def private_file(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(value)


def seed(store, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(36)
    operator = secrets.token_urlsafe(36)
    for operation in catalogue():
        store.put_operation("fixture", operation)
    for enrollment, point_kind in [("fixture-endpoint", "endpoint"), ("fixture-regional", "regional"), ("fixture-silent", "endpoint")]:
        credential = token if enrollment == "fixture-endpoint" else secrets.token_urlsafe(36)
        store.provision("fixture", enrollment, "nawari-plugin", enrollment, enrollment, "fixture-site", "fixture-routing", credential, point_kind)
        if enrollment == "fixture-silent":
            continue
        for i in range(40):
            observed = store.clock() - (39 - i) * 15
            # Keep the controlled degradation in the final minute so correlation
            # can prove current behavior without accepting historical replay.
            delayed = 36 <= i <= 38 and point_kind == "endpoint"
            store.ingest(credential, record(observed, enrollment, total=1007 if delayed else 12 + i % 8))
        for kind in ("network_context", "path", "selected_event"):
            store.ingest(credential, record(store.clock() - 5, enrollment, kind=kind))
        # Operation-specific scenarios remain separate from the employee's
        # actual application traffic. The endpoint front door is slow while
        # the regional point and independent reference remain healthy.
        store.ingest(credential, record(store.clock() - 4, enrollment, total=1007 if point_kind == "endpoint" else 22,
                                        service_id="fixture-collaboration", operation_id="front-door"))
        store.ingest(credential, record(store.clock() - 3, enrollment, total=18,
                                        service_id="fixture-collaboration", operation_id="auth-dependency"))
        store.ingest(credential, record(store.clock() - 2, enrollment, result="unknown", total=None, outcome="unsupported",
                                        service_id="fixture-collaboration", operation_id="media-coverage"))
        store.ingest(credential, record(store.clock() - 1, enrollment, total=15,
                                        service_id="fixture-reference", operation_id="homepage"))
    store.operator(operator, "fixture")
    private_file(directory / "endpoint.token", token)
    private_file(directory / "operator.token", operator)
    config = {"enrollment_id": "fixture-endpoint", "producer_id": "nawari-plugin", "observation_point_id": "fixture-endpoint",
              "service_id": "fixture-portal", "operation_id": "page", "config_version": "fixture-v1", "execution_context": "fixture",
              "url": "http://127.0.0.1:18080/healthy", "intake": "http://127.0.0.1:18090/api/v1/evidence",
              "token_file": str((directory / "endpoint.token").resolve()), "queue_dir": str((directory / "queue").resolve()),
              "interval_ms": 15000, "jitter_ms": 1000, "timeout_ms": 3000, "expected_statuses": [200], "fixture": True}
    private_file(directory / "collector.json", json.dumps(config, indent=2))
    while store.process_one():
        # Unconfigured Loki items back off and remain visibly pending.
        pass
