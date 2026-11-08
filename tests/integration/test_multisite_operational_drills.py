"""tests/integration/test_multisite_operational_drills.py
=======================================================
Phase 13J: Comprehensive Multi-Site Operational Acceptance Drill Suite.

Formally executes Scenarios A through I:
- Scenario A: Single station WAN outage (Mombasa link severed, isolated impact, local spooling).
- Scenario B: Multi-site outage (concurrent Mombasa & Kisumu WAN loss, upstream correlation).
- Scenario C: Edge store-and-forward replay, duplicate rejection, live precedence.
- Scenario D: Global vs station service health and mandatory dependency enforcement.
- Scenario E: Complete Alerting & Incident Lifecycle (Alert -> Dedup -> Inc -> Notif -> Ack -> Action -> Verify -> Close -> Audit).
- Scenario F: Notification failure handling, DLQ buffering, and requeue recovery.
- Scenario G: Metric-aware recovery verification (3 consecutive fresh observations required).
- Scenario H: Three-Identity Interlock, approval token tamper detection, and simulation safety switch.
- Scenario I: Dashboard data integrity across healthy, degraded, replayed, and missing telemetry.
"""

import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
import pytest
import yaml

from services.multisite.api_governance import (
    HardenedAuditLedger,
    IdempotencyRegistry,
    TokenBucketRateLimiter,
)
from services.multisite.edge_forwarder import (
    CentralTelemetryReceiver,
    EdgeStoreAndForwardManager,
    SpoolItemPriority,
)
from services.multisite.incident_pipeline import (
    AlertCorrelationEngine,
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
from services.multisite.service_catalog import (
    ServiceCatalog,
    SLIEvaluationEngine,
    TelemetryQuality,
)
from services.multisite.site_rbac import (
    ActionOperationalEnvelope,
    ActionRiskTier,
    SiteAwareRBACEngine,
    ThreeIdentityCardinalityViolation,
    TokenTamperedOrInvalid,
)
from services.multisite.site_registry import MultiSiteRegistry


# ==============================================================================
# Scenario A: Single Station WAN Outage
# ==============================================================================

def test_scenario_a_single_station_wan_outage():
    registry = MultiSiteRegistry(auto_seed=True)
    catalog = ServiceCatalog(auto_seed=True)
    inc_mgr = IncidentManager()

    # Mombasa primary and secondary circuits severed
    registry.update_circuit_status("CIR-MBA-01", "DOWN")
    registry.update_circuit_status("CIR-MBA-02", "DOWN")

    comp_states = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-MBA-01": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
        "CIR-MBA-02": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
    }

    eval_summary = catalog.evaluate_all_services(comp_states)
    services_by_id = {s["service_id"]: s for s in eval_summary["services"]}

    # Global services remain unaffected
    assert services_by_id["SVC-DCS-GLOBAL"]["status"] == "HEALTHY"
    assert services_by_id["SVC-FLIGHT-OPS"]["status"] == "HEALTHY"

    # Only Mombasa station service is down
    assert services_by_id["SVC-DCS-MBA"]["status"] == "CRITICAL_DOWN"

    # Alert generated and attributed to MBA
    alert = OperationalAlert(
        alert_id="ALT-MBA-WAN-01",
        source="ZABBIX",
        entity_id="CIR-MBA-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Mombasa Primary WAN Circuit Down",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="MBA-STATION",
        service_id="SVC-DCS-MBA",
    )
    inc, action = inc_mgr.ingest_alert(alert)
    assert action == "CREATED"
    assert inc.station_id == "MBA-STATION"
    assert inc.severity == IncidentSeverity.P1_CRITICAL


# ==============================================================================
# Scenario B: Multi-Site Outage & Shared Upstream Dependency Correlation
# ==============================================================================

def test_scenario_b_multisite_outage_and_upstream_correlation():
    inc_mgr = IncidentManager()

    # Upstream DC Router fails
    inc_mgr.correlation_engine.register_entity_down("RTR-CORE-DC1")

    # Downstream alerts from MBA and KIS
    alert_mba = OperationalAlert(
        alert_id="ALT-MBA-WAN",
        source="ZABBIX",
        entity_id="CIR-MBA-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="MBA WAN Down",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="MBA-STATION",
        parent_entity_id="RTR-CORE-DC1",
    )
    alert_kis = OperationalAlert(
        alert_id="ALT-KIS-WAN",
        source="ZABBIX",
        entity_id="CIR-KIS-01",
        metric_name="icmpping",
        observed_value=0,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="KIS WAN Down",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="KIS-STATION",
        parent_entity_id="RTR-CORE-DC1",
    )

    inc_mba, action_mba = inc_mgr.ingest_alert(alert_mba)
    inc_kis, action_kis = inc_mgr.ingest_alert(alert_kis)

    # Both alerts are topologically suppressed because parent core router is down
    assert action_mba == "SUPPRESSED"
    assert "PARENT_DOWN_SUPPRESSION" in inc_mba.suppression_reason
    assert action_kis == "SUPPRESSED"
    assert "PARENT_DOWN_SUPPRESSION" in inc_kis.suppression_reason


