"""Unit tests for Statistical Anomaly Detection Engine (Workstream 11C)."""

import pytest
from services.analytics.anomaly_detector import (
    AnomalyDirection,
    AnomalySeverity,
    MetricThresholdConfig,
    StatisticalAnomalyDetector,
)
from services.analytics.dynamic_baselines import DiurnalBaselineProfiler
from services.analytics.telemetry_foundation import (
    DomainType,
    TelemetryObservation,
    TelemetryProvenance,
)


@pytest.fixture
def trained_detector():
    profiler = DiurnalBaselineProfiler(min_samples=30)
    detector = StatisticalAnomalyDetector(profiler=profiler)

    entity_id = "sw-core01::GigabitEthernet1/0/1"
    metric = "ifInDiscardsRate"
    t_base = 1794124800.0  # Hour 8, Weekday

    # Ingest 40 normal baseline samples: mean ~ 2.0 pps, std_dev ~ 0.5
    for i in range(40):
        val = 2.0 + (0.4 if i % 2 == 0 else -0.4)
        profiler.record_observation(
            TelemetryObservation(
                entity_id=entity_id,
                metric_name=metric,
                value=val,
                unit="pps",
                timestamp=t_base + (i * 60.0),
                domain=DomainType.NETWORK,
                provenance=TelemetryProvenance.LIVE_SNMP,
            )
        )
    return detector, profiler, entity_id, metric, t_base


def test_normal_telemetry_evaluation(trained_detector):
    detector, profiler, entity_id, metric, t_base = trained_detector

    normal_obs = TelemetryObservation(
        entity_id=entity_id,
        metric_name=metric,
        value=2.1,
        unit="pps",
        timestamp=t_base + 3000.0,
        domain=DomainType.NETWORK,
        provenance=TelemetryProvenance.LIVE_SNMP,
    )
    result = detector.evaluate(normal_obs)
    assert result.is_anomaly is False
    assert result.severity == AnomalySeverity.NORMAL
    assert result.direction == AnomalyDirection.NORMAL
    assert result.current_value == 2.1
    assert result.unit == "pps"


def test_critical_discard_anomaly_detection(trained_detector):
    detector, profiler, entity_id, metric, t_base = trained_detector

    # Baseline is ~2.0 pps. Value of 18.0 pps is an extreme outlier (> 30 sigma)
    spike_obs = TelemetryObservation(
        entity_id=entity_id,
        metric_name=metric,
        value=18.0,
        unit="pps",
        timestamp=t_base + 3100.0,
        domain=DomainType.NETWORK,
        provenance=TelemetryProvenance.LIVE_SNMP,
    )
    result = detector.evaluate(spike_obs)
    assert result.is_anomaly is True
    assert result.severity == AnomalySeverity.CRITICAL
    assert result.direction == AnomalyDirection.HIGH_ABNORMAL
    assert result.z_score > 4.5
    assert result.confidence_score > 0.80


def test_voice_mos_absolute_delta_mode():
    profiler = DiurnalBaselineProfiler(min_samples=30)
    detector = StatisticalAnomalyDetector(profiler=profiler)
    trunk = "voice_trunk::primary_safaricom"
    t_base = 1794124800.0

    # Train 35 normal MOS samples (4.30)
    for i in range(35):
        profiler.record_observation(
            TelemetryObservation(
                entity_id=trunk,
                metric_name="mos",
                value=4.30,
                unit="score",
                timestamp=t_base + (i * 60.0),
                domain=DomainType.VOICE_MEDIA,
                provenance=TelemetryProvenance.ASTERISK_AMI,
            )
        )

    # 1. Single sample drop to 3.85 (delta = 0.45 >= 0.30 warning delta)
    obs_drop1 = TelemetryObservation(
        entity_id=trunk,
        metric_name="mos",
        value=3.85,
        unit="score",
        timestamp=t_base + 3000.0,
        domain=DomainType.VOICE_MEDIA,
        provenance=TelemetryProvenance.ASTERISK_AMI,
    )
    res1 = detector.evaluate(obs_drop1)
    assert res1.is_anomaly is True
    assert res1.severity == AnomalySeverity.WARNING
    assert res1.direction == AnomalyDirection.LOW_ABNORMAL
    # MOS requires min_consecutive_samples=2, so sample 1 is not yet persistent
    assert res1.is_persistent is False
    assert res1.consecutive_anomalous_samples == 1

    # 2. Second consecutive sample drop to 3.80
    obs_drop2 = TelemetryObservation(
        entity_id=trunk,
        metric_name="mos",
        value=3.80,
        unit="score",
        timestamp=t_base + 3060.0,
        domain=DomainType.VOICE_MEDIA,
        provenance=TelemetryProvenance.ASTERISK_AMI,
    )
    res2 = detector.evaluate(obs_drop2)
    assert res2.is_anomaly is True
    assert res2.is_persistent is True  # Reached streak of 2!
    assert res2.consecutive_anomalous_samples == 2


def test_zero_drop_telemetry_detection():
    profiler = DiurnalBaselineProfiler(min_samples=30)
    detector = StatisticalAnomalyDetector(profiler=profiler)
    entity_id = "sbce-jkia-pri"
    metric = "active_sessions"
    t_base = 1794124800.0

    # Normal session count ~ 250
    for i in range(35):
        profiler.record_observation(
            TelemetryObservation(
                entity_id=entity_id,
                metric_name=metric,
                value=250.0,
                unit="sessions",
                timestamp=t_base + (i * 60.0),
                domain=DomainType.SYSTEM,
                provenance=TelemetryProvenance.AVAYA_SBCE,
            )
        )

    # Sudden complete silence / drop to 0 sessions
    obs_zero = TelemetryObservation(
        entity_id=entity_id,
        metric_name=metric,
        value=0.0,
        unit="sessions",
        timestamp=t_base + 3000.0,
        domain=DomainType.SYSTEM,
        provenance=TelemetryProvenance.AVAYA_SBCE,
    )
    result = detector.evaluate(obs_zero)
    assert result.is_anomaly is True
    assert result.direction == AnomalyDirection.ZERO_DROP
    assert result.severity == AnomalySeverity.CRITICAL

