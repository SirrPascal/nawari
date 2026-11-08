"""tests/unit/test_multisite_wan_voice_probes.py
=============================================
Unit tests for trans-WAN voice quality probing and trunk survivability (Workstream 13D).
"""

from services.multisite.wan_voice_probes import (
    TransWanVoiceProber,
    VoiceTrunkStatus,
    WanVoiceQualityEvaluator,
)


def test_e_model_r_factor_and_mos_calculations():
    # 1. Optimal voice path: low delay, zero loss, zero jitter
    r_optimal = WanVoiceQualityEvaluator.calculate_r_factor(
        one_way_delay_ms=20.0,
        packet_loss_percent=0.0,
        jitter_ms=2.0,
    )
    mos_optimal = WanVoiceQualityEvaluator.calculate_mos(r_optimal)
    assert r_optimal >= 90.0
    assert mos_optimal >= 4.3

    # 2. Moderate voice path: moderate delay (120ms) and minor loss (1.5%)
    r_degraded = WanVoiceQualityEvaluator.calculate_r_factor(
        one_way_delay_ms=120.0,
        packet_loss_percent=1.5,
        jitter_ms=15.0,
    )
    mos_degraded = WanVoiceQualityEvaluator.calculate_mos(r_degraded)
    assert 75.0 <= r_degraded < 90.0
    assert 3.8 <= mos_degraded < 4.3

    # 3. Severe impairment: high delay (220ms) and high loss (8.0%)
    r_severe = WanVoiceQualityEvaluator.calculate_r_factor(
        one_way_delay_ms=220.0,
        packet_loss_percent=8.0,
        jitter_ms=35.0,
    )
    mos_severe = WanVoiceQualityEvaluator.calculate_mos(r_severe)
    assert r_severe <= 55.0
    assert mos_severe < 3.0


def test_trans_wan_voice_prober_optimal_and_failover():
    prober = TransWanVoiceProber()

    # 1. Mombasa primary circuit probe under optimal conditions
    res_optimal = prober.execute_probe(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=35.0,
        jitter_ms=4.0,
        packet_loss_percent=0.0,
    )
    assert res_optimal.status == VoiceTrunkStatus.OPTIMAL
    assert res_optimal.mos_score >= 4.2
    assert res_optimal.failover_recommended is False
    assert res_optimal.failover_target_circuit_id is None

    # 2. Mombasa primary circuit probe under severe degradation (high RTT, high loss)
    res_failover = prober.execute_probe(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=280.0,
        jitter_ms=45.0,
        packet_loss_percent=5.5,
    )
    assert res_failover.status == VoiceTrunkStatus.CRITICAL_FAILOVER
    assert res_failover.mos_score < 3.5
    assert res_failover.failover_recommended is True
    assert res_failover.failover_target_circuit_id == "CIR-MBA-02"
    assert any("Recommending immediate failover" in n for n in res_failover.notes)

    # 3. Verify probe history tracking
    history = prober.get_station_probes("MBA-STATION")
    assert len(history) == 2
    assert history[0].probe_id == res_optimal.probe_id
    assert history[1].probe_id == res_failover.probe_id
