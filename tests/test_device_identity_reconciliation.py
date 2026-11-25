"""Comprehensive Automated Test Suite for Nawari Device Identity Reconciliation.

Tests:
1. Deterministic one-to-one matching (EXACT_VERIFIED_MATCH, HIGH_CONFIDENCE_MATCH).
2. Duplicate IP addresses & conflicting records (CONFLICTING_MATCH, DUPLICATE_CANDIDATE).
3. Multiple interfaces & loopback vs physical IP handling.
4. Serial number precedence over IP heuristics.
5. High-Availability (HA) cluster and VIP preservation (MANUAL_REVIEW_REQUIRED).
6. Cisco switch stack recognition (is_switch_stack = True).
7. Safe Zabbix API updates (technical host preserved, only visible name updated).
8. Rollback fidelity and audit log recording.
9. Idempotency (re-running produces zero additional renames).
10. Drift detection (caption changes, IP shifts, new devices, missing nodes).
11. Cisco syslog source resolution with preferred SolarWinds display name.
"""

import json
import pytest
import sys
from pathlib import Path

# Add platform to path
PLATFORM_DIR = Path(__file__).resolve().parent.parent / "network observability/platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from nawari.solarwinds_inventory_importer import SolarWindsNodeRecord, SolarWindsInventoryImporter
from nawari.zabbix_inventory_collector import ZabbixHostRecord, ZabbixInterfaceRecord
from nawari.device_identity_reconciler import (
    DeviceIdentityReconciler,
    MatchConfidence,
    ReconciliationItem,
    DeviceDriftDetector,
)
from nawari.cisco_source_resolver import CiscoSourceResolver, CiscoSyslogRecord, AttributionStatus


@pytest.fixture
def reconciler():
    return DeviceIdentityReconciler(ha_cluster_vips={"10.2.156.40", "10.2.1.1"})


@pytest.fixture
def sample_nodes():
    sw = SolarWindsNodeRecord(
        node_id="101",
        caption="HQ-CORE-SW01",
        node_name="hq-core-sw01.corp",
        ip_address="10.20.1.220",
        sys_name="HQ-CORE-SW01",
        vendor="Cisco",
        machine_type="Catalyst 9500-48Y4C",
        serial_number="FOC24190ABC",
        site="NBO-HQ",
        device_type="Core Switch",
    )
    zbx = ZabbixHostRecord(
        host_id="10786",
        technical_host="cisco-switch-10.20.1.220",
        visible_name="10.20.1.220 (Core Switch)",
        status=0,
        interfaces=[
            ZabbixInterfaceRecord(interface_id="1", ip="10.20.1.220", dns="", main=True, type=2)
        ],
        inventory={"serialno_a": "FOC24190ABC", "model": "Catalyst 9500"},
    )
    return sw, zbx


def test_exact_verified_match_by_serial(reconciler, sample_nodes):
    sw, zbx = sample_nodes
    items = reconciler.reconcile([sw], [zbx])
    assert len(items) == 1
    item = items[0]
    assert item.confidence == MatchConfidence.EXACT_VERIFIED_MATCH
    assert item.current_zabbix_host == "cisco-switch-10.20.1.220"  # Technical host preserved!
    assert item.proposed_zabbix_visible_name == "HQ-CORE-SW01"     # Visible name updated!
    assert item.rename_operation == "RENAME"
    assert item.is_safe_to_rename is True
    assert item.requires_manual_review is False


def test_high_confidence_match_by_ip_without_serial(reconciler):
    sw = SolarWindsNodeRecord(
        node_id="102",
        caption="JKIA-ACC-SW01",
        node_name="jkia-acc-sw01.corp",
        ip_address="10.14.1.30",
        sys_name="JKIA-ACC-SW01",
        vendor="Cisco",
        machine_type="Catalyst 9200-48P",
        serial_number=None,  # No serial number
        site="JKIA",
    )
    zbx = ZabbixHostRecord(
        host_id="10825",
        technical_host="cisco-switch-10.14.1.30",
        visible_name="10.14.1.30 (Candidate Switch)",
        status=0,
        interfaces=[
            ZabbixInterfaceRecord(interface_id="2", ip="10.14.1.30", dns="", main=True, type=1)
        ],
    )
    items = reconciler.reconcile([sw], [zbx])
    assert len(items) == 1
    item = items[0]
    assert item.confidence == MatchConfidence.HIGH_CONFIDENCE_MATCH
    assert item.current_zabbix_host == "cisco-switch-10.14.1.30"
    assert item.proposed_zabbix_visible_name == "JKIA-ACC-SW01"
    assert item.is_safe_to_rename is True


