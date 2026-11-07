"""RTP/RTCP Telemetry Analysis and ITU-T G.107 E-model MOS Estimation.

CRITICAL ARCHITECTURAL DIRECTIVE:
When RTCP data is absent or incomplete, media quality MUST be reported as UNKNOWN
(is_valid=False, mos_score=None, r_factor=None). Healthy values must NEVER be fabricated.
"""

import math
from typing import Any, Optional

from services.voice.models import MediaQualityMetrics


class RtpAnalyzer:
    """Analyzes RTCP statistics and calculates voice quality ratings using ITU-T G.107."""

    # G.711 Baseline Parameters
    R0: float = 93.2

    @classmethod
    def calculate_mos(
        cls,
        jitter_ms: Optional[float],
        loss_pct: Optional[float],
        rtt_ms: Optional[float],
    ) -> tuple[Optional[float], Optional[float]]:
        """Calculate estimated R-Factor and MOS score using ITU-T G.107 E-model.

        Returns (r_factor, mos_score).
        If any of the mandatory metrics are None or invalid, returns (None, None).
        """
        if jitter_ms is None or loss_pct is None:
            return None, None

        # Sanitize non-negative inputs
        jitter = max(0.0, float(jitter_ms))
        loss = max(0.0, min(100.0, float(loss_pct)))
        rtt = max(0.0, float(rtt_ms)) if rtt_ms is not None else 0.0

        # 1. One-way delay estimation including jitter buffer compensation
        one_way_delay = (rtt / 2.0) + (2.0 * jitter)

        # 2. Delay impairment Id
        if one_way_delay <= 100.0:
            id_impairment = 0.0
        else:
            id_impairment = 0.024 * one_way_delay
            if one_way_delay > 177.3:
                id_impairment += 0.11 * (one_way_delay - 177.3)

        # 3. Equipment impairment Ie (G.711 with packet loss)
        ie_impairment = 30.0 * math.log(1.0 + 15.0 * (loss / 100.0))

        # 4. Transmission rating factor R
        r_factor = cls.R0 - id_impairment - ie_impairment
        r_factor = max(0.0, min(100.0, r_factor))

        # 5. Conversion from R to MOS (ITU-T G.107 formula)
        if r_factor <= 0.0:
            mos = 1.0
        elif r_factor >= 100.0:
            mos = 4.5
        else:
            mos = (
                1.0
                + (0.035 * r_factor)
                + (r_factor * (r_factor - 60.0) * (100.0 - r_factor) * 7.0e-6)
            )
            mos = max(1.0, min(4.5, mos))

        return round(r_factor, 1), round(mos, 2)

    @classmethod
    def from_metrics(
        cls,
        jitter_ms: Optional[float] = None,
        loss_pct: Optional[float] = None,
        rtt_ms: Optional[float] = None,
        packets_sent: int = 0,
        packets_received: int = 0,
    ) -> MediaQualityMetrics:
        """Create MediaQualityMetrics with strict validity validation."""
        if jitter_ms is None or loss_pct is None:
            return MediaQualityMetrics(
                jitter_ms=jitter_ms,
                loss_pct=loss_pct,
                rtt_ms=rtt_ms,
                packets_sent=packets_sent,
                packets_received=packets_received,
                is_valid=False,
                mos_score=None,
                r_factor=None,
            )

        r_factor, mos = cls.calculate_mos(jitter_ms, loss_pct, rtt_ms)
        return MediaQualityMetrics(
            jitter_ms=round(jitter_ms, 2),
            loss_pct=round(loss_pct, 2),
            rtt_ms=round(rtt_ms, 2) if rtt_ms is not None else None,
            mos_score=mos,
            r_factor=r_factor,
            packets_sent=packets_sent,
            packets_received=packets_received,
            is_valid=True,
        )

    @classmethod
    def parse_ami_rtcp_events(
        cls, events: list[dict[str, Any]]
    ) -> MediaQualityMetrics:
        """Extract RTCP telemetry from Asterisk AMI event stream.

        Recognizes RTCPReceived, RTCPSent, and RTPAudioQuality events.
        If no valid RTCP telemetry is present, returns is_valid=False.
        """
        rtcp_events = [
            e for e in events if e.get("Event") in {"RTCPReceived", "RTCPSent", "RTPAudioQuality"}
        ]

        if not rtcp_events:
            return MediaQualityMetrics(is_valid=False)

        jitter_values: list[float] = []
        loss_values: list[float] = []
        rtt_values: list[float] = []
        total_sent = 0
        total_recv = 0

        for ev in rtcp_events:
            # Jitter extraction (can be in seconds or ms depending on event)
            raw_jitter = ev.get("Jitter") or ev.get("Report0Jitter") or ev.get("IAJitter")
            if raw_jitter is not None:
                try:
                    val = float(raw_jitter)
                    # If Asterisk reports jitter in seconds (e.g. 0.002), convert to ms
                    if val < 1.0 and val > 0.0:
                        val *= 1000.0
                    jitter_values.append(val)
                except (ValueError, TypeError):
                    pass

            # Packet loss extraction
            raw_loss = (
                ev.get("FractionLost")
                or ev.get("Report0FractionLost")
                or ev.get("LossPercent")
            )
            if raw_loss is not None:
                try:
                    loss_val = float(raw_loss)
                    # In RTCP, fraction lost is often 0-256 (where 256 = 100%)
                    if loss_val > 1.0 and loss_val <= 256.0 and "Fraction" in str(ev):
                        loss_val = (loss_val / 256.0) * 100.0
                    loss_values.append(loss_val)
                except (ValueError, TypeError):
                    pass

            # RTT extraction
            raw_rtt = ev.get("RTT") or ev.get("Report0RTT") or ev.get("RoundTripTime")
            if raw_rtt is not None:
                try:
                    rtt_val = float(raw_rtt)
                    if rtt_val < 1.0 and rtt_val > 0.0:
                        rtt_val *= 1000.0
                    rtt_values.append(rtt_val)
                except (ValueError, TypeError):
                    pass

            # Packets
            if "PacketsSent" in ev:
                total_sent = max(total_sent, int(ev["PacketsSent"]))
            if "PacketsReceived" in ev:
                total_recv = max(total_recv, int(ev["PacketsReceived"]))

        if not jitter_values or not loss_values:
            return MediaQualityMetrics(
                packets_sent=total_sent,
                packets_received=total_recv,
                is_valid=False,
            )

        avg_jitter = sum(jitter_values) / len(jitter_values)
        avg_loss = sum(loss_values) / len(loss_values)
        avg_rtt = sum(rtt_values) / len(rtt_values) if rtt_values else None

        return cls.from_metrics(
            jitter_ms=avg_jitter,
            loss_pct=avg_loss,
            rtt_ms=avg_rtt,
            packets_sent=total_sent,
            packets_received=total_recv,
        )

