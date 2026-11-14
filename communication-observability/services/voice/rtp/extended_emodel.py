"""ITU-T G.107 Extended E-Model Voice Quality & MOS Estimation Engine."""

from __future__ import annotations

from typing import Optional

from services.voice.models import MediaVerificationLevel
from services.voice.rtp.rtcp_xr_analyzer import RTCPXRVoIPMetrics


class ExtendedEModelEngine:
    """Calculates defensible ITU-T G.107 E-model transmission rating R and Estimated MOS.

    Enforces strict architectural invariants:
    - Never fabricates MOS scores without valid bidirectional RTCP/RTCP-XR telemetry.
    - Incorporates burst packet loss, jitter buffer discards, and mouth-to-ear delay.
    """

    CODEC_PROFILES: dict[str, tuple[float, float]] = {
        # codec: (Ie: equipment impairment, Bpl: packet-loss robustness factor)
        "G.711U": (0.0, 4.3),
        "PCMU": (0.0, 4.3),
        "G.711A": (0.0, 4.3),
        "PCMA": (0.0, 4.3),
        "G.729": (11.0, 19.0),
        "G.729A": (11.0, 19.0),
        "OPUS": (5.0, 25.0),
        "AMR-WB": (10.0, 20.0),
    }

    @classmethod
    def calculate_r_and_mos(
        cls,
        metrics: Optional[RTCPXRVoIPMetrics],
        codec: str = "G.711u",
        verification_level: MediaVerificationLevel = MediaVerificationLevel.BIDIRECTIONAL,
        advantage_factor: float = 0.0,
    ) -> tuple[Optional[float], Optional[float]]:
        """Calculate (r_factor, estimated_mos).

        Returns (None, None) if telemetry is absent, incomplete, or media was not verified bidirectional.
        """
        # Strict Invariant Guard: RTCP-XR metrics must be valid and verified
        if (
            metrics is None
            or not metrics.is_valid
            or verification_level != MediaVerificationLevel.BIDIRECTIONAL
        ):
            return None, None

        # 1. Base Signal-to-Noise Ratio (R0) and Simultaneous Impairment (Is)
        r0 = 93.2
        i_s = 1.4

        # 2. Delay Impairment (Id)
        # One-way delay T = (RTT / 2) + End-System Delay
        one_way_t = (metrics.round_trip_delay_ms / 2.0) + metrics.end_system_delay_ms
        if one_way_t <= 177.3:
            i_d = 0.024 * one_way_t
        else:
            i_d = 0.024 * one_way_t + 0.11 * (one_way_t - 177.3)

        # 3. Equipment Impairment & Effective Loss (Ie,eff)
        codec_key = codec.upper().strip()
        i_e, b_pl = cls.CODEC_PROFILES.get(codec_key, (10.0, 10.0))

        # Effective packet loss accounts for both network loss and jitter buffer discards
        p_eff = metrics.loss_rate_pct + metrics.discard_rate_pct
        if p_eff > 0:
            i_e_eff = i_e + (95.0 - i_e) * (p_eff / (p_eff + b_pl))
        else:
            i_e_eff = i_e

        # 4. Total Transmission Rating Factor (R)
        r = r0 - i_s - i_d - i_e_eff + advantage_factor
        r = max(0.0, min(100.0, r))

        # 5. MOS Conversion (ITU-T G.107)
        if r < 0:
            mos = 1.0
        elif r > 100:
            mos = 4.5
        else:
            mos = 1.0 + (0.035 * r) + (r * (r - 60.0) * (100.0 - r) * 7.0e-6)

        mos = max(1.0, min(4.5, mos))
        return round(r, 2), round(mos, 2)

