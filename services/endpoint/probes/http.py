"""HTTP and HTTPS application latency and availability probe."""

from __future__ import annotations

import asyncio
import http.client
import socket
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class HttpStatusOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    CLIENT_ERROR_4XX = "CLIENT_ERROR_4XX"
    SERVER_ERROR_5XX = "SERVER_ERROR_5XX"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class HttpProbeResult:
    url: str
    method: str
    status_outcome: HttpStatusOutcome
    is_success: bool
    status_code: Optional[int]
    dns_time_ms: Optional[float]
    tcp_time_ms: Optional[float]
    tls_time_ms: Optional[float]
    ttfb_ms: Optional[float]
    total_time_ms: Optional[float]
    response_size_bytes: Optional[int]
    redirect_count: int = 0
    final_url: Optional[str] = None
    error_message: Optional[str] = None


class HttpProbe:
    """Measures HTTP(S) endpoint availability with decomposed timing:

    DNS lookup -> TCP connect -> TLS handshake -> Time To First Byte (TTFB) -> Total.

    Data Privacy Invariant:
    Never logs or persists response bodies, cookies, or authorization tokens.
    """

    def __init__(
        self,
        default_timeout_seconds: float = 5.0,
        max_response_bytes: int = 1048576,  # 1 MB max
        max_redirects: int = 3,
        verify_certificates: bool = True,
    ) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.verify_certificates = verify_certificates

    async def probe(
        self,
        url: str,
        method: str = "GET",
        expected_status_codes: Optional[List[int]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> HttpProbeResult:
        """Asynchronously execute decomposed HTTP probe."""
        timeout = timeout_seconds or self.default_timeout_seconds
        expected_codes = expected_status_codes or [200, 201, 204, 301, 302, 304]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sync_probe,
            url,
            method.upper(),
            expected_codes,
            timeout,
        )

    def _execute_sync_probe(
        self,
        url: str,
        method: str,
        expected_codes: List[int],
        timeout: float,
    ) -> HttpProbeResult:
        t_total_start = time.perf_counter()

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=HttpStatusOutcome.ERROR,
                is_success=False,
                status_code=None,
                dns_time_ms=None,
                tcp_time_ms=None,
                tls_time_ms=None,
                ttfb_ms=None,
                total_time_ms=None,
                response_size_bytes=None,
                error_message=f"Unsupported URL scheme: {parsed.scheme}",
            )

        is_https = (parsed.scheme == "https")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if is_https else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        # 1. Measure DNS lookup
        t_dns_start = time.perf_counter()
        try:
            addr_info = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
            target_ip = addr_info[0][4][0]
            dns_time_ms = (time.perf_counter() - t_dns_start) * 1000.0
        except Exception as exc:
            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=HttpStatusOutcome.CONNECTION_FAILED,
                is_success=False,
                status_code=None,
                dns_time_ms=round((time.perf_counter() - t_dns_start) * 1000.0, 2),
                tcp_time_ms=None,
                tls_time_ms=None,
                ttfb_ms=None,
                total_time_ms=round((time.perf_counter() - t_total_start) * 1000.0, 2),
                response_size_bytes=None,
                error_message=f"DNS resolution failed: {exc}",
            )

        # 2. Measure TCP connect
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(timeout)
        t_tcp_start = time.perf_counter()
        try:
            raw_sock.connect((target_ip, port))
            tcp_time_ms = (time.perf_counter() - t_tcp_start) * 1000.0
        except Exception as exc:
            raw_sock.close()
            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=HttpStatusOutcome.CONNECTION_FAILED,
                is_success=False,
                status_code=None,
                dns_time_ms=round(dns_time_ms, 2),
                tcp_time_ms=round((time.perf_counter() - t_tcp_start) * 1000.0, 2),
                tls_time_ms=None,
                ttfb_ms=None,
                total_time_ms=round((time.perf_counter() - t_total_start) * 1000.0, 2),
                response_size_bytes=None,
                error_message=f"TCP connection failed: {exc}",
            )

        # 3. Measure TLS handshake if HTTPS
        tls_time_ms = None
        active_sock = raw_sock
        if is_https:
            if self.verify_certificates:
                ctx = ssl.create_default_context()
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            tls_sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            tls_sock.settimeout(timeout)
            t_tls_start = time.perf_counter()
            try:
                tls_sock.do_handshake()
                tls_time_ms = (time.perf_counter() - t_tls_start) * 1000.0
                active_sock = tls_sock
            except Exception as exc:
                tls_sock.close()
                return HttpProbeResult(
                    url=url,
                    method=method,
                    status_outcome=HttpStatusOutcome.CONNECTION_FAILED,
                    is_success=False,
                    status_code=None,
                    dns_time_ms=round(dns_time_ms, 2),
                    tcp_time_ms=round(tcp_time_ms, 2),
                    tls_time_ms=round((time.perf_counter() - t_tls_start) * 1000.0, 2),
                    ttfb_ms=None,
                    total_time_ms=round((time.perf_counter() - t_total_start) * 1000.0, 2),
                    response_size_bytes=None,
                    error_message=f"TLS handshake failed: {exc}",
                )

        # 4. HTTP Request & TTFB Measurement
        try:
            if is_https:
                conn = http.client.HTTPSConnection(host, port=port, timeout=timeout)
                conn.sock = active_sock
            else:
                conn = http.client.HTTPConnection(host, port=port, timeout=timeout)
                conn.sock = active_sock

            t_req_start = time.perf_counter()
            headers = {
                "Host": host,
                "User-Agent": "Nawari-Endpoint-Agent/1.0",
                "Accept": "*/*",
                "Connection": "close",
            }
            conn.request(method, path, headers=headers)

            # TTFB: Read response header
            response = conn.getresponse()
            ttfb_ms = (time.perf_counter() - t_req_start) * 1000.0
            status_code = response.status

            # Read bounded body (discard content, measure byte count only for privacy)
            body = response.read(self.max_response_bytes)
            response_size = len(body)
            total_time_ms = (time.perf_counter() - t_total_start) * 1000.0

            # Evaluate outcome
            if status_code in expected_codes:
                outcome = HttpStatusOutcome.SUCCESS
                is_success = True
            elif 400 <= status_code < 500:
                outcome = HttpStatusOutcome.CLIENT_ERROR_4XX
                is_success = False
            elif status_code >= 500:
                outcome = HttpStatusOutcome.SERVER_ERROR_5XX
                is_success = False
            else:
                outcome = HttpStatusOutcome.SUCCESS if (200 <= status_code < 400) else HttpStatusOutcome.ERROR
                is_success = outcome == HttpStatusOutcome.SUCCESS

            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=outcome,
                is_success=is_success,
                status_code=status_code,
                dns_time_ms=round(dns_time_ms, 2),
                tcp_time_ms=round(tcp_time_ms, 2),
                tls_time_ms=round(tls_time_ms, 2) if tls_time_ms is not None else None,
                ttfb_ms=round(ttfb_ms, 2),
                total_time_ms=round(total_time_ms, 2),
                response_size_bytes=response_size,
                final_url=url,
                error_message=None,
            )

        except socket.timeout:
            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=HttpStatusOutcome.TIMEOUT,
                is_success=False,
                status_code=None,
                dns_time_ms=round(dns_time_ms, 2),
                tcp_time_ms=round(tcp_time_ms, 2),
                tls_time_ms=round(tls_time_ms, 2) if tls_time_ms is not None else None,
                ttfb_ms=None,
                total_time_ms=round((time.perf_counter() - t_total_start) * 1000.0, 2),
                response_size_bytes=None,
                error_message=f"HTTP request timed out after {timeout}s",
            )
        except Exception as exc:
            return HttpProbeResult(
                url=url,
                method=method,
                status_outcome=HttpStatusOutcome.ERROR,
                is_success=False,
                status_code=None,
                dns_time_ms=round(dns_time_ms, 2),
                tcp_time_ms=round(tcp_time_ms, 2),
                tls_time_ms=round(tls_time_ms, 2) if tls_time_ms is not None else None,
                ttfb_ms=None,
                total_time_ms=round((time.perf_counter() - t_total_start) * 1000.0, 2),
                response_size_bytes=None,
                error_message=str(exc),
            )
        finally:
            try:
                active_sock.close()
            except Exception:
                pass

