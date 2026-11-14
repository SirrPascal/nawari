"""Integration test for Nawari Predictive Assurance & Analytics Pipeline (Workstream 11H).

Validates end-to-end integration: Feature Extraction -> Dynamic Baselining ->
Statistical Anomaly Detection -> Model Governance -> Predictive Degradation (TTE) ->
Intelligent Diagnosis with Supporting and Contradicting Evidence.
"""

import time
import pytest
from services.analytics.anomaly_detector import (
    AnomalySeverity,
    StatisticalAnomalyDetector,
)
from services.analytics.dynamic_baselines import DiurnalBaselineProfiler
from services.analytics.intelligent_diagnosis import (
    EvidencePolarity,
    IntelligentDiagnosisEngine,
)
from services.analytics.model_governance import (
    AuditEventType,
    ModelGovernanceEngine,
)
from services.analytics.predictive_degradation import (
    TimeToExhaustionForecaster,
    VoiceMOSDegradationTracker,
)
from services.analytics.telemetry_foundation import (
    DomainType,
    FeatureExtractor,
    TelemetryObservation,
    TelemetryProvenance,
)


def test_end_to_end_predictive_assurance_pipeline():
    start_time = time.time()

    # 1. Initialize Pipeline Components
    profiler = DiurnalBaselineProfiler(min_samples=30, version="1.0.0")
    detector = StatisticalAnomalyDetector(profiler=profiler)
    governance = ModelGovernanceEngine(profiler=profiler)

    switch_id = "sw-jkia-core01"
    iface_name = "TenGigabitEthernet1/1/1"
    switch_entity = f"{switch_id}::{iface_name}"
    sbce_id = "sbce-jkia-pri"
    trunk_entity = "voice_trunk::primary_safaricom"

    t_base = 1794124800.0  # Mon 08:00 UTC (Hour 8, Weekday)

    # 2. Stage 1: Baseline Ingestion (35 normal cycles of network and SBCE data)
    for i in range(35):
        t = t_base + (i * 60.0)

        # Network observations: ~1.0 pps discards
        net_obs_list = FeatureExtractor.extract_from_network_interface(
            device_id=switch_id,
            interface_name=iface_name,
            metrics={"ifInDiscardsRate": 1.0 + (0.2 if i % 2 == 0 else -0.2)},
            timestamp=t,
        )
        for obs in net_obs_list:
            if not governance.should_freeze_baseline_update(obs.entity_id, obs.metric_name):
                profiler.record_observation(obs)

        # SBCE observations: ~200 active sessions
        sbce_obs_list = FeatureExtractor.extract_from_avaya_sbce(
            sbce_id=sbce_id,
            metrics={"active_sessions": 200.0 + (i % 5)},
            timestamp=t,
        )
        for obs in sbce_obs_list:
            if not governance.should_freeze_baseline_update(obs.entity_id, obs.metric_name):
                profiler.record_observation(obs)

        # Voice observations: ~4.30 MOS
        voice_obs_list = FeatureExtractor.extract_from_voice_session(
            call_id=f"call-base-{i}",
            trunk_name="primary_safaricom",
            metrics={"mos": 4.30, "post_dial_delay_ms": 900.0},
            timestamp=t,
        )
        for obs in voice_obs_list:
            if not governance.should_freeze_baseline_update(obs.entity_id, obs.metric_name):
                profiler.record_observation(obs)

    # Verify baselines are valid after 35 samples
    p_net = profiler.get_baseline(switch_entity, "ifInDiscardsRate", t_base)
    assert p_net.is_valid is True
    assert p_net.sample_count == 35

    p_sbce = profiler.get_baseline(sbce_id, "active_sessions", t_base)
    assert p_sbce.is_valid is True
    assert p_sbce.sample_count == 35

    # 3. Stage 2: Normal Evaluation Verification (No False Positives)
    test_normal_obs = FeatureExtractor.extract_from_network_interface(
        device_id=switch_id,
        interface_name=iface_name,
        metrics={"ifInDiscardsRate": 1.1},
        timestamp=t_base + 3000.0,
    )[0]
    norm_res = detector.evaluate(test_normal_obs)
    assert norm_res.is_anomaly is False
    assert norm_res.severity == AnomalySeverity.NORMAL

    # 4. Stage 3 & 4: Injected Network Degradation with Governance Hysteresis
    # Inject 4 consecutive severe discard spikes (50 pps, baseline is 1.0 pps)
    active_anomalies = []
    for cycle in range(1, 5):
        t_spike = t_base + 3100.0 + (cycle * 60.0)
        spike_obs = FeatureExtractor.extract_from_network_interface(
            device_id=switch_id,
            interface_name=iface_name,
            metrics={"ifInDiscardsRate": 50.0},
            timestamp=t_spike,
        )[0]
        anom_res = detector.evaluate(spike_obs)
        assert anom_res.is_anomaly is True
        assert anom_res.severity == AnomalySeverity.CRITICAL

        is_active, evt = governance.process_anomaly_state_transition(anom_res)
        if cycle < 3:
            # Cycles 1 and 2 suppressed by 3-cycle persistence filter
            assert is_active is False
            assert evt == AuditEventType.ANOMALY_SUPPRESSED_FLAP
        else:
            # Cycle 3 and 4: Active alarm raised!
            assert is_active is True
            active_anomalies.append(anom_res)

    # 5. Baseline update freezing must now be active for the switch
    assert governance.should_freeze_baseline_update(switch_entity, "ifInDiscardsRate") is True

    # 6. Stage 5: Concurrent Voice Quality Decay
    # Voice MOS drops to 3.40 (below critical threshold)
    voice_spike_obs = FeatureExtractor.extract_from_voice_session(
        call_id="call-outage-01",
        trunk_name="primary_safaricom",
        metrics={"mos": 3.40, "post_dial_delay_ms": 910.0},
        timestamp=t_base + 3340.0,
    )
    for v_obs in voice_spike_obs:
        v_res = detector.evaluate(v_obs)
        if v_res.is_anomaly:
            active_anomalies.append(v_res)

    # 7. Stage 6: Cross-Domain Intelligent Diagnosis
    hypotheses = IntelligentDiagnosisEngine.diagnose(
        anomalies=active_anomalies,
        topology_context={"is_lag_redundant": True},
        now=t_base + 3350.0,
    )
    assert len(hypotheses) >= 1
    top_hyp = hypotheses[0]
    assert top_hyp.hypothesis_id == "HYP_SWITCH_EGRESS_QUEUE_DISCARDS"
    assert top_hyp.target_entity == switch_entity
    # Must contain both supporting and contradicting evidence
    assert len(top_hyp.supporting_evidence) >= 2
    assert len(top_hyp.contradicting_evidence) >= 1

    # 8. Stage 7: Predictive Degradation (TTE) for SBCE Session Capacity
    # Ingest 20 points of rising SBCE session counts (from 250 climbing by 30 sessions/hour)
    t_trend = [t_base + (j * 300.0) for j in range(20)]
    v_trend = [250.0 + (30.0 * (j * 300.0 / 3600.0)) for j in range(20)]

    tte_forecast = TimeToExhaustionForecaster.forecast(
        entity_id=sbce_id,
        metric_name="active_sessions",
        timestamps=t_trend,
        values=v_trend,
        safe_threshold=425.0,
        hard_limit=500.0,
        timestamp=t_trend[-1],
    )
    assert tte_forecast.is_forecast_valid is True
    assert tte_forecast.status == "EXHAUSTION_PROJECTED"
    assert tte_forecast.r_squared > 0.99
    assert tte_forecast.time_to_safe_breach_hours is not None
    assert 3.5 <= tte_forecast.time_to_safe_breach_hours <= 4.5

    # 9. Performance & Execution Speed Check
    elapsed_seconds = time.time() - start_time
    assert elapsed_seconds < 1.0  # Entire pipeline test executes in < 1 second!

