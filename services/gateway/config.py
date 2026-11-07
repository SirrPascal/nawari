"""Configuration and security policy for the Nawari Ingestion Gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.endpoint.models import TelemetricEnvironment


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration for the Nawari Telemetry Ingestion Gateway."""

    host: str = "127.0.0.1"
    port: int = 8443
    environment: TelemetricEnvironment = TelemetricEnvironment.MOCK_SIMULATED
    zabbix_server_host: str = "127.0.0.1"
    zabbix_server_port: int = 10051
    auth_token: Optional[str] = "nawari-dev-token"
    require_auth: bool = True
    max_payload_bytes: int = 2097152  # 2 MiB
    max_queue_depth: int = 5000
    backpressure_threshold: float = 0.90  # 90% of max_queue_depth triggers HTTP 429
    retry_after_seconds: int = 30
    enforce_replay_guard: bool = False  # Enabled in production/stress tests
    max_clock_skew_seconds: float = 300.0  # 5 minutes
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    allowed_agent_versions: List[str] = field(default_factory=lambda: ["1.0.0"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "environment": self.environment.value,
            "zabbix_server_host": self.zabbix_server_host,
            "zabbix_server_port": self.zabbix_server_port,
            "require_auth": self.require_auth,
            "max_payload_bytes": self.max_payload_bytes,
            "max_queue_depth": self.max_queue_depth,
            "backpressure_threshold": self.backpressure_threshold,
            "retry_after_seconds": self.retry_after_seconds,
            "tls_enabled": bool(self.tls_cert_path and self.tls_key_path),
        }

