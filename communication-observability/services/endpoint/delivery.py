"""Shared identity and receipt vocabulary for endpoint telemetry delivery."""

import hashlib
import json
from typing import Any

RECEIPT_VERSION = 1
TARGET_ACCEPTED = "TARGET_ACCEPTED"
RETRY = "RETRY"
REJECTED = "REJECTED"


def record_id(report: dict[str, Any]) -> str:
    """Identify the immutable wire report, including its original acquisition timestamp."""
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
