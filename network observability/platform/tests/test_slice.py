import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from nawari.fixtures import record, service
from nawari.server import make_server
from nawari.store import Store

TOKEN = "fixture-endpoint-credential-32-characters"


class SliceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1794389000.0
        self.location = str(Path(self.temp.name) / "slice.db")
        self.store = Store(self.location, lambda: self.now)
        self.store.provision("fixture", "fixture-endpoint", "nawari-plugin", "fixture-endpoint", "laptop", "site", "vrf-a", TOKEN)
        self.store.put_operation("fixture", service())

    def test_durable_accept_duplicate_conflict_restart(self):
        value = record(self.now)
        self.assertEqual(self.store.ingest(TOKEN, value)["status"], "accepted")
        restarted = Store(self.location, lambda: self.now)
        self.assertEqual(restarted.ingest(TOKEN, value)["status"], "duplicate")
        changed = copy.deepcopy(value)
        changed["payload"]["total_ms"] = 200
        self.assertEqual(restarted.ingest(TOKEN, changed)["status"], "conflict")
        data = restarted.investigation("fixture")
        self.assertEqual(data["observations"][0]["record"]["payload"]["total_ms"], 12)
        self.assertEqual(data["outbox"][0]["state"], "pending")
        restarted.process_one()
        self.assertEqual(restarted.investigation("fixture")["observations"][0]["state"], "delivered")

    def test_transaction_rollback_is_not_acceptance(self):
        with self.assertRaises(RuntimeError):
            with self.store.db.transaction() as s:
                s.execute("UPDATE enrollments SET revoked_at=1")
                raise RuntimeError("simulated_crash")
        self.assertIsNotNone(self.store.authenticate(TOKEN))

    def test_legacy_evidence_schema_upgrades_without_column_order_dependency(self):
        location = str(Path(self.temp.name) / "legacy.db")
        connection = sqlite3.connect(location)
        connection.execute("CREATE TABLE evidence (tenant TEXT,enrollment_id TEXT,producer_id TEXT,record_id TEXT,content_hash TEXT,payload_type TEXT,asset_id TEXT,service_id TEXT,observed_at DOUBLE PRECISION,received_at DOUBLE PRECISION,timestamp_quality TEXT,expires_at DOUBLE PRECISION,dedup_until DOUBLE PRECISION,body TEXT,state TEXT,PRIMARY KEY(tenant,enrollment_id,producer_id,record_id))")
        connection.close()
        upgraded = Store(location, lambda: self.now)
        with upgraded.db.transaction() as session:
            columns = {row["name"] for row in session.all("PRAGMA table_info(evidence)")}
        self.assertIn("first_trusted_received_at", columns)
        self.assertIn("retention_basis_at", columns)

    def test_revocation_persists_and_asset_spoofing_rejected(self):
        spoof = record(self.now)
        spoof["asset_id"] = "somebody-else"
        self.assertEqual(self.store.ingest(TOKEN, spoof)["status"], "unauthorized")
        self.store.revoke("fixture", "fixture-endpoint")
        restarted = Store(self.location, lambda: self.now)
        self.assertIsNone(restarted.authenticate(TOKEN))
        self.assertEqual(restarted.ingest(TOKEN, record(self.now))["status"], "unauthorized")

    def test_tenant_query_and_overlapping_networks(self):
        self.store.ingest(TOKEN, record(self.now))
        self.store.provision("other", "other-device", "nawari-plugin", "other-device", "laptop", "other-site", "vrf-b", "o" * 36)
        self.assertEqual(self.store.investigation("other")["observations"], [])
        self.assertEqual(self.store.investigation("other")["assets"][0]["routing_domain_id"], "vrf-b")

    def test_expiry_retry_and_clock_policy(self):
        value = record(self.now)
        accepted = self.store.ingest(TOKEN, value)
        self.now += 60
        self.assertEqual(self.store.ingest(TOKEN, value)["expires_at"], accepted["expires_at"])
        future = record(self.now + 121)
        self.assertEqual(self.store.ingest(TOKEN, future)["status"], "invalid")
        invalid = record(self.now)
        invalid["observed_at"] = "invalid"
        self.assertEqual(self.store.ingest(TOKEN, invalid)["status"], "invalid")
        self.now = accepted["expires_at"] + 1
        self.assertEqual(self.store.purge()["payloads_purged"], 1)
        self.assertEqual(self.store.investigation("fixture")["observations"], [])
        with self.store.db.transaction() as s:
            self.assertIsNone(s.one("SELECT body FROM evidence")["body"])
        self.assertEqual(self.store.ingest(TOKEN, value)["expires_at"], accepted["expires_at"])

    def test_freshness_and_missing_endpoint(self):
        self.store.ingest(TOKEN, record(self.now))
        self.store.provision("fixture", "silent", "nawari-plugin", "silent", "silent", "site", "vrf-a", "s" * 36)
        data = self.store.investigation("fixture")
        self.assertEqual(data["observations"][0]["freshness"], "fresh")
        self.assertEqual(next(x for x in data["sources"] if x["enrollment_id"] == "silent")["coverage"], "unknown")
        self.now += 61
        self.assertEqual(self.store.investigation("fixture")["observations"][0]["freshness"], "stale")

    def test_permission_denial_cannot_be_service_success(self):
        value = record(self.now)
        value["collection_outcome"] = "permission_denied"
        self.assertEqual(self.store.ingest(TOKEN, value)["status"], "invalid")
        value["payload"]["test_result"] = "unknown"
        self.assertEqual(self.store.ingest(TOKEN, value)["status"], "accepted")
        self.store.process_one()
        self.assertEqual(self.store.investigation("fixture")["incidents"], [])

    def test_service_failure_is_shadow_and_late_replay_does_not_page(self):
        self.store.ingest(TOKEN, record(self.now, result="dns_failure", total=50))
        self.store.process_one()
        incident = self.store.investigation("fixture")["incidents"][0]
        self.assertEqual((incident["suspected_domain"], incident["state"]), ("dns", "shadow"))
        value = record(self.now - 600, result="bad_status")
        self.store.ingest(TOKEN, value)
        self.store.process_one()
        self.assertEqual(len(self.store.investigation("fixture")["incidents"]), 1)

    def test_partial_batch_and_http_authorization(self):
        self.store.operator("r" * 36, "fixture")
        server = make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(origin + "/api/v1/investigation")
        self.assertEqual(denied.exception.code, 401)
        request = urllib.request.Request(origin + "/api/v1/evidence", data=json.dumps([record(self.now), {}]).encode(), headers={"Authorization": "Bearer " + TOKEN})
        with urllib.request.urlopen(request) as response:
            self.assertEqual([x["status"] for x in json.load(response)["results"]], ["accepted", "invalid"])
        request = urllib.request.Request(origin + "/api/v1/investigation", headers={"Authorization": "Bearer " + "r" * 36})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(len(json.load(response)["observations"]), 1)

    def test_worker_lease_recovery_and_downstream_ambiguity(self):
        value = record(self.now, kind="selected_event")
        self.store.ingest(TOKEN, value)
        calls = []
        def fail_after_write(item):
            calls.append(item["record_id"])
            raise OSError("ambiguous_sink_write")
        self.store.process_one(fail_after_write)
        self.now += 10
        self.store.process_one(lambda item: calls.append(item["record_id"]))
        self.assertEqual(calls, [value["record_id"], value["record_id"]])
        self.assertEqual(self.store.investigation("fixture")["observations"][0]["state"], "delivered")

    def test_context_is_time_bounded_and_not_service_bound(self):
        value = record(self.now, kind="network_context")
        self.assertNotIn("service_id", value)
        self.assertEqual(self.store.ingest(TOKEN, value)["status"], "accepted")
        bad = copy.deepcopy(value)
        bad["record_id"] = "bad-context"
        bad["payload"]["effective_until"] = bad["payload"]["effective_from"]
        self.assertEqual(self.store.ingest(TOKEN, bad)["status"], "invalid")

    def test_dynamic_metric_catalogue_marks_disappearing_metrics_historical(self):
        class Adapter:
            metrics = [
                {"metric_id": "cpu-user", "context_id": "system.cpu", "chart_id": "system.cpu", "dimension_id": "user",
                 "display_name": "user", "description": "CPU", "units": "percentage", "semantics": "netdata_dimension",
                 "plugin": "macos.plugin", "module": "mach_smi", "update_every": 1, "first_seen": self.now - 100,
                 "last_observed": self.now, "collection_outcome": "complete", "timestamp_quality": "agent_reported",
                 "availability": "available", "retention_start": self.now - 100, "retention_end": self.now,
                 "source_api": "v3_contexts+v1_chart_enrichment", "section": "system", "catalogue_version": "1"},
                {"metric_id": "net-in", "context_id": "net.net", "chart_id": "net.en0", "dimension_id": "received",
                 "display_name": "received", "description": "Network", "units": "kilobits/s", "semantics": "netdata_dimension",
                 "plugin": "macos.plugin", "module": "sysctl", "update_every": 1, "first_seen": self.now - 100,
                 "last_observed": self.now, "collection_outcome": "complete", "timestamp_quality": "agent_reported",
                 "availability": "available", "retention_start": self.now - 100, "retention_end": self.now,
                 "source_api": "v3_contexts+v1_chart_enrichment", "section": "network", "catalogue_version": "1"},
            ]
            def discover(inner, now):
                return ({"node_guid": "node-1", "node_name": "Mac", "agent_version": "v2.12.3", "os_name": "macOS",
                         "api_generation": 2, "discovered_at": now, "last_seen": now, "status": "available",
                         "capabilities": {"network_connections": {"registered": True, "access": "denied_412"}}}, inner.metrics)
            def query(inner, metric, start, end, points):
                return {"metric": metric, "samples": [{"time": end, "value": 12.5}], "sample_count": 1}
        adapter = Adapter()
        self.store.refresh_metric_catalogue("fixture", "laptop", adapter)
        self.assertEqual(self.store.metrics("fixture", "laptop", section="all")["total"], 2)
        adapter.metrics = adapter.metrics[:1]
        self.store.refresh_metric_catalogue("fixture", "laptop", adapter)
        historical = self.store.metrics("fixture", "laptop", search="received")["metrics"][0]
        self.assertEqual((historical["availability"], historical["collection_outcome"]), ("historical", "not_observed"))

        server = make_server(self.store, port=0, fixture=True, netdata=adapter)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(origin + "/api/v1/devices/laptop/metrics?section=system&limit=1") as response:
            catalogue = json.load(response)
        self.assertEqual((catalogue["total"], len(catalogue["metrics"])), (1, 1))
        identifier = catalogue["metrics"][0]["metric_id"]
        with urllib.request.urlopen(origin + f"/api/v1/devices/laptop/metrics/{identifier}/history?points=10") as response:
            history = json.load(response)
        self.assertEqual(history["sample_count"], 1)


if __name__ == "__main__":
    unittest.main()