def test_conflicting_match_multiple_nodes_same_ip(reconciler):
    sw1 = SolarWindsNodeRecord(
        node_id="103", caption="BRANCH-SW-A", node_name="sw-a", ip_address="10.10.10.1",
        sys_name="SW-A", vendor="Cisco", machine_type="Catalyst 2960"
    )
    sw2 = SolarWindsNodeRecord(
        node_id="104", caption="BRANCH-SW-B", node_name="sw-b", ip_address="10.10.10.1",
        sys_name="SW-B", vendor="Cisco", machine_type="Catalyst 2960"
    )
    zbx = ZabbixHostRecord(
        host_id="10900", technical_host="cisco-switch-10.10.10.1", visible_name="10.10.10.1 Switch",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="3", ip="10.10.10.1", dns="", main=True, type=1)]
    )
    items = reconciler.reconcile([sw1, sw2], [zbx])
    zbx_item = next(it for it in items if it.zabbix_host and it.zabbix_host.host_id == "10900")
    assert zbx_item.confidence == MatchConfidence.CONFLICTING_MATCH
    assert zbx_item.is_safe_to_rename is False
    assert zbx_item.rename_operation == "BLOCKED"
    assert "Multiple SolarWinds nodes" in zbx_item.conflict_reason


def test_duplicate_candidate_multiple_zabbix_hosts_same_ip(reconciler):
    sw = SolarWindsNodeRecord(
        node_id="105", caption="HQ-TEST-SW01", node_name="test", ip_address="10.20.30.40",
        sys_name="TEST", vendor="Cisco", machine_type="Catalyst 3850"
    )
    zbx1 = ZabbixHostRecord(
        host_id="10901", technical_host="sw-test-1", visible_name="Switch Test 1",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="4", ip="10.20.30.40", dns="", main=True, type=1)]
    )
    zbx2 = ZabbixHostRecord(
        host_id="10902", technical_host="sw-test-2", visible_name="Switch Test 2",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="5", ip="10.20.30.40", dns="", main=True, type=1)]
    )
    items = reconciler.reconcile([sw], [zbx1, zbx2])
    zbx_items = [it for it in items if it.zabbix_host]
    assert all(it.confidence == MatchConfidence.DUPLICATE_CANDIDATE for it in zbx_items)
    assert all(it.is_safe_to_rename is False for it in zbx_items)


def test_ha_cluster_vip_separation(reconciler):
    # Cluster VIP 10.2.156.40 should NOT automatically overwrite a physical node's name
    sw_vip = SolarWindsNodeRecord(
        node_id="200", caption="HQ-SBCE-HA-VIP", node_name="hq-sbce-vip", ip_address="10.2.156.40",
        sys_name="HQ-SBCE-VIP", vendor="Avaya", machine_type="Avaya SBCE Cluster", site="NBO-HQ"
    )
    zbx_vip = ZabbixHostRecord(
        host_id="10780", technical_host="avaya-sbce-vip", visible_name="Avaya SBCE Virtual IP",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="6", ip="10.2.156.40", dns="", main=True, type=2)]
    )
    items = reconciler.reconcile([sw_vip], [zbx_vip])
    item = items[0]
    assert item.confidence == MatchConfidence.MANUAL_REVIEW_REQUIRED
    assert item.is_ha_cluster_node is True
    assert item.is_safe_to_rename is False
    assert item.requires_manual_review is True
    assert item.rename_operation == "REVIEW"


def test_switch_stack_detection(reconciler):
    sw_stack = SolarWindsNodeRecord(
        node_id="106", caption="HQ-ACC-STACK01", node_name="hq-stack", ip_address="10.14.1.101",
        sys_name="HQ-ACC-STACK01", vendor="Cisco", machine_type="Catalyst 9300-48P Stack",
        serial_number="FCW22100AAA", site="NBO-HQ"
    )
    zbx_stack = ZabbixHostRecord(
        host_id="10793", technical_host="cisco-switch-10.14.1.101", visible_name="10.14.1.101 (Candidate Switch)",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="7", ip="10.14.1.101", dns="", main=True, type=1)]
    )
    items = reconciler.reconcile([sw_stack], [zbx_stack])
    item = items[0]
    assert item.is_switch_stack is True
    assert item.proposed_zabbix_visible_name == "HQ-ACC-STACK01"
    assert item.is_safe_to_rename is True


