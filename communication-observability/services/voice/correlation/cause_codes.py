"""ITU-T Q.850 & SIP RFC 3326 Reason Header Translation Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CauseInfo:
    cause_code: int
    name: str
    category: str  # NORMAL, STATION_STATE, DIALPLAN_DEFECT, TRUNK_CONGESTION, INFRASTRUCTURE, TIMEOUT
    description: str
    is_operational_failure: bool


class CauseCodeTranslator:
    """Translates ITU-T Q.850 cause codes and RFC 3326 Reason headers into actionable diagnostics."""

    Q850_DICTIONARY: dict[int, CauseInfo] = {
        1: CauseInfo(1, "Unallocated (unassigned) number", "DIALPLAN_DEFECT", "Dialed extension or number does not exist in dial plan", True),
        16: CauseInfo(16, "Normal call clearing", "NORMAL", "Normal hangup by user or network", False),
        17: CauseInfo(17, "User busy", "STATION_STATE", "Destination station is active on another call (station busy)", False),
        18: CauseInfo(18, "No user responding", "STATION_STATE", "Destination station alerting but no answer received", False),
        19: CauseInfo(19, "No answer from user (user alerted)", "STATION_STATE", "Destination station ring timeout expired", False),
        21: CauseInfo(21, "Call rejected", "POLICY_REJECTION", "Call blocked by administrative policy, COR/COS, or blacklist", True),
        28: CauseInfo(28, "Invalid number format (address incomplete)", "DIALPLAN_DEFECT", "Incomplete dialed digits or malformed number format", True),
        31: CauseInfo(31, "Normal, unspecified", "NORMAL", "Normal release without specific diagnostic detail", False),
        34: CauseInfo(34, "No circuit/channel available", "TRUNK_CONGESTION", "SIP trunk or B-channel circuit group is completely saturated", True),
        38: CauseInfo(38, "Network out of order", "INFRASTRUCTURE", "Transit signaling link or upstream network interface down", True),
        41: CauseInfo(41, "Temporary failure", "INFRASTRUCTURE", "Signaling proxy or gateway temporary routing failure", True),
        42: CauseInfo(42, "Switching equipment congestion", "TRUNK_CONGESTION", "Avaya PBX or switch CPU/queue congestion", True),
        47: CauseInfo(47, "Resource unavailable, unspecified", "RESOURCE_EXHAUSTION", "DSP resources, transcoders, or licenses exhausted", True),
        50: CauseInfo(50, "Requested facility not subscribed", "CONFIGURATION_ERROR", "Supplementary service not provisioned on trunk", True),
        55: CauseInfo(55, "Incoming calls barred within CUG", "POLICY_REJECTION", "Closed User Group policy rejected the call", True),
        58: CauseInfo(58, "Bearer capability not presently available", "CODEC_MISMATCH", "Requested voice codec or bandwidth not available", True),
        63: CauseInfo(63, "Service or option not available, unspecified", "INFRASTRUCTURE", "Signaling option not supported by downstream node", True),
        65: CauseInfo(65, "Bearer capability not implemented", "CODEC_UNSUPPORTED", "Negotiated codec is not supported by target appliance", True),
        88: CauseInfo(88, "Incompatible destination", "MEDIA_INCOMPATIBLE", "Media transport or encryption incompatibility (e.g. SRTP vs RTP)", True),
        102: CauseInfo(102, "Recovery on timer expiry", "TIMEOUT", "Signaling transaction timer expired waiting for peer response", True),
        111: CauseInfo(111, "Protocol error, unspecified", "PROTOCOL_ERROR", "Unparseable or non-compliant SIP/ISDN message", True),
    }

    _REASON_PATTERN = re.compile(
        r'(?:Q\.850|SIP)\s*;\s*cause\s*=\s*(\d+)(?:\s*;\s*text\s*=\s*"([^"]*)")?',
        re.IGNORECASE,
    )

    @classmethod
    def get_q850_info(cls, cause: int) -> CauseInfo:
        return cls.Q850_DICTIONARY.get(
            cause,
            CauseInfo(cause, f"Q.850 Cause {cause}", "UNKNOWN", f"Unrecognized Q.850 cause code {cause}", True),
        )

    @classmethod
    def parse_reason_header(cls, header_val: str | None) -> dict[str, Any]:
        """Parse RFC 3326 Reason header into protocol, cause code, and textual diagnostic."""
        if not header_val:
            return {}

        match = cls._REASON_PATTERN.search(header_val)
        if not match:
            return {"raw_reason": header_val}

        proto = "Q.850" if "Q.850" in header_val.upper() else "SIP"
        cause_code = int(match.group(1))
        text = match.group(2) or ""

        info = cls.get_q850_info(cause_code) if proto == "Q.850" else None

        return {
            "protocol": proto,
            "cause_code": cause_code,
            "text": text,
            "name": info.name if info else f"SIP {cause_code}",
            "category": info.category if info else "SIP_ERROR",
            "is_operational_failure": info.is_operational_failure if info else (cause_code >= 400),
        }

    @classmethod
    def classify_call_termination(
        cls,
        status_code: Optional[int],
        reason_header: Optional[str] = None,
        warning_header: Optional[str] = None,
    ) -> dict[str, Any]:
        """Classify call termination into operational categories distinguishing station state from trunk failure."""
        res: dict[str, Any] = {
            "status_code": status_code,
            "category": "SUCCESS",
            "is_infrastructure_failure": False,
            "diagnostic_summary": "Call completed successfully",
        }

        # Check Reason header first (contains authoritative release cause)
        if reason_header:
            parsed_reason = cls.parse_reason_header(reason_header)
            if parsed_reason:
                res["reason_info"] = parsed_reason
                res["category"] = parsed_reason.get("category", "UNKNOWN")
                res["is_infrastructure_failure"] = parsed_reason.get("is_operational_failure", False)
                res["diagnostic_summary"] = f"{parsed_reason.get('name')}: {parsed_reason.get('text')}".strip(": ")

        # Specific Avaya warning header analysis (e.g. Warning: 399 SM "User not registered")
        if warning_header and "User not registered" in warning_header:
            res["category"] = "STATION_STATE"
            res["is_infrastructure_failure"] = False
            res["diagnostic_summary"] = "Destination station offline / softphone logged out (User not registered)"
            return res

        if status_code == 200:
            res["category"] = "SUCCESS"
            res["is_infrastructure_failure"] = False
            res["diagnostic_summary"] = "Call established successfully"
        elif status_code == 480:
            res["category"] = "STATION_STATE"
            res["is_infrastructure_failure"] = False
            res["diagnostic_summary"] = "Destination temporarily unavailable / phone offline"
        elif status_code == 486:
            res["category"] = "STATION_STATE"
            res["is_infrastructure_failure"] = False
            res["diagnostic_summary"] = "Destination station busy"
        elif status_code == 487:
            res["category"] = "PROBE_TEARDOWN"
            res["is_infrastructure_failure"] = False
            res["diagnostic_summary"] = "Planned probe cancellation before answer"
        elif status_code in (404, 484):
            res["category"] = "DIALPLAN_DEFECT"
            res["is_infrastructure_failure"] = True
            res["diagnostic_summary"] = "Extension not found in PBX dial plan"
        elif status_code == 403:
            res["category"] = "POLICY_REJECTION"
            res["is_infrastructure_failure"] = True
            res["diagnostic_summary"] = "Call forbidden by PBX permissions or COR/COS"
        elif status_code in (500, 502, 503, 504):
            if "reason_info" not in res:
                res["category"] = "INFRASTRUCTURE"
                res["diagnostic_summary"] = f"Avaya server or trunk failure (SIP {status_code})"
            res["is_infrastructure_failure"] = True

        return res
