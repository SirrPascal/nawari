"""Telemetry Uploader and Spool Replay Client for the Endpoint Agent."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from services.endpoint.core.spooler import DiskSpooler
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
        req = self._build_request("/api/v1/telemetry", report.to_dict())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status in (200, 202):
                    return True
                logger.warning(f"Gateway returned non-success status: {resp.status}")
                return False
        except Exception as exc:
            logger.warning(f"Failed to upload telemetry report to {self.gateway_url}: {exc}")
            return False

    def replay_spooled(self, batch_size: int = 50) -> int:
        """Replay pending records from local disk spooler to Gateway and dequeue on confirmation."""
        if not self.spooler or self.spooler.get_pending_count() == 0:
            return 0

        pending_records = self.spooler.peek(limit=batch_size)
        if not pending_records:
            return 0

        req = self._build_request("/api/v1/telemetry/replay", {"reports": pending_records})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds * 2) as resp:
                if resp.status in (200, 202):
                    body = json.loads(resp.read().decode("utf-8"))
                    replayed_count = int(body.get("replayed_count", len(pending_records)))
                    if replayed_count > 0:
                        self.spooler.dequeue(count=replayed_count)
                        logger.info(f"Successfully replayed and dequeued {replayed_count} spooled reports")
                    return replayed_count
                return 0
        except Exception as exc:
            logger.warning(f"Failed to replay spooled records to {self.gateway_url}: {exc}")
            return 0