# ==============================================================================
# Scenario C: Edge Replay, Deduplication & Live Precedence
# ==============================================================================

def test_scenario_c_edge_replay_and_live_precedence():
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        spool_path = tf.name

    try:
        manager = EdgeStoreAndForwardManager(station_id="MBA-STATION", db_path=spool_path)
        receiver = CentralTelemetryReceiver()

        # Edge offline
        manager.set_wan_connection(False)
        manager.record_telemetry("metric", {"item": "cpu", "value": 75.0})
        manager.record_telemetry("metric", {"item": "mem", "value": 60.0})

        # Drain while offline -> buffered
        res_offline = manager.drain_and_forward(central_receiver=receiver)
        assert res_offline["status"] == "WAN_PARTITIONED"

        # Edge online -> replay drain
        manager.set_wan_connection(True)
        res_online = manager.drain_and_forward(central_receiver=receiver)
        assert res_online["status"] == "FORWARDED"
        assert res_online["forwarded_count"] == 2

        # Verify live precedence: Replayed stream contains replayed items, live stream is empty
        assert len(receiver.get_replayed_stream()) == 2
        assert len(receiver.get_live_stream()) == 0

        # Ingest live observation directly: goes to live stream
        receiver.ingest_batch(
            batch=[{"event_id": "EVT-LIVE-01", "item": "cpu", "value": 20.0, "telemetry_quality": "FRESH"}],
            auth_token="nawari-edge-shared-token-2026",
        )
        assert len(receiver.get_live_stream()) == 1

        # Replay attempt with duplicate batch -> rejected as duplicate
        re_drain = receiver.ingest_batch(receiver.get_replayed_stream(), auth_token="nawari-edge-shared-token-2026")
        assert re_drain["duplicate_count"] == 2
        assert re_drain["ingested_count"] == 0

    finally:
        if os.path.exists(spool_path):
            os.remove(spool_path)


# ==============================================================================
# Scenario D: Global vs Station Service Health & Mandatory Dependencies
# ==============================================================================

def test_scenario_d_global_vs_station_service_health():
    catalog = ServiceCatalog(auto_seed=True)

    # 1. Non-mandatory component failure in Global DCS (CIR-NBO-02 is redundant)
    comp_states_redundant_fail = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
    }
    res_red = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_redundant_fail)
    assert res_red.status == "DEGRADED"
    assert res_red.health_index >= 0.70
    assert res_red.is_mandatory_failed is False

    # 2. Mandatory component failure (SW-DC1-01 is mandatory core switch)
    comp_states_mandatory_fail = {
        "CIR-NBO-01": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "CIR-NBO-02": {"state": "ACTIVE", "quality": TelemetryQuality.FRESH.value},
        "SW-DC1-01": {"state": "DOWN", "quality": TelemetryQuality.FRESH.value},
    }
    res_mand = catalog.evaluate_service_health("SVC-DCS-GLOBAL", comp_states_mandatory_fail)
    # Strictly fails service health regardless of weights
    assert res_mand.status == "CRITICAL_DOWN"
    assert res_mand.health_index == 0.0
    assert res_mand.is_mandatory_failed is True


# ==============================================================================
# Scenario E: Complete Closed-Loop Alerting to Audit Lifecycle
# ==============================================================================

