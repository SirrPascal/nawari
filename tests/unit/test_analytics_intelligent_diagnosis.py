"""Unit tests for Intelligent Diagnosis & Evidence-Ranked Hypotheses (Workstream 11E)."""

import pytest
from services.analytics.anomaly_detector import (
    AnomalyDirection,
    AnomalySeverity,
    StatisticalAnomalyResult,
)
from services.analytics.intelligent_diagnosis import (
    EvidencePolarity,
    IntelligentDiagnosisEngine,
)


def test_carrier_trunk_congestion_hypothesis_with_contradicting_evidence():
    # Anomaly: PDD on Safaricom trunk is 2800ms (Z=3.8)
    pdd_anom = StatisticalAnomalyResult(
        entity_id="voice_trunk::primary_safaricom",
        metric_name="post_dial_delay_ms",
        current_value=2800.0,
        unit="ms",
        baseline_mean=900.0,
        baseline_median=880.0,
        baseline_mad=40.0,
        baseline_std_dev=150.0,
        baseline_p10=800.0,
        baseline_p90=1100.0,
        z_score=3.8,
        modified_z_score=3.7,
        ewma_value=2500.0,
        direction=AnomalyDirection.HIGH_ABNORMAL,
        severity=AnomalySeverity.WARNING,
        is_anomaly=True,
        is_persistent=True,
        consecutive_anomalous_samples=3,
        confidence_score=0.88,
        status="EVALUATED",
        timestamp=1794125000.0,
    )

    hypotheses = IntelligentDiagnosisEngine.diagnose(
        anomalies=[pdd_anom],
        now=1794125005.0,
    )

    assert len(hypotheses) == 1
    h = hypotheses[0]
    assert h.hypothesis_id == "HYP_CARRIER_TRUNK_CONGESTION"
    assert h.target_entity == "voice_trunk::primary_safaricom"

    # Must contain both SUPPORTING and CONTRADICTING evidence
    assert len(h.supporting_evidence) >= 1
    assert len(h.contradicting_evidence) >= 1

    supp_items = [e for e in h.supporting_evidence if e.polarity == EvidencePolarity.SUPPORTING]
    contra_items = [e for e in h.contradicting_evidence if e.polarity == EvidencePolarity.CONTRADICTING]

    assert len(supp_items) >= 1
    assert len(contra_items) >= 1
    # Contradicting evidence proves campus switches are clean, narrowing fault to external carrier
    assert "Campus switch interfaces" in contra_items[0].observation_summary
    assert h.rank_score > 0.0


def test_switch_discards_impacting_voice_media_with_lag_redundancy():
    # 1. Switch discard anomaly
    net_anom = StatisticalAnomalyResult(
        entity_id="sw-jkia-dist01::TenGig1/1/2",
        metric_name="ifInDiscardsRate",
        current_value=45.0,
        unit="pps",
        baseline_mean=1.0,
        baseline_median=1.0,
        baseline_mad=0.2,
        baseline_std_dev=0.5,
        baseline_p10=0.5,
        baseline_p90=1.8,
        z_score=5.2,
        modified_z_score=5.0,
        ewma_value=40.0,
        direction=AnomalyDirection.HIGH_ABNORMAL,
        severity=AnomalySeverity.CRITICAL,
        is_anomaly=True,
        is_persistent=True,
        consecutive_anomalous_samples=4,
        confidence_score=0.92,
        status="EVALUATED",
        timestamp=1794125000.0,
    )
    # 2. Concurrent Voice MOS anomaly
    voice_anom = StatisticalAnomalyResult(
        entity_id="voice_trunk::primary_safaricom",
        metric_name="mos",
        current_value=3.40,
        unit="score",
        baseline_mean=4.25,
        baseline_median=4.25,
        baseline_mad=0.05,
        baseline_std_dev=0.10,
        baseline_p10=4.15,
        baseline_p90=4.35,
        z_score=-4.5,
        modified_z_score=-4.2,
        ewma_value=3.50,
        direction=AnomalyDirection.LOW_ABNORMAL,
        severity=AnomalySeverity.CRITICAL,
        is_anomaly=True,
        is_persistent=True,
        consecutive_anomalous_samples=3,
        confidence_score=0.90,
        status="EVALUATED",
        timestamp=1794125000.0,
    )

    # Topology context indicates link is redundant LAG member
    hypotheses = IntelligentDiagnosisEngine.diagnose(
        anomalies=[net_anom, voice_anom],
        topology_context={"is_lag_redundant": True},
        now=1794125010.0,
    )

    h_switch = next((h for h in hypotheses if h.hypothesis_id == "HYP_SWITCH_EGRESS_QUEUE_DISCARDS"), None)
    assert h_switch is not None
    assert h_switch.target_entity == "sw-jkia-dist01::TenGig1/1/2"

    # LAG redundancy must be logged as CONTRADICTING evidence to dampen total severity
    contra_lag = [e for e in h_switch.contradicting_evidence if e.metric_name == "lag_redundancy"]
    assert len(contra_lag) == 1
    assert contra_lag[0].polarity == EvidencePolarity.CONTRADICTING


def test_endpoint_wifi_isolated_from_wired_core():
    ep_anom = StatisticalAnomalyResult(
        entity_id="laptop-jkia-crew04",
        metric_name="wifi_rssi_dbm",
        current_value=-88.0,
        unit="dBm",
        baseline_mean=-62.0,
        baseline_median=-61.0,
        baseline_mad=2.0,
        baseline_std_dev=3.5,
        baseline_p10=-65.0,
        baseline_p90=-58.0,
        z_score=-4.1,
        modified_z_score=-4.0,
        ewma_value=-85.0,
        direction=AnomalyDirection.LOW_ABNORMAL,
        severity=AnomalySeverity.WARNING,
        is_anomaly=True,
        is_persistent=True,
        consecutive_anomalous_samples=3,
        confidence_score=0.85,
        status="EVALUATED",
        timestamp=1794125000.0,
    )

    hypotheses = IntelligentDiagnosisEngine.diagnose(
        anomalies=[ep_anom],
        now=1794125005.0,
    )

    assert len(hypotheses) == 1
    h_wifi = hypotheses[0]
    assert h_wifi.hypothesis_id == "HYP_ENDPOINT_WIFI_INTERFERENCE"
    # Wired core network health acts as contradicting evidence against general network failure
    assert len(h_wifi.contradicting_evidence) >= 1
    assert "Wired distribution switch backplane" in h_wifi.contradicting_evidence[0].observation_summary

