"""Topology Visual Graph & REST API Service for Nawari Network Intelligence."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any

from services.topology.change_detector import TopologyChangeDetector
from services.topology.dependency import DependencyEngine
from services.topology.graph import TopologyGraph
from services.topology.models import Device, Interface, Layer2Link

logger = logging.getLogger("nawari.topology.api")


class TopologyAPI:
    """REST API service for Network Topology graph queries, blast radius, and change audit."""

    def __init__(
        self,
        graph: TopologyGraph | None = None,
        change_detector: TopologyChangeDetector | None = None,
    ) -> None:
        self.graph = graph or TopologyGraph()
        self.dependency_engine = DependencyEngine(self.graph)
        self.change_detector = change_detector or TopologyChangeDetector()

    def dispatch(
        self, method: str, path: str, query_params: dict[str, list[str]] | None = None
    ) -> tuple[int, dict[str, Any]]:
        """Dispatch an API request and return (status_code, response_data)."""
        method = method.upper()
        params = query_params or {}

        # 1. GET /api/v1/topology/graph
        if method == "GET" and path == "/api/v1/topology/graph":
            site_id = params.get("site_id", [None])[0]
            service_id = params.get("service_id", [None])[0]
            data = self.graph.to_node_graph(site_id=site_id, service_id=service_id)
            return HTTPStatus.OK, data

        # 2. GET /api/v1/topology/devices/{device_id}
        if method == "GET" and path.startswith("/api/v1/topology/devices/"):
            device_id = path[len("/api/v1/topology/devices/") :]
            dev = self.graph.get_device(device_id)
            if not dev:
                return HTTPStatus.NOT_FOUND, {"error": f"Device '{device_id}' not found"}
            interfaces = [i.to_dict() for i in self.graph.get_device_interfaces(device_id)]
            return HTTPStatus.OK, {
                "device": dev.to_dict(),
                "interfaces": interfaces,
            }

        # 3. GET /api/v1/topology/path
        if method == "GET" and path == "/api/v1/topology/path":
            src = params.get("source", [None])[0]
            dst = params.get("destination", [None])[0]
            if not src or not dst:
                return HTTPStatus.BAD_REQUEST, {"error": "Parameters 'source' and 'destination' are required"}

            src_dev = self.graph.get_device(src) or self.graph.find_device_by_ip(src)
            dst_dev = self.graph.get_device(dst) or self.graph.find_device_by_ip(dst)

            if not src_dev:
                return HTTPStatus.NOT_FOUND, {"error": f"Source device '{src}' not found"}
            if not dst_dev:
                return HTTPStatus.NOT_FOUND, {"error": f"Destination device '{dst}' not found"}

            path_nodes = self.graph.find_path(src_dev.device_id, dst_dev.device_id)
            nodes = [self.graph.devices[did].to_dict() for did in path_nodes if did in self.graph.devices]

            return HTTPStatus.OK, {
                "source": src_dev.device_id,
                "destination": dst_dev.device_id,
                "hop_count": max(0, len(path_nodes) - 1),
                "path": path_nodes,
                "nodes": nodes,
            }

        # 4. GET /api/v1/topology/blast-radius
        if method == "GET" and path == "/api/v1/topology/blast-radius":
            dev_id = params.get("device_id", [None])[0]
            if_id = params.get("interface_id", [None])[0]

            if not dev_id and not if_id:
                return HTTPStatus.BAD_REQUEST, {"error": "Must provide either 'device_id' or 'interface_id'"}

            if if_id:
                try:
                    report = self.dependency_engine.calculate_interface_blast_radius(if_id)
                    return HTTPStatus.OK, report.to_dict()
                except KeyError as e:
                    return HTTPStatus.NOT_FOUND, {"error": str(e)}
            elif dev_id:
                try:
                    report = self.dependency_engine.calculate_device_blast_radius(dev_id)
                    return HTTPStatus.OK, report.to_dict()
                except KeyError as e:
                    return HTTPStatus.NOT_FOUND, {"error": str(e)}

        # 5. GET /api/v1/topology/spof
        if method == "GET" and path == "/api/v1/topology/spof":
            spofs = self.dependency_engine.identify_single_points_of_failure()
            return HTTPStatus.OK, {"spofs": spofs}

        # 6. GET /api/v1/topology/changes
        if method == "GET" and path == "/api/v1/topology/changes":
            entity_id = params.get("entity_id", [None])[0]
            try:
                within = int(params.get("within_seconds", [900])[0])
            except (ValueError, TypeError):
                within = 900

            if entity_id:
                changes = self.change_detector.find_recent_changes_for_entity(
                    entity_id=entity_id, within_seconds=within
                )
            else:
                changes = self.change_detector.changes_log

            return HTTPStatus.OK, {"changes": [c.to_dict() for c in changes]}

        return HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{method} {path}' not found"}


class TopologyRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler routing requests to the TopologyAPI instance."""

    @property
    def api(self) -> TopologyAPI:
        return getattr(self.server, "api", None)  # type: ignore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        status, data = self.api.dispatch("GET", parsed.path, params)

        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(f"{self.address_string()} - {format % args}")


class TopologyAPIServer(ThreadingHTTPServer):
    """Standard multi-threaded HTTP server exposing the Topology REST API."""

    def __init__(self, server_address: tuple[str, int], api: TopologyAPI) -> None:
        self.api = api
        super().__init__(server_address, TopologyRequestHandler)
