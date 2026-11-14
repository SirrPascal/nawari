"""Unit tests for Nawari Incident Lifecycle and Correlation Pipeline (Workstream 13C)."""

import threading
from datetime import datetime, timedelta, timezone
import pytest

from services.multisite.incident_pipeline import (
    AlertCorrelationEngine,
    EscalationPolicy,
    IncidentManager,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
    InvalidStateTransitionError,
    OperationalAlert,
)


def test_duplicate_alerts_and_repeated_occurrences_deduplication():
    mgr = IncidentManager()
    alert1 = OperationalAlert(
        alert_id="ALT-001",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Core switch ICMP ping failed",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
        service_id="SVC-DCS-GLOBAL",
    )
    inc1, action1 = mgr.ingest_alert(alert1)
    assert action1 == "CREATED"
    assert inc1.status == IncidentStatus.DETECTED
    assert len(mgr.get_active_incidents()) == 1

    # Ingest duplicate alert on same entity and metric
    alert2 = OperationalAlert(
        alert_id="ALT-002",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Core switch ICMP ping failed again",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
        service_id="SVC-DCS-GLOBAL",
    )
    inc2, action2 = mgr.ingest_alert(alert2)
    assert action2 == "DEDUPLICATED"
    assert inc2.incident_id == inc1.incident_id
    assert "ALT-002" in inc2.correlated_alert_ids
    assert len(mgr.get_active_incidents()) == 1


def test_unrelated_alerts_remain_separate():
    mgr = IncidentManager()
    alert_sw = OperationalAlert(
        alert_id="ALT-SW",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P2_HIGH,
        summary="Switch ping fail",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
    )
    alert_voice = OperationalAlert(
        alert_id="ALT-VOICE",
        source="VOICE_SYNTHETIC",
        entity_id="AVAYA-SBCE-01",
        metric_name="sip_options",
        observed_value=504,
        severity=IncidentSeverity.P2_HIGH,
        summary="SBCE SIP Gateway timeout",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
    )
    inc1, act1 = mgr.ingest_alert(alert_sw)
    inc2, act2 = mgr.ingest_alert(alert_voice)

    assert act1 == "CREATED"
    assert act2 == "CREATED"
    assert inc1.incident_id != inc2.incident_id
    assert len(mgr.get_active_incidents()) == 2


def test_parent_down_topology_suppression():
    mgr = IncidentManager()
    
    # 1. Core switch fails (parent)
    parent_alert = OperationalAlert(
        alert_id="ALT-PARENT",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Core DC Switch SW-DC1-01 is DOWN",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
    )
    inc_parent, act_parent = mgr.ingest_alert(parent_alert)
    assert act_parent == "CREATED"

    # 2. Downstream access switch or client reports failure referencing parent
    child_alert = OperationalAlert(
        alert_id="ALT-CHILD",
        source="ZABBIX",
        entity_id="SW-T1A-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P2_HIGH,
        summary="Access switch SW-T1A-01 unreachable",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
        parent_entity_id="SW-DC1-01",  # Downstream child!
    )
    inc_child, act_child = mgr.ingest_alert(child_alert)
    assert act_child == "SUPPRESSED"
    assert inc_child.is_suppressed is True
    assert "PARENT_DOWN_SUPPRESSION" in inc_child.suppression_reason


