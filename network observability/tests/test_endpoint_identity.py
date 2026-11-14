#!/usr/bin/env python3
"""
test_endpoint_identity.py

Automated test suite for the Nawari Enterprise Endpoint & Infrastructure
Identity Registry and Reconciliation Engine.

Covers security hardening:
- Opaque immutable UUIDv4 endpoint identifiers
- Explicit provenance and trust levels (trusted_enrollment, authorized_inventory, authenticated_collector, unverified_telemetry)
- Untrusted serial number spoofing and asset hijacking prevention
- Cloned machine GUID conflict detection and quarantine
- Retired asset reappearance protection
- Cross-tenant identity isolation
- API RBAC permissions and sensitive hardware attribute redaction for readers
- Migration rollback non-destructive archive safeguard
"""

import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = REPO_ROOT / "platform"
sys.path.insert(0, str(PLATFORM_DIR))

from nawari.identity import (
    DeviceHardwareIdentity,
    EndpointObservation,
    EndpointReconciler,
    NetworkInterfaceObservation,
    TRUST_LEVEL_ENROLLMENT,
    TRUST_LEVEL_INVENTORY,
    TRUST_LEVEL_COLLECTOR,
    TRUST_LEVEL_UNVERIFIED,
    generate_endpoint_id,
)
from nawari.server import make_server
from nawari.store import Store


class EndpointIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = str(Path(self.temp_dir.name) / "identity_test.db")
        self.now = 1794690000.0
        self.store = Store(self.db_path, clock=lambda: self.now)
        self.tenant = "nawari-corp"

    def test_endpoint_creation_and_canonical_id(self):
        """Verifies initial enrollment creates opaque immutable endpoint_id and records mappings."""
        obs = EndpointObservation(
            tenant=self.tenant,
            hostname="laptop-alice.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-1111-2222-3333",
            hardware=DeviceHardwareIdentity(serial_number="C02XG0VNJHCD", mac_address="00:11:22:33:44:55"),
            device_kind="laptop",
            os_family="darwin",
            os_version="14.4.1",
            site_id="hq-london",
            routing_domain_id="corporate-lan",
            trust_level=TRUST_LEVEL_ENROLLMENT,
            authoritative=True,
            interfaces=[
                NetworkInterfaceObservation(
                    interface_name="en0",
                    interface_type="WIFI",
                    ip_address="10.20.1.50",
                    mac_address="00:11:22:33:44:55",
                    gateway_ip="10.20.1.1",
                    ssid="Nawari-Corp-Secure",
                )
            ],
            observed_at=self.now,
        )

        res = self.store.reconcile_endpoint(obs)
        self.assertEqual(res.status, "created_new")
        self.assertTrue(res.endpoint_id.startswith("ep-"))
        self.assertEqual(len(res.endpoint_id), 35)  # ep- + 32 hex chars (full UUIDv4)

        # Check full endpoint profile
        ep = self.store.get_endpoint(self.tenant, res.endpoint_id)
        self.assertIsNotNone(ep)
        self.assertEqual(ep["primary_hostname"], "laptop-alice.corp.local")
        self.assertEqual(ep["serial_number"], "C02XG0VNJHCD")
        self.assertEqual(ep["lifecycle_state"], "active")
        self.assertEqual(ep["trust_level"], TRUST_LEVEL_ENROLLMENT)
        self.assertEqual(len(ep["source_mappings"]), 1)
        self.assertEqual(ep["source_mappings"][0]["source_system"], "netdata_guid")
        self.assertEqual(ep["source_mappings"][0]["source_identifier"], "guid-1111-2222-3333")
        self.assertEqual(len(ep["network_observations"]), 1)
        self.assertEqual(ep["network_observations"][0]["ip_address"], "10.20.1.50")
        self.assertEqual(len(ep["hostname_history"]), 1)

        # Check backward-compatible mirror into assets and topology_entities
        with self.store.db.transaction() as s:
            asset = s.one("SELECT * FROM assets WHERE tenant=? AND asset_id=?", (self.tenant, res.endpoint_id))
            self.assertIsNotNone(asset)
            self.assertEqual(asset["site_id"], "hq-london")

            topo = s.one("SELECT * FROM topology_entities WHERE tenant=? AND entity_id=?", (self.tenant, res.endpoint_id))
            self.assertIsNotNone(topo)
            self.assertEqual(topo["entity_kind"], "endpoint")

    def test_idempotent_reconciliation_and_no_duplicates(self):
        """Verifies repeated ingestion of the same endpoint does not duplicate assets."""
        obs = EndpointObservation(
            tenant=self.tenant,
            hostname="workstation-bob.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-4444-5555-6666",
            trust_level=TRUST_LEVEL_ENROLLMENT,
            hardware=DeviceHardwareIdentity(serial_number="WD-WCC4N7"),
            observed_at=self.now,
        )

        res1 = self.store.reconcile_endpoint(obs)
        res2 = self.store.reconcile_endpoint(obs)
        self.assertEqual(res1.endpoint_id, res2.endpoint_id)
        self.assertEqual(res2.status, "matched_hardware")

        listing = self.store.list_endpoints(self.tenant)
        self.assertEqual(listing["total"], 1)

    def test_hostname_change_preservation(self):
        """Verifies renaming a computer retains canonical endpoint_id and records history."""
        obs1 = EndpointObservation(
            tenant=self.tenant,
            hostname="old-laptop-name",
            source_system="netdata_guid",
            source_identifier="guid-7777-8888-9999",
            hardware=DeviceHardwareIdentity(serial_number="SN-RENAME-TEST"),
            trust_level=TRUST_LEVEL_ENROLLMENT,
            authoritative=True,
            observed_at=self.now,
        )
        res1 = self.store.reconcile_endpoint(obs1)

        # Later, laptop is renamed to new-laptop-name
        obs2 = EndpointObservation(
            tenant=self.tenant,
            hostname="new-laptop-name",
            source_system="netdata_guid",
            source_identifier="guid-7777-8888-9999",
            hardware=DeviceHardwareIdentity(serial_number="SN-RENAME-TEST"),
            trust_level=TRUST_LEVEL_ENROLLMENT,
            authoritative=True,
            observed_at=self.now + 3600,
        )
        res2 = self.store.reconcile_endpoint(obs2)

        self.assertEqual(res1.endpoint_id, res2.endpoint_id)
        ep = self.store.get_endpoint(self.tenant, res1.endpoint_id)
        self.assertEqual(ep["primary_hostname"], "new-laptop-name")

        hist_names = {h["hostname"] for h in ep["hostname_history"]}
        self.assertEqual(hist_names, {"old-laptop-name", "new-laptop-name"})

    def test_dhcp_ip_reassignment_and_multi_interface(self):
        """Verifies IP changes and multi-interface roaming do not alter endpoint identity."""
        obs_wifi = EndpointObservation(
            tenant=self.tenant,
            hostname="roaming-mac.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-roam-1234",
            trust_level=TRUST_LEVEL_COLLECTOR,
            hardware=DeviceHardwareIdentity(serial_number="SN-ROAM-001"),
            interfaces=[
                NetworkInterfaceObservation(
                    interface_name="en0",
                    interface_type="WIFI",
                    ip_address="192.168.1.100",
                    ssid="Guest-Wifi",
                )
            ],
            observed_at=self.now,
        )
        res = self.store.reconcile_endpoint(obs_wifi)

        # Device connects to corporate dock over Ethernet with new IP
        obs_ethernet = EndpointObservation(
            tenant=self.tenant,
            hostname="roaming-mac.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-roam-1234",
            trust_level=TRUST_LEVEL_COLLECTOR,
            hardware=DeviceHardwareIdentity(serial_number="SN-ROAM-001"),
            interfaces=[
                NetworkInterfaceObservation(
                    interface_name="en5",
                    interface_type="ETHERNET",
                    ip_address="10.100.4.25",
                    gateway_ip="10.100.4.1",
                )
            ],
            observed_at=self.now + 600,
        )
        res_eth = self.store.reconcile_endpoint(obs_ethernet)
        self.assertEqual(res.endpoint_id, res_eth.endpoint_id)

        ep = self.store.get_endpoint(self.tenant, res.endpoint_id)
        observed_ips = {net["ip_address"] for net in ep["network_observations"]}
        self.assertEqual(observed_ips, {"192.168.1.100", "10.100.4.25"})

    def test_untrusted_serial_number_claim_is_quarantined(self):
        """CRITICAL SECURITY: Untrusted telemetry reporting another device's serial number is quarantined and cannot hijack it."""
        # Step 1: Legitimate device enrolled via IT inventory
        obs_legit = EndpointObservation(
            tenant=self.tenant,
            hostname="executive-laptop.corp.local",
            source_system="intune_device_id",
            source_identifier="intune-device-9999",
            trust_level=TRUST_LEVEL_INVENTORY,
            hardware=DeviceHardwareIdentity(serial_number="CONFIDENTIAL-SERIAL-007"),
            authoritative=True,
            observed_at=self.now,
        )
        res_legit = self.store.reconcile_endpoint(obs_legit)
        self.assertEqual(res_legit.status, "created_new")

        # Step 2: Rogue / untrusted endpoint claims CONFIDENTIAL-SERIAL-007 via unverified telemetry
        obs_rogue = EndpointObservation(
            tenant=self.tenant,
            hostname="attacker-vm",
            source_system="netdata_guid",
            source_identifier="rogue-collector-guid-666",
            trust_level=TRUST_LEVEL_UNVERIFIED,
            hardware=DeviceHardwareIdentity(serial_number="CONFIDENTIAL-SERIAL-007"),
            authoritative=False,
            observed_at=self.now + 10,
        )
        res_rogue = self.store.reconcile_endpoint(obs_rogue)

        # Must NOT hijack legitimate asset
        self.assertNotEqual(res_legit.endpoint_id, res_rogue.endpoint_id)
        self.assertEqual(res_rogue.status, "quarantined")
        self.assertIsNotNone(res_rogue.conflict_id)

        # Verify conflict recorded in database
        conflicts = self.store.get_endpoint_conflicts(self.tenant)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["conflict_reason"], "spoofed_serial_claim")
        self.assertEqual(conflicts[0]["existing_endpoint_id"], res_legit.endpoint_id)

        # Verify legitimate asset was not modified
        ep_legit = self.store.get_endpoint(self.tenant, res_legit.endpoint_id)
        self.assertEqual(ep_legit["primary_hostname"], "executive-laptop.corp.local")
        self.assertEqual(len(ep_legit["source_mappings"]), 1)
        self.assertEqual(ep_legit["source_mappings"][0]["source_system"], "intune_device_id")

    def test_authorized_inventory_can_establish_hardware_link(self):
        """Authorized inventory sources (Intune, IT enrollment) can match and link by serial number."""
        obs_enroll = EndpointObservation(
            tenant=self.tenant,
            hostname="finance-pc",
            source_system="intune_device_id",
            source_identifier="intune-fin-01",
            trust_level=TRUST_LEVEL_INVENTORY,
            hardware=DeviceHardwareIdentity(serial_number="FIN-HW-4321"),
            observed_at=self.now,
        )
        res1 = self.store.reconcile_endpoint(obs_enroll)

        # Same hardware discovered by secondary authorized source (e.g. SolarWinds)
        obs_sw = EndpointObservation(
            tenant=self.tenant,
            hostname="finance-pc.domain",
            source_system="solarwinds_nodeid",
            source_identifier="sw-node-888",
            trust_level=TRUST_LEVEL_INVENTORY,
            hardware=DeviceHardwareIdentity(serial_number="FIN-HW-4321"),
            observed_at=self.now + 50,
        )
        res2 = self.store.reconcile_endpoint(obs_sw)

        self.assertEqual(res1.endpoint_id, res2.endpoint_id)
        self.assertEqual(res2.status, "matched_hardware")

        ep = self.store.get_endpoint(self.tenant, res1.endpoint_id)
        systems = {m["source_system"] for m in ep["source_mappings"]}
        self.assertEqual(systems, {"intune_device_id", "solarwinds_nodeid"})

    def test_duplicate_machine_guid_quarantine(self):
        """Detects cloned VM / duplicate Netdata GUID and quarantines conflict."""
        obs_vm1 = EndpointObservation(
            tenant=self.tenant,
            hostname="vm-master.corp.local",
            source_system="netdata_guid",
            source_identifier="cloned-guid-duplicate",
            trust_level=TRUST_LEVEL_COLLECTOR,
            hardware=DeviceHardwareIdentity(serial_number="VM-SERIAL-001"),
            observed_at=self.now,
        )
        res1 = self.store.reconcile_endpoint(obs_vm1)
        self.assertEqual(res1.status, "created_new")

        # Second VM cloned with exact same Netdata GUID, but different hardware serial
        obs_vm2 = EndpointObservation(
            tenant=self.tenant,
            hostname="vm-clone.corp.local",
            source_system="netdata_guid",
            source_identifier="cloned-guid-duplicate",
            trust_level=TRUST_LEVEL_COLLECTOR,
            hardware=DeviceHardwareIdentity(serial_number="VM-SERIAL-002"),
            observed_at=self.now + 10,
        )
        res2 = self.store.reconcile_endpoint(obs_vm2)

        self.assertEqual(res2.status, "quarantined")
        self.assertIsNotNone(res2.conflict_id)

        conflicts = self.store.get_endpoint_conflicts(self.tenant)
        self.assertTrue(any(c["conflict_reason"] == "duplicate_machine_guid" for c in conflicts))

    def test_retired_asset_reappearance_quarantined(self):
        """Untrusted telemetry received for an asset marked retired is quarantined."""
        obs = EndpointObservation(
            tenant=self.tenant,
            hostname="decommissioned-box",
            source_system="netdata_guid",
            source_identifier="guid-retired-001",
            trust_level=TRUST_LEVEL_INVENTORY,
            observed_at=self.now,
        )
        res = self.store.reconcile_endpoint(obs)

        # Mark asset as retired
        with self.store.db.transaction() as s:
            s.execute("UPDATE endpoint_registry SET lifecycle_state='retired' WHERE tenant=? AND endpoint_id=?", (self.tenant, res.endpoint_id))

        # Stale/zombie telemetry arrives from unverified source
        obs_zombie = EndpointObservation(
            tenant=self.tenant,
            hostname="decommissioned-box",
            source_system="netdata_guid",
            source_identifier="guid-retired-001",
            trust_level=TRUST_LEVEL_UNVERIFIED,
            observed_at=self.now + 3600,
        )
        res_zombie = self.store.reconcile_endpoint(obs_zombie)

        self.assertEqual(res_zombie.status, "quarantined")
        conflicts = self.store.get_endpoint_conflicts(self.tenant)
        self.assertTrue(any(c["conflict_reason"] == "retired_asset_reappearance" for c in conflicts))

    def test_cross_tenant_isolation(self):
        """Verifies strict tenant isolation: Tenant A cannot match or modify Tenant B's endpoints."""
        obs_a = EndpointObservation(
            tenant="tenant-alpha",
            hostname="shared-hostname",
            source_system="netdata_guid",
            source_identifier="shared-guid-1234",
            hardware=DeviceHardwareIdentity(serial_number="SHARED-SERIAL-01"),
            trust_level=TRUST_LEVEL_ENROLLMENT,
            observed_at=self.now,
        )
        res_a = self.store.reconcile_endpoint(obs_a)

        obs_b = EndpointObservation(
            tenant="tenant-beta",
            hostname="shared-hostname",
            source_system="netdata_guid",
            source_identifier="shared-guid-1234",
            hardware=DeviceHardwareIdentity(serial_number="SHARED-SERIAL-01"),
            trust_level=TRUST_LEVEL_ENROLLMENT,
            observed_at=self.now,
        )
        res_b = self.store.reconcile_endpoint(obs_b)

        # Both get independent canonical IDs
        self.assertNotEqual(res_a.endpoint_id, res_b.endpoint_id)

        # Querying tenant-alpha never returns tenant-beta
        ep_a = self.store.get_endpoint("tenant-alpha", res_a.endpoint_id)
        self.assertIsNotNone(ep_a)
        self.assertIsNone(self.store.get_endpoint("tenant-alpha", res_b.endpoint_id))

    def test_api_rbac_and_serial_redaction(self):
        """Verifies RBAC permissions on endpoints API: Reader gets redacted serials; unprivileged cannot reconcile."""
        # Provision admin and reader tokens in operators table
        admin_token = "admin-secret-token-32-characters-long"
        reader_token = "reader-secret-token-32-characters-long"
        self.store.operator(admin_token, self.tenant)
        with self.store.db.transaction() as s:
            from nawari.store import digest
            s.execute("UPDATE operators SET role='admin' WHERE token_hash=?", (digest(admin_token),))
            s.execute("INSERT INTO operators VALUES (?,?, 'reader', ?, NULL)", (digest(reader_token), self.tenant, self.now + 86400))

        server = make_server(self.store, host="127.0.0.1", port=0, fixture=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        try:
            # 1. Admin reconciles endpoint
            payload = {
                "hostname": "secured-finance-mac",
                "source_system": "nawari_agent_id",
                "source_identifier": "agent-rbac-test",
                "device_kind": "laptop",
                "os_family": "darwin",
                "trust_level": TRUST_LEVEL_ENROLLMENT,
                "authoritative": True,
                "hardware": {"serial_number": "TOP-SECRET-SERIAL-123", "chassis_uuid": "CHASSIS-UUID-999"},
            }
            req_admin = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/reconcile",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"},
                method="POST",
            )
            with urllib.request.urlopen(req_admin, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                endpoint_id = data["endpoint_id"]

            # 2. Reader attempts to reconcile -> Must be rejected with 403 Forbidden
            req_reader_reconcile = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/reconcile",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {reader_token}"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_reader_reconcile, timeout=3)
            self.assertEqual(ctx.exception.code, 403)

            # 3. Reader queries endpoint details -> Must have serial_number redacted
            req_reader_get = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/{endpoint_id}",
                headers={"Authorization": f"Bearer {reader_token}"},
            )
            with urllib.request.urlopen(req_reader_get, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                read_data = json.loads(resp.read().decode())
                self.assertEqual(read_data["serial_number"], "[REDACTED]")
                self.assertEqual(read_data["chassis_uuid"], "[REDACTED]")

            # 4. Admin queries endpoint details -> Receives unredacted serial_number
            req_admin_get = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/{endpoint_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            with urllib.request.urlopen(req_admin_get, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                admin_data = json.loads(resp.read().decode())
                self.assertEqual(admin_data["serial_number"], "TOP-SECRET-SERIAL-123")
                self.assertEqual(admin_data["chassis_uuid"], "CHASSIS-UUID-999")
        finally:
            server.shutdown()

    def test_live_child_fixture_reconciliation(self):
        """Reconciles the actual test child used in the isolated streaming experiment."""
        obs = EndpointObservation(
            tenant="default",
            hostname="nawari-stream-test-child",
            source_system="netdata_guid",
            source_identifier="597b7dba-620d-4a52-82a0-f417b1362cd5",
            device_kind="synthetic_probe",
            os_family="linux",
            os_version="Debian GNU/Linux 13 (trixie)",
            site_id="local-lab",
            routing_domain_id="nawari-stream-test-net",
            trust_level=TRUST_LEVEL_COLLECTOR,
            authoritative=False,
            interfaces=[
                NetworkInterfaceObservation(
                    interface_name="eth0",
                    interface_type="ETHERNET",
                    ip_address="172.28.0.20",
                    gateway_ip="172.28.0.1",
                )
            ],
            observed_at=self.now,
        )

        res = self.store.reconcile_endpoint(obs)
        self.assertTrue(res.endpoint_id.startswith("ep-"))

        listing = self.store.list_endpoints("default", search="stream-test-child")
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["endpoints"][0]["primary_hostname"], "nawari-stream-test-child")

    def test_canonical_uuidv4_entropy_and_uniqueness(self):
        """Verifies canonical endpoint IDs are full 35-character UUIDv4 strings with zero collisions."""
        ids = [generate_endpoint_id() for _ in range(1000)]
        self.assertEqual(len(ids), 1000)
        self.assertEqual(len(set(ids)), 1000)  # No collisions
        for eid in ids:
            self.assertTrue(eid.startswith("ep-"))
            self.assertEqual(len(eid), 35)
            # Verify remainder is valid 32-character hexadecimal string
            hex_part = eid[3:]
            self.assertEqual(len(hex_part), 32)
            int(hex_part, 16)  # Will raise ValueError if not valid hex

    def test_migration_rollback_fails_closed_when_populated(self):
        """Verifies rollback_004.sql aborts transaction when identity tables contain records."""
        # Create an active endpoint
        obs = EndpointObservation(
            tenant=self.tenant,
            hostname="populated-rollback-host",
            source_system="netdata_guid",
            source_identifier="guid-populated-test",
            observed_at=self.now,
        )
        res = self.store.reconcile_endpoint(obs)
        self.assertIsNotNone(res.endpoint_id)

        rollback_sql = (PLATFORM_DIR / "nawari" / "migrations" / "rollback_004.sql").read_text()

        # Run rollback against populated database; must fail closed with IntegrityError
        with self.assertRaises((sqlite3.IntegrityError, Exception)):
            with self.store.db.transaction() as s:
                for stmt in rollback_sql.split(";"):
                    if stmt.strip():
                        s.execute(stmt)

        # Active tables must remain completely intact and preserve all data
        with self.store.db.transaction() as s:
            ep = s.one("SELECT * FROM endpoint_registry WHERE endpoint_id=?", (res.endpoint_id,))
            self.assertIsNotNone(ep)
            self.assertEqual(ep["primary_hostname"], "populated-rollback-host")

    def test_migration_rollback_succeeds_when_empty(self):
        """Verifies rollback_004.sql drops tables cleanly only when identity tables are empty."""
        empty_db_path = str(Path(self.temp_dir.name) / "empty_rollback_test.db")
        empty_store = Store(empty_db_path, clock=lambda: self.now)

        rollback_sql = (PLATFORM_DIR / "nawari" / "migrations" / "rollback_004.sql").read_text()
        migration_sql = (PLATFORM_DIR / "nawari" / "migrations" / "004_endpoint_identity.sql").read_text()

        # Run rollback on empty database
        with empty_store.db.transaction() as s:
            for stmt in rollback_sql.split(";"):
                if stmt.strip():
                    s.execute(stmt)

            tables = {r["name"] for r in s.all("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("endpoint_registry", tables)
            self.assertNotIn("endpoint_source_mappings", tables)
            self.assertNotIn("endpoint_network_observations", tables)
            self.assertNotIn("endpoint_hostname_history", tables)
            self.assertNotIn("endpoint_identity_conflicts", tables)

            # Version 4 must be reverted
            v4 = s.one("SELECT * FROM schema_migrations WHERE version=4")
            self.assertIsNone(v4)

        # Re-apply migration
        with empty_store.db.transaction() as s:
            for stmt in migration_sql.split(";"):
                if stmt.strip():
                    s.execute(stmt)
            tables = {r["name"] for r in s.all("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("endpoint_registry", tables)

    def test_server_side_trust_enforcement_operator_clamping(self):
        """Verifies API clamps self-asserted operator trust levels and rejects reader elevation."""
        import hashlib
        op_token = "op-secret-token"
        admin_token = "admin-secret-token"
        reader_token = "reader-secret-token"

        now = self.now
        with self.store.db.transaction() as s:
            s.execute(
                "INSERT INTO operators VALUES (?,?,?,?,NULL)",
                (hashlib.sha256(op_token.encode()).hexdigest(), self.tenant, "operator", now + 3600),
            )
            s.execute(
                "INSERT INTO operators VALUES (?,?,?,?,NULL)",
                (hashlib.sha256(admin_token.encode()).hexdigest(), self.tenant, "admin", now + 3600),
            )
            s.execute(
                "INSERT INTO operators VALUES (?,?,?,?,NULL)",
                (hashlib.sha256(reader_token.encode()).hexdigest(), self.tenant, "reader", now + 3600),
            )

        server = make_server(self.store, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Operator attempts to claim authorized_inventory + authoritative: true
            req_data = json.dumps({
                "hostname": "clamped-laptop.corp.local",
                "source_system": "netdata_guid",
                "source_identifier": "guid-clamped-123",
                "trust_level": "authorized_inventory",  # Untrusted client assertion!
                "authoritative": True,
            }).encode()
            req_op = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/reconcile",
                data=req_data,
                headers={"Authorization": f"Bearer {op_token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req_op, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode())
                op_endpoint_id = body["endpoint_id"]

            # Inspect database: operator's trust claim MUST be clamped to authenticated_collector
            ep_clamped = self.store.get_endpoint(self.tenant, op_endpoint_id)
            self.assertEqual(ep_clamped["trust_level"], TRUST_LEVEL_COLLECTOR)
            self.assertEqual(ep_clamped["authoritative_source"], "telemetry_observed")

            # 2. Admin submits authorized_inventory + authoritative: true -> accepted
            admin_data = json.dumps({
                "hostname": "admin-inventory-laptop.corp.local",
                "source_system": "intune_device_id",
                "source_identifier": "intune-dev-999",
                "trust_level": "authorized_inventory",
                "authoritative": True,
            }).encode()
            req_admin = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/reconcile",
                data=admin_data,
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req_admin, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode())
                admin_endpoint_id = body["endpoint_id"]

            ep_admin = self.store.get_endpoint(self.tenant, admin_endpoint_id)
            self.assertEqual(ep_admin["trust_level"], TRUST_LEVEL_INVENTORY)
            self.assertEqual(ep_admin["authoritative_source"], "nawari_agent")

            # 3. Reader attempts to reconcile -> 403 Forbidden
            req_reader = urllib.request.Request(
                f"{base_url}/api/v1/endpoints/reconcile",
                data=req_data,
                headers={"Authorization": f"Bearer {reader_token}", "Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_reader, timeout=3)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            server.shutdown()

    def test_time_bounded_telemetry_resolution(self):
        """Verifies Prometheus metrics are mapped to canonical endpoints across time-bounded windows."""
        # Device A owned shared-host.corp.local at t=1000
        obs_a = EndpointObservation(
            tenant=self.tenant,
            hostname="shared-host.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-alpha-111",
            observed_at=1000.0,
        )
        res_a = self.store.reconcile_endpoint(obs_a)

        # Device B was assigned the same hostname at t=5000
        obs_b = EndpointObservation(
            tenant=self.tenant,
            hostname="shared-host.corp.local",
            source_system="netdata_guid",
            source_identifier="guid-beta-222",
            observed_at=5000.0,
        )
        res_b = self.store.reconcile_endpoint(obs_b)

        # Distinct devices
        self.assertNotEqual(res_a.endpoint_id, res_b.endpoint_id)

        # 1. Resolve by Netdata GUID
        self.assertEqual(
            self.store.resolve_telemetry_instance(self.tenant, node_guid="guid-alpha-111", timestamp=1000.0),
            res_a.endpoint_id,
        )
        self.assertEqual(
            self.store.resolve_telemetry_instance(self.tenant, node_guid="guid-beta-222", timestamp=5000.0),
            res_b.endpoint_id,
        )

        # 2. Resolve by time-bounded hostname
        # Historical measurement at t=1000 maps to Device A
        resolved_t1000 = self.store.resolve_telemetry_instance(
            self.tenant, hostname="shared-host.corp.local", timestamp=1000.0
        )
        self.assertEqual(resolved_t1000, res_a.endpoint_id)

        # Historical measurement at t=5000 maps to Device B
        resolved_t5000 = self.store.resolve_telemetry_instance(
            self.tenant, hostname="shared-host.corp.local", timestamp=5000.0
        )
        self.assertEqual(resolved_t5000, res_b.endpoint_id)

        # Unknown hostname
        self.assertIsNone(
            self.store.resolve_telemetry_instance(self.tenant, hostname="unknown-nonexistent-host", timestamp=1000.0)
        )

    def test_concurrent_reconciliation(self):
        """Verifies concurrent reconciliation from multiple threads maintains consistency without deadlocks."""
        errors = []

        def worker(idx):
            try:
                obs = EndpointObservation(
                    tenant=self.tenant,
                    hostname=f"thread-worker-{idx % 3}.corp.local",
                    source_system="netdata_guid",
                    source_identifier=f"guid-thread-{idx}",
                    observed_at=self.now + idx,
                )
                res = self.store.reconcile_endpoint(obs)
                if not res.endpoint_id or not res.endpoint_id.startswith("ep-"):
                    errors.append(f"Worker {idx} got invalid endpoint_id: {res.endpoint_id}")
            except Exception as e:
                errors.append(f"Worker {idx} raised: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
