"""RFC 3611 RTCP Extended Reports (RTCP-XR) VoIP Metrics Block Analyzer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class RTCPXRVoIPMetrics:
    """RFC 3611 Section 4.7 VoIP Metrics Block data structure."""

    # Loss and Discard Rates
    loss_rate_pct: float = 0.0               # Fraction of packets lost in transit
    discard_rate_pct: float = 0.0            # Fraction of packets discarded by jitter buffer
    burst_density_pct: float = 0.0          # Loss/discard density during bursts
    gap_density_pct: float = 0.0            # Loss density during non-burst gaps
    burst_duration_ms: float = 0.0          # Mean burst duration in milliseconds
    gap_duration_ms: float = 0.0            # Mean gap duration in milliseconds

    # Delay Metrics
    round_trip_delay_ms: float = 0.0        # Measured network round trip time
    end_system_delay_ms: float = 0.0        # Algorithmic + jitter buffer holding delay

    # Acoustic and Signal Quality
    signal_level_dbm: float = -20.0         # Signal level in dBm
    noise_level_dbm: float = -60.0          # Background noise level in dBm
    rerl_db: float = 40.0                   # Residual Echo Return Loss in dB

    # Quality Calculations
    r_factor: Optional[float] = None
    estimated_mos: Optional[float] = None
    is_valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RTCPXRAnalyzer:
    """Analyzes RFC 3611 RTCP-XR VoIP reports and classifies degradation causes."""

    @classmethod
    def parse_voip_metrics_block(cls, data: dict[str, Any]) -> RTCPXRVoIPMetrics:
        """Parse structured RTCP-XR dictionary or raw telemetry items into RTCPXRVoIPMetrics."""
        if not data:
            return RTCPXRVoIPMetrics(is_valid=False)

        loss_rate = float(data.get("loss_rate_pct", data.get("loss_pct", 0.0)))
        discard_rate = float(data.get("discard_rate_pct", data.get("discard_pct", 0.0)))
        burst_density = float(data.get("burst_density_pct", data.get("burst_density", 0.0)))
        gap_density = float(data.get("gap_density_pct", data.get("gap_density", 0.0)))
        burst_dur = float(data.get("burst_duration_ms", 0.0))
        gap_dur = float(data.get("gap_duration_ms", 0.0))
        rtt = float(data.get("round_trip_delay_ms", data.get("rtt_ms", 0.0)))
        end_delay = float(data.get("end_system_delay_ms", 0.0))
        signal = float(data.get("signal_level_dbm", -20.0))
        noise = float(data.get("noise_level_dbm", -60.0))
        rerl = float(data.get("rerl_db", 40.0))

        # Check validity: must have at least one measured network attribute
        has_metrics = bool(rtt > 0 or loss_rate > 0 or discard_rate > 0 or burst_dur > 0)

        metrics = RTCPXRVoIPMetrics(
            loss_rate_pct=round(loss_rate, 2),
            discard_rate_pct=round(discard_rate, 2),
            burst_density_pct=round(burst_density, 2),
            gap_density_pct=round(gap_density, 2),
            burst_duration_ms=round(burst_dur, 2),
            gap_duration_ms=round(gap_dur, 2),
            round_trip_delay_ms=round(rtt, 2),
            end_system_delay_ms=round(end_delay, 2),
            signal_level_dbm=round(signal, 1),
            noise_level_dbm=round(noise, 1),
            rerl_db=round(rerl, 1),
            is_valid=has_metrics,
        )
        return metrics

    @classmethod
    def diagnose_media_degradation(cls, metrics: RTCPXRVoIPMetrics) -> list[str]:
        """Classify root causes of media degradation from RTCP-XR metrics."""
        diagnostics = []
        if not metrics.is_valid:
            return ["No valid RTCP-XR media metrics available"]

        # Jitter buffer discards vs network loss
        if metrics.discard_rate_pct > 1.0 and metrics.discard_rate_pct > metrics.loss_rate_pct:
            diagnostics.append(
                f"Jitter Buffer Discard Dominant ({metrics.discard_rate_pct}% discarded vs {metrics.loss_rate_pct}% network loss): Packets arrived late due to excessive transit latency variance."
            )
        elif metrics.loss_rate_pct > 1.0:
            diagnostics.append(
                f"Transit Network Packet Loss Dominant ({metrics.loss_rate_pct}% dropped): Physical link degradation, fiber micro-bend, or buffer overflow."
            )

        # Micro-burst loss
        if metrics.burst_duration_ms > 40.0 and metrics.burst_density_pct > 20.0:
            diagnostics.append(
                f"Micro-burst loss pattern detected: Bursts lasting {metrics.burst_duration_ms}ms with {metrics.burst_density_pct}% density indicate switch port queue exhaustion."
            )

        # Excessive delay
        one_way_delay = (metrics.round_trip_delay_ms / 2.0) + metrics.end_system_delay_ms
        if one_way_delay > 150.0:
            diagnostics.append(
                f"Excessive mouth-to-ear delay ({one_way_delay:.1f}ms > 150ms ITU-T G.114 target): High conversational latency causing talker overlap."
            )

        if not diagnostics:
            diagnostics.append("Media parameters nominal and compliant with ITU-T voice quality standards")

        return diagnostics

