"""services/multisite/wan_voice_probes.py
======================================
Trans-WAN Voice Quality Prober & Outstation Survivability Evaluator (Workstream 13D).

Monitors synthetic voice paths and SIP signaling between Central Hub (JKIA) and outstations
(e.g., Mombasa, Kisumu, London Heathrow). Calculates ITU-T G.107 E-model R-factor, listening
MOS, packet jitter, and packet loss, detecting voice trunk degradation before passenger
or flight operations are impacted.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nawari.multisite.wan_voice_probes")


class VoiceTrunkStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    DEGRADED = "DEGRADED"
    CRITICAL_FAILOVER = "CRITICAL_FAILOVER"


@dataclass
class VoiceProbeResult:
    """Represents a discrete synthetic voice probe across an outstation WAN circuit."""
    probe_id: str
    station_id: str
    circuit_id: str
    hub_endpoint: str
    edge_endpoint: str
    rtt_ms: float
    jitter_ms: float
    packet_loss_percent: float
    r_factor: float
    mos_score: float
    status: VoiceTrunkStatus
    failover_recommended: bool
    failover_target_circuit_id: Optional[str]
    notes: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "station_id": self.station_id,
            "circuit_id": self.circuit_id,
            "hub_endpoint": self.hub_endpoint,
            "edge_endpoint": self.edge_endpoint,
            "rtt_ms": round(self.rtt_ms, 2),
            "jitter_ms": round(self.jitter_ms, 2),
            "packet_loss_percent": round(self.packet_loss_percent, 2),
            "r_factor": round(self.r_factor, 2),
            "mos_score": round(self.mos_score, 2),
            "status": self.status.value,
            "failover_recommended": self.failover_recommended,
            "failover_target_circuit_id": self.failover_target_circuit_id,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }


class WanVoiceQualityEvaluator:
    """Calculates ITU-T G.107 E-model transmission ratings and determines

    outstation voice path health and failover urgency.
    """

    # G.711 codec baseline parameters
    R0 = 93.2  # Basic signal-to-noise ratio
    IS = 1.4   # Simultaneous impairment factor
    DEFAULT_BPL = 4.3  # Packet loss robustness factor for G.711

    @classmethod
    def calculate_r_factor(
        cls,
        one_way_delay_ms: float,
        packet_loss_percent: float,
        jitter_ms: float,
    ) -> float:
        """Calculate ITU-T G.107 transmission rating factor R:

        R = R0 - Is - Id - Ie_eff + A
        Where Id is delay impairment and Ie_eff is equipment/loss impairment.
        """
        # Effective delay including jitter buffer adaptation
        effective_delay = one_way_delay_ms + (2.0 * jitter_ms)

        # Delay impairment Id
        if effective_delay <= 100.0:
            id_delay = 0.0
        else:
            id_delay = 0.024 * effective_delay
            if effective_delay > 177.3:
                id_delay += 0.11 * (effective_delay - 177.3)

        # Equipment impairment Ie_eff with packet loss (loss is percentage 0..100)
        pl = max(0.0, min(100.0, packet_loss_percent))
        ie_eff = 30.0 * math.log(1.0 + 15.0 * (pl / 100.0))

        r = cls.R0 - id_delay - ie_eff
        return max(0.0, min(100.0, r))

    @classmethod
    def calculate_mos(cls, r_factor: float) -> float:
        """Convert R-factor to standard Listening MOS score (1.0 to 4.5)."""
        if r_factor <= 0.0:
            return 1.0
        elif r_factor >= 100.0:
            return 4.5
        elif 0.0 < r_factor < 60.0:
            return 1.0 + 0.035 * r_factor
        elif 60.0 <= r_factor <= 100.0:
            mos = 1.0 + 0.035 * r_factor + (r_factor * (r_factor - 60.0) * (100.0 - r_factor) * 7.0e-6)
            return max(1.0, min(4.5, mos))
        return 1.0


class TransWanVoiceProber:
    """Orchestrates synthetic voice probing between JKIA Hub and Outstations."""

    def __init__(self) -> None:
        self._probe_history: Dict[str, List[VoiceProbeResult]] = {}
        # Backup circuits table: station_id -> backup circuit
        self._circuit_redundancy_map = {
            "MBA-STATION": {"primary": "CIR-MBA-01", "secondary": "CIR-MBA-02"},
            "KIS-STATION": {"primary": "CIR-KIS-01", "secondary": "CIR-KIS-02"},
            "LHR-STATION": {"primary": "CIR-LHR-01", "secondary": "CIR-LHR-02"},
            "DXB-STATION": {"primary": "CIR-DXB-01", "secondary": "CIR-DXB-02"},
            "AMS-STATION": {"primary": "CIR-AMS-01", "secondary": "CIR-AMS-02"},
        }

    def execute_probe(
        self,
        station_id: str,
        circuit_id: str,
        rtt_ms: float,
        jitter_ms: float,
        packet_loss_percent: float,
        hub_endpoint: str = "10.10.10.15:5060",
        edge_endpoint: str = "10.20.1.10:5060",
    ) -> VoiceProbeResult:
        """Evaluate voice quality for a specific station circuit probe."""
        one_way_delay = rtt_ms / 2.0
        r_factor = WanVoiceQualityEvaluator.calculate_r_factor(
            one_way_delay_ms=one_way_delay,
            packet_loss_percent=packet_loss_percent,
            jitter_ms=jitter_ms,
        )
        mos = WanVoiceQualityEvaluator.calculate_mos(r_factor)

        notes: List[str] = []
        failover_recommended = False
        target_circuit: Optional[str] = None

        # Evaluate against aviation voice SLA standards:
        # Tier 1 voice SLA requires MOS >= 4.0, RTT <= 100ms, loss <= 1.0%
        if mos >= 4.0 and rtt_ms <= 100.0 and packet_loss_percent <= 1.0 and jitter_ms <= 20.0:
            status = VoiceTrunkStatus.OPTIMAL
            notes.append("Voice path meets Tier 1 Mission-Critical SLA criteria.")
        elif mos >= 3.5 and rtt_ms <= 250.0 and packet_loss_percent <= 3.0:
            status = VoiceTrunkStatus.DEGRADED
            notes.append("Voice quality degraded (elevated delay/jitter); non-critical distortion present.")
        else:
            status = VoiceTrunkStatus.CRITICAL_FAILOVER
            failover_recommended = True
            notes.append(f"Voice SLA breached: MOS={mos:.2f}, RTT={rtt_ms:.1f}ms, Loss={packet_loss_percent:.2f}%.")

            # Determine failover circuit
            st_circuits = self._circuit_redundancy_map.get(station_id, {})
            if circuit_id == st_circuits.get("primary"):
                target_circuit = st_circuits.get("secondary")
                notes.append(f"CRITICAL: Recommending immediate failover from primary {circuit_id} to secondary circuit {target_circuit}.")
            else:
                notes.append(f"CRITICAL: Primary and secondary paths impaired; recommend local PSTN survivability breakout.")

        result = VoiceProbeResult(
            probe_id=f"PROBE-{uuid.uuid4().hex[:8].upper()}",
            station_id=station_id,
            circuit_id=circuit_id,
            hub_endpoint=hub_endpoint,
            edge_endpoint=edge_endpoint,
            rtt_ms=rtt_ms,
            jitter_ms=jitter_ms,
            packet_loss_percent=packet_loss_percent,
            r_factor=r_factor,
            mos_score=mos,
            status=status,
            failover_recommended=failover_recommended,
            failover_target_circuit_id=target_circuit,
            notes=notes,
        )

        if station_id not in self._probe_history:
            self._probe_history[station_id] = []
        self._probe_history[station_id].append(result)

        return result

    def get_station_probes(self, station_id: str) -> List[VoiceProbeResult]:
        return list(self._probe_history.get(station_id, []))
