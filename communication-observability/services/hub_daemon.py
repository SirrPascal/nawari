"""services/hub_daemon.py
======================
Nawari Central Hub Enterprise Service Assurance & Telemetry Ingestion Daemon.

Main entry point for the nawari-core application container.
Binds HTTP/HTTPS Ingestion Gateway, serves health checks (/health, /api/v1/health),
receives telemetry reports, routes metrics to Zabbix, and handles lifecycle signals.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from services.endpoint.models import TelemetricEnvironment
from services.gateway.config import GatewayConfig
from services.gateway.server import IngestionGatewayServer
from services.voice.zabbix_sender import ZabbixSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nawari.hub")

VERSION = "1.0.0-phase13"


def parse_environment(env_str: str) -> TelemetricEnvironment:
    """Safely map environment string to TelemetricEnvironment enum."""
    lookup = {
        "production": TelemetricEnvironment.PHYSICAL_PRODUCTION,
        "staging": TelemetricEnvironment.MOCK_SIMULATED,
        "simulation": TelemetricEnvironment.MOCK_SIMULATED,
        "development": TelemetricEnvironment.MOCK_SIMULATED,
    }
    return lookup.get(env_str.lower().strip(), TelemetricEnvironment.MOCK_SIMULATED)


class HubDaemon:
    """Lifecycle controller for Nawari Central Hub application."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8443,
        env_name: str = "staging",
        profile: str = "staging",
        zabbix_host: str = "zabbix-server",
        zabbix_port: int = 10051,
        auth_token: Optional[str] = None,
        require_auth: bool = False,
        receipt_db_path: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.env_name = env_name
        self.profile = profile
        self.zabbix_host = zabbix_host
        self.zabbix_port = zabbix_port
        self.auth_token = auth_token
        self.require_auth = require_auth
        self.receipt_db_path = receipt_db_path

        self.telemetry_env = parse_environment(env_name)
        self._shutdown_event = threading.Event()
        self.gateway: Optional[IngestionGatewayServer] = None

    def start(self) -> None:
        """Start the Ingestion Gateway and all background sub-services."""
        logger.info("==================================================================")
        logger.info("NAWARI ENTERPRISE PLATFORM — CENTRAL HUB DAEMON")
        logger.info(f"Version:      {VERSION}")
        logger.info(f"Environment:  {self.env_name} ({self.telemetry_env.value})")
        logger.info(f"Profile:      {self.profile}")
        logger.info(f"Listen:       http://{self.host}:{self.port}")
        logger.info(f"Zabbix Host:  {self.zabbix_host}:{self.zabbix_port}")
        logger.info(f"Auth Guard:   {'Enforced' if self.require_auth else 'Disabled/Permissive'}")
        logger.info("==================================================================")

        config = GatewayConfig(
            host=self.host,
            port=self.port,
            environment=self.telemetry_env,
            zabbix_server_host=self.zabbix_host,
            zabbix_server_port=self.zabbix_port,
            auth_token=self.auth_token,
            require_auth=self.require_auth,
            receipt_db_path=self.receipt_db_path,
        )

        zabbix_sender = ZabbixSender(
            host=self.zabbix_host,
            port=self.zabbix_port,
        )

        self.gateway = IngestionGatewayServer(
            config=config,
            zabbix_sender=zabbix_sender,
        )

        self.gateway.start()
        logger.info(f"Nawari Ingestion Gateway started successfully on port {self.port}")

    def stop(self) -> None:
        """Stop all running services cleanly."""
        logger.info("Received termination signal. Initiating graceful shutdown...")
        if self.gateway:
            self.gateway.stop()
            self.gateway = None
        self._shutdown_event.set()
        logger.info("Nawari Central Hub Daemon shutdown complete")

    def run_forever(self) -> None:
        """Main process loop."""
        self.start()

        def _signal_handler(signum, frame):
            logger.info(f"Signal {signum} caught by daemon")
            self.stop()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        logger.info("Hub Daemon is running. Health endpoints active on /health and /api/v1/health")
        while not self._shutdown_event.is_set():
            time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hub_daemon",
        description="Nawari Central Hub Ingestion Gateway & Service Assurance Daemon",
    )
    parser.add_argument("--host", default=os.getenv("NAWARI_HOST", "0.0.0.0"), help="Bind host IP")
    parser.add_argument("--port", type=int, default=int(os.getenv("NAWARI_PORT", "8443")), help="Bind TCP port")
    parser.add_argument("--env", default=os.getenv("NAWARI_ENV", "staging"), help="Environment name (staging/production/simulation)")
    parser.add_argument("--profile", default=os.getenv("NAWARI_PROFILE", "staging"), help="Deployment profile name")
    parser.add_argument("--zabbix-host", default=os.getenv("ZABBIX_SERVER_HOST", "zabbix-server"), help="Zabbix Server host")
    parser.add_argument("--zabbix-port", type=int, default=int(os.getenv("ZABBIX_SERVER_PORT", "10051")), help="Zabbix Server port")
    parser.add_argument("--auth-token", default=os.getenv("NAWARI_AUTH_TOKEN"), help="API Auth Token")
    parser.add_argument("--require-auth", action="store_true", default=os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes"), help="Enforce token auth")
    parser.add_argument("--receipt-db-path", default=os.getenv("NAWARI_RECEIPT_DB_PATH"), help="Protected SQLite path for endpoint receipts")
    parser.add_argument("--version", action="version", version=f"Nawari Hub {VERSION}")

    args = parser.parse_args()

    daemon = HubDaemon(
        host=args.host,
        port=args.port,
        env_name=args.env,
        profile=args.profile,
        zabbix_host=args.zabbix_host,
        zabbix_port=args.zabbix_port,
        auth_token=args.auth_token,
        require_auth=args.require_auth,
        receipt_db_path=args.receipt_db_path,
    )

    try:
        daemon.run_forever()
    except (KeyboardInterrupt, SystemExit):
        daemon.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
