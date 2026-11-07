"""RFC 4950 Multi-Protocol Label Switching (MPLS) ICMP Extension Parser."""

from __future__ import annotations

import re
import struct
from typing import List, Optional

from services.endpoint.path.models import MplsLabelEntry


class MplsLabelParser:
    """Parser for RFC 4950 MPLS ICMP extension objects and text tags."""

    @staticmethod
    def parse_rfc4950(data: bytes) -> List[MplsLabelEntry]:
        """Parse binary RFC 4950 ICMP Extension Object payload.

        RFC 4950 Section 2.1 Object Header:
          0                   1                   2                   3
          0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
         +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
         |             Length            |   Class-Num   |   C-Type      |
         +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
         |                    MPLS Label Stack Entry                     |
         +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

        Class-Num = 1 (MPLS)
        C-Type = 1 (Incoming MPLS payload label stack)
        """
        if len(data) < 4:
            return []

        obj_len, class_num, class_type = struct.unpack("!HBB", data[:4])
        # Validate Class-Num and Class-Type for MPLS (RFC 4950)
        if class_num != 1 or class_type != 1:
            return []

        entries: List[MplsLabelEntry] = []
        offset = 4
        limit = min(obj_len, len(data))

        while offset + 4 <= limit:
            entry_raw = struct.unpack("!I", data[offset : offset + 4])[0]
            label = (entry_raw >> 12) & 0xFFFFF
            exp = (entry_raw >> 9) & 0x07
            bos = (entry_raw >> 8) & 0x01
            ttl = entry_raw & 0xFF

            entries.append(
                MplsLabelEntry(
                    label=label,
                    exp=exp,
                    bos=bos,
                    ttl=ttl,
                )
            )
            offset += 4

        return entries

    @staticmethod
    def parse_text_tag(text: str) -> List[MplsLabelEntry]:
        """Parse textual MPLS annotations emitted by standard traceroute tools.

        Example formats:
          [MPLS: Label 1002 Exp 0 S 1 TTL 1]
          [MPLS: 1002]
        """
        entries: List[MplsLabelEntry] = []
        # Pattern matching: Label <num> [Exp <num>] [S <num>] [TTL <num>]
        matches = re.finditer(
            r"\[MPLS:\s*(?:Label\s+)?(\d+)(?:\s+Exp\s+(\d+))?(?:\s+S\s+(\d+))?(?:\s+TTL\s+(\d+))?\]",
            text,
            re.IGNORECASE,
        )
        for m in matches:
            label = int(m.group(1))
            exp = int(m.group(2)) if m.group(2) is not None else 0
            bos = int(m.group(3)) if m.group(3) is not None else 1
            ttl = int(m.group(4)) if m.group(4) is not None else 1

            try:
                entries.append(
                    MplsLabelEntry(
                        label=label,
                        exp=exp,
                        bos=bos,
                        ttl=ttl,
                    )
                )
            except ValueError:
                continue

        return entries

