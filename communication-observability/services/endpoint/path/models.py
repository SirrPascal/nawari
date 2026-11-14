"""Data structures and internal models for Network Path Analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MplsLabelEntry:
    """RFC 4950 MPLS Label Stack Entry (LSE).

    Represents a 4-byte MPLS header entry extracted from ICMP extension payload.
    """
    label: int      # 20 bits (0 - 1048575)
    exp: int        # 3 bits (0 - 7, Experimental / Traffic Class)
    bos: int        # 1 bit (0 or 1, Bottom of Stack indicator)
    ttl: int        # 8 bits (0 - 255)

    def __post_init__(self) -> None:
        if not (0 <= self.label <= 1048575):
            raise ValueError(f"MPLS label value out of 20-bit range: {self.label}")
        if not (0 <= self.exp <= 7):
            raise ValueError(f"MPLS EXP/TC out of 3-bit range: {self.exp}")
        if self.bos not in (0, 1):
            raise ValueError(f"MPLS Bottom of Stack (BOS) must be 0 or 1: {self.bos}")
        if not (0 <= self.ttl <= 255):
            raise ValueError(f"MPLS TTL out of 8-bit range: {self.ttl}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "exp": self.exp,
            "bos": self.bos,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MplsLabelEntry:
        return cls(
            label=int(data["label"]),
            exp=int(data["exp"]),
            bos=int(data["bos"]),
            ttl=int(data["ttl"]),
        )


@dataclass(frozen=True)
class RawHopProbe:
    """Raw unanalyzed probe response data collected at an individual TTL hop."""
    hop_index: int
    ip_address: Optional[str]
    rtts_ms: List[float] = field(default_factory=list)
    probes_sent: int = 3
    probes_received: int = 0
    mpls_labels: List[int] = field(default_factory=list)

