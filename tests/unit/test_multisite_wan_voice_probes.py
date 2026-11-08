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


def test_sip_options_ping_signaling_only_invariant():
    prober = TransWanVoiceProber()

    # SIP OPTIONS probe succeeds
    opt_res = prober.execute_sip_options_ping(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=24.5,
        response_code=200,
    )
    assert opt_res.signaling_reachable is True
    assert opt_res.rtt_ms == 24.5
    # Strict Invariant: SIP OPTIONS does not prove voice media or call completion
    assert opt_res.proves_voice_media is False
    assert "It does NOT prove call completion" in opt_res.evidence_note


def test_missing_or_unidirectional_media_invalidates_mos():
    prober = TransWanVoiceProber()

    # Probe without bidirectional RTP media
    res = prober.execute_probe(
        station_id="KIS-STATION",
        circuit_id="CIR-KIS-01",
        rtt_ms=30.0,
        jitter_ms=3.0,
        packet_loss_percent=0.0,
        has_bidirectional_media=False,  # Unidirectional or absent
    )
    # Even though RTT and loss are low, lack of bidirectional media strictly fails voice SLA
    assert res.mos_score == 1.0
    assert res.status == VoiceTrunkStatus.CRITICAL_FAILOVER
    assert any("Bidirectional RTP/RTCP required for MOS" in n for n in res.notes)


def test_missing_rtcp_produces_unknown_and_distinguishes_delay_types():
    prober = TransWanVoiceProber()

    # 1. Missing RTCP telemetry must NOT fabricate MOS
    res_no_rtcp = prober.execute_probe(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=40.0,
        jitter_ms=5.0,
        packet_loss_percent=0.0,
        has_bidirectional_media=True,
        rtcp_available=False,  # RTCP absent
    )
    assert res_no_rtcp.is_valid_mos is False
    assert res_no_rtcp.mos_score is None
    assert res_no_rtcp.r_factor is None
    assert any("MISSING RTCP TELEMETRY" in n for n in res_no_rtcp.notes)

    # 2. Measured RTCP-XR delay vs Estimated symmetric delay
    res_estimated = prober.execute_probe(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=50.0,
        jitter_ms=5.0,
        packet_loss_percent=0.0,
    )
    assert res_estimated.delay_measurement_type == "ESTIMATED_SYMMETRIC_RTT"
    assert res_estimated.estimated_one_way_delay_ms == 25.0
    assert res_estimated.measured_one_way_delay_ms is None

    res_measured = prober.execute_probe(
        station_id="MBA-STATION",
        circuit_id="CIR-MBA-01",
        rtt_ms=50.0,
        jitter_ms=5.0,
        packet_loss_percent=0.0,
        measured_one_way_delay_ms=32.0,  # Asymmetric WAN path measured via RTCP-XR
    )
    assert res_measured.delay_measurement_type == "MEASURED_RTCP_XR"
    assert res_measured.measured_one_way_delay_ms == 32.0


def test_contradictory_and_out_of_bounds_media_telemetry():
    prober = TransWanVoiceProber()

    # Out of bounds packet loss (150%) and negative jitter (-10ms)
    res = prober.execute_probe(
        station_id="LHR-STATION",
        circuit_id="CIR-LHR-01",
        rtt_ms=160.0,
        jitter_ms=-10.0,
        packet_loss_percent=150.0,
    )
    # Jitter clamped to 0, packet loss clamped to 100%, notes warning generated
    assert res.jitter_ms == 0.0
    assert res.packet_loss_percent == 100.0
    assert any("CONTRADICTORY TELEMETRY" in n for n in res.notes)
    assert res.status == VoiceTrunkStatus.CRITICAL_FAILOVER

