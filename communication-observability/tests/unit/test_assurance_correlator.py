"""Unit tests for Voice Service Assurance Cross-Domain Incident Correlation Engine."""

import pytest
import time
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import (
    EvidenceDomain,
    HypothesisStatus,
    RootCauseDomain,
    ServiceHealthState,
)
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import (
    CanonicalVoiceEvent,
    DataCompleteness,
    EndpointIdentifiers,
    MeasurementConfidence,
    MediaTelemetry,
    MilestoneTimestamps,
    SignalingTelemetry,
)


def make_voice_event(
    outcome: CallOutcome = CallOutcome.ANSWERED,
    sip_code: int = 200,
    setup_time_ms: float = 120.0,
    verification_level: MediaVerificationLevel = MediaVerificationLevel.BIDIRECTIONAL,
    mos: float = 4.35,
    jitter: float = 2.0,
    loss: float = 0.1,
    duration: float = 5.0,
) -> CanonicalVoiceEvent:
    now = time.time()
    return CanonicalVoiceEvent(
        collection_timestamp=now,
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=now - duration, hungup=now),
        signaling=SignalingTelemetry(
            outcome=outcome,
            setup_time_ms=setup_time_ms,
            duration_seconds=duration,
            sip_status_code=sip_code,
        ),
        media=MediaTelemetry(
            verification_level=verification_level,
            estimated_mos=mos if verification_level == MediaVerificationLevel.BIDIRECTIONAL else None,
            jitter_ms=jitter,
            loss_pct=loss,
            rtt_ms=15.0,
            estimated_one_way_delay_ms=25.0,
            data_completeness=DataCompleteness.COMPLETE if verification_level == MediaVerificationLevel.BIDIRECTIONAL else DataCompleteness.PARTIAL_MISSING_MEDIA,
        ),
    )


def test_correlation_scenario_a_network_link_failure():
    """Scenario A: Physical interface B1 link down on SBCE causes call timeout (Probable Cause)."""
    event = make_voice_event(
        outcome=CallOutcome.TIMEOUT,
        sip_code=408,
        verification_level=MediaVerificationLevel.NO_MEDIA,
    )
    active_problems = [
        {"eventid": "101", "name": "Interface B1 (DMZ/ITSP) link down on mock-avaya-sbce-01", "severity": "4"}
    ]

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.CRITICAL
    assert report.health_score <= 20.0
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.NETWORK_LINK
    assert "Interface" in primary.title
    assert any(e.domain == EvidenceDomain.NETWORK for e in primary.evidence)
    assert any(e.domain == EvidenceDomain.SIGNALING for e in primary.evidence)
    assert len(primary.remediation_recommendations) > 0


def test_correlation_scenario_a_direct_causality_confirmed():
    """Scenario A2: Direct socket proof elevates hypothesis from Probable to Confirmed."""
    event = make_voice_event(
        outcome=CallOutcome.FAILED,
        sip_code=500,
        verification_level=MediaVerificationLevel.NO_MEDIA,
    )
    active_problems = [
        {"eventid": "101", "name": "Interface B1 link down on mock-avaya-sbce-01", "severity": "4"}
    ]

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(
        event, active_problems=active_problems, infrastructure_metrics={"direct_causality": True}
    )

    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.CONFIRMED
    assert primary.confidence >= 0.95


def test_correlation_scenario_b_appliance_cpu_overload():
    """Scenario B: High CPU utilization on SBCE causes massive setup latency and 503 (Probable Cause)."""
    event = make_voice_event(
        outcome=CallOutcome.CONGESTION,
        sip_code=503,
        setup_time_ms=6200.0,
        verification_level=MediaVerificationLevel.NO_MEDIA,
    )
    active_problems = [
        {"eventid": "202", "name": "High CPU utilization (>90%) on mock-avaya-sbce-01", "severity": "4"}
    ]

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.CRITICAL
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.APPLIANCE_OVERLOAD
    assert "Resource Saturation" in primary.title or "CPU" in primary.title
    assert any(e.domain == EvidenceDomain.APPLIANCE for e in primary.evidence)


def test_correlation_scenario_c_one_way_audio_nat_asymmetry():
    """Scenario C: SIP 200 OK answered, but media is TRANSMIT_ONLY due to firewall RTP block (Probable Cause)."""
    event = make_voice_event(
        outcome=CallOutcome.ANSWERED,
        sip_code=200,
        verification_level=MediaVerificationLevel.TRANSMIT_ONLY,
    )
    # Infrastructure is completely healthy
    active_problems = []

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.CRITICAL
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.FIREWALL_NAT_ASYMMETRY
    assert "One-Way Audio" in primary.title
    assert any("firewall" in r.lower() or "rtp" in r.lower() for r in primary.remediation_recommendations)


def test_correlation_scenario_d_upstream_carrier_outage():
    """Scenario D: External carrier outage returns SIP 503 while local infra is healthy (Probable Cause)."""
    event = make_voice_event(
        outcome=CallOutcome.CONGESTION,
        sip_code=503,
        verification_level=MediaVerificationLevel.NO_MEDIA,
    )
    # Zero active problems on local SBCE or network switches
    active_problems = []

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.CRITICAL
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.UPSTREAM_CARRIER
    assert "Carrier" in primary.title or "Trunk" in primary.title
    assert any(e.domain == EvidenceDomain.SIGNALING for e in primary.evidence)


def test_correlation_scenario_e_voice_quality_degradation():
    """Scenario E: Call answered with bidirectional media, but high jitter causes MOS < 3.8 (Probable Cause)."""
    event = make_voice_event(
        outcome=CallOutcome.ANSWERED,
        sip_code=200,
        verification_level=MediaVerificationLevel.BIDIRECTIONAL,
        mos=3.25,
        jitter=45.0,
        loss=3.5,
    )
    active_problems = []

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.DEGRADED
    assert 50.0 <= report.health_score <= 80.0
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert primary.root_cause_domain == RootCauseDomain.NETWORK_LINK
    assert "Quality" in primary.title
    assert any("dscp" in r.lower() or "qos" in r.lower() for r in primary.remediation_recommendations)


def test_correlation_scenario_f_healthy_call():
    """Scenario F: Clean normal call with high MOS and no alarms (Confirmed Healthy)."""
    event = make_voice_event(
        outcome=CallOutcome.ANSWERED,
        sip_code=200,
        verification_level=MediaVerificationLevel.BIDIRECTIONAL,
        mos=4.42,
        jitter=1.2,
        loss=0.0,
    )
    active_problems = []

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=active_problems)

    assert report.health_state == ServiceHealthState.HEALTHY
    assert report.health_score >= 90.0
    primary = report.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.HEALTHY
    assert primary.root_cause_domain == RootCauseDomain.HEALTHY


def test_stale_telemetry_detection():
    """Verify that voice telemetry older than 15 minutes is flagged as stale with UNKNOWN health."""
    now = time.time()
    # Event timestamp from 25 minutes ago
    event = make_voice_event(
        outcome=CallOutcome.ANSWERED,
        verification_level=MediaVerificationLevel.BIDIRECTIONAL,
        mos=4.4,
    )
    event.collection_timestamp = now - 1500.0  # 25 min ago
    event.timestamps.initiated = now - 1505.0
    event.timestamps.hungup = now - 1500.0

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=[])

    assert report.is_stale is True
    assert report.health_state == ServiceHealthState.UNKNOWN
    assert any("Stale Voice Telemetry" in h.title for h in report.hypotheses)