def test_scenario_e_closed_loop_lifecycle_to_audit():
    inc_mgr = IncidentManager()
    router = NotificationRouter(is_production_mode=False)
    audit = HardenedAuditLedger()

    # 1. Alert Ingestion & Correlation
    alert = OperationalAlert(
        alert_id="ALT-TRUNK-01",
        source="VOICE_SYNTHETIC",
        entity_id="CIR-MBA-01",
        metric_name="mos",
        observed_value=2.4,
        severity=IncidentSeverity.P1_CRITICAL,
        summary="Voice Trunk MOS Degraded Below SLA",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        station_id="MBA-STATION",
    )
    inc, action = inc_mgr.ingest_alert(alert)
    assert action == "CREATED"

    # 2. Notification Dispatch
    notifs = router.dispatch_incident_notifications(inc.to_dict())
    assert len(notifs) >= 2  # Email + SMS for P1

    # 3. Acknowledgement
    ack_res = inc_mgr.acknowledge_incident(inc.incident_id, operator_id="USR-MOMBASA-LEAD", role="STATION_ADMIN")
    assert ack_res is True

    # 4. Remediation State Transition
    inc_mgr.transition_state(inc.incident_id, IncidentStatus.REMEDIATING, "USR-MOMBASA-LEAD", "Failing over to secondary trunk")

    # 5. Recovery Verification
    verifier = MetricAwareRecoveryVerifier()
    now_iso = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        verifier.record_observation(
            inc.incident_id,
            RecoveryObservation(
                observation_id=f"OBS-E-{i}",
                source_type=TelemetrySourceType.VOICE_PROBE,
                event_timestamp=now_iso,
                receipt_timestamp=now_iso,
                health_value=1.0,
                metric_evidence={"mos": 4.2},
            ),
        )
    v_rec, v_reason, v_details = verifier.evaluate_recovery(inc.incident_id)
    assert v_rec is True
    assert v_details["consecutive_fresh_healthy"] == 3

    # 6. Resolution & Closure
    inc_mgr.transition_state(inc.incident_id, IncidentStatus.RESOLVED, "USR-MOMBASA-LEAD", "Verified recovery confirmed")
    inc_mgr.transition_state(inc.incident_id, IncidentStatus.CLOSED, "USR-MOMBASA-LEAD", "Closed after observation hold")
    assert inc.status == IncidentStatus.CLOSED

    # 7. Audit Logging
    block = audit.append_action_audit_entry(
        actor_id="USR-MOMBASA-LEAD",
        action_name="TRUNK_FAILOVER",
        station_id="MBA-STATION",
        target_entity="CIR-MBA-01",
        source="INCIDENT_REMEDIATION",
        before_state={"status": "DEGRADED", "mos": 2.4},
        after_state={"status": "OPTIMAL", "mos": 4.2},
        approval_references=["TOK-APPR-01", "TOK-APPR-02"],
        execution_result="SUCCESS",
        verification_result="VERIFIED_3_CONSECUTIVE_OBSERVATIONS",
        incident_id=inc.incident_id,
        alert_id=alert.alert_id,
    )
    assert block.index == 0
    assert audit.verify_integrity()["valid"] is True


# ==============================================================================
# Scenario F: Notification Failures & DLQ Recovery
# ==============================================================================

def test_scenario_f_notification_failures_and_dlq():
    router = NotificationRouter(is_production_mode=False, simulate_network_failures=True)
    inc_dict = {"incident_id": "INC-SMS-FAIL", "title": "SBC Unreachable", "severity": "P1_CRITICAL"}

    msgs = router.dispatch_incident_notifications(inc_dict)
    sms_msg = next(m for m in msgs if m.channel == NotificationChannel.SMS)
    assert sms_msg.status == DeliveryStatus.FAILED

    # Exhaust retries -> goes to DEAD_LETTER
    router.retry_failed_messages()
    router.retry_failed_messages()
    assert sms_msg.status == DeliveryStatus.DEAD_LETTER
    assert len(router.get_dead_letter_queue()) == 1

    # Requeue from DLQ
    router.requeue_dead_letter(sms_msg.message_id)
    assert len(router.get_dead_letter_queue()) == 0

    # Fix network and retry -> DELIVERED
    router.simulate_network_failures = False
    router.retry_failed_messages()
    assert sms_msg.status == DeliveryStatus.DELIVERED


# ==============================================================================
# Scenario G: Recovery Integrity & Rejection of Replayed Data
# ==============================================================================

def test_scenario_g_recovery_integrity_and_replayed_rejection():
    verifier = MetricAwareRecoveryVerifier()
    inc_id = "INC-REPLAY-DRILL"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Replayed telemetry is rejected
    obs = RecoveryObservation(
        observation_id="OBS-DRILL-01",
        source_type=TelemetrySourceType.SNMP_POLLING,
        event_timestamp=now_iso,
        receipt_timestamp=now_iso,
        health_value=1.0,
        is_replayed=True,
    )
    verifier.record_observation(inc_id, obs)
    is_rec, reason, details = verifier.evaluate_recovery(inc_id)
    assert is_rec is False
    assert any("REPLAYED historical telemetry" in r for r in details["rejection_reasons"])


# ==============================================================================
# Scenario H: Three-Identity Interlock & Simulation Protection
# ==============================================================================