def test_maintenance_suppression_and_automatic_expiry():
    mgr = IncidentManager()
    now = datetime.now(timezone.utc)

    # 1. Alert with active maintenance window (ends in 1 hour)
    active_maint_alert = OperationalAlert(
        alert_id="ALT-MAINT-1",
        source="ZABBIX",
        entity_id="RTR-CORE-01",
        metric_name="bgpPeerState",
        observed_value=1,
        severity=IncidentSeverity.P2_HIGH,
        summary="BGP peer down during scheduled router maintenance",
        event_timestamp=now.isoformat(),
        in_maintenance=True,
        maintenance_window_end=(now + timedelta(hours=1)).isoformat(),
    )
    inc1, act1 = mgr.ingest_alert(active_maint_alert)
    assert act1 == "SUPPRESSED"
    assert inc1.is_suppressed is True
    assert "MUTED_BY_MAINTENANCE_WINDOW" in inc1.suppression_reason

    # 2. Alert where maintenance window expired 10 minutes ago
    expired_maint_alert = OperationalAlert(
        alert_id="ALT-MAINT-2",
        source="ZABBIX",
        entity_id="RTR-CORE-02",
        metric_name="bgpPeerState",
        observed_value=1,
        severity=IncidentSeverity.P2_HIGH,
        summary="BGP peer down after maintenance completed",
        event_timestamp=now.isoformat(),
        in_maintenance=True,
        maintenance_window_end=(now - timedelta(minutes=10)).isoformat(),  # EXPIRED
    )
    inc2, act2 = mgr.ingest_alert(expired_maint_alert)
    assert act2 == "CREATED"
    assert inc2.is_suppressed is False
    assert inc2.status == IncidentStatus.DETECTED


def test_acknowledgement_and_configurable_escalation():
    mgr = IncidentManager()
    now = datetime.now(timezone.utc)

    alert = OperationalAlert(
        alert_id="ALT-ESC",
        source="ZABBIX",
        entity_id="CIR-NBO-01",
        metric_name="ifOperStatus",
        observed_value=2,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Primary fiber link down",
        event_timestamp=now.isoformat(),
        station_id="JKIA-HUB",
        service_id="SVC-DCS-GLOBAL",
    )
    inc, _ = mgr.ingest_alert(alert)

    # Fast forward time by 20 minutes (exceeds 15 min P1 deadline)
    escalated = mgr.check_sla_escalations(current_time=now + timedelta(minutes=20))
    assert len(escalated) == 1
    assert escalated[0].incident_id == inc.incident_id
    assert escalated[0].is_escalated is True
    assert escalated[0].escalated_to == "NOC_DUTY_MANAGER"

    # Now acknowledge incident
    ok = mgr.acknowledge_incident(inc.incident_id, "operator_42", "NOC_DUTY_LEAD")
    assert ok is True
    assert inc.status == IncidentStatus.ACKNOWLEDGED
    assert inc.assigned_owner == "operator_42"

    # Acknowledging stops further SLA escalations
    escalated_after = mgr.check_sla_escalations(current_time=now + timedelta(minutes=40))
    assert len(escalated_after) == 0


def test_rejected_acknowledgement():
    mgr = IncidentManager()
    alert = OperationalAlert(
        alert_id="ALT-REJ",
        source="ZABBIX",
        entity_id="SW-DC1-02",
        metric_name="cpu_load",
        observed_value=98,
        severity=IncidentSeverity.P3_MEDIUM,
        summary="High CPU load",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
    )
    inc, _ = mgr.ingest_alert(alert)
    mgr.acknowledge_incident(inc.incident_id, "op_wrong", "TIER1")
    assert inc.status == IncidentStatus.ACKNOWLEDGED

    # Rejection returns incident to DETECTED
    ok = mgr.reject_acknowledgement(inc.incident_id, "op_wrong", "Wrong assignment group")
    assert ok is True
    assert inc.status == IncidentStatus.DETECTED
    assert inc.assigned_owner is None


