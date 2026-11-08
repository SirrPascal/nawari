"""RFC 3264 / RFC 4566 SDP Offer/Answer Inspector and Codec Negotiator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SDPMediaSession:
    media_type: str = "audio"
    port: int = 0
    protocol: str = "RTP/AVP"
    payload_types: list[int] = field(default_factory=list)
    codec_map: dict[int, str] = field(default_factory=dict)
    ptime: int = 20
    connection_ip: Optional[str] = None
    raw_sdp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_type": self.media_type,
            "port": self.port,
            "protocol": self.protocol,
            "payload_types": self.payload_types,
            "codec_map": self.codec_map,
            "ptime": self.ptime,
            "connection_ip": self.connection_ip,
        }


class SDPInspector:
    """Parses and validates SDP session descriptions and offer/answer negotiations."""

    STATIC_PAYLOADS = {
        0: "PCMU/8000",
        8: "PCMA/8000",
        9: "G722/8000",
        18: "G729/8000",
    }

    @classmethod
    def parse_sdp(cls, sdp_text: Optional[str]) -> Optional[SDPMediaSession]:
        """Parse raw SDP text into structured SDPMediaSession."""
        if not sdp_text or not sdp_text.strip():
            return None

        lines = sdp_text.splitlines()
        session = SDPMediaSession(raw_sdp=sdp_text)

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3 or line[1] != "=":
                continue

            prefix = line[:2].lower()
            val = line[2:].strip()

            if prefix == "c=":
                # c=IN IP4 10.2.156.60
                c_parts = val.split()
                if len(c_parts) >= 3:
                    session.connection_ip = c_parts[2]

            elif prefix == "m=":
                # m=audio 10002 RTP/AVP 0 8 18
                m_parts = val.split()
                if len(m_parts) >= 4:
                    session.media_type = m_parts[0].lower()
                    try:
                        session.port = int(m_parts[1])
                    except ValueError:
                        session.port = 0
                    session.protocol = m_parts[2].upper()
                    session.payload_types = []
                    for pt_str in m_parts[3:]:
                        try:
                            pt = int(pt_str)
                            session.payload_types.append(pt)
                            if pt in cls.STATIC_PAYLOADS:
                                session.codec_map[pt] = cls.STATIC_PAYLOADS[pt]
                        except ValueError:
                            pass

            elif prefix == "a=":
                # a=rtpmap:111 opus/48000/2
                if val.lower().startswith("rtpmap:"):
                    sub = val[len("rtpmap:") :].strip()
                    rtp_parts = sub.split(maxsplit=1)
                    if len(rtp_parts) == 2:
                        try:
                            pt = int(rtp_parts[0])
                            session.codec_map[pt] = rtp_parts[1].strip()
                        except ValueError:
                            pass

                # a=ptime:20
                elif val.lower().startswith("ptime:"):
                    try:
                        session.ptime = int(val[len("ptime:") :].strip())
                    except ValueError:
                        pass

        return session

    @classmethod
    def compare_offer_answer(
        cls, offer_sdp: Optional[str], answer_sdp: Optional[str]
    ) -> dict[str, Any]:
        """Compare SDP offer and answer and detect codec mismatches or packetization anomalies."""
        offer = cls.parse_sdp(offer_sdp)
        answer = cls.parse_sdp(answer_sdp)

        if not offer or not answer:
            return {
                "negotiation_success": False,
                "error": "Incomplete SDP offer/answer pair",
                "selected_codec": None,
            }

        # Check common codecs
        common_pts = [pt for pt in answer.payload_types if pt in offer.payload_types]
        if not common_pts:
            return {
                "negotiation_success": False,
                "error": "Codec Mismatch: No intersecting audio payload types between offer and answer",
                "offered_codecs": list(offer.codec_map.values()),
                "answered_codecs": list(answer.codec_map.values()),
                "selected_codec": None,
            }

        selected_pt = common_pts[0]
        selected_codec = answer.codec_map.get(
            selected_pt, offer.codec_map.get(selected_pt, f"PT-{selected_pt}")
        )

        anomalies = []
        if offer.ptime != answer.ptime:
            anomalies.append(
                f"Asymmetric packetization time: Offer ptime={offer.ptime}ms vs Answer ptime={answer.ptime}ms"
            )

        if offer.protocol != answer.protocol:
            anomalies.append(
                f"Media protocol mismatch: Offer {offer.protocol} vs Answer {answer.protocol}"
            )

        return {
            "negotiation_success": True,
            "selected_payload_type": selected_pt,
            "selected_codec": selected_codec,
            "ptime": answer.ptime,
            "anomalies": anomalies,
            "has_anomalies": len(anomalies) > 0,
        }

