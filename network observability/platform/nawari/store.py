"""Transactional evidence storage. SQLite is isolated development, PostgreSQL is server storage."""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from . import contracts, identity


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Database:
    def __init__(self, location):
        self.location = location
        self.postgres = location.startswith(("postgresql://", "postgres://"))

    @contextlib.contextmanager
    def transaction(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(self.location, row_factory=dict_row, connect_timeout=5)
            connection.execute("SET synchronous_commit TO on")
        else:
            location = Path(self.location)
            location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not location.exists():
                descriptor = os.open(location, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            connection = sqlite3.connect(location, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
        try:
            yield Session(connection, self.postgres)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self):
        with self.transaction() as session:
            if self.postgres:
                session.execute("SELECT pg_advisory_xact_lock(714202611)")
            for migration in sorted((Path(__file__).parent / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
                for statement in migration.read_text().split(";"):
                    if statement.strip():
                        session.execute(statement)
            if self.postgres:
                columns = {row["column_name"] for row in session.all("SELECT column_name FROM information_schema.columns WHERE table_name='evidence'")}
            else:
                columns = {row["name"] for row in session.all("PRAGMA table_info(evidence)")}
            # The earliest local fixture schema predates the trusted receipt and
            # retention-basis fields. Upgrade it without depending on column order.
            if "first_trusted_received_at" not in columns:
                session.execute("ALTER TABLE evidence ADD COLUMN first_trusted_received_at DOUBLE PRECISION NOT NULL DEFAULT 0")
                session.execute("UPDATE evidence SET first_trusted_received_at=received_at WHERE first_trusted_received_at=0")
            if "retention_basis_at" not in columns:
                session.execute("ALTER TABLE evidence ADD COLUMN retention_basis_at DOUBLE PRECISION NOT NULL DEFAULT 0")
                session.execute("UPDATE evidence SET retention_basis_at=received_at WHERE retention_basis_at=0")


class Session:
    def __init__(self, connection, postgres):
        self.connection = connection
        self.postgres = postgres

    def execute(self, sql, parameters=()):
        return self.connection.execute(sql.replace("?", "%s") if self.postgres else sql, parameters)

    def one(self, sql, parameters=()):
        row = self.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql, parameters=()):
        return [dict(row) for row in self.execute(sql, parameters).fetchall()]


class Store:
    def __init__(self, location, clock=time.time, migrate=True):
        self.db = Database(location)
        self.clock = clock
        self.reconciler = identity.EndpointReconciler()
        if migrate:
            self.db.migrate()

    def provision(self, tenant, enrollment, producer, point, asset, site, routing_domain, token, kind="endpoint"):
        for value in (tenant, enrollment, producer, point, asset, site, routing_domain):
            contracts.identifier(value)
        if len(token) < 32:
            raise ValueError("credential_too_short")
        now = self.clock()
        with self.db.transaction() as s:
            s.execute("INSERT INTO assets VALUES (?,?,?,?,?) ON CONFLICT (tenant,asset_id) DO NOTHING",
                      (tenant, asset, asset, site, routing_domain))
            s.execute("INSERT INTO enrollments VALUES (?,?,?,?,?,?,?,?,NULL)",
                      (tenant, enrollment, digest(token), producer, point, kind, now - 86400, now + 90 * 86400))
            s.execute("INSERT INTO identity_mappings VALUES (?,?,?,?,?)",
                      (tenant, enrollment, asset, now - 86400, now + 90 * 86400))

    def operator(self, token, tenant):
        if len(token) < 32:
            raise ValueError("credential_too_short")
        with self.db.transaction() as s:
            s.execute("INSERT INTO operators VALUES (?,?,?, ?, NULL)",
                      (digest(token), tenant, "reader", self.clock() + 86400))

    def revoke(self, tenant, enrollment):
        with self.db.transaction() as s:
            s.execute("UPDATE enrollments SET revoked_at=? WHERE tenant=? AND enrollment_id=?",
                      (self.clock(), tenant, enrollment))

    def authenticate(self, token, operator=False):
        now = self.clock()
        with self.db.transaction() as s:
            if operator:
                return s.one("SELECT tenant,role FROM operators WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
                             (digest(token), now))
            return s.one("SELECT * FROM enrollments WHERE token_hash=? AND revoked_at IS NULL AND valid_from<=? AND valid_until>?",
                         (digest(token), now, now))

    def put_operation(self, tenant, definition):
        contracts.operation(definition)
        with self.db.transaction() as s:
            s.execute("INSERT INTO operations VALUES (?,?,?,?) ON CONFLICT (tenant,service_id,operation_id) DO UPDATE SET definition=excluded.definition",
                      (tenant, definition["service_id"], definition["operation_id"], canonical(definition)))

    def refresh_metric_catalogue(self, tenant, asset, adapter):
        contracts.identifier(tenant)
        contracts.identifier(asset)
        node, metrics = adapter.discover(self.clock())
        capabilities = canonical(node["capabilities"])
        with self.db.transaction() as s:
            if s.one("SELECT 1 AS present FROM assets WHERE tenant=? AND asset_id=?", (tenant, asset)) is None:
                raise ValueError("unknown_asset")
            s.execute("INSERT INTO netdata_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (tenant,asset_id,node_guid) DO UPDATE SET node_name=excluded.node_name,agent_version=excluded.agent_version,os_name=excluded.os_name,api_generation=excluded.api_generation,last_seen=excluded.last_seen,status=excluded.status,capabilities=excluded.capabilities",
                      (tenant, asset, node["node_guid"], node["node_name"], node["agent_version"], node["os_name"], node["api_generation"], node["discovered_at"], node["last_seen"], node["status"], capabilities))
            s.execute("UPDATE metric_catalogue SET availability='historical',collection_outcome='not_observed' WHERE tenant=? AND asset_id=?", (tenant, asset))
            for metric in metrics:
                values = (tenant, asset, node["node_guid"], *(metric[key] for key in (
                    "metric_id", "context_id", "chart_id", "dimension_id", "display_name", "description", "units", "semantics",
                    "plugin", "module", "update_every", "first_seen", "last_observed", "collection_outcome", "timestamp_quality",
                    "availability", "retention_start", "retention_end", "source_api", "section", "catalogue_version")))
                s.execute("INSERT INTO metric_catalogue VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (tenant,asset_id,metric_id) DO UPDATE SET display_name=excluded.display_name,description=excluded.description,units=excluded.units,plugin=excluded.plugin,module=excluded.module,update_every=excluded.update_every,last_observed=excluded.last_observed,collection_outcome=excluded.collection_outcome,timestamp_quality=excluded.timestamp_quality,availability=excluded.availability,retention_start=excluded.retention_start,retention_end=excluded.retention_end,source_api=excluded.source_api,section=excluded.section,catalogue_version=excluded.catalogue_version", values)
        return {"node": node, "metrics": len(metrics)}

    def metrics(self, tenant, asset, search=None, section=None, limit=100, offset=0):
        contracts.identifier(asset)
        if section not in {None, "system", "applications", "network", "services", "other", "all"}:
            raise ValueError("invalid_metric_section")
        if search is not None and (not isinstance(search, str) or len(search) > 100):
            raise ValueError("invalid_metric_search")
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("invalid_metric_page")
        filters, params = "tenant=? AND asset_id=?", [tenant, asset]
        if section and section != "all":
            filters += " AND section=?"
            params.append(section)
        if search:
            filters += " AND (LOWER(context_id) LIKE ? OR LOWER(chart_id) LIKE ? OR LOWER(dimension_id) LIKE ? OR LOWER(display_name) LIKE ?)"
            pattern = "%" + search.lower().replace("%", "") + "%"
            params.extend([pattern] * 4)
        with self.db.transaction() as s:
            rows = s.all(f"SELECT * FROM metric_catalogue WHERE {filters} ORDER BY section,context_id,chart_id,dimension_id LIMIT ? OFFSET ?", (*params, limit + 1, offset))
            node = s.one("SELECT * FROM netdata_nodes WHERE tenant=? AND asset_id=? ORDER BY last_seen DESC LIMIT 1", (tenant, asset))
            total = s.one(f"SELECT COUNT(*) AS count FROM metric_catalogue WHERE {filters}", tuple(params))["count"]
            counts = s.all("SELECT section,availability,COUNT(*) AS count FROM metric_catalogue WHERE tenant=? AND asset_id=? GROUP BY section,availability ORDER BY section,availability", (tenant, asset))
        if node:
            node["capabilities"] = json.loads(node["capabilities"])
        return {"schema_version": "1", "asset_id": asset, "node": node, "metrics": rows[:limit], "section_counts": counts, "total": total,
                "partial": len(rows) > limit, "next_offset": offset + limit if len(rows) > limit else None}

    def metric(self, tenant, asset, identifier):
        contracts.identifier(asset)
        contracts.identifier(identifier)
        with self.db.transaction() as s:
            return s.one("SELECT * FROM metric_catalogue WHERE tenant=? AND asset_id=? AND metric_id=?", (tenant, asset, identifier))

    def ingest(self, token, record):
        try:
            contracts.validate(record)
            encoded = canonical(record)
            if len(encoded.encode()) > 32768:
                raise ValueError("record_too_large")
        except (ValueError, TypeError, AttributeError):
            return {"record_id": record.get("record_id") if isinstance(record, dict) else None, "status": "invalid"}
        now = self.clock()
        with self.db.transaction() as s:
            suffix = " FOR UPDATE" if s.postgres else ""
            auth = s.one("SELECT * FROM enrollments WHERE token_hash=?" + suffix, (digest(token),))
            if (not auth or auth["revoked_at"] is not None or not auth["valid_from"] <= now < auth["valid_until"]
                    or any(record[k] != auth[k] for k in ("enrollment_id", "producer_id", "observation_point_id"))):
                return {"record_id": record["record_id"], "status": "unauthorized"}
            key = (auth["tenant"], auth["enrollment_id"], auth["producer_id"], record["record_id"])
            previous = s.one("SELECT content_hash,expires_at,state FROM evidence WHERE tenant=? AND enrollment_id=? AND producer_id=? AND record_id=?", key)
            if previous:
                status = "conflict" if previous["content_hash"] != digest(encoded) else "duplicate"
                return {"record_id": record["record_id"], "status": status, "expires_at": previous["expires_at"], "delivery_state": previous["state"]}
            try:
                observed, retention_basis, expiry, quality = contracts.retention(record, now)
            except (ValueError, TypeError, OverflowError):
                return {"record_id": record["record_id"], "status": "invalid"}
            if expiry <= now:
                return {"record_id": record["record_id"], "status": "expired"}
            mapping = s.all("SELECT asset_id FROM identity_mappings WHERE tenant=? AND enrollment_id=? AND valid_from<=? AND valid_until>?",
                            (auth["tenant"], auth["enrollment_id"], observed, observed))
            if len(mapping) != 1:
                return {"record_id": record["record_id"], "status": "invalid"}
            asset = mapping[0]["asset_id"]
            if record.get("asset_id", asset) != asset:
                return {"record_id": record["record_id"], "status": "unauthorized"}
            if record["payload_type"] == "service_test":
                op = s.one("SELECT definition FROM operations WHERE tenant=? AND service_id=? AND operation_id=?",
                           (auth["tenant"], record["service_id"], record["operation_id"]))
                if op is None:
                    return {"record_id": record["record_id"], "status": "invalid"}
                operation = json.loads(op["definition"])
                if (operation["config_version"] != record["config_version"]
                        or operation["interval_ms"] != record["collection_interval_ms"]
                        or operation["execution_context"] != record["execution_context"]):
                    return {"record_id": record["record_id"], "status": "invalid"}
            destination = "loki" if record["payload_type"] == "selected_event" else "investigation"
            s.execute("INSERT INTO evidence (tenant,enrollment_id,producer_id,record_id,content_hash,payload_type,asset_id,service_id,observed_at,received_at,first_trusted_received_at,timestamp_quality,retention_basis_at,expires_at,dedup_until,body,state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (*key, digest(encoded), record["payload_type"], asset, record.get("service_id"), observed,
                       now, now, quality, retention_basis, expiry, expiry + 86400, encoded, "pending"))
            s.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,0,?,0)", (*key, destination, "pending", now))
        return {"record_id": record["record_id"], "status": "accepted", "expires_at": expiry, "delivery_state": "pending"}

    def purge(self):
        now = self.clock()
        with self.db.transaction() as s:
            expired = s.execute("UPDATE evidence SET body=NULL,state='expired' WHERE expires_at<=? AND body IS NOT NULL", (now,)).rowcount
            s.execute("UPDATE outbox SET state='expired' WHERE EXISTS (SELECT 1 FROM evidence e WHERE e.tenant=outbox.tenant AND e.enrollment_id=outbox.enrollment_id AND e.producer_id=outbox.producer_id AND e.record_id=outbox.record_id AND e.expires_at<=?)", (now,))
            s.execute("DELETE FROM evidence WHERE dedup_until<=?", (now,))
            s.execute("DELETE FROM incidents WHERE evidence_until<=?", (now,))
        return {"payloads_purged": expired, "checked_at": now, "physical_erasure_verified": False}

    def process_one(self, sink=None):
        self.purge()
        now = self.clock()
        with self.db.transaction() as s:
            suffix = " FOR UPDATE OF o SKIP LOCKED" if s.postgres else ""
            item = s.one("SELECT e.*,o.destination,o.attempts FROM outbox o JOIN evidence e ON e.tenant=o.tenant AND e.enrollment_id=o.enrollment_id AND e.producer_id=o.producer_id AND e.record_id=o.record_id WHERE o.state IN ('pending','processing') AND o.next_attempt<=? AND o.lease_until<=? AND e.expires_at>? ORDER BY e.received_at LIMIT 1" + suffix, (now, now, now))
            if not item:
                return False
            key = tuple(item[k] for k in ("tenant", "enrollment_id", "producer_id", "record_id"))
            s.execute("UPDATE outbox SET state='processing',lease_until=?,attempts=attempts+1 WHERE tenant=? AND enrollment_id=? AND producer_id=? AND record_id=?", (now + 30, *key))
        try:
            if item["destination"] == "loki":
                if sink is None:
                    raise OSError("loki_unconfigured")
                sink(item)
            with self.db.transaction() as s:
                if item["expires_at"] <= self.clock():
                    return True
                s.execute("UPDATE evidence SET state='delivered' WHERE tenant=? AND enrollment_id=? AND producer_id=? AND record_id=? AND expires_at>?", (*key, self.clock()))
                s.execute("UPDATE outbox SET state='delivered',lease_until=0 WHERE tenant=? AND enrollment_id=? AND producer_id=? AND record_id=?", key)
                self._correlate(s, item)
        except (OSError, ValueError):
            delay = min(300, 2 ** min(item["attempts"] + 1, 8))
            with self.db.transaction() as s:
                s.execute("UPDATE outbox SET state='pending',lease_until=0,next_attempt=? WHERE tenant=? AND enrollment_id=? AND producer_id=? AND record_id=?", (self.clock() + delay, *key))
        return True

    def _correlate(self, s, item):
        if item["payload_type"] != "service_test" or item["timestamp_quality"] != "validated":
            return
        body = json.loads(item["body"])
        if body["collection_outcome"] != "complete":
            return
        op = s.one("SELECT definition FROM operations WHERE tenant=? AND service_id=? AND operation_id=?", (item["tenant"], item["service_id"], body["operation_id"]))
        objective = json.loads(op["definition"])["objective_ms"]
        result = body["payload"]["test_result"]
        total = body["payload"].get("total_ms")
        if result == "success" and (total is None or total <= objective):
            return
        if self.clock() - item["observed_at"] > body["collection_interval_ms"] / 500 + 30:
            return
        domain = {"dns_failure": "dns", "connectivity_failure": "connectivity", "tls_failure": "tls"}.get(result, "service_response")
        incident = digest(f"{item['tenant']}|{item['asset_id']}|{item['service_id']}|{domain}|{int(item['observed_at']//300)}")[:24]
        s.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,'shadow',1,?) ON CONFLICT (tenant,incident_id) DO UPDATE SET updated_at=excluded.updated_at,revision=incidents.revision+1,evidence_until=excluded.evidence_until",
                  (item["tenant"], incident, item["asset_id"], item["service_id"], item["observed_at"], item["observed_at"], domain, item["expires_at"]))

    def investigation(self, tenant, asset=None, service=None, start=None, end=None, limit=500, offset=0):
        now = self.clock()
        end = now if end is None else end
        start = end - 3600 if start is None else start
        if start >= end or end - start > 7 * 86400 or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid_query_window")
        filters = "tenant=? AND expires_at>? AND observed_at>=? AND observed_at<=?"
        params = [tenant, now, start, end]
        if asset:
            filters += " AND asset_id=?"
            params.append(contracts.identifier(asset))
        if service:
            # Retain time-valid device/path context alongside service results.
            filters += " AND (service_id=? OR service_id IS NULL)"
            params.append(contracts.identifier(service))
        with self.db.transaction() as s:
            rows = s.all(f"SELECT * FROM evidence WHERE {filters} ORDER BY observed_at DESC LIMIT ? OFFSET ?", (*params, limit + 1, offset))
            assets = s.all("SELECT * FROM assets WHERE tenant=? ORDER BY asset_id", (tenant,))
            operations = [json.loads(row["definition"]) for row in s.all("SELECT definition FROM operations WHERE tenant=? ORDER BY service_id,operation_id", (tenant,))]
            incidents = s.all("SELECT * FROM incidents WHERE tenant=? AND evidence_until>? AND opened_at<=? AND updated_at>=? ORDER BY updated_at DESC LIMIT 100", (tenant, now, end, start))
            sources = s.all("SELECT e.enrollment_id,e.observation_point_id,e.point_kind,m.asset_id,MAX(v.observed_at) AS last_observed_at,e.revoked_at FROM enrollments e JOIN identity_mappings m ON m.tenant=e.tenant AND m.enrollment_id=e.enrollment_id AND m.valid_from<=? AND m.valid_until>? LEFT JOIN evidence v ON v.tenant=e.tenant AND v.enrollment_id=e.enrollment_id AND v.expires_at>? WHERE e.tenant=? GROUP BY e.enrollment_id,e.observation_point_id,e.point_kind,m.asset_id,e.revoked_at", (now, now, now, tenant))
            queue = s.all("SELECT state,COUNT(*) AS count,MIN(next_attempt) AS oldest_due_at FROM outbox WHERE tenant=? GROUP BY state", (tenant,))
        partial = len(rows) > limit
        observations = []
        for row in rows[:limit]:
            if row["body"] is None:
                continue
            body = json.loads(row.pop("body"))
            row.pop("content_hash")
            row["record"] = body
            row["freshness"] = contracts.freshness(row, min(end, now))
            row["receipt_age_seconds"] = max(0, now - row["received_at"])
            observations.append(row)
        for source in sources:
            source["coverage"] = "unknown" if source["last_observed_at"] is None else ("fresh" if now - source["last_observed_at"] <= 150 else "stale")
        incidents = [x for x in incidents if (not asset or x["asset_id"] == asset) and (not service or x["service_id"] == service)]
        definitions = {(item["service_id"], item["operation_id"]): item for item in operations}
        latest = {}
        for item in observations:
            body = item["record"]
            if body["payload_type"] != "service_test" or item["freshness"] != "fresh":
                continue
            key = (item["asset_id"], item["service_id"], body["operation_id"])
            if key not in latest:
                latest[key] = item
        hypotheses = []
        for current_asset in {key[0] for key in latest}:
            values = [item for key, item in latest.items() if key[0] == current_asset]
            failed, healthy, unsupported = [], [], []
            for item in values:
                body, payload = item["record"], item["record"]["payload"]
                if body["collection_outcome"] != "complete":
                    unsupported.append(item)
                    continue
                objective = definitions.get((item["service_id"], body["operation_id"]), {}).get("objective_ms")
                degraded = payload.get("test_result") != "success" or (objective is not None and payload.get("total_ms") is not None and payload["total_ms"] > objective)
                (failed if degraded else healthy).append(item)
            if failed and healthy and len({item["service_id"] for item in failed}) == 1:
                hypotheses.append({"asset_id": current_asset, "classification": "service_specific_degradation_suspected",
                                   "confidence": "supported_not_confirmed", "evidence": [item["record_id"] for item in failed + healthy[:3]],
                                   "statement": f"{failed[0]['service_id']} is degraded while independent operations are healthy; investigate its destination path or service dependency."})
            dns = [item for item in failed if item["record"]["payload"].get("test_result") == "dns_failure"]
            if len({item["service_id"] for item in dns}) > 1:
                hypotheses.append({"asset_id": current_asset, "classification": "shared_dns_issue_suspected",
                                   "confidence": "supported_not_confirmed", "evidence": [item["record_id"] for item in dns],
                                   "statement": "DNS failures affect multiple services in a compatible window; shared resolver or access-path investigation is warranted."})
            if unsupported:
                hypotheses.append({"asset_id": current_asset, "classification": "diagnostic_coverage_gap",
                                   "confidence": "observed", "evidence": [item["record_id"] for item in unsupported],
                                   "statement": "One or more operations have unsupported evidence; healthy HTTPS checks do not cover those application or media symptoms."})
        return {"schema_version": "1", "mode": "evidence", "generated_at": now, "requested_range": {"start": start, "end": end}, "effective_range": {"start": start, "end": min(end, now)}, "resolution": "individual_observations", "partial": partial, "next_offset": offset + limit if partial else None, "assets": assets, "operations": operations, "observations": observations, "incidents": incidents, "hypotheses": hypotheses, "sources": sources, "outbox": queue, "metric_catalogue": [{"id": "total_ms", "name": "HTTP operation duration", "unit": "ms", "type": "gauge", "aggregation": "individual samples or arithmetic mean with sample count", "definition": "Request start through bounded response body read. Redirects disabled. Fresh connection per run.", "source": "nawari.plugin"}], "integration_status": {"mimir": "pending_runtime_validation", "controller": "fixture_only", "ai": "pending", "paging": "shadow"}}

    def reconcile_endpoint(self, obs: identity.EndpointObservation):
        now = self.clock()
        with self.db.transaction() as s:
            return self.reconciler.reconcile(s, obs, now)

    def get_endpoint(self, tenant: str, endpoint_id: str):
        contracts.identifier(tenant)
        contracts.identifier(endpoint_id)
        with self.db.transaction() as s:
            reg = s.one("SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?", (tenant, endpoint_id))
            if not reg:
                return None
            mappings = s.all("SELECT * FROM endpoint_source_mappings WHERE tenant=? AND endpoint_id=?", (tenant, endpoint_id))
            network = s.all("SELECT * FROM endpoint_network_observations WHERE tenant=? AND endpoint_id=? ORDER BY observed_at DESC LIMIT 50", (tenant, endpoint_id))
            hostnames = s.all("SELECT * FROM endpoint_hostname_history WHERE tenant=? AND endpoint_id=? ORDER BY last_seen_at DESC", (tenant, endpoint_id))
            conflicts = s.all("SELECT * FROM endpoint_identity_conflicts WHERE tenant=? AND (claimed_endpoint_id=? OR existing_endpoint_id=?)", (tenant, endpoint_id, endpoint_id))
            reg["source_mappings"] = mappings
            reg["network_observations"] = network
            reg["hostname_history"] = hostnames
            reg["conflicts"] = conflicts
            return reg

    def list_endpoints(self, tenant: str, site_id: str = None, lifecycle_state: str = None, search: str = None, limit: int = 100, offset: int = 0):
        contracts.identifier(tenant)
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("invalid_page")
        filters = ["tenant=?"]
        params = [tenant]
        if site_id:
            filters.append("site_id=?")
            params.append(contracts.identifier(site_id))
        if lifecycle_state:
            filters.append("lifecycle_state=?")
            params.append(lifecycle_state)
        if search:
            filters.append("(LOWER(primary_hostname) LIKE ? OR LOWER(display_name) LIKE ? OR LOWER(endpoint_id) LIKE ?)")
            pat = f"%{search.lower().replace('%', '')}%"
            params.extend([pat, pat, pat])
        where_clause = " AND ".join(filters)
        with self.db.transaction() as s:
            rows = s.all(f"SELECT * FROM endpoint_registry WHERE {where_clause} ORDER BY last_seen_at DESC LIMIT ? OFFSET ?", (*params, limit + 1, offset))
            total = s.one(f"SELECT COUNT(*) AS count FROM endpoint_registry WHERE {where_clause}", tuple(params))["count"]
            by_lifecycle = s.all("SELECT lifecycle_state, COUNT(*) as count FROM endpoint_registry WHERE tenant=? GROUP BY lifecycle_state", (tenant,))
        partial = len(rows) > limit
        return {
            "tenant": tenant,
            "endpoints": rows[:limit],
            "total": total,
            "lifecycle_counts": {r["lifecycle_state"]: r["count"] for r in by_lifecycle},
            "partial": partial,
            "next_offset": offset + limit if partial else None,
        }

    def get_endpoint_conflicts(self, tenant: str, resolved: bool = False):
        contracts.identifier(tenant)
        clause = "resolved_at IS NOT NULL" if resolved else "resolved_at IS NULL"
        with self.db.transaction() as s:
            rows = s.all(f"SELECT * FROM endpoint_identity_conflicts WHERE tenant=? AND {clause} ORDER BY detected_at DESC", (tenant,))
            for r in rows:
                try:
                    r["details"] = json.loads(r["details"])
                except Exception:
                    pass
            return rows

    def resolve_conflict(self, tenant: str, conflict_id: str, resolution_action: str, actor_id: str):
        contracts.identifier(tenant)
        now = self.clock()
        with self.db.transaction() as s:
            res = s.execute("UPDATE endpoint_identity_conflicts SET resolved_at=?, resolution_action=? WHERE tenant=? AND conflict_id=? AND resolved_at IS NULL", (now, resolution_action, tenant, conflict_id))
            if res.rowcount == 0:
                raise ValueError("conflict_not_found_or_already_resolved")
            s.execute("INSERT INTO audit_records VALUES (?,?,?,?,?,?,?,?)", (tenant, f"aud-{now}", actor_id, "resolve_conflict", conflict_id, "success", now, json.dumps({"resolution": resolution_action})))

    def resolve_telemetry_instance(self, tenant: str, hostname: str = None, timestamp: float = None, node_guid: str = None):
        """Resolves Prometheus metric instance labels (hostname or node_guid) to canonical endpoint_id.

        Uses time-bounded historical windows to accurately associate telemetry with the device
        that owned the hostname at the time of the measurement, without metric label bloat.
        """
        contracts.identifier(tenant)
        if not hostname and not node_guid:
            return None
        if timestamp is None:
            timestamp = self.clock()

        with self.db.transaction() as s:
            # 1. Primary check: If node_guid is provided, map via source mappings
            if node_guid:
                mapping = s.one(
                    "SELECT endpoint_id FROM endpoint_source_mappings "
                    "WHERE tenant=? AND source_system='netdata_guid' AND source_identifier=? "
                    "AND valid_from <= ? AND valid_until >= ? "
                    "ORDER BY is_primary DESC, last_verified_at DESC LIMIT 1",
                    (tenant, node_guid, timestamp, timestamp),
                )
                if mapping:
                    return mapping["endpoint_id"]
                # Fallback to any active mapping for that GUID if outside tight validity window
                mapping_any = s.one(
                    "SELECT endpoint_id FROM endpoint_source_mappings "
                    "WHERE tenant=? AND source_system='netdata_guid' AND source_identifier=? "
                    "ORDER BY is_primary DESC, last_verified_at DESC LIMIT 1",
                    (tenant, node_guid),
                )
                if mapping_any:
                    return mapping_any["endpoint_id"]

            # 2. Time-bounded hostname check:
            # Find the endpoint that was observed with this hostname encompassing the timestamp.
            if hostname:
                hist = s.one(
                    "SELECT endpoint_id FROM endpoint_hostname_history "
                    "WHERE tenant=? AND hostname=? "
                    "AND first_seen_at <= ? AND last_seen_at >= ? "
                    "ORDER BY last_seen_at DESC LIMIT 1",
                    (tenant, hostname, timestamp, timestamp),
                )
                if hist:
                    return hist["endpoint_id"]

                # If timestamp is between or near observations, pick the closest window
                hist_closest = s.one(
                    "SELECT endpoint_id FROM endpoint_hostname_history "
                    "WHERE tenant=? AND hostname=? "
                    "ORDER BY ABS(last_seen_at - ?) ASC LIMIT 1",
                    (tenant, hostname, timestamp),
                )
                if hist_closest:
                    return hist_closest["endpoint_id"]

                # Fallback: Current primary_hostname in endpoint_registry
                reg = s.one(
                    "SELECT endpoint_id FROM endpoint_registry WHERE tenant=? AND primary_hostname=?",
                    (tenant, hostname),
                )
                if reg:
                    return reg["endpoint_id"]

        return None
