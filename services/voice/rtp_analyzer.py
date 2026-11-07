"""RTP/RTCP Telemetry Analysis and ITU-T G.107 E-Model Estimated MOS Engine.

Calculates voice transmission rating (R-factor) and Estimated MOS based on
measured RTCP parameters, codec impairment models, and mouth-to-ear latency.

CRITICAL ARCHITECTURAL INVARIANT:
When RTCP telemetry is absent, incomplete, or below threshold, media quality MUST
be reported as UNKNOWN (is_valid=False, estimated_mos=None, r_factor=None).
Healthy values must NEVER be fabricated or assumed.
"""

import math
from typing import Any, Optional

from services.voice.models import MediaQualityMetrics, MediaVerificationLevel


class RtpAnalyzer:
    """Analyzes RTCP telemetry and computes ITU-T G.107 E-model Estimated MOS."""

    # Baseline theoretical maximum signal-to-noise ratio for G.711 Narrowband
    R0_DEFAULT: float = 93.2

    # Standard packetization delay (20ms for 160 samples @ 8kHz)
    DEFAULT_PACKETIZATION_DELAY_MS: float = 20.0

    @classmethod
    def calculate_mouth_to_ear_delay(
        cls,
        rtt_ms: Optional[float],
        jitter_ms: float,
        packetization_delay_ms: float = 20.0,
    ) -> float:
        """Compute total one-way mouth-to-ear delay d in milliseconds.

        d = (RTT / 2) + (2 * jitter_buffer) + packetization_delay
        Accounts for physical transit, de-jitter buffer holding time, and encoder framing.
        """
        half_rtt = (rtt_ms / 2.0) if rtt_ms is not None and rtt_ms > 0 else 0.0
        # Adaptive jitter buffer buffer depth approximated as 2 * jitter
        de_jitter_delay = 2.0 * max(0.0, jitter_ms)
        return half_rtt + de_jitter_delay + packetization_delay_ms

    @classmethod
    def calculate_estimated_mos(
        cls,
        jitter_ms: Optional[float],
        loss_pct: Optional[float],
        rtt_ms: Optional[float] = None,
        codec: str = "G.711u",
        burst_ratio: float = 1.0,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate estimated R-Factor, Estimated MOS, and one-way delay using ITU-T G.107.

        Returns (r_factor, estimated_mos, one_way_delay_ms).
        If mandatory metrics are absent, returns (None, None, None).
        """
        if jitter_ms is None or loss_pct is None:
            return None, None, None

        jitter = max(0.0, float(jitter_ms))
        loss = max(0.0, min(100.0, float(loss_pct)))
        rtt = max(0.0, float(rtt_ms)) if rtt_ms is not None else 0.0

        # 1. Total one-way mouth-to-ear delay
        one_way_delay = cls.calculate_mouth_to_ear_delay(rtt, jitter, cls.DEFAULT_PACKETIZATION_DELAY_MS)

        # 2. Delay impairment Id
        # ITU-T G.107 Equation for delay impairment
        if one_way_delay <= 100.0:
            id_impairment = 0.0
        else:
            id_impairment = 0.024 * one_way_delay
            if one_way_delay > 177.3:
                id_impairment += 0.11 * (one_way_delay - 177.3)

        # 3. Equipment impairment Ie (Codec & Packet Loss)
        codec_upper = codec.upper()
        if "729" in codec_upper:
            # G.729A: intrinsic impairment Ie=11 + packet loss factor
            base_ie = 11.0
            ie_impairment = base_ie + (40.0 * (loss / (loss + 10.0)))
        elif "OPUS" in codec_upper:
            # Opus Narrowband
            ie_impairment = 15.0 * math.log(1.0 + 10.0 * (loss / 100.0))
        else:
            # G.711 (Default): 0 intrinsic impairment at 0% loss
            # Incorporates burst ratio Bpl (Bpl=1 random, Bpl>1 bursty)
            effective_loss = loss * max(1.0, burst_ratio)
            ie_impairment = 30.0 * math.log(1.0 + 15.0 * (effective_loss / 100.0))

        # 4. Transmission rating factor R
        r_factor = cls.R0_DEFAULT - id_impairment - ie_impairment
        r_factor = max(0.0, min(100.0, r_factor))

        # 5. Conversion from R to Estimated MOS (ITU-T G.107 Eq. 6-1)
        if r_factor <= 0.0:
            estimated_mos = 1.0
        elif r_factor >= 100.0:
            estimated_mos = 4.5
        else:
            estimated_mos = (
                1.0
                + (0.035 * r_factor)
                + (r_factor * (r_factor - 60.0) * (100.0 - r_factor) * 7.0e-6)
            )
            estimated_mos = max(1.0, min(4.5, estimated_mos))

        return round(r_factor, 1), round(estimated_mos, 2), round(one_way_delay, 1)

    @classmethod
    def calculate_mos(
        cls,
        jitter_ms: Optional[float],
        loss_pct: Optional[float],
        rtt_ms: Optional[float],
    ) -> tuple[Optional[float], Optional[float]]:
        """Backward-compatible helper returning (r_factor, estimated_mos)."""
        r, mos, _ = cls.calculate_estimated_mos(jitter_ms, loss_pct, rtt_ms)
        return r, mos

    @classmethod
    def determine_verification_level(
        cls, packets_sent: int, packets_received: int
    ) -> MediaVerificationLevel:
        """Classify bidirectional media verification state."""
        if packets_sent > 0 and packets_received > 0:
            return MediaVerificationLevel.BIDIRECTIONAL
        elif packets_sent > 0 and packets_received == 0:
            return MediaVerificationLevel.TRANSMIT_ONLY
        elif packets_received > 0 and packets_sent == 0:
            return MediaVerificationLevel.RECEIVE_ONLY
        elif packets_sent == 0 and packets_received == 0:
            return MediaVerificationLevel.NO_MEDIA
        return MediaVerificationLevel.UNVERIFIED

    @classmethod
    def from_metrics(
        cls,
        jitter_ms: Optional[float] = None,
        loss_pct: Optional[float] = None,
        rtt_ms: Optional[float] = None,
        packets_sent: int = 0,
        packets_received: int = 0,
        codec: str = "G.711u",
    ) -> MediaQualityMetrics:
        """Create MediaQualityMetrics with strict validity and bidirectional verification."""
        v_level = cls.determine_verification_level(packets_sent, packets_received)

        if jitter_ms is None or loss_pct is None:
            return MediaQualityMetrics(
                jitter_ms=jitter_ms,
                loss_pct=loss_pct,
                rtt_ms=rtt_ms,
                packets_sent=packets_sent,
                packets_received=packets_received,
                codec=codec,
                verification_level=v_level,
                is_valid=False,
                estimated_mos=None,
                r_factor=None,
                one_way_delay_ms=None,
            )

        r_factor, mos, delay_ms = cls.calculate_estimated_mos(
            jitter_ms=jitter_ms, loss_pct=loss_pct, rtt_ms=rtt_ms, codec=codec
        )

        return MediaQualityMetrics(
            jitter_ms=round(jitter_ms, 2),
            loss_pct=round(loss_pct, 2),
            rtt_ms=round(rtt_ms, 2) if rtt_ms is not None else None,
            one_way_delay_ms=delay_ms,
            estimated_mos=mos,
            r_factor=r_factor,
            packets_sent=packets_sent,
            packets_received=packets_received,
            codec=codec,
            verification_level=v_level,
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

        # Extract packet counters from any available events
        total_sent = 0
        total_recv = 0
        for ev in events:
            if "PacketsSent" in ev:
                try:
                    total_sent = max(total_sent, int(ev["PacketsSent"]))
                except (ValueError, TypeError):
                    pass
            if "PacketsReceived" in ev:
                try:
                    total_recv = max(total_recv, int(ev["PacketsReceived"]))
                except (ValueError, TypeError):
                    pass

        v_level = cls.determine_verification_level(total_sent, total_recv)

        if not rtcp_events:
            return MediaQualityMetrics(
                packets_sent=total_sent,
                packets_received=total_recv,
                verification_level=v_level,
                is_valid=False,
            )

        jitter_values: list[float] = []
        loss_values: list[float] = []
        rtt_values: list[float] = []

        for ev in rtcp_events:
            raw_jitter = ev.get("Jitter") or ev.get("Report0Jitter") or ev.get("IAJitter")
            if raw_jitter is not None:
                try:
                    val = float(raw_jitter)
                    # Convert seconds to ms if reported in seconds (e.g. 0.005 -> 5.0)
                    if 0.0 < val < 1.0:
                        val *= 1000.0
                    jitter_values.append(val)
                except (ValueError, TypeError):
                    pass

            raw_loss = (
                ev.get("FractionLost")
                or ev.get("Report0FractionLost")
                or ev.get("LossPercent")
            )
            if raw_loss is not None:
                try:
                    loss_val = float(raw_loss)
                    # Convert 8-bit fraction lost (0-256) to percentage (0-100%)
                    if 1.0 < loss_val <= 256.0 and "Fraction" in str(ev):
                        loss_val = (loss_val / 256.0) * 100.0
                    loss_values.append(loss_val)
                except (ValueError, TypeError):
                    pass

            raw_rtt = ev.get("RTT") or ev.get("Report0RTT") or ev.get("RoundTripTime")
            if raw_rtt is not None:
                try:
                    rtt_val = float(raw_rtt)
                    if 0.0 < rtt_val < 1.0:
                        rtt_val *= 1000.0
                    rtt_values.append(rtt_val)
                except (ValueError, TypeError):
                    pass

        if not jitter_values or not loss_values:
            return MediaQualityMetrics(
                packets_sent=total_sent,
                packets_received=total_recv,
                verification_level=v_level,
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
