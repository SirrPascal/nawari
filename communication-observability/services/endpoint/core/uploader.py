"""Telemetry Uploader and Spool Replay Client for the Endpoint Agent."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from services.endpoint.core.spooler import DiskSpooler
from services.endpoint.delivery import RECEIPT_VERSION, TARGET_ACCEPTED, record_id
from services.endpoint.models import EndpointTelemetryReport

logger = logging.getLogger("nawari.endpoint.uploader")


class TelemetryUploader:
    """Transmits endpoint telemetry to the Ingestion Gateway and manages spool replay."""

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8443",
        auth_token: Optional[str] = "nawari-dev-token",
        spooler: Optional[DiskSpooler] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.auth_token = auth_token
        self.spooler = spooler
        self.timeout_seconds = timeout_seconds

    def _build_request(self, endpoint_path: str, data: Dict[str, Any]) -> urllib.request.Request:
        url = f"{self.gateway_url}{endpoint_path}"
        payload_bytes = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload_bytes, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(payload_bytes)))
        if self.auth_token:
            req.add_header("Authorization", f"Bearer {self.auth_token}")
            req.add_header("X-Nawari-Token", self.auth_token)
        return req

    def upload_report(self, report: EndpointTelemetryReport) -> bool:
        """Transmit single telemetry report to Ingestion Gateway."""
        payload = report.to_dict()
        try:
            identifier = record_id(payload)
        except (ValueError, TypeError):
            return False
        response = self._send("/api/v1/telemetry", payload, self.timeout_seconds)
        return (
            response.get("receipt_version") == RECEIPT_VERSION
            and response.get("record_id") == identifier
            and response.get("receipt") == TARGET_ACCEPTED
        )

    def replay_spooled(self, batch_size: int = 50) -> int:
        """Replay pending records and remove only explicitly acknowledged IDs."""
        if not self.spooler or batch_size <= 0:
            return 0

        pending = []
        sent_ids = set()
        for report in self.spooler.peek(limit=batch_size):
            try:
                sent_ids.add(record_id(report))
                pending.append(report)
            except (ValueError, TypeError):
                continue
        if not pending:
            return 0

        response = self._send(
            "/api/v1/telemetry/replay",
            {"reports": pending, "receipt_version": RECEIPT_VERSION},
            self.timeout_seconds * 2,
        )
        receipts = response.get("receipts")
        if (
            response.get("receipt_version") != RECEIPT_VERSION
            or not isinstance(receipts, dict)
            or not receipts.keys() <= sent_ids
        ):
            return 0
        acknowledged = {identifier for identifier, outcome in receipts.items() if outcome == TARGET_ACCEPTED}
        return self.spooler.acknowledge(acknowledged)

    def _send(self, path: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        try:
            request = self._build_request(path, payload)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    return {}
                body = json.load(response)
                return body if isinstance(body, dict) else {}
        except urllib.error.HTTPError as exc:
            logger.warning("Endpoint gateway returned HTTP %s; telemetry retained", exc.code)
        except (OSError, ValueError):
            logger.warning("Endpoint gateway confirmation unavailable; telemetry retained")
        return {}