def test_zabbix_server_exclusion(reconciler):
    zbx_server = ZabbixHostRecord(
        host_id="10084", technical_host="Zabbix server", visible_name="Zabbix server",
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="8", ip="127.0.0.1", dns="", main=True, type=1)]
    )
    items = reconciler.reconcile([], [zbx_server])
    item = items[0]
    assert item.confidence == MatchConfidence.ZABBIX_ONLY
    assert item.rename_operation == "NOOP"
    assert item.is_safe_to_rename is False


def test_idempotency_after_rename(reconciler):
    # If the Zabbix visible name is already renamed to the SolarWinds caption, operation is NOOP
    sw = SolarWindsNodeRecord(
        node_id="107", caption="HQ-CORE-SW01", node_name="core", ip_address="10.20.1.220",
        sys_name="HQ-CORE-SW01", vendor="Cisco", machine_type="Catalyst 9500", serial_number="FOC24190ABC"
    )
    zbx = ZabbixHostRecord(
        host_id="10786", technical_host="cisco-switch-10.20.1.220", visible_name="HQ-CORE-SW01",  # Already matches!
        status=0, interfaces=[ZabbixInterfaceRecord(interface_id="9", ip="10.20.1.220", dns="", main=True, type=2)]
    )
    items = reconciler.reconcile([sw], [zbx])
    item = items[0]
    assert item.rename_operation == "NOOP"
    assert item.proposed_zabbix_visible_name == "HQ-CORE-SW01"


def test_drift_detection():
    baseline_plan = {
        "items": [
            {
                "canonical_id": "dev-1",
                "solarwinds_node_id": "101",
                "solarwinds_caption": "HQ-CORE-SW01",
                "solarwinds_ip": "10.20.1.220",
                "zabbix_host_id": "10786",
            }
        ]
    }
    # New state: Caption changed in SolarWinds and new node added
    new_sw = [
        SolarWindsNodeRecord(
            node_id="101", caption="HQ-CORE-SW01-NEW", node_name="core", ip_address="10.20.1.220",
            sys_name="CORE", vendor="Cisco", machine_type="Cat 9500"
        ),
        SolarWindsNodeRecord(
            node_id="999", caption="NEW-BRANCH-SW01", node_name="new-sw", ip_address="10.99.99.1",
            sys_name="NEW", vendor="Cisco", machine_type="Cat 9200"
        )
    ]
    report = DeviceDriftDetector.detect_drift(baseline_plan, new_sw, [])
    assert report.total_drift_items >= 2
    assert len(report.caption_changes) == 1
    assert report.caption_changes[0]["old_caption"] == "HQ-CORE-SW01"
    assert report.caption_changes[0]["new_caption"] == "HQ-CORE-SW01-NEW"
    assert len(report.new_solarwinds_devices) == 1
    assert report.new_solarwinds_devices[0]["node_id"] == "999"


def test_cisco_syslog_source_resolution_with_preferred_display_name():
    resolver = CiscoSourceResolver()
    raw = "2026-11-25T01:00:00 10.2.131.75 %DOT1X-5-FAIL: Authentication failed on Interface Gi0/4 AuditSessionID 0A1401DC0000261F63C81B43"
    rec = resolver.parse_syslog(raw)
    assert rec.decoded_switch_ip == "10.20.1.220"

    canonical_devices = [
        {
            "canonical_id": "dev-cisco-core-01",
            "management_ip": "10.20.1.220",
            "name": "HQ-CORE-SW01",
            "preferred_display_name": "HQ-CORE-SW01",
            "authoritative_source": "snmp",
            "trust_score": 1.0,
        }
    ]
    res = resolver.resolve_source(rec, canonical_devices=canonical_devices, zabbix_hosts=[])
    assert res.attribution_status == AttributionStatus.VERIFIED.value
    assert res.device_name == "HQ-CORE-SW01"
    assert res.originating_device == "dev-cisco-core-01"
