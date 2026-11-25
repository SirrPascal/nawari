"""
tests/test_canonical_entities_and_ha.py

Comprehensive test suite verifying:
1. Telemetry contract canonical measurement states and operational health enums.
2. Canonical HA cluster registration, retrieval, and listing (SBCE HA pairs, CM Duplex).
3. Canonical device site and network segment associations.
4. Canonical entity measurement state transitions and evidence summaries.
5. Microsoft Entra ID (Azure AD) OIDC token validation and role mapping.
"""

import tempfile
import time
import unittest
from pathlib import Path
import sys

_pkg = Path(__file__).resolve().parent.parent / "network observability" / "platform"
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))

from nawari.store import Store
from nawari.canonical_inventory import CanonicalInventoryManager
from nawari.telemetry_contract import (
    MeasurementState,
    OperationalHealth,
    EvidenceCategory,
    MeasurementRecord,
)
from nawari.security_rbac import RBACSecurityManager


class TestCanonicalEntitiesAndHA(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_ha.db"
        self.store = Store(str(db_path))
        self.inventory = CanonicalInventoryManager(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_measurement_states_and_operational_health_enums(self):
        """Verify canonical measurement states and operational health enums according to Work Package B."""
        self.assertEqual(MeasurementState.MEASURED_FRESH.value, "MEASURED_FRESH")
        self.assertEqual(MeasurementState.MEASURED_STALE.value, "MEASURED_STALE")
        self.assertEqual(MeasurementState.NO_DATA.value, "NO_DATA")
        self.assertEqual(MeasurementState.SOURCE_UNREACHABLE.value, "SOURCE_UNREACHABLE")
        self.assertEqual(MeasurementState.AUTHENTICATION_FAILED.value, "AUTHENTICATION_FAILED")
        self.assertEqual(MeasurementState.COLLECTION_ERROR.value, "COLLECTION_ERROR")
        self.assertEqual(MeasurementState.UNSUPPORTED.value, "UNSUPPORTED")
        self.assertEqual(MeasurementState.NOT_CONFIGURED.value, "NOT_CONFIGURED")
        self.assertEqual(MeasurementState.SYNTHETIC.value, "SYNTHETIC")
        self.assertEqual(MeasurementState.INFERRED.value, "INFERRED")
        self.assertEqual(MeasurementState.UNKNOWN.value, "UNKNOWN")

        self.assertEqual(OperationalHealth.HEALTHY.value, "HEALTHY")
        self.assertEqual(OperationalHealth.DEGRADED.value, "DEGRADED")
        self.assertEqual(OperationalHealth.FAILED.value, "FAILED")
        self.assertEqual(OperationalHealth.UNKNOWN.value, "UNKNOWN")

        rec = MeasurementRecord(
            metric_name="icmp.rtt",
            value=1.24,
            unit="ms",
            source_system="zabbix",
            source_agent_id="zbx-poller-01",
            destination="10.2.156.131",
            measurement_state=MeasurementState.MEASURED_FRESH.value,
            operational_health=OperationalHealth.HEALTHY.value,
        )
        d = rec.to_dict()
        self.assertEqual(d["measurement_state"], "MEASURED_FRESH")
        self.assertEqual(d["operational_health"], "HEALTHY")
        self.assertEqual(d["value"], 1.24)

    def test_ha_cluster_management(self):
        """Verify registration, retrieval, and listing of HA clusters (e.g. SBCE and CM Duplex)."""
        # First register underlying devices
        dev_p = self.inventory.reconcile_device(
            name="Avaya SBCE Primary",
            source_system="zabbix",
            source_id="10101",
            management_ip="10.2.156.131",
            device_type="sbc",
            environment="production",
        )
        dev_s = self.inventory.reconcile_device(
            name="Avaya SBCE Secondary",
            source_system="zabbix",
            source_id="10102",
            management_ip="10.2.156.132",
            device_type="sbc",
            environment="production",
        )

        cluster_id = self.inventory.register_ha_cluster(
            cluster_id="ha-sbce-core",
            name="Avaya SBCE Production HA Cluster",
            cluster_type="sbce_ha_pair",
            vip_ip="10.2.156.130",
            primary_canonical_id=dev_p["canonical_id"],
            secondary_canonical_id=dev_s["canonical_id"],
            failover_mode="active_standby",
            status="healthy",
            attributes={"ems_managed": True, "signaling_interfaces": ["A1", "B1"]},
        )
        self.assertEqual(cluster_id, "ha-sbce-core")

        cluster = self.inventory.get_ha_cluster("ha-sbce-core")
        self.assertIsNotNone(cluster)
        self.assertEqual(cluster["name"], "Avaya SBCE Production HA Cluster")
        self.assertEqual(cluster["vip_ip"], "10.2.156.130")
        self.assertEqual(cluster["primary_canonical_id"], dev_p["canonical_id"])
        self.assertEqual(cluster["attributes"]["ems_managed"], True)

        clusters = self.inventory.list_ha_clusters(cluster_type="sbce_ha_pair")
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["cluster_id"], "ha-sbce-core")

    def test_device_site_association(self):
        """Verify associating canonical devices with physical sites and network segments."""
        dev = self.inventory.reconcile_device(
            name="Core-Switch-01",
            source_system="zabbix",
            source_id="20201",
            management_ip="10.2.1.1",
            device_type="switch",
            environment="production",
        )
        self.inventory.associate_device_site(
            canonical_id=dev["canonical_id"],
            site_id="site-hq-nbo",
            location_name="Nairobi HQ Data Center",
            rack_unit="Rack 12, U40-U42",
            network_segment="Core Infrastructure VLAN 10",
        )

        with self.store.db.transaction() as session:
            site_row = session.first(
                "SELECT * FROM canonical_device_sites WHERE canonical_id = ? AND site_id = ?",
                (dev["canonical_id"], "site-hq-nbo"),
            )
            self.assertIsNotNone(site_row)
            self.assertEqual(site_row["location_name"], "Nairobi HQ Data Center")
            self.assertEqual(site_row["network_segment"], "Core Infrastructure VLAN 10")

    def test_canonical_entity_state_lifecycle(self):
        """Verify recording and querying canonical entity measurement states and operational health."""
        entity_id = "trunk-safaricom-sip-01"
        entity_type = "trunk"

        self.inventory.record_entity_state(
            entity_id=entity_id,
            entity_type=entity_type,
            measurement_state=MeasurementState.MEASURED_FRESH.value,
            operational_health=OperationalHealth.HEALTHY.value,
            evidence_category=EvidenceCategory.OBSERVED.value,
            source_system="zabbix",
            evidence_summary="SIP OPTIONS keepalives responsive RTT 12.4ms (0% loss)",
        )

        st = self.inventory.get_entity_state(entity_id, entity_type)
        self.assertIsNotNone(st)
        self.assertEqual(st["measurement_state"], "MEASURED_FRESH")
        self.assertEqual(st["operational_health"], "HEALTHY")
        self.assertIn("12.4ms", st["evidence_summary"])

        # Transition to NO_DATA upon collector disconnect
        self.inventory.record_entity_state(
            entity_id=entity_id,
            entity_type=entity_type,
            measurement_state=MeasurementState.NO_DATA.value,
            operational_health=OperationalHealth.UNKNOWN.value,
            evidence_category=EvidenceCategory.INCONCLUSIVE.value,
            source_system="zabbix",
            evidence_summary="Collector timeout: No fresh telemetry received for > 300s",
        )

        st2 = self.inventory.get_entity_state(entity_id, entity_type)
        self.assertEqual(st2["measurement_state"], "NO_DATA")
        self.assertEqual(st2["operational_health"], "UNKNOWN")

    def test_entra_id_oidc_claims_mapping(self):
        """Verify mapping Microsoft Entra ID (Azure AD) OIDC token claims to Nawari RBAC roles."""
        # 1. Admin claims
        admin_claims = {
            "sub": "usr-entra-001",
            "oid": "guid-entra-001",
            "preferred_username": "noc.admin@enterprise.com",
            "roles": ["Nawari.Admin"],
            "exp": time.time() + 3600,
            "tid": "tenant-corp-guid",
        }
        res_admin = RBACSecurityManager.validate_entra_id_token_structure(admin_claims)
        self.assertTrue(res_admin["valid"])
        self.assertEqual(res_admin["assigned_role"], "admin")
        self.assertIn("configure", res_admin["permissions"])

        # 2. Operator claims
        operator_claims = {
            "sub": "usr-entra-002",
            "oid": "guid-entra-002",
            "preferred_username": "telecom.eng@enterprise.com",
            "roles": ["voice.engineer"],
            "exp": time.time() + 3600,
        }
        res_op = RBACSecurityManager.validate_entra_id_token_structure(operator_claims)
        self.assertEqual(res_op["assigned_role"], "operator")
        self.assertIn("dispatch", res_op["permissions"])
        self.assertNotIn("configure", res_op["permissions"])

        # 3. Auditor claims
        auditor_claims = {
            "sub": "usr-entra-003",
            "oid": "guid-entra-003",
            "preferred_username": "sec.audit@enterprise.com",
            "groups": ["security.auditor"],
            "exp": time.time() + 3600,
        }
        res_audit = RBACSecurityManager.validate_entra_id_token_structure(auditor_claims)
        self.assertEqual(res_audit["assigned_role"], "auditor")
        self.assertIn("audit", res_audit["permissions"])

        # 4. Default viewer claims
        viewer_claims = {
            "sub": "usr-entra-004",
            "oid": "guid-entra-004",
            "preferred_username": "intern@enterprise.com",
            "roles": [],
            "exp": time.time() + 3600,
        }
        res_view = RBACSecurityManager.validate_entra_id_token_structure(viewer_claims)
        self.assertEqual(res_view["assigned_role"], "viewer")
        self.assertEqual(res_view["permissions"], ["read"])

        # 5. Expired token rejection
        expired_claims = {
            "sub": "usr-entra-005",
            "exp": time.time() - 100,
        }
        with self.assertRaises(ValueError):
            RBACSecurityManager.validate_entra_id_token_structure(expired_claims)


if __name__ == "__main__":
    unittest.main()
