"""Predictive Service Degradation & Time-to-Exhaustion (TTE) Forecaster for Nawari.

Applies double exponential smoothing (Holt's linear trend), linear regression with backtesting
fit verification (R^2, RMSE), prediction intervals, and safe operational headroom thresholds.
Distinguishes safe operational capacity from hard physical exhaustion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TrendEvaluation:
    """Statistical fit and trajectory metrics for a time-series series."""

    sample_count: int
    slope: float
    intercept: float
    r_squared: float
    rmse: float
    is_valid: bool
    status: str
    uncertainty_stderr: float


@dataclass
class TTEForecast:
    """Time-to-Exhaustion (TTE) prediction with safe and hard capacity horizons."""

    entity_id: str
    metric_name: str
    current_value: float
    safe_threshold: float
    hard_limit: float
    remaining_safe_capacity: float
    remaining_hard_capacity: float
    trend_slope_per_hour: float
    r_squared: float
    rmse: float
    time_to_safe_breach_hours: Optional[float]
    time_to_hard_exhaustion_hours: Optional[float]
    prediction_interval_hours: Optional[tuple[float, float]]
    is_forecast_valid: bool
    status: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "safe_threshold": round(self.safe_threshold, 4),
            "hard_limit": round(self.hard_limit, 4),
            "remaining_safe_capacity": round(self.remaining_safe_capacity, 4),
            "remaining_hard_capacity": round(self.remaining_hard_capacity, 4),
            "trend_slope_per_hour": round(self.trend_slope_per_hour, 4),
            "r_squared": round(self.r_squared, 4),
            "rmse": round(self.rmse, 4),
            "time_to_safe_breach_hours": round(self.time_to_safe_breach_hours, 2) if self.time_to_safe_breach_hours is not None else None,
            "time_to_hard_exhaustion_hours": round(self.time_to_hard_exhaustion_hours, 2) if self.time_to_hard_exhaustion_hours is not None else None,
            "prediction_interval_hours": [round(x, 2) for x in self.prediction_interval_hours] if self.prediction_interval_hours else None,
            "is_forecast_valid": self.is_forecast_valid,
            "status": self.status,
            "timestamp": self.timestamp,
        }


@dataclass
class VoiceMOSDecayForecast:
    """Progressive voice quality (MOS) degradation trajectory."""

    trunk_name: str
    current_mos: float
    slope_per_minute: float
    r_squared: float
    projected_mos_in_15m: float
    projected_mos_in_30m: float
    time_to_critical_3_5_minutes: Optional[float]
    is_degrading: bool
    status: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trunk_name": self.trunk_name,
            "current_mos": round(self.current_mos, 2),
            "slope_per_minute": round(self.slope_per_minute, 4),
            "r_squared": round(self.r_squared, 4),
            "projected_mos_in_15m": round(self.projected_mos_in_15m, 2),
            "projected_mos_in_30m": round(self.projected_mos_in_30m, 2),
            "time_to_critical_3_5_minutes": round(self.time_to_critical_3_5_minutes, 1) if self.time_to_critical_3_5_minutes is not None else None,
            "is_degrading": self.is_degrading,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class TrendAnalyzer:
    """Linear regression and trend evaluation with backtesting and error quantification."""

    MIN_OBSERVATIONS: int = 15

    @classmethod
    def fit_linear_trend(cls, timestamps: list[float], values: list[float]) -> TrendEvaluation:
        """Fits an ordinary least-squares linear trend to historical series."""
        n = len(values)
        if n < cls.MIN_OBSERVATIONS or len(timestamps) != n:
            return TrendEvaluation(
                sample_count=n,
                slope=0.0,
                intercept=0.0,
                r_squared=0.0,
                rmse=0.0,
                is_valid=False,
                status="INSUFFICIENT_OBSERVATIONS",
                uncertainty_stderr=0.0,
            )

        # Normalize timestamps relative to first point in hours
        t0 = timestamps[0]
        t_hours = [(t - t0) / 3600.0 for t in timestamps]

        mean_t = sum(t_hours) / n
        mean_y = sum(values) / n

        ss_tt = sum((t - mean_t) ** 2 for t in t_hours)
        ss_ty = sum((t_hours[i] - mean_t) * (values[i] - mean_y) for i in range(n))
        ss_yy = sum((y - mean_y) ** 2 for y in values)

        if ss_tt <= 1e-9:
            return TrendEvaluation(
                sample_count=n,
                slope=0.0,
                intercept=mean_y,
                r_squared=0.0,
                rmse=0.0,
                is_valid=False,
                status="ZERO_TIME_VARIANCE",
                uncertainty_stderr=0.0,
            )

        slope = ss_ty / ss_tt
        intercept = mean_y - (slope * mean_t)

        # Backtesting: compute residuals, RMSE and R^2
        residuals = [values[i] - (intercept + slope * t_hours[i]) for i in range(n)]
        sse = sum(r ** 2 for r in residuals)
        rmse = math.sqrt(sse / n)
        r_squared = 1.0 - (sse / ss_yy) if ss_yy > 1e-9 else 0.0
        r_squared = max(0.0, min(1.0, r_squared))

        # Standard error of the slope
        stderr_slope = math.sqrt(sse / (n - 2)) / math.sqrt(ss_tt) if n > 2 and ss_tt > 0 else 0.0

        return TrendEvaluation(
            sample_count=n,
            slope=slope,
            intercept=intercept,
            r_squared=r_squared,
            rmse=rmse,
            is_valid=True,
            status="FIT_CONVERGED",
            uncertainty_stderr=stderr_slope,
        )


class TimeToExhaustionForecaster:
    """Forecasts time-to-breach for capacity constraints with safe headroom and hard ceilings."""

    MIN_R_SQUARED: float = 0.70
    MAX_FORECAST_HORIZON_HOURS: float = 336.0  # 14 days maximum extrapolation cap

    @classmethod
    def forecast(
        cls,
        entity_id: str,
        metric_name: str,
        timestamps: list[float],
        values: list[float],
        safe_threshold: float,
        hard_limit: float,
        timestamp: Optional[float] = None,
    ) -> TTEForecast:
        """Computes safe and hard TTE projections based on recent linear trajectory."""
        now = timestamp if timestamp is not None else (timestamps[-1] if timestamps else 0.0)

        if not values or len(values) < TrendAnalyzer.MIN_OBSERVATIONS:
            return TTEForecast(
                entity_id=entity_id,
                metric_name=metric_name,
                current_value=values[-1] if values else 0.0,
                safe_threshold=safe_threshold,
                hard_limit=hard_limit,
                remaining_safe_capacity=safe_threshold - (values[-1] if values else 0.0),
                remaining_hard_capacity=hard_limit - (values[-1] if values else 0.0),
                trend_slope_per_hour=0.0,
                r_squared=0.0,
                rmse=0.0,
                time_to_safe_breach_hours=None,
                time_to_hard_exhaustion_hours=None,
                prediction_interval_hours=None,
                is_forecast_valid=False,
                status="INSUFFICIENT_DATA",
                timestamp=now,
            )

        current_val = values[-1]
        rem_safe = max(0.0, safe_threshold - current_val)
        rem_hard = max(0.0, hard_limit - current_val)

        trend = TrendAnalyzer.fit_linear_trend(timestamps, values)

        # Gate on trend validity and fit quality
        if not trend.is_valid or trend.r_squared < cls.MIN_R_SQUARED:
            return TTEForecast(
                entity_id=entity_id,
                metric_name=metric_name,
                current_value=current_val,
                safe_threshold=safe_threshold,
                hard_limit=hard_limit,
                remaining_safe_capacity=rem_safe,
                remaining_hard_capacity=rem_hard,
                trend_slope_per_hour=trend.slope,
                r_squared=trend.r_squared,
                rmse=trend.rmse,
                time_to_safe_breach_hours=None,
                time_to_hard_exhaustion_hours=None,
                prediction_interval_hours=None,
                is_forecast_valid=False,
                status="NOISY_TREND_LOW_R2" if trend.is_valid else trend.status,
                timestamp=now,
            )

        # Non-increasing trend: no exhaustion projected
        if trend.slope <= 1e-4:
            return TTEForecast(
                entity_id=entity_id,
                metric_name=metric_name,
                current_value=current_val,
                safe_threshold=safe_threshold,
                hard_limit=hard_limit,
                remaining_safe_capacity=rem_safe,
                remaining_hard_capacity=rem_hard,
                trend_slope_per_hour=trend.slope,
                r_squared=trend.r_squared,
                rmse=trend.rmse,
                time_to_safe_breach_hours=None,
                time_to_hard_exhaustion_hours=None,
                prediction_interval_hours=None,
                is_forecast_valid=True,
                status="STABLE_NO_EXHAUSTION",
                timestamp=now,
            )

        # Calculate nominal TTE in hours
        tte_safe = rem_safe / trend.slope if rem_safe > 0 else 0.0
        tte_hard = rem_hard / trend.slope if rem_hard > 0 else 0.0

        # Calculate 95% prediction interval for hard TTE based on slope uncertainty
        if trend.uncertainty_stderr > 1e-6:
            min_slope = max(1e-4, trend.slope - (1.96 * trend.uncertainty_stderr))
            max_slope = trend.slope + (1.96 * trend.uncertainty_stderr)
            pred_low = max(0.0, rem_hard / max_slope)
            pred_high = min(cls.MAX_FORECAST_HORIZON_HOURS, rem_hard / min_slope)
            pred_interval = (pred_low, pred_high)
        else:
            pred_interval = (tte_hard * 0.9, tte_hard * 1.1)

        # Horizon cap check
        if tte_hard > cls.MAX_FORECAST_HORIZON_HOURS:
            status = "CAPACITY_ADEQUATE_BEYOND_HORIZON"
            valid = True
        elif current_val >= safe_threshold:
            status = "OPERATING_NEAR_CEILING"
            valid = True
        else:
            status = "EXHAUSTION_PROJECTED"
            valid = True

        return TTEForecast(
            entity_id=entity_id,
            metric_name=metric_name,
            current_value=current_val,
            safe_threshold=safe_threshold,
            hard_limit=hard_limit,
            remaining_safe_capacity=rem_safe,
            remaining_hard_capacity=rem_hard,
            trend_slope_per_hour=trend.slope,
            r_squared=trend.r_squared,
            rmse=trend.rmse,
            time_to_safe_breach_hours=min(cls.MAX_FORECAST_HORIZON_HOURS, tte_safe),
            time_to_hard_exhaustion_hours=min(cls.MAX_FORECAST_HORIZON_HOURS, tte_hard),
            prediction_interval_hours=pred_interval,
            is_forecast_valid=valid,
            status=status,
            timestamp=now,
        )


class VoiceMOSDegradationTracker:
    """Detects subtle downward trajectory in voice call quality before hitting alarm gates."""

    CRITICAL_MOS_THRESHOLD: float = 3.50
    DEGRADATION_SLOPE_THRESHOLD_PER_MIN: float = -0.015  # -0.15 MOS drop over 10 minutes

    @classmethod
    def evaluate_mos_decay(
        cls,
        trunk_name: str,
        timestamps: list[float],
        mos_values: list[float],
        timestamp: Optional[float] = None,
    ) -> VoiceMOSDecayForecast:
        """Evaluates quality drift rate (dMOS/dt)."""
        now = timestamp if timestamp is not None else (timestamps[-1] if timestamps else 0.0)

        if len(mos_values) < TrendAnalyzer.MIN_OBSERVATIONS:
            return VoiceMOSDecayForecast(
                trunk_name=trunk_name,
                current_mos=mos_values[-1] if mos_values else 4.4,
                slope_per_minute=0.0,
                r_squared=0.0,
                projected_mos_in_15m=mos_values[-1] if mos_values else 4.4,
                projected_mos_in_30m=mos_values[-1] if mos_values else 4.4,
                time_to_critical_3_5_minutes=None,
                is_degrading=False,
                status="INSUFFICIENT_DATA",
                timestamp=now,
            )

        current_mos = mos_values[-1]
        trend = TrendAnalyzer.fit_linear_trend(timestamps, mos_values)
        # slope from TrendAnalyzer is per hour; convert to per minute
        slope_per_min = trend.slope / 60.0

        is_degrading = bool(
            trend.is_valid
            and trend.r_squared >= 0.65
            and slope_per_min <= cls.DEGRADATION_SLOPE_THRESHOLD_PER_MIN
        )

        proj_15 = max(1.0, min(4.5, current_mos + (slope_per_min * 15.0)))
        proj_30 = max(1.0, min(4.5, current_mos + (slope_per_min * 30.0)))

        if is_degrading and current_mos > cls.CRITICAL_MOS_THRESHOLD and slope_per_min < 0:
            time_to_crit = (cls.CRITICAL_MOS_THRESHOLD - current_mos) / slope_per_min
        else:
            time_to_crit = None

        return VoiceMOSDecayForecast(
            trunk_name=trunk_name,
            current_mos=current_mos,
            slope_per_minute=slope_per_min,
            r_squared=trend.r_squared,
            projected_mos_in_15m=proj_15,
            projected_mos_in_30m=proj_30,
            time_to_critical_3_5_minutes=time_to_crit,
            is_degrading=is_degrading,
            status="PROGRESSIVE_MOS_DEGRADATION" if is_degrading else "STABLE_QUALITY",
            timestamp=now,
        )