def test_incident_recurrence_after_resolution_reopens():
    mgr = IncidentManager()
    now = datetime.now(timezone.utc)
    alert1 = OperationalAlert(
        alert_id="ALT-REC-1",
        source="ZABBIX",
        entity_id="CIR-MBA-01",
        metric_name="ifOperStatus",
        observed_value=2,
        severity=IncidentSeverity.P2_HIGH,
        summary="Mombasa MPLS circuit down",
        event_timestamp=now.isoformat(),
        station_id="MBA-STATION",
    )
    inc, _ = mgr.ingest_alert(alert1)
    
    # Resolve incident
    mgr.transition_state(inc.incident_id, IncidentStatus.RESOLVED, "noc_lead", "Service restored")
    assert inc.status == IncidentStatus.RESOLVED
    assert inc.resolved_at is not None

    # Within 20 minutes, same circuit trips again
    alert2 = OperationalAlert(
        alert_id="ALT-REC-2",
        source="ZABBIX",
        entity_id="CIR-MBA-01",
        metric_name="ifOperStatus",
        observed_value=2,
        severity=IncidentSeverity.P2_HIGH,
        summary="Mombasa MPLS circuit down again",
        event_timestamp=(now + timedelta(minutes=20)).isoformat(),
        station_id="MBA-STATION",
    )
    inc_rec, action_rec = mgr.ingest_alert(alert2)
    assert action_rec == "REOPENED"
    assert inc_rec.incident_id == inc.incident_id
    assert inc_rec.status == IncidentStatus.REOPENED
    assert inc_rec.recurrence_count == 1


