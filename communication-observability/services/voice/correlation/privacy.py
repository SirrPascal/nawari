"""Privacy & PII Protection Engine for Voice Observability and Dialed Numbers."""

from __future__ import annotations

import re
from typing import Optional

# Allowlisted internal diagnostic endpoints that do not require PII masking
ALLOWLISTED_EXTENSIONS: set[str] = {
    "1001",  # Diagnostic Echo Test
    "1002",  # Diagnostic Fast Answer
    "1003",  # Diagnostic Busy Simulation
    "1004",  # Diagnostic Congestion Simulation
    "4286",  # Internal Test Extension
}


def mask_phone_number(number: Optional[str]) -> str:
    """Mask sensitive telephone digits in accordance with aviation and customer data privacy standards.

    Preserves country code and operator prefix for carrier route verification while redacting individual subscriber digits.
    Examples:
        "+254712345678" -> "+2547****678"
        "0712345678"    -> "071****678"
        "2398"          -> "2**8" (non-allowlisted internal extension)
        "1001"          -> "1001" (allowlisted diagnostic extension preserved)
    """
    if not number:
        return "ANONYMOUS"

    clean = re.sub(r"[\s\-\(\)]", "", number.strip())

    if clean in ALLOWLISTED_EXTENSIONS:
        return clean

    # E.164 Kenyan number format (+254 7XX ...)
    if clean.startswith("+254") and len(clean) >= 12:
        prefix = clean[:5]  # +2547
        suffix = clean[-3:]
        return f"{prefix}****{suffix}"

    # Kenyan local mobile format (07XX ...)
    if clean.startswith("07") and len(clean) >= 10:
        prefix = clean[:3]  # 071
        suffix = clean[-3:]
        return f"{prefix}****{suffix}"

    # 4-digit internal extension
    if len(clean) == 4 and clean.isdigit():
        return f"{clean[0]}**{clean[-1]}"

    # 5-digit outstation extension
    if len(clean) == 5 and clean.isdigit():
        return f"{clean[:2]}**{clean[-1]}"

    # Generic masking for arbitrary length
    if len(clean) > 6:
        return f"{clean[:3]}****{clean[-3:]}"

    return "****"


def mask_sip_uri(uri: Optional[str]) -> str:
    """Mask the user/number portion of a SIP URI while preserving domain/host.

    Example: 'sip:+254712345678@10.2.156.60:5060' -> 'sip:+2547****678@10.2.156.60:5060'
    """
    if not uri:
        return ""

    match = re.match(r"^(sips?:)?([^@]+)@(.+)$", uri.strip(), re.IGNORECASE)
    if not match:
        return mask_phone_number(uri)

    scheme = match.group(1) or "sip:"
    user = match.group(2)
    host = match.group(3)

    masked_user = mask_phone_number(user)
    return f"{scheme}{masked_user}@{host}"
