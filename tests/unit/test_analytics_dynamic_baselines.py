"""Unit tests for Dynamic Multi-Seasonal Baselines & Profiling (Workstream 11B)."""

import math
import pytest
from services.analytics.dynamic_baselines import (
    BaselineProfile,
    DayType,
    DiurnalBaselineProfiler,
    RobustStats,
    WelfordStats,
)
from services.analytics.telemetry_foundation import (
    DomainType,
    TelemetryObservation,
    TelemetryProvenance,
)


def test_welford_stats_accuracy():
    w = WelfordStats()
    # Data: [10, 20, 30, 40, 50]
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    for x in data:
        w.update(x)

    assert w.count == 5
    assert w.mean == 30.0
    # Sample variance for [10,20,30,40,50]: sum((x-30)^2)/(5-1) = (400+100+0+100+400)/4 = 250.0
    assert w.sample_variance == 250.0
    assert round(w.standard_deviation, 4) == round(math.sqrt(250.0), 4)


def test_robust_stats_mad_and_percentiles():
    r = RobustStats(window_size=10)
    # Data with an extreme outlier: [10, 12, 11, 13, 12, 11, 1000]
    # Median of [10, 11, 11, 12, 12, 13, 1000] is 12
    # Absolute deviations: [2, 1, 1, 0, 0, 1, 988] -> sorted: [0, 0, 1, 1, 1, 2, 988] -> median is 1.0
    for x in [10.0, 12.0, 11.0, 13.0, 12.0, 11.0, 1000.0]:
        r.add(x)

    assert r.median == 12.0
    assert r.mad == 1.0  # Completely resilient to the 1000.0 outlier!


def test_diurnal_profiler_cold_start_and_per_bucket_isolation():
    profiler = DiurnalBaselineProfiler(min_samples=30)
    entity_id = "sw-jkia-core01::GigabitEthernet1/0/1"
    metric = "ifInOctetsRate"

    # Mon, 08 Nov 2026 08:00:00 UTC (hour 8, Weekday)
    t_hour8 = 1794124800.0

    # 1. Check with 0 samples -> INSUFFICIENT_DATA
    profile_empty = profiler.get_baseline(entity_id, metric, t_hour8)
    assert profile_empty.is_valid is False
    assert profile_empty.status == "INSUFFICIENT_DATA"
    assert profile_empty.sample_count == 0

    # 2. Add 29 samples to hour 8 -> Still INSUFFICIENT_DATA
    for i in range(29):
        profiler.record_observation(
            TelemetryObservation(
                entity_id=entity_id,
                metric_name=metric,
                value=50000000.0 + (i * 1000.0),
                unit="bps",
                timestamp=t_hour8 + (i * 60.0),
                domain=DomainType.NETWORK,
                provenance=TelemetryProvenance.LIVE_SNMP,
            )
        )

    profile_29 = profiler.get_baseline(entity_id, metric, t_hour8)
    assert profile_29.sample_count == 29
    assert profile_29.is_valid is False
    assert profile_29.status == "INSUFFICIENT_DATA"

    # 3. Add the 30th sample to hour 8 -> Becomes VALID
    profiler.record_observation(
        TelemetryObservation(
            entity_id=entity_id,
            metric_name=metric,
            value=50000000.0,
            unit="bps",
            timestamp=t_hour8 + 1800.0,
            domain=DomainType.NETWORK,
            provenance=TelemetryProvenance.LIVE_SNMP,
        )
    )
    profile_30 = profiler.get_baseline(entity_id, metric, t_hour8)
    assert profile_30.sample_count == 30
    assert profile_30.is_valid is True
    assert profile_30.status == "VALID"
    assert profile_30.mean > 0.0

    # 4. Verify Per-Bucket Isolation:
    # A different hour (hour 14) on the same day must NOT inherit the hour 8 samples!
    t_hour14 = t_hour8 + (6 * 3600.0)
    profile_hour14 = profiler.get_baseline(entity_id, metric, t_hour14)
    assert profile_hour14.sample_count == 0
    assert profile_hour14.is_valid is False
    assert profile_hour14.status == "INSUFFICIENT_DATA"


def test_maintenance_window_and_snapshot_restore():
    profiler = DiurnalBaselineProfiler(min_samples=10, version="1.1.0")
    entity_id = "sbce-jkia-pri"
    metric = "active_sessions"
    t_base = 1794124800.0

    # Ingest 15 samples
    for i in range(15):
        profiler.record_observation(
            TelemetryObservation(
                entity_id=entity_id,
                metric_name=metric,
                value=200.0,
                unit="sessions",
                timestamp=t_base + (i * 60.0),
                domain=DomainType.SYSTEM,
                provenance=TelemetryProvenance.AVAYA_SBCE,
            )
        )

    p_before = profiler.get_baseline(entity_id, metric, t_base)
    assert p_before.sample_count == 15
    assert p_before.is_valid is True

    # Set maintenance window for the next 2 hours
    profiler.set_maintenance_window(entity_id, t_base + 7200.0)
    # Attempting to record during maintenance window must be rejected
    recorded = profiler.record_observation(
        TelemetryObservation(
            entity_id=entity_id,
            metric_name=metric,
            value=999.0,  # Maintenance spike
            unit="sessions",
            timestamp=t_base + 3600.0,
            domain=DomainType.SYSTEM,
            provenance=TelemetryProvenance.AVAYA_SBCE,
        )
    )
    assert recorded is False
    # Sample count remains 15
    assert profiler.get_baseline(entity_id, metric, t_base).sample_count == 15

    # Snapshot & Restore
    snapshot = profiler.snapshot()
    assert snapshot["version"] == "1.1.0"

    profiler_new = DiurnalBaselineProfiler(min_samples=10)
    profiler_new.restore_snapshot(snapshot)
    p_restored = profiler_new.get_baseline(entity_id, metric, t_base)
    assert p_restored.sample_count == 15
    assert p_restored.mean == 200.0
    assert p_restored.version == "1.1.0"

