"""Integration test for Nawari Closed-Loop Incident Management and Notification Pipeline (Workstream 13C).

Demonstrates the Complete Closed-Loop Operational Chain:
Monitoring Detection -> Incident Creation -> Multi-Channel Notifications (SMTP/SMS/ITSM)
-> Operator Acknowledgment -> Phase 12 Controlled Remediation Lineage
-> Metric-Aware Fresh Recovery Verification -> Verified Resolution & Closure.
"""

from datetime import datetime, timezone
import pytest

from services.multisite.incident_pipeline import (
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
    OperationalAlert,
)
from services.multisite.notifications import (
    DeliveryStatus,
    NotificationChannel,
    NotificationRouter,
)
from services.multisite.recovery_verifier import (
    MetricAwareRecoveryVerifier,
    RecoveryObservation,
    TelemetrySourceType,
)


def test_closed_loop_incident_to_recovery_pipeline():
    # 1. Initialize subsystem components
    mgr = IncidentManager()
    router = NotificationRouter(is_production_mode=False)
    verifier = MetricAwareRecoveryVerifier()

    now = datetime.now(timezone.utc)

    # 2. Ingest Critical Outage Alert
    raw_alert = OperationalAlert(
        alert_id="ALT-CORE-001",
        source="ZABBIX",
        entity_id="SW-DC1-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Core Datacenter Switch SW-DC1-01 Unreachable",
        event_timestamp=now.isoformat(),
        station_id="JKIA-HUB",
        service_id="SVC-DCS-GLOBAL",
    )
    inc, action = mgr.ingest_alert(raw_alert)
    assert action == "CREATED"
    assert inc.status == IncidentStatus.DETECTED
    assert inc.severity == IncidentSeverity.P1_CRITICAL

    # 3. Dispatch Multi-Channel Notifications (SMTP Email, SMS Paging, ServiceNow ITSM)
    dispatched_msgs = router.dispatch_incident_notifications(inc.to_dict())
    assert len(dispatched_msgs) == 3
    channels = {m.channel for m in dispatched_msgs}
    assert NotificationChannel.SMTP_EMAIL in channels
    assert NotificationChannel.SMS in channels
    assert NotificationChannel.SERVICENOW_ITSM in channels
    assert all(m.status == DeliveryStatus.DELIVERED for m in dispatched_msgs)

    # Verify ITSM ticket was created
    itsm_ticket = router.get_itsm_ticket(inc.incident_id)
    assert itsm_ticket is not None
    assert itsm_ticket["state"] == "New"
    assert itsm_ticket["urgency"] == "1 - High"

    # 4. Human Operator Acknowledges Incident
    ack_ok = mgr.acknowledge_incident(inc.incident_id, "noc_lead_01", "SENIOR_NOC_ENGINEER")
    assert ack_ok is True
    assert inc.status == IncidentStatus.ACKNOWLEDGED
    assert inc.assigned_owner == "noc_lead_01"

    # 5. Move to INVESTIGATING and REMEDIATING
    mgr.transition_state(inc.incident_id, IncidentStatus.INVESTIGATING, "noc_lead_01", "Starting diagnosis and topology path check.")
    assert inc.status == IncidentStatus.INVESTIGATING

    mgr.transition_state(inc.incident_id, IncidentStatus.REMEDIATING, "noc_lead_01", "Executing approved Phase 12 remediation playbook.")
    assert inc.status == IncidentStatus.REMEDIATING
    
    # Link Phase 12 Remediation Action Lineage
    simulated_action_id = "ACT-REM-12345"
    simulated_audit_hash = "f5a8b9c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9"
    inc.remediation_action_id = simulated_action_id
    inc.audit_block_hash = simulated_audit_hash

    # 6. Move to VERIFYING
    mgr.transition_state(inc.incident_id, IncidentStatus.VERIFYING, "noc_lead_01", "Remediation step executed; awaiting independent fresh telemetry verification.")
    assert inc.status == IncidentStatus.VERIFYING

    # 7. Verification Invariant Check 1: Replayed telemetry rejected
    replayed_obs = RecoveryObservation(
        observation_id="OBS-REP-01",
        source_type=TelemetrySourceType.SYNTHETIC_PROBE,
        event_timestamp=now.isoformat(),
        receipt_timestamp=now.isoformat(),
        health_value=1.0,
        is_replayed=True,
    )
    verifier.record_observation(inc.incident_id, replayed_obs)
    is_rec, reason, _ = verifier.evaluate_recovery(inc.incident_id)
    assert is_rec is False
    assert "REPLAYED historical telemetry" in reason
    # Incident remains in VERIFYING / cannot close!
    assert inc.status == IncidentStatus.VERIFYING

    # 8. Verification Invariant Check 2: Fresh live observations arrive
    t_live = datetime.now(timezone.utc).isoformat()
    obs1 = RecoveryObservation("OBS-LIVE-01", TelemetrySourceType.SYNTHETIC_PROBE, t_live, t_live, health_value=1.0)
    obs2 = RecoveryObservation("OBS-LIVE-02", TelemetrySourceType.SYNTHETIC_PROBE, t_live, t_live, health_value=1.0)
    obs3 = RecoveryObservation("OBS-LIVE-03", TelemetrySourceType.SYNTHETIC_PROBE, t_live, t_live, health_value=0.98)
    verifier.record_observation(inc.incident_id, obs1)
    verifier.record_observation(inc.incident_id, obs2)
    verifier.record_observation(inc.incident_id, obs3)

    is_recovered, rec_reason, details = verifier.evaluate_recovery(inc.incident_id)
    assert is_recovered is True
    assert details["consecutive_fresh_healthy"] == 3
    assert "VERIFIED_RECOVERY" in rec_reason

    # 9. Formally Transition to RESOLVED then CLOSED
    mgr.transition_state(inc.incident_id, IncidentStatus.RESOLVED, "noc_lead_01", f"Service recovery confirmed: {rec_reason}")
    assert inc.status == IncidentStatus.RESOLVED
    assert inc.resolved_at is not None

    mgr.transition_state(inc.incident_id, IncidentStatus.CLOSED, "noc_lead_01", "Post-incident verification complete.")
    assert inc.status == IncidentStatus.CLOSED
    assert inc.closed_at is not None

    # 10. Verify Full Traceable Lineage
    inc_dict = inc.to_dict()
    assert inc_dict["root_cause_alert_id"] == "ALT-CORE-001"
    assert inc_dict["remediation_action_id"] == simulated_action_id
    assert inc.audit_block_hash == simulated_audit_hash
    assert len(inc.work_notes) >= 5