def test_concurrent_worker_duplicate_prevention():
    mgr = IncidentManager()
    now = datetime.now(timezone.utc).isoformat()
    results = []

    def ingest_worker(idx: int):
        alt = OperationalAlert(
            alert_id=f"ALT-CONC-{idx}",
            source="ZABBIX",
            entity_id="SW-DC1-CONC",
            metric_name="link_loss",
            observed_value=1,
            severity=IncidentSeverity.P1_CRITICAL,
            summary="Concurrent alert storm",
            event_timestamp=now,
        )
        inc, act = mgr.ingest_alert(alt)
        results.append((inc.incident_id, act))

    threads = [threading.Thread(target=ingest_worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 1 CREATED and 9 DEDUPLICATED
    created_count = sum(1 for _, act in results if act == "CREATED")
    dedup_count = sum(1 for _, act in results if act == "DEDUPLICATED")
    assert created_count == 1
    assert dedup_count == 9
    assert len(mgr.get_active_incidents()) == 1


def test_incident_lifecycle_formal_state_transitions_and_forbidden_jumps():
    """Verify formal state lifecycle:
    NEW/DETECTED -> CORRELATED -> ACKNOWLEDGED -> INVESTIGATING -> REMEDIATING -> VERIFYING -> RESOLVED -> CLOSED.
    Also verify reopen, suppression, failed remediation, approval denial, and forbidden jumps.
    """
    mgr = IncidentManager()
    alert = OperationalAlert(
        alert_id="ALT-LIFE-01",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Switch reachability lost",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="JKIA-HUB",
    )
    inc, _ = mgr.ingest_alert(alert)
    iid = inc.incident_id
    assert inc.status == IncidentStatus.DETECTED

    # 1. Forward progression
    mgr.transition_state(iid, IncidentStatus.CORRELATED, "correlator", "Alert grouped with related alarms")
    assert inc.status == IncidentStatus.CORRELATED

    mgr.transition_state(iid, IncidentStatus.ACKNOWLEDGED, "duty_operator", "NOC operator took ownership")
    assert inc.status == IncidentStatus.ACKNOWLEDGED

    mgr.transition_state(iid, IncidentStatus.INVESTIGATING, "net_eng", "Investigating link topology and optics")
    assert inc.status == IncidentStatus.INVESTIGATING

    mgr.transition_state(iid, IncidentStatus.REMEDIATING, "net_eng", "Applying interface bounce via playbook")
    assert inc.status == IncidentStatus.REMEDIATING

    # 2. Failed remediation handling: fall back to investigating
    mgr.transition_state(iid, IncidentStatus.INVESTIGATING, "net_eng", "Bounce failed; escalating investigation")
    assert inc.status == IncidentStatus.INVESTIGATING

    # Re-enter remediation
    mgr.transition_state(iid, IncidentStatus.REMEDIATING, "net_eng", "Applying alternate fiber route failover")
    assert inc.status == IncidentStatus.REMEDIATING

    mgr.transition_state(iid, IncidentStatus.VERIFYING, "net_eng", "Monitoring post-failover ping telemetry")
    assert inc.status == IncidentStatus.VERIFYING

    # 3. Verification failure handling: retry remediation
    mgr.transition_state(iid, IncidentStatus.REMEDIATING, "net_eng", "Verification detected packet loss; retuning")
    assert inc.status == IncidentStatus.REMEDIATING

    mgr.transition_state(iid, IncidentStatus.VERIFYING, "net_eng", "Verifying retuned route")
    assert inc.status == IncidentStatus.VERIFYING

    # Verification passes -> RESOLVED
    mgr.transition_state(iid, IncidentStatus.RESOLVED, "net_eng", "Route clean; 0 packet loss confirmed")
    assert inc.status == IncidentStatus.RESOLVED
    assert inc.resolved_at is not None

    # Sign-off -> CLOSED
    mgr.transition_state(iid, IncidentStatus.CLOSED, "noc_lead", "Incident reviewed and closed")
    assert inc.status == IncidentStatus.CLOSED
    assert inc.closed_at is not None

    # 4. Reopen post-closure
    mgr.transition_state(iid, IncidentStatus.REOPENED, "noc_lead", "Route flapped again post-closure")
    assert inc.status == IncidentStatus.REOPENED
    assert inc.resolved_at is None
    assert inc.closed_at is None

    # 5. Forbidden state transitions must raise InvalidStateTransitionError
    # Cannot jump from REOPENED directly to CLOSED without resolution
    with pytest.raises(InvalidStateTransitionError):
        mgr.transition_state(iid, IncidentStatus.CLOSED, "bad_actor", "Illegal skip to CLOSED")

    # Move to RESOLVED then CLOSED
    mgr.transition_state(iid, IncidentStatus.RESOLVED, "net_eng", "Resolved again")
    mgr.transition_state(iid, IncidentStatus.CLOSED, "noc_lead", "Closed again")

    # Cannot jump from CLOSED directly to REMEDIATING without reopening
    with pytest.raises(InvalidStateTransitionError):
        mgr.transition_state(iid, IncidentStatus.REMEDIATING, "bad_actor", "Illegal direct remediate on closed")

    # 6. Test suppression and approval denial branches on a new incident
    alt_suppress = OperationalAlert(
        alert_id="ALT-SUPP-01",
        source="ZABBIX",
        entity_id="CIR-MBA-01",
        metric_name="maintenance_ping",
        observed_value=0,
        severity=IncidentSeverity.P3_MEDIUM,
        summary="Maintenance window noise",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="MBA-STATION",
    )
    inc_supp, _ = mgr.ingest_alert(alt_suppress)
    sid = inc_supp.incident_id

    # DETECTED -> SUPPRESSED -> CLOSED
    mgr.transition_state(sid, IncidentStatus.SUPPRESSED, "noc_operator", "Entity in scheduled maintenance")
    assert inc_supp.status == IncidentStatus.SUPPRESSED
    mgr.transition_state(sid, IncidentStatus.CLOSED, "noc_lead", "Closed under suppression")
    assert inc_supp.status == IncidentStatus.CLOSED

    # Test BLOCKED_APPROVAL_DENIED
    alt_denied = OperationalAlert(
        alert_id="ALT-DENY-01",
        source="ZABBIX",
        entity_id="SW-MBA-01",
        metric_name="high_temp",
        observed_value=85,
        severity=IncidentSeverity.P2_HIGH,
        summary="High temperature alert",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="MBA-STATION",
    )
    inc_deny, _ = mgr.ingest_alert(alt_denied)
    did = inc_deny.incident_id
    mgr.transition_state(did, IncidentStatus.CORRELATED, "system", "Correlated")
    mgr.transition_state(did, IncidentStatus.BLOCKED_APPROVAL_DENIED, "change_mgr", "Approval denied: freeze window")
    assert inc_deny.status == IncidentStatus.BLOCKED_APPROVAL_DENIED
    # Can return to INVESTIGATING or CLOSE
    mgr.transition_state(did, IncidentStatus.INVESTIGATING, "net_eng", "Investigating alternative manual workaround")
    assert inc_deny.status == IncidentStatus.INVESTIGATING

