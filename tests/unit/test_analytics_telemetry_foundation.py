"""Unit tests for Telemetry Foundation & Feature Extraction (Workstream 11A)."""

import math
import pytest
from services.analytics.telemetry_foundation import (
    AlignedBucket,
    DomainType,
    FeatureExtractor,
    TelemetryObservation,
    TelemetryProvenance,
    TimeBucketAligner,
)


def test_telemetry_observation_validity():
    obs_valid = TelemetryObservation(
        entity_id="sw-core01::GigabitEthernet1/0/1",
        metric_name="ifInOctetsRate",
        value=54000000.0,
        unit="bps",
        timestamp=1700000000.0,
        domain=DomainType.NETWORK,
        provenance=TelemetryProvenance.LIVE_SNMP,
    )
    assert obs_valid.is_valid is True

    obs_none = TelemetryObservation(
        entity_id="sw-core01::GigabitEthernet1/0/1",
        metric_name="ifInOctetsRate",
        value=None,
        unit="bps",
        timestamp=1700000000.0,
        domain=DomainType.NETWORK,
        provenance=TelemetryProvenance.LIVE_SNMP,
    )
    assert obs_none.is_valid is False

    obs_nan = TelemetryObservation(
        entity_id="sw-core01::GigabitEthernet1/0/1",
        metric_name="ifInOctetsRate",
        value=float("nan"),
        unit="bps",
        timestamp=1700000000.0,
        domain=DomainType.NETWORK,
        provenance=TelemetryProvenance.LIVE_SNMP,
    )
    assert obs_nan.is_valid is False


def test_time_bucket_aligner_no_zero_imputation():
    aligner = TimeBucketAligner(bucket_size_seconds=60.0)

    # Observations at t=10, t=25, and t=130 (skipping bucket [60..120))
    obs = [
        TelemetryObservation(
            entity_id="e1",
            metric_name="cpu",
            value=10.0,
            unit="%",
            timestamp=10.0,
            domain=DomainType.SYSTEM,
            provenance=TelemetryProvenance.LIVE_SNMP,
        ),
        TelemetryObservation(
            entity_id="e1",
            metric_name="cpu",
            value=20.0,
            unit="%",
            timestamp=25.0,
            domain=DomainType.SYSTEM,
            provenance=TelemetryProvenance.LIVE_SNMP,
        ),
        TelemetryObservation(
            entity_id="e1",
            metric_name="cpu",
            value=50.0,
            unit="%",
            timestamp=130.0,
            domain=DomainType.SYSTEM,
            provenance=TelemetryProvenance.LIVE_SNMP,
        ),
    ]

    buckets = aligner.align(obs)
    assert len(buckets) == 3

    # Bucket 0: [0, 60)
    assert buckets[0].bucket_start == 0.0
    assert buckets[0].sample_count == 2
    assert buckets[0].mean_value == 15.0
    assert buckets[0].is_missing is False

    # Bucket 1: [60, 120) - Explicitly tagged as missing; NEVER zero-imputed!
    assert buckets[1].bucket_start == 60.0
    assert buckets[1].sample_count == 0
    assert buckets[1].mean_value is None
    assert buckets[1].is_missing is True

    # Bucket 2: [120, 180)
    assert buckets[2].bucket_start == 120.0
    assert buckets[2].sample_count == 1
    assert buckets[2].mean_value == 50.0
    assert buckets[2].is_missing is False


def test_feature_extractor_network_and_voice():
    # Network extraction
    net_obs = FeatureExtractor.extract_from_network_interface(
        device_id="sw-jkia-core01",
        interface_name="TenGigabitEthernet1/1/1",
        metrics={
            "ifInOctetsRate": 850000000,
            "ifOutOctetsRate": 920000000,
            "ifInDiscardsRate": 12.5,
            "bandwidth_utilization_pct": 85.0,
        },
        timestamp=1700001000.0,
    )
    assert len(net_obs) == 4
    metrics_map = {o.metric_name: o for o in net_obs}
    assert metrics_map["ifInDiscardsRate"].value == 12.5
    assert metrics_map["ifInDiscardsRate"].unit == "pps"
    assert metrics_map["ifInDiscardsRate"].domain == DomainType.NETWORK

    # Voice extraction
    voice_obs = FeatureExtractor.extract_from_voice_session(
        call_id="call-99120-kq",
        trunk_name="safaricom_sip_pri",
        metrics={
            "post_dial_delay_ms": 1150.0,
            "mos": 4.15,
            "r_factor": 88.0,
            "burst_loss_density_pct": 0.05,
        },
        timestamp=1700001000.0,
    )
    v_map = {o.metric_name: o for o in voice_obs}
    assert v_map["post_dial_delay_ms"].value == 1150.0
    assert v_map["post_dial_delay_ms"].domain == DomainType.VOICE_SIGNALING
    assert v_map["mos"].value == 4.15
    assert v_map["mos"].domain == DomainType.VOICE_MEDIA

