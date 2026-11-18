"""Unit tests for Network Discovery and Reconciliation API endpoints."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "platform"))

from nawari.server import make_server
from nawari.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "test_discovery.db"))
    # Seed sample discovery candidates
    with s.db.transaction() as session:
        session.execute(
            """
            INSERT INTO network_discovery_candidates (
                ip_address, inferred_name, inferred_role, discovery_source,
                observed_log_count, sample_ports, dominant_events, sample_log,
                icmp_status, icmp_rtt_ms, icmp_loss_pct,
                snmp_status, solarwinds_status,
                zabbix_status, zabbix_hostid, canonical_id,
                verification_status, evidence_trail,
                last_probed_at, last_seen_at, created_at, updated_at
            ) VALUES
            (
                '10.20.1.220', 'Candidate Core Switch (10.20.1.220)', 'candidate_core_switch', 'cisco_syslog_auditsessionid',
                4024, 'Gi0/4, Gi0/21', '%FAIL, %START', 'Sample log message',
                'reachable', 7.01, 0,
                'timeout_acl_restricted', 'pending_swis_auth',
                'monitored', '10786', 'dev-cisco-core-10-20-1-220',
                'monitored_candidate', 'AuditSessionID heuristic',
                1000.0, 1000.0, 1000.0, 1000.0
            ),
            (
                '10.12.1.104', 'Candidate Distribution Switch (10.12.1.104)', 'candidate_distribution_switch', 'cisco_syslog_auditsessionid',
                839, 'Gi0/7', '%FAIL', 'Sample log message',
                'reachable', 2.47, 0,
                'timeout_acl_restricted', 'pending_swis_auth',
                'unregistered', NULL, 'dev-cisco-dist-10-12-1-104',
                'pending_verification', 'AuditSessionID heuristic',
                1000.0, 1000.0, 1000.0, 1000.0
            )
            """
        )
    return s


def test_list_discovery_candidates(store):
    res = store.list_discovery_candidates()
    assert res["total"] == 2
    assert len(res["candidates"]) == 2
    assert res["candidates"][0]["ip_address"] == "10.20.1.220"
    assert res["status_counts"]["monitored_candidate"] == 1
    assert res["status_counts"]["pending_verification"] == 1


def test_filter_discovery_candidates_by_status(store):
    res = store.list_discovery_candidates(status="pending_verification")
    assert res["total"] == 1
    assert res["candidates"][0]["ip_address"] == "10.12.1.104"


def test_search_discovery_candidates(store):
    res = store.list_discovery_candidates(search="10.20.1.220")
    assert res["total"] == 1
    assert res["candidates"][0]["ip_address"] == "10.20.1.220"


def test_discovery_summary(store):
    summary = store.get_discovery_summary()
    assert summary["total_candidates"] == 2
    assert summary["monitored_candidate"] == 1
    assert summary["pending_verification"] == 1
    assert summary["icmp_reachable"] == 2
    assert summary["monitored_in_zabbix"] == 1
    assert summary["unregistered_in_zabbix"] == 1
    assert "10.2.131.75:17774" in summary["solarwinds_swis"]


def test_continuous_candidate_upsert(store):
    # Simulate first observation of a new candidate IP 10.99.1.5
    now = 1795000000.0
    with store.db.transaction() as session:
        session.execute(
            """
            INSERT INTO network_discovery_candidates (
                ip_address, inferred_name, inferred_role, discovery_source,
                observed_log_count, sample_ports, dominant_events, sample_log,
                icmp_status, snmp_status, solarwinds_status, zabbix_status,
                verification_status, evidence_trail, last_seen_at, created_at, updated_at
            ) VALUES (
                ?, ?, ?, 'cisco_syslog_auditsessionid',
                1, ?, ?, ?,
                'untested', 'unavailable_unconfirmed', 'swis_auth_forbidden_403', 'unregistered',
                'pending_verification', ?, ?, ?, ?
            )
            ON CONFLICT (ip_address) DO UPDATE SET
                observed_log_count = network_discovery_candidates.observed_log_count + 1,
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                "10.99.1.5", "Candidate Cisco Switch (10.99.1.5)", "candidate_access_switch",
                "Gi1/0/1", "%MAB-5-FAIL", "Sample MAB log message",
                "Discovered by continuous syslog reconciler; pending verification",
                now, now, now,
            )
        )
    
    cand = store.get_discovery_candidate("10.99.1.5")
    assert cand is not None
    assert cand["observed_log_count"] == 1
    assert cand["verification_status"] == "pending_verification"

    # Simulate second observation of the same candidate
    now_next = now + 10.0
    with store.db.transaction() as session:
        session.execute(
            """
            INSERT INTO network_discovery_candidates (
                ip_address, inferred_name, inferred_role, discovery_source,
                observed_log_count, sample_ports, dominant_events, sample_log,
                icmp_status, snmp_status, solarwinds_status, zabbix_status,
                verification_status, evidence_trail, last_seen_at, created_at, updated_at
            ) VALUES (
                ?, ?, ?, 'cisco_syslog_auditsessionid',
                1, ?, ?, ?,
                'untested', 'unavailable_unconfirmed', 'swis_auth_forbidden_403', 'unregistered',
                'pending_verification', ?, ?, ?, ?
            )
            ON CONFLICT (ip_address) DO UPDATE SET
                observed_log_count = network_discovery_candidates.observed_log_count + 1,
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                "10.99.1.5", "Candidate Cisco Switch (10.99.1.5)", "candidate_access_switch",
                "Gi1/0/1", "%MAB-5-FAIL", "Sample MAB log message",
                "Discovered by continuous syslog reconciler; pending verification",
                now_next, now, now_next,
            )
        )

    cand_after = store.get_discovery_candidate("10.99.1.5")
    assert cand_after["observed_log_count"] == 2
    assert cand_after["verification_status"] == "pending_verification"