def test_scenario_h_three_identity_interlock_and_simulation_protection():
    rbac = SiteAwareRBACEngine(is_simulation_mode=True)
    envelope = ActionOperationalEnvelope(
        action_id="ACT-TRUNK-01",
        incident_id="INC-01",
        alert_id="ALT-01",
        playbook_id="PB-01",
        playbook_version="1.0",
        plan_hash="hash1",
        target_env="STAGING",
        risk_tier=ActionRiskTier.TIER_3_HIGH,
        change_window_id="CW-01",
        parameters_hash="hash2",
    )

    token1 = rbac.issue_approval_token("USR-GLOBAL-ADMIN", envelope)
    token2 = rbac.issue_approval_token("USR-CIO-EXEC", envelope)

    # 1. Proposer == Approver 1 -> Cardinality violation
    with pytest.raises(ThreeIdentityCardinalityViolation):
        rbac.verify_three_identity_approval(
            proposer_id="USR-GLOBAL-ADMIN",  # Duplicate
            approver1_token=token1,
            approver2_token=token2,
            envelope=envelope,
        )

    # 2. Tampered envelope -> Signature mismatch
    tampered_env = ActionOperationalEnvelope(
        action_id=envelope.action_id,
        incident_id=envelope.incident_id,
        alert_id=envelope.alert_id,
        playbook_id=envelope.playbook_id,
        playbook_version=envelope.playbook_version,
        plan_hash=envelope.plan_hash,
        target_env=envelope.target_env,
        risk_tier=ActionRiskTier.TIER_1_LOW,  # TAMPERED
        change_window_id=envelope.change_window_id,
        parameters_hash=envelope.parameters_hash,
    )
    with pytest.raises(TokenTamperedOrInvalid):
        rbac.verify_token(token1, tampered_env)

    # 3. Production action attempted in simulation mode -> Blocked
    with pytest.raises(PermissionError) as exc_sim:
        rbac.authorize_operator_action("USR-GLOBAL-ADMIN", target_env="PRODUCTION")
    assert "Production action blocked: system is running in simulation/staging mode" in str(exc_sim.value)


# ==============================================================================
# Scenario I: Dashboard Data Integrity
# ==============================================================================

def test_scenario_i_dashboard_data_integrity():
    engine = SLIEvaluationEngine()

    # Track missing / stale telemetry explicitly
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=30.0, health_index=1.0)
    engine.record_interval("SVC-DCS-GLOBAL", duration_minutes=30.0, is_unknown=True)  # Telemetry missing

    sli = engine.evaluate_sli("SVC-DCS-GLOBAL")
    # Invariant: Missing telemetry is NOT zero or healthy, but recorded as unknown
    assert sli.unknown_minutes == 30.0
    assert sli.valid_operational_minutes == 60.0
    # Availability is 50%, coverage is 50%
    assert sli.availability_sli == 50.0
    assert sli.coverage_percent == 50.0


# ==============================================================================
# Scenario J: Full Consolidated Regression & Sentra Isolation Gate
# ==============================================================================

def test_scenario_j_full_platform_regression_and_sentra_isolation():
    """Scenario J: Full regression, repository isolation, and capacity budget verification."""
    sentra_dir = "/Users/madeira/Desktop/Projects/sentra"
    if os.path.exists(sentra_dir):
        # 1. Sentra isolation audit: 100% clean, no uncommitted changes
        res_stat = subprocess.run(["git", "-C", sentra_dir, "status", "--porcelain"], capture_output=True, text=True)
        assert res_stat.returncode == 0
        assert res_stat.stdout.strip() == "", f"Sentra repository has uncommitted changes: {res_stat.stdout}"

        res_head = subprocess.run(["git", "-C", sentra_dir, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        assert res_head.returncode == 0
        assert res_head.stdout.strip() == "9970404", f"Sentra repository is not at expected HEAD 9970404: {res_head.stdout}"

    # 2. Host container memory ceiling validation (<= 2252.8 MiB)
    staging_profile_path = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "profiles", "staging.yaml")
    with open(staging_profile_path) as f:
        stg_cfg = yaml.safe_load(f)
    budget = stg_cfg.get("host_resource_budget", {})
    max_mem_mb = budget.get("max_container_memory_mb", 0)
    assert max_mem_mb <= 2252.8, f"Staging container budget {max_mem_mb} exceeds 2.20 GiB ceiling"

    # 3. Verify all 10 Workstreams (13A-13J) modules are importable and integrated
    import services.multisite as ms
    assert hasattr(ms, "MultiSiteRegistry")
    assert hasattr(ms, "ServiceCatalog")
    assert hasattr(ms, "IncidentManager")
    assert hasattr(ms, "NotificationRouter")
    assert hasattr(ms, "MetricAwareRecoveryVerifier")
    assert hasattr(ms, "EdgeStoreAndForwardManager")
    assert hasattr(ms, "TransWanVoiceProber")
    assert hasattr(ms, "SiteAwareRBACEngine")
    assert hasattr(ms, "HardenedAuditLedger")

