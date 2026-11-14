#!/usr/bin/env python3
"""Isolated PostgreSQL durability acceptance without printing credentials."""

import argparse
import copy
import json
from pathlib import Path
import time
from urllib.parse import quote

import psycopg

from nawari.fixtures import record, service
from nawari.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    password = args.password_file.read_text().strip()
    url = f"postgresql://nawari_validation:{quote(password, safe='')}@{args.host}:{args.port}/{args.database}"
    if args.legacy:
        with psycopg.connect(url, connect_timeout=5) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS evidence (tenant TEXT,enrollment_id TEXT,producer_id TEXT,record_id TEXT,content_hash TEXT,payload_type TEXT,asset_id TEXT,service_id TEXT,observed_at DOUBLE PRECISION,received_at DOUBLE PRECISION,timestamp_quality TEXT,expires_at DOUBLE PRECISION,dedup_until DOUBLE PRECISION,body TEXT,state TEXT,PRIMARY KEY(tenant,enrollment_id,producer_id,record_id))")
    now = time.time()
    token = "isolated-postgres-validation-token-000000"
    store = Store(url, lambda: now)
    store.provision("validation", "endpoint", "nawari-plugin", "endpoint", "laptop", "site", "routing", token)
    definition = service()
    store.put_operation("validation", definition)
    value = record(now, enrollment="endpoint")
    accepted = store.ingest(token, value)
    duplicate = store.ingest(token, value)
    conflict_value = copy.deepcopy(value)
    conflict_value["payload"]["total_ms"] = 999
    conflict = store.ingest(token, conflict_value)
    try:
        with store.db.transaction() as session:
            session.execute("UPDATE enrollments SET revoked_at=?", (now,))
            raise RuntimeError("before_commit_failure")
    except RuntimeError:
        pass
    restart = Store(url, lambda: now)
    authentication_survived = restart.authenticate(token) is not None
    restart.process_one()
    delivered = restart.investigation("validation")["observations"][0]["state"]
    with restart.db.transaction() as session:
        columns = {row["column_name"] for row in session.all("SELECT column_name FROM information_schema.columns WHERE table_name='evidence'")}
    result = {
        "schema": "legacy_upgrade" if args.legacy else "fresh_install",
        "accepted": accepted["status"], "duplicate": duplicate["status"], "conflict": conflict["status"],
        "rollback_preserved_authentication": authentication_survived, "delivery_state_after_restart": delivered,
        "trusted_receipt_columns": {"first_trusted_received_at", "retention_basis_at"}.issubset(columns),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
