"""Bounded HTTP API and same-origin frontend hosting."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import identity


def make_server(store, host="127.0.0.1", port=18090, fixture=False, web=None, netdata=None):
    if fixture and host not in {"127.0.0.1", "::1"}:
        raise ValueError("fixture_mode_requires_loopback")
    web = Path(web or Path(__file__).parents[1] / "web/dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "Nawari/0.1"

        def log_message(self, *_):
            # Requests can include protected query identifiers. Keep them out of logs.
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, value):
            payload = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def token(self):
            header = self.headers.get("Authorization", "")
            return header[7:] if header.startswith("Bearer ") and len(header) <= 512 else ""

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/healthz":
                return self.reply(200, {"status": "ready", "version": "0.1.0", "release": os.environ.get("NAWARI_RELEASE_ID", "development"), "mode": "fixture" if fixture else "authenticated"})
            if parsed.path == "/api/v1/investigation":
                auth = {"tenant": "fixture"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                try:
                    query = parse_qs(parsed.query, max_num_fields=12)
                    def get(key):
                        values = query.get(key, [])
                        if len(values) > 1:
                            raise ValueError("duplicate_query_field")
                        return values[0] if values else None
                    start, end = get("start"), get("end")
                    data = store.investigation(auth["tenant"], get("device"), get("service"),
                                               float(start) if start else None, float(end) if end else None,
                                               int(get("limit") or 500), int(get("offset") or 0))
                    data["mode"] = "fixture" if fixture else "authenticated"
                    return self.reply(200, data)
                except (ValueError, TypeError, OverflowError):
                    return self.reply(400, {"error": "invalid_query"})
            parts = parsed.path.strip("/").split("/")
            if len(parts) in {5, 7} and parts[:3] == ["api", "v1", "devices"] and parts[4] == "metrics":
                auth = {"tenant": "fixture"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                try:
                    query = parse_qs(parsed.query, max_num_fields=8)
                    if any(len(values) != 1 for values in query.values()):
                        raise ValueError("duplicate_query_field")
                    get = lambda key: query.get(key, [None])[0]
                    asset = parts[3]
                    if len(parts) == 5:
                        data = store.metrics(auth["tenant"], asset, get("q"), get("section"),
                                             int(get("limit") or 100), int(get("offset") or 0))
                        data["mode"] = "fixture" if fixture else "authenticated"
                        return self.reply(200, data)
                    if parts[6] != "history" or netdata is None:
                        return self.reply(503, {"error": "metric_history_source_unavailable"})
                    metric = store.metric(auth["tenant"], asset, parts[5])
                    if metric is None:
                        return self.reply(404, {"error": "metric_not_found"})
                    now = store.clock()
                    start, end = float(get("start") or now - 3600), float(get("end") or now)
                    return self.reply(200, netdata.query(metric, start, end, int(get("points") or 120)))
                except (ValueError, TypeError, OverflowError):
                    return self.reply(400, {"error": "invalid_metric_query"})
                except Exception:
                    return self.reply(503, {"error": "metric_source_unavailable"})
            if parsed.path == "/api/v1/endpoints":
                auth = {"tenant": "fixture"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                try:
                    query = parse_qs(parsed.query, max_num_fields=8)
                    get = lambda key: query.get(key, [None])[0]
                    data = store.list_endpoints(auth["tenant"], get("site"), get("lifecycle"), get("q"),
                                                int(get("limit") or 100), int(get("offset") or 0))
                    data["mode"] = "fixture" if fixture else "authenticated"
                    return self.reply(200, data)
                except (ValueError, TypeError):
                    return self.reply(400, {"error": "invalid_query"})
            if parsed.path == "/api/v1/endpoints/conflicts":
                auth = {"tenant": "fixture"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                conflicts = store.get_endpoint_conflicts(auth["tenant"])
                return self.reply(200, {"tenant": auth["tenant"], "conflicts": conflicts, "mode": "fixture" if fixture else "authenticated"})
            if len(parts) == 4 and parts[:3] == ["api", "v1", "endpoints"]:
                auth = {"tenant": "fixture", "role": "operator"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                data = store.get_endpoint(auth["tenant"], parts[3])
                if not data:
                    return self.reply(404, {"error": "endpoint_not_found"})
                # RBAC data redaction: mask sensitive hardware serials for readers
                role = auth.get("role", "reader")
                if role == "reader":
                    if data.get("serial_number"):
                        data["serial_number"] = "[REDACTED]"
                    if data.get("chassis_uuid"):
                        data["chassis_uuid"] = "[REDACTED]"
                data["mode"] = "fixture" if fixture else "authenticated"
                return self.reply(200, data)
            if parsed.path.startswith("/api/"):
                return self.reply(404, {"error": "unknown_resource"})
            relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            candidate = (web / relative).resolve()
            if web not in candidate.parents or not candidate.is_file():
                return self.reply(404, {"error": "frontend_not_built_or_resource_missing"})
            types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}
            content = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", types.get(candidate.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if self.path == "/api/v1/endpoints/reconcile":
                auth = {"tenant": "fixture", "role": "operator"} if fixture else store.authenticate(self.token(), operator=True)
                if not auth:
                    return self.reply(401, {"error": "operator_authentication_required"})
                role = auth.get("role", "operator" if fixture else "reader")
                if role not in {"admin", "operator"}:
                    return self.reply(403, {"error": "reconciliation_permission_denied"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        return self.reply(413, {"error": "payload_size_limit"})
                    payload = json.loads(self.rfile.read(length))
                    hw = None
                    if "hardware" in payload and payload["hardware"]:
                        hw = identity.DeviceHardwareIdentity(
                            serial_number=payload["hardware"].get("serial_number"),
                            chassis_uuid=payload["hardware"].get("chassis_uuid"),
                            mac_address=payload["hardware"].get("mac_address"),
                        )
                    ifaces = []
                    for iface in payload.get("interfaces", []):
                        ifaces.append(identity.NetworkInterfaceObservation(
                            interface_name=iface["interface_name"],
                            interface_type=iface.get("interface_type", "ETHERNET"),
                            ip_address=iface["ip_address"],
                            mac_address=iface.get("mac_address"),
                            subnet_mask=iface.get("subnet_mask"),
                            gateway_ip=iface.get("gateway_ip"),
                            ssid=iface.get("ssid"),
                            bssid=iface.get("bssid"),
                        ))
                    # Server-side trust enforcement:
                    # Trust levels must be derived exclusively from authenticated server-side principals and roles.
                    # Never accept authoritative trust claims from client JSON payloads without verification.
                    if role == "admin":
                        requested_trust = payload.get("trust_level")
                        if requested_trust in {
                            identity.TRUST_LEVEL_ENROLLMENT,
                            identity.TRUST_LEVEL_INVENTORY,
                            identity.TRUST_LEVEL_COLLECTOR,
                            identity.TRUST_LEVEL_UNVERIFIED,
                        }:
                            trust_level = requested_trust
                        elif payload.get("authoritative"):
                            trust_level = identity.TRUST_LEVEL_INVENTORY
                        else:
                            trust_level = identity.TRUST_LEVEL_INVENTORY
                        authoritative = (trust_level in identity.TRUSTED_OWNERSHIP_LEVELS)
                    elif role == "operator":
                        # Operators represent collectors or telemetry pipelines and cannot assert ownership
                        requested_trust = payload.get("trust_level")
                        if requested_trust == identity.TRUST_LEVEL_UNVERIFIED:
                            trust_level = identity.TRUST_LEVEL_UNVERIFIED
                        else:
                            trust_level = identity.TRUST_LEVEL_COLLECTOR
                        authoritative = False
                    else:
                        trust_level = identity.TRUST_LEVEL_UNVERIFIED
                        authoritative = False

                    obs = identity.EndpointObservation(
                        tenant=auth["tenant"],
                        hostname=payload["hostname"],
                        source_system=payload["source_system"],
                        source_identifier=payload["source_identifier"],
                        device_kind=payload.get("device_kind", "laptop"),
                        os_family=payload.get("os_family", "unknown"),
                        os_version=payload.get("os_version", "unknown"),
                        site_id=payload.get("site_id", "default"),
                        routing_domain_id=payload.get("routing_domain_id", "default"),
                        trust_level=trust_level,
                        authoritative=authoritative,
                        hardware=hw,
                        interfaces=ifaces,
                        observed_at=float(payload.get("observed_at", 0.0) or store.clock()),
                    )
                    res = store.reconcile_endpoint(obs)
                    return self.reply(200, {
                        "endpoint_id": res.endpoint_id,
                        "status": res.status,
                        "conflict_id": res.conflict_id,
                        "details": res.details,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    return self.reply(400, {"error": f"invalid_reconciliation_payload: {e}"})

            if self.path != "/api/v1/evidence":
                return self.reply(404, {"error": "unknown_resource"})
            token = self.token()
            if not store.authenticate(token):
                return self.reply(401, {"error": "enrollment_authentication_required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 262144:
                    return self.reply(413, {"error": "batch_size_limit"})
                batch = json.loads(self.rfile.read(length))
                if not isinstance(batch, list) or not 1 <= len(batch) <= 32:
                    return self.reply(400, {"error": "invalid_batch"})
                results = [store.ingest(token, record) for record in batch]
                return self.reply(200, {"results": results})
            except (ValueError, TypeError, UnicodeError):
                return self.reply(400, {"error": "invalid_json"})
            except Exception:
                # A failed or ambiguous commit must be retried using the original IDs.
                return self.reply(503, {"error": "durable_acceptance_unavailable"})

    return ThreadingHTTPServer((host, port), Handler)
