"""HTTPS/HTTP Ingestion Gateway Server for Nawari Endpoint Telemetry."""

from __future__ import annotations

import hmac
import json
import logging
import ssl
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from services.endpoint.models import EndpointTelemetryReport, TelemetricEnvironment
from services.gateway.config import GatewayConfig
from services.gateway.zabbix_mapper import ZabbixEndpointMapper
from services.voice.zabbix_sender import ZabbixSender

logger = logging.getLogger("nawari.gateway.server")


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for receiving endpoint telemetry and dispatching to Zabbix."""

    @property
    def gateway(self) -> "IngestionGatewayServer":
        return getattr(self.server, "gateway", self.server)  # type: ignore

    def log_message(self, format: str, *args: Any) -> None:
        # Route handler logging to standard logging
        logger.debug(f"{self.address_string()} - {format % args}")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _verify_auth(self) -> bool:
        if not self.gateway.config.require_auth:
            return True

        auth_header = self.headers.get("Authorization", "")
        token_header = self.headers.get("X-Nawari-Token", "")
        expected = self.gateway.config.auth_token

        if not expected:
            return True

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if hmac.compare_digest(token, expected):
                return True

        if token_header.strip() and hmac.compare_digest(token_header.strip(), expected):
            return True

        return False

    def do_GET(self) -> None:
        """Route GET requests: /api/v1/health or /health."""
        if self.path in ("/api/v1/health", "/health"):
            stats = self.gateway.get_stats()
            self._send_json_response(HTTPStatus.OK, stats)
        else:
            self._send_json_response(HTTPStatus.NOT_FOUND, {"error": f"Endpoint not found: {self.path}"})

    def do_POST(self) -> None:
        """Route POST requests: /api/v1/telemetry and /api/v1/telemetry/replay."""
        # 0. Backpressure / Congestion Guard (Workstream 8F)
        if self.gateway.is_congested():
            body = json.dumps({
                "error": "Gateway ingestion queue is backpressured; spool telemetry locally and retry",
                "retry_after": self.gateway.config.retry_after_seconds,
            }).encode("utf-8")
            self.send_response(HTTPStatus.TOO_MANY_REQUESTS)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", str(self.gateway.config.retry_after_seconds))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 1. Authentication Guard
        if not self._verify_auth():
            self._send_json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "Unauthorized: Missing or invalid authentication token"},
            )
            return

        # 2. Content Length & Body Size Guard
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length header"})
            return

        if content_length > self.gateway.config.max_payload_bytes:
            self._send_json_response(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"Payload size exceeds maximum limit of {self.gateway.config.max_payload_bytes} bytes"},
            )
            return

        body = self.rfile.read(content_length)

        # 3. Endpoint Routing with Queue Tracking
        self.gateway.increment_queue_depth()
        try:
            if self.path == "/api/v1/telemetry":
                self._handle_telemetry_post(body)
            elif self.path == "/api/v1/telemetry/replay":
                self._handle_replay_post(body)
            else:
                self._send_json_response(HTTPStatus.NOT_FOUND, {"error": f"Endpoint not found: {self.path}"})
        finally:
            self.gateway.decrement_queue_depth()

    def _handle_telemetry_post(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            report = EndpointTelemetryReport.from_dict(payload)
        except Exception as exc:
            logger.warning(f"Rejected malformed telemetry payload: {exc}")
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Malformed telemetry payload: invalid schema or JSON syntax"},
            )
            return

        # Invariant 3: Authoritative Telemetry Provenance & Anti-Spoofing Guard
        server_env = self.gateway.config.environment
        if (
            server_env == TelemetricEnvironment.MOCK_SIMULATED
            and report.metadata.environment == TelemetricEnvironment.PHYSICAL_PRODUCTION
        ):
            self._send_json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "Anti-spoofing guard: Client cannot claim PHYSICAL_PRODUCTION in MOCK_SIMULATED gateway environment."},
            )
            return

        server_ts_ns = time.time_ns()

        # Map to Zabbix metrics and LLD
        metrics = ZabbixEndpointMapper.map_report_to_metrics(
            report=report,
            authoritative_environment=server_env,
            server_received_timestamp_ns=server_ts_ns,
        )

        # Dispatch to Zabbix Server
        dispatch_success = self.gateway.dispatch_to_zabbix(metrics)

        self.gateway.record_ingestion()

        self._send_json_response(
            HTTPStatus.OK,
            {
                "status": "ACCEPTED",
                "agent_id": report.metadata.agent_id,
                "hostname": report.metadata.hostname,
                "metrics_dispatched": len(metrics),
                "zabbix_dispatched": dispatch_success,
                "server_received_timestamp_ns": server_ts_ns,
                "environment": server_env.value,
            },
        )

    def _handle_replay_post(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            reports_data = payload.get("reports", payload if isinstance(payload, list) else [])
            if not isinstance(reports_data, list):
                raise ValueError("Reports field must be a list of telemetry reports")
        except Exception as exc:
            logger.warning(f"Rejected malformed replay payload: {exc}")
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Malformed replay payload: invalid schema or JSON syntax"},
            )
            return

        server_env = self.gateway.config.environment
        server_ts_ns = time.time_ns()
        replayed_count = 0

        for r_dict in reports_data:
            try:
                report = EndpointTelemetryReport.from_dict(r_dict)
                # Anti-spoofing check
                if (
                    server_env == TelemetricEnvironment.MOCK_SIMULATED
                    and report.metadata.environment == TelemetricEnvironment.PHYSICAL_PRODUCTION
                ):
                    continue

                metrics = ZabbixEndpointMapper.map_report_to_metrics(
                    report=report,
                    authoritative_environment=server_env,
                    server_received_timestamp_ns=server_ts_ns,
                )
                self.gateway.dispatch_to_zabbix(metrics)
                self.gateway.record_ingestion()
                replayed_count += 1
            except Exception as exc:
                logger.warning(f"Error processing replayed report: {exc}")

        self._send_json_response(
            HTTPStatus.OK,
            {
                "status": "ACCEPTED",
                "replayed_count": replayed_count,
                "server_received_timestamp_ns": server_ts_ns,
            },
        )


class IngestionGatewayServer:
    """Threaded HTTPS/HTTP Telemetry Ingestion Gateway."""

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        zabbix_sender: Optional[ZabbixSender] = None,
    ) -> None:
        self.config = config or GatewayConfig()
        self.zabbix_sender = zabbix_sender or ZabbixSender(
            host=self.config.zabbix_server_host,
            port=self.config.zabbix_server_port,
        )
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._total_ingested_reports: int = 0
        self._active_queue_depth: int = 0
        self._lock = threading.Lock()

    def is_congested(self) -> bool:
        """Determines if the active queue depth exceeds the backpressure threshold."""
        with self._lock:
            threshold = int(self.config.max_queue_depth * self.config.backpressure_threshold)
            return self._active_queue_depth >= threshold

    def increment_queue_depth(self) -> None:
        with self._lock:
            self._active_queue_depth += 1

    def decrement_queue_depth(self) -> None:
        with self._lock:
            if self._active_queue_depth > 0:
                self._active_queue_depth -= 1

    def start(self) -> None:
        """Start the Gateway HTTP server in a background daemon thread."""
        server_address = (self.config.host, self.config.port)

        class CustomServer(ThreadingHTTPServer):
            def __init__(self, addr: Any, handler_cls: Any, gateway_inst: IngestionGatewayServer):
                self.gateway = gateway_inst
                super().__init__(addr, handler_cls)

            def finish_request(self, request: Any, client_address: Any) -> None:
                # Inject gateway instance into handler
                self.RequestHandlerClass.server = self.gateway
                super().finish_request(request, client_address)

        self._httpd = CustomServer(server_address, GatewayRequestHandler, self)

        # Configure TLS if certificates provided
        if self.config.tls_cert_path and self.config.tls_key_path:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(
                certfile=self.config.tls_cert_path,
                keyfile=self.config.tls_key_path,
            )
            self._httpd.socket = ctx.wrap_socket(self._httpd.socket, server_side=True)
            logger.info(f"Ingestion Gateway HTTPS enabled on port {self.config.port}")

        self._start_time = time.time()
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info(
            f"Ingestion Gateway started on http{'s' if self.config.tls_cert_path else ''}://"
            f"{self.config.host}:{self.config.port} (Env: {self.config.environment.value})"
        )

    def stop(self) -> None:
        """Stop the Gateway HTTP server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("Ingestion Gateway stopped cleanly")

    @property
    def is_running(self) -> bool:
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    def record_ingestion(self) -> None:
        with self._lock:
            self._total_ingested_reports += 1

    def dispatch_to_zabbix(self, metrics: List[Any]) -> bool:
        """Dispatch converted metrics to Zabbix Server Trapper items."""
        if not metrics:
            return True
        try:
            self.zabbix_sender.send(metrics)
            return True
        except Exception as exc:
            logger.warning(f"Error dispatching metrics to Zabbix: {exc}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            ingested = self._total_ingested_reports
            queue_depth = self._active_queue_depth
        uptime = round(time.time() - self._start_time, 2) if self._start_time > 0 else 0.0
        return {
            "status": "HEALTHY",
            "environment": self.config.environment.value,
            "zabbix_server": f"{self.config.zabbix_server_host}:{self.config.zabbix_server_port}",
            "require_auth": self.config.require_auth,
            "total_ingested_reports": ingested,
            "active_queue_depth": queue_depth,
            "max_queue_depth": self.config.max_queue_depth,
            "uptime_seconds": uptime,
        }
