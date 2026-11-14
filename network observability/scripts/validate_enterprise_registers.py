#!/usr/bin/env python3
"""Validate the versioned architecture registers without contacting source systems."""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")


def load(name):
    with (CONFIG / name).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != "1" or not value.get("register_version"):
        raise ValueError(f"{name}: invalid version")
    return value


def text(entry, fields, source):
    for field in fields:
        value = entry.get(field)
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError(f"{source}: invalid {field}")


def validate_ownership():
    data = load("source-ownership.v1.json")
    required = ("source", "measurement_family", "polling_owner", "alert_owner", "access_scope", "fallback")
    seen = set()
    for entry in data.get("entries", []):
        text(entry, required, "source ownership")
        key = (entry["source"], entry["measurement_family"])
        if key in seen:
            raise ValueError(f"duplicate ownership: {key}")
        seen.add(key)
        if not entry.get("identity_fields") or entry.get("retention_seconds", -1) < 0:
            raise ValueError(f"incomplete ownership: {key}")
    if not seen:
        raise ValueError("empty source ownership register")


def validate_alerts():
    data = load("alert-ownership.v1.json")
    if data.get("default_mode") != "shadow":
        raise ValueError("new Nawari alerts must default to shadow mode")
    required = ("condition", "source", "evaluation_owner", "notification_owner", "route",
                "maintenance_behavior", "deduplication_key", "escalation")
    conditions = set()
    for entry in data.get("entries", []):
        text(entry, required, "alert ownership")
        if entry["condition"] in conditions:
            raise ValueError(f"duplicate alert condition: {entry['condition']}")
        conditions.add(entry["condition"])


def validate_regions():
    data = load("regional-coverage.v1.json")
    for site in data.get("sites", []):
        if not ID.fullmatch(site.get("site_id", "")):
            raise ValueError("invalid site_id")
        queue = site.get("queue_policy", {})
        if not 1048576 <= queue.get("max_bytes", 0) <= 10737418240:
            raise ValueError("regional queue max_bytes outside bounded range")
        if not 60 <= queue.get("max_age_seconds", 0) <= 604800:
            raise ValueError("regional queue max_age_seconds outside bounded range")
        if "preserving_original_expiry" not in queue.get("wan_outage_behavior", ""):
            raise ValueError("regional replay must preserve original expiry")


def validate_integrations():
    data = load("integration-inventory.v1.json")
    for item in data.get("integrations", []):
        if not ID.fullmatch(item.get("id", "")) or item.get("direct_database_access") is not False:
            raise ValueError("integration must have a stable id and forbid direct database access")
        if item.get("status") not in {"verified", "partially_verified", "unsupported", "failed", "not_tested", "inventory_required"}:
            raise ValueError(f"invalid integration status: {item.get('id')}")


def validate_tls():
    data = load("tls-policy.v1.json")
    if data.get("minimum") != "TLSv1.2" or data.get("preferred") != "TLSv1.3":
        raise ValueError("TLS policy must prefer 1.3 with a 1.2 minimum")
    if set(data.get("disabled", [])) != {"SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"}:
        raise ValueError("obsolete transport protocols must be disabled")
    if data.get("certificate_verification") != "mandatory" or data.get("hostname_verification") != "mandatory":
        raise ValueError("certificate and hostname verification must be mandatory")
    if not data.get("boundaries"):
        raise ValueError("TLS policy requires connection boundaries")


def main():
    validate_ownership()
    validate_alerts()
    validate_regions()
    validate_integrations()
    validate_tls()
    print("enterprise registers: valid")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
