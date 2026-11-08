"""Unit tests for Metric-Aware Recovery Verifier (Workstream 13C)."""

from datetime import datetime, timedelta, timezone
import pytest

from services.multisite.recovery_verifier import (
    MetricAwareRecoveryVerifier,
    RecoveryObservation,
    TelemetrySourceProfile,
    TelemetrySourceType,
)


def test_three_consecutive_fresh_healthy_observations_satisfies_recovery():
    verifier = MetricAwareRecoveryVerifier()
    inc_id = "INC-REC-001"
    now = datetime.now(timezone.utc)

    # 1. Observation 1: Healthy (1/3)
    t1 = (now - timedelta(seconds=20)).isoformat()
    obs1 = RecoveryObservation("OBS-1", TelemetrySourceType.SYNTHETIC_PROBE, t1, t1, health_value=1.0)
    verifier.record_observation(inc_id, obs1)
    rec1, _, details1 = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert rec1 is False
    assert details1["consecutive_fresh_healthy"] == 1

    # 2. Observation 2: Healthy (2/3)
    t2 = (now - timedelta(seconds=10)).isoformat()
    obs2 = RecoveryObservation("OBS-2", TelemetrySourceType.SYNTHETIC_PROBE, t2, t2, health_value=1.0)
    verifier.record_observation(inc_id, obs2)
    rec2, _, details2 = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert rec2 is False
    assert details2["consecutive_fresh_healthy"] == 2

    # 3. Observation 3: Healthy (3/3) -> Satisfies recovery!
    t3 = (now - timedelta(seconds=2)).isoformat()
    obs3 = RecoveryObservation("OBS-3", TelemetrySourceType.SYNTHETIC_PROBE, t3, t3, health_value=0.95)
    verifier.record_observation(inc_id, obs3)
    rec3, reason3, details3 = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert rec3 is True
    assert details3["consecutive_fresh_healthy"] == 3
    assert "VERIFIED_RECOVERY" in reason3


def test_replayed_telemetry_is_strictly_rejected():
    verifier = MetricAwareRecoveryVerifier()
    inc_id = "INC-REPLAY-REJECT"
    now = datetime.now(timezone.utc)

    # Replayed observations arriving from outstation buffer
    t1 = (now - timedelta(seconds=5)).isoformat()
    obs1 = RecoveryObservation("OBS-REPLAY-1", TelemetrySourceType.SYNTHETIC_PROBE, t1, t1, health_value=1.0, is_replayed=True)
    obs2 = RecoveryObservation("OBS-REPLAY-2", TelemetrySourceType.SYNTHETIC_PROBE, t1, t1, health_value=1.0, is_replayed=True)
    obs3 = RecoveryObservation("OBS-REPLAY-3", TelemetrySourceType.SYNTHETIC_PROBE, t1, t1, health_value=1.0, is_replayed=True)
    
    verifier.record_observation(inc_id, obs1)
    verifier.record_observation(inc_id, obs2)
    verifier.record_observation(inc_id, obs3)

    is_rec, reason, details = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert is_rec is False
    assert details["consecutive_fresh_healthy"] == 0
    assert any("REPLAYED historical telemetry" in r for r in details["rejection_reasons"])


def test_stale_telemetry_is_strictly_rejected():
    verifier = MetricAwareRecoveryVerifier()
    inc_id = "INC-STALE-REJECT"
    now = datetime.now(timezone.utc)

    # Synthetic probe max freshness is 30.0s. Capture an observation 60s ago.
    t_stale = (now - timedelta(seconds=60)).isoformat()
    obs = RecoveryObservation("OBS-STALE", TelemetrySourceType.SYNTHETIC_PROBE, t_stale, t_stale, health_value=1.0)
    verifier.record_observation(inc_id, obs)

    is_rec, reason, details = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert is_rec is False
    assert any("STALE telemetry" in r for r in details["rejection_reasons"])


def test_metric_aware_source_freshness_windows():
    verifier = MetricAwareRecoveryVerifier()
    now = datetime.now(timezone.utc)

    # 1. SNMP polling has a 90s freshness window
    t_snmp = (now - timedelta(seconds=70)).isoformat()  # 70s is fresh for SNMP, but stale for Synthetic Probe (30s)
    obs_snmp = RecoveryObservation("OBS-SNMP", TelemetrySourceType.SNMP_POLLING, t_snmp, t_snmp, health_value=1.0)
    res_snmp = verifier.record_observation("INC-SNMP", obs_snmp)
    assert res_snmp["is_fresh"] is True

    # 2. Synthetic probe has a 30s freshness window -> 70s is STALE
    obs_probe = RecoveryObservation("OBS-PROBE", TelemetrySourceType.SYNTHETIC_PROBE, t_snmp, t_snmp, health_value=1.0)
    res_probe = verifier.record_observation("INC-PROBE", obs_probe)
    assert res_probe["is_fresh"] is False


def test_unhealthy_observation_breaks_consecutive_chain():
    verifier = MetricAwareRecoveryVerifier()
    inc_id = "INC-FLAP"
    now = datetime.now(timezone.utc)

    # 2 healthy observations
    obs1 = RecoveryObservation("OBS-1", TelemetrySourceType.SYNTHETIC_PROBE, now.isoformat(), now.isoformat(), health_value=1.0)
    obs2 = RecoveryObservation("OBS-2", TelemetrySourceType.SYNTHETIC_PROBE, now.isoformat(), now.isoformat(), health_value=1.0)
    verifier.record_observation(inc_id, obs1)
    verifier.record_observation(inc_id, obs2)

    # 1 degraded observation (breaks the chain)
    obs3 = RecoveryObservation("OBS-3", TelemetrySourceType.SYNTHETIC_PROBE, now.isoformat(), now.isoformat(), health_value=0.50)
    verifier.record_observation(inc_id, obs3)

    is_rec, _, details = verifier.evaluate_recovery(inc_id, evaluation_time=now)
    assert is_rec is False
    assert details["consecutive_fresh_healthy"] == 0

