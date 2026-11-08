"""Unit tests for Model Governance, Audit Trails & Operational Controls (Workstream 11G)."""

import pytest
from services.analytics.anomaly_detector import (
    AnomalyDirection,
    AnomalySeverity,
    StatisticalAnomalyResult,
)
from services.analytics.dynamic_baselines import DiurnalBaselineProfiler
from services.analytics.model_governance import (
    AuditEventType,
    ModelGovernanceEngine,
)


@pytest.fixture
def governance_setup():
    profiler = DiurnalBaselineProfiler(min_samples=10, version="1.0.0")
    gov = ModelGovernanceEngine(profiler=profiler)
    entity_id = "sw-core01::Gig1/0/1"
    metric = "ifInDiscardsRate"
    return gov, profiler, entity_id, metric


def test_hysteresis_and_persistence_gating(governance_setup):
    gov, profiler, entity_id, metric = governance_setup

    def make_result(val, z, streak):
        return StatisticalAnomalyResult(
            entity_id=entity_id,
            metric_name=metric,
            current_value=val,
            unit="pps",
            baseline_mean=1.0,
            baseline_median=1.0,
            baseline_mad=0.2,
            baseline_std_dev=0.5,
            baseline_p10=0.5,
            baseline_p90=1.5,
            z_score=z,
            modified_z_score=z,
            ewma_value=val,
            direction=AnomalyDirection.HIGH_ABNORMAL if z > 0 else AnomalyDirection.NORMAL,
            severity=AnomalySeverity.WARNING if z >= 3.0 else AnomalySeverity.NORMAL,
            is_anomaly=z >= 3.0,
            is_persistent=streak >= 3,
            consecutive_anomalous_samples=streak,
            confidence_score=0.85,
            status="EVALUATED",
            timestamp=1794125000.0,
        )

    # 1. First cycle: Z=3.5 >= 3.0, but streak=1 (< 3 required) -> Suppressed as flap
    is_active, evt = gov.process_anomaly_state_transition(make_result(10.0, 3.5, 1))
    assert is_active is False
    assert evt == AuditEventType.ANOMALY_SUPPRESSED_FLAP

    # 2. Second cycle: streak=2 -> Still suppressed
    is_active, evt = gov.process_anomaly_state_transition(make_result(11.0, 3.8, 2))
    assert is_active is False
    assert evt == AuditEventType.ANOMALY_SUPPRESSED_FLAP

    # 3. Third cycle: streak=3 -> Escalated to ANOMALY_RAISED!
    is_active, evt = gov.process_anomaly_state_transition(make_result(12.0, 4.0, 3))
    assert is_active is True
    assert evt == AuditEventType.ANOMALY_RAISED

    # 4. In hysteresis zone: Z drops to 2.2 (< 3.0 trigger, but >= 1.5 clear threshold)
    # The anomaly must REMAIN active!
    is_active, evt = gov.process_anomaly_state_transition(make_result(4.0, 2.2, 4))
    assert is_active is True
    assert evt is None  # No transition, remains active

    # 5. Clearance: Z drops to 1.1 (< 1.5 clear threshold) -> Anomaly clears!
    is_active, evt = gov.process_anomaly_state_transition(make_result(1.5, 1.1, 0))
    assert is_active is False
    assert evt == AuditEventType.ANOMALY_CLEARED


def test_baseline_freezing_during_active_anomaly(governance_setup):
    gov, profiler, entity_id, metric = governance_setup

    # Initially inactive: baseline should NOT be frozen
    assert gov.should_freeze_baseline_update(entity_id, metric) is False

    # Manually activate anomaly
    gov._active_anomalies[(entity_id, metric)] = True

    # Now baseline updates MUST be frozen to prevent learning outage as normal
    assert gov.should_freeze_baseline_update(entity_id, metric) is True


def test_version_checkpointing_and_rollback(governance_setup):
    gov, profiler, entity_id, metric = governance_setup

    # Create checkpoint v1.0.0
    gov.create_version_checkpoint("v1.0.0")
    assert "v1.0.0" in gov._version_archive

    # Change version
    profiler.version = "v2.0.0"
    assert profiler.version == "v2.0.0"

    # Rollback to v1.0.0
    success = gov.rollback_to_version("v1.0.0")
    assert success is True
    assert profiler.version == "v1.0.0"

    # Audit log must contain checkpoint and rollback records
    events = [r.event_type for r in gov.audit_log]
    assert AuditEventType.BASELINE_UPDATED in events
    assert AuditEventType.MODEL_ROLLBACK in events

