"""Unit tests for Predictive Degradation & Time-to-Exhaustion Forecaster (Workstream 11D)."""

import pytest
from services.analytics.predictive_degradation import (
    TimeToExhaustionForecaster,
    TrendAnalyzer,
    VoiceMOSDegradationTracker,
)


def test_trend_analyzer_fit_and_insufficient_samples():
    # 1. Less than 15 samples -> INSUFFICIENT_OBSERVATIONS
    t_short = [float(i * 60) for i in range(10)]
    v_short = [10.0 + i for i in range(10)]
    t_eval = TrendAnalyzer.fit_linear_trend(t_short, v_short)
    assert t_eval.is_valid is False
    assert t_eval.status == "INSUFFICIENT_OBSERVATIONS"

    # 2. 20 clean linear points: y = 100 + 20 * t_hours
    t_valid = [float(i * 300) for i in range(20)]  # 0 to 5700 seconds
    v_valid = [100.0 + (20.0 * (t / 3600.0)) for t in t_valid]
    t_eval2 = TrendAnalyzer.fit_linear_trend(t_valid, v_valid)
    assert t_eval2.is_valid is True
    assert round(t_eval2.slope, 2) == 20.0
    assert t_eval2.r_squared > 0.99
    assert t_eval2.rmse < 0.01


def test_tte_forecaster_sbce_session_capacity():
    # 20 points, steadily climbing from 200 sessions toward 500 session hard limit
    # Safe limit: 425 sessions (85%). Hard limit: 500 sessions.
    # Growth rate: 50 sessions per hour
    t_points = [float(i * 300) for i in range(20)]
    # At i=19 (95 minutes = 1.583 hours): y = 200 + (50 * 1.583) = 279.16 sessions
    v_points = [200.0 + (50.0 * (t / 3600.0)) for t in t_points]

    forecast = TimeToExhaustionForecaster.forecast(
        entity_id="sbce-jkia-pri",
        metric_name="active_sessions",
        timestamps=t_points,
        values=v_points,
        safe_threshold=425.0,
        hard_limit=500.0,
    )

    assert forecast.is_forecast_valid is True
    assert forecast.status == "EXHAUSTION_PROJECTED"
    assert round(forecast.trend_slope_per_hour, 1) == 50.0
    assert forecast.r_squared > 0.99

    # Remaining safe capacity from ~279.16 to 425 is ~145.84 sessions
    # At 50 sessions/hour, time to safe breach is ~2.9 hours
    assert forecast.time_to_safe_breach_hours is not None
    assert 2.7 <= forecast.time_to_safe_breach_hours <= 3.1

    # Time to hard 500 exhaustion: (500 - 279.16)/50 = ~4.4 hours
    assert forecast.time_to_hard_exhaustion_hours is not None
    assert 4.2 <= forecast.time_to_hard_exhaustion_hours <= 4.6

    # Prediction interval should encapsulate the point estimate
    assert forecast.prediction_interval_hours is not None
    low, high = forecast.prediction_interval_hours
    assert low <= forecast.time_to_hard_exhaustion_hours <= high


def test_tte_forecaster_noisy_trend_rejected():
    # 20 noisy oscillating points: R^2 will be very low
    t_points = [float(i * 300) for i in range(20)]
    v_points = [100.0 + (25.0 if i % 2 == 0 else -25.0) for i in range(20)]

    forecast = TimeToExhaustionForecaster.forecast(
        entity_id="sw-core01::TenGig1/1/1",
        metric_name="bandwidth_utilization_pct",
        timestamps=t_points,
        values=v_points,
        safe_threshold=80.0,
        hard_limit=95.0,
    )
    # Gated by R^2 >= 0.70; noise must be rejected
    assert forecast.is_forecast_valid is False
    assert forecast.status == "NOISY_TREND_LOW_R2"
    assert forecast.time_to_hard_exhaustion_hours is None


def test_voice_mos_decay_tracking():
    # 20 intervals (1 minute apart), showing subtle downward trajectory from 4.30 down to 3.80
    # Slope: -0.50 MOS / 19 minutes = -0.0263 MOS/min (steeper than -0.015/min threshold)
    t_points = [float(i * 60) for i in range(20)]
    mos_points = [4.30 - (0.0263 * i) for i in range(20)]

    decay = VoiceMOSDegradationTracker.evaluate_mos_decay(
        trunk_name="safaricom_sip_pri",
        timestamps=t_points,
        mos_values=mos_points,
    )

    assert decay.is_degrading is True
    assert decay.status == "PROGRESSIVE_MOS_DEGRADATION"
    assert decay.slope_per_minute < -0.02
    assert decay.r_squared > 0.95

    # Projected MOS in 15m must be lower than current (~3.80 - 0.39 ~ 3.41)
    assert decay.projected_mos_in_15m < decay.current_mos
    # Time to critical 3.50 MOS is projected
    assert decay.time_to_critical_3_5_minutes is not None
    assert 10.0 <= decay.time_to_critical_3_5_minutes <= 15.0

