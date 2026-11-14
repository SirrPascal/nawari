"""TLS handshake latency, certificate validity, and protocol negotiation probe."""

from __future__ import annotations

import asyncio
import datetime
import socket
import ssl
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TlsHandshakeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    CERTIFICATE_EXPIRED = "CERTIFICATE_EXPIRED"
    HOSTNAME_MISMATCH = "HOSTNAME_MISMATCH"
    CERT_UNTRUSTED = "CERT_UNTRUSTED"
    HANDSHAKE_TIMEOUT = "HANDSHAKE_TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TlsProbeResult:
    destination_host: str
    destination_port: int
    status: TlsHandshakeStatus
    is_valid: bool
    handshake_time_ms: Optional[float]
    tls_version: Optional[str]
    cipher_suite: Optional[str]
    cert_subject: Optional[str]
    cert_issuer: Optional[str]
    cert_not_after: Optional[str]
    cert_days_remaining: Optional[int]
    error_message: Optional[str] = None


class TlsProbe:
    """Measures TLS handshake latency, protocol version, cipher suite, and certificate health.

    Invariant:
    Certificate verification is strictly ENABLED by default. The agent will never
    silently bypass certificate verification.
    """

    def __init__(self, verify_certificates: bool = True, default_timeout_seconds: float = 3.0) -> None:
        self.verify_certificates = verify_certificates
        self.default_timeout_seconds = default_timeout_seconds

    async def probe(
        self,
        destination_host: str,
        destination_port: int = 5061,
        server_hostname: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        verify_certificates: Optional[bool] = None,
    ) -> TlsProbeResult:
        """Asynchronously execute TLS handshake probe."""
        timeout = timeout_seconds or self.default_timeout_seconds
        verify = self.verify_certificates if verify_certificates is None else verify_certificates
        sni_host = server_hostname or destination_host

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sync_probe,
            destination_host,
            destination_port,
            sni_host,
            timeout,
            verify,
        )

    def _execute_sync_probe(
        self,
        destination_host: str,
        destination_port: int,
        server_hostname: str,
        timeout: float,
        verify: bool,
    ) -> TlsProbeResult:
        # Create SSL context
        if verify:
            ctx = ssl.create_default_context()
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(timeout)

        t_tcp_start = time.perf_counter()
        try:
            raw_sock.connect((destination_host, destination_port))
        except socket.timeout:
            raw_sock.close()
            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=TlsHandshakeStatus.CONNECTION_FAILED,
                is_valid=False,
                handshake_time_ms=None,
                tls_version=None,
                cipher_suite=None,
                cert_subject=None,
                cert_issuer=None,
                cert_not_after=None,
                cert_days_remaining=None,
                error_message=f"Underlying TCP connection timed out after {timeout}s",
            )
        except Exception as exc:
            raw_sock.close()
            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=TlsHandshakeStatus.CONNECTION_FAILED,
                is_valid=False,
                handshake_time_ms=None,
                tls_version=None,
                cipher_suite=None,
                cert_subject=None,
                cert_issuer=None,
                cert_not_after=None,
                cert_days_remaining=None,
                error_message=f"TCP connection failed: {exc}",
            )

        # Wrap in TLS and measure handshake time
        tls_sock = ctx.wrap_socket(raw_sock, server_hostname=server_hostname)
        tls_sock.settimeout(timeout)

        t_handshake_start = time.perf_counter()
        try:
            tls_sock.do_handshake()
            handshake_time_ms = (time.perf_counter() - t_handshake_start) * 1000.0

            tls_version = tls_sock.version()
            cipher_info = tls_sock.cipher()
            cipher_name = cipher_info[0] if cipher_info else None

            # Parse certificate details
            peer_cert = tls_sock.getpeercert()
            cert_subject = None
            cert_issuer = None
            not_after_str = None
            days_remaining = None
            cert_status = TlsHandshakeStatus.SUCCESS
            err_msg = None

            if peer_cert:
                not_after_str = peer_cert.get("notAfter")
                if not_after_str:
                    try:
                        # Format e.g. "May 25 12:00:00 2027 GMT"
                        expiry_dt = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(
                            tzinfo=datetime.timezone.utc
                        )
                        now_dt = datetime.datetime.now(datetime.timezone.utc)
                        delta = expiry_dt - now_dt
                        days_remaining = delta.days
                        if days_remaining < 0:
                            cert_status = TlsHandshakeStatus.CERTIFICATE_EXPIRED
                            err_msg = f"Certificate expired {abs(days_remaining)} days ago on {not_after_str}"
                    except Exception:
                        pass

                # Extract subject common name
                for rdn in peer_cert.get("subject", ()):
                    for k, v in rdn:
                        if k == "commonName":
                            cert_subject = v

                for rdn in peer_cert.get("issuer", ()):
                    for k, v in rdn:
                        if k == "commonName":
                            cert_issuer = v

            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=cert_status,
                is_valid=(cert_status == TlsHandshakeStatus.SUCCESS),
                handshake_time_ms=round(handshake_time_ms, 2),
                tls_version=tls_version,
                cipher_suite=cipher_name,
                cert_subject=cert_subject,
                cert_issuer=cert_issuer,
                cert_not_after=not_after_str,
                cert_days_remaining=days_remaining,
                error_message=err_msg,
            )

        except ssl.SSLCertVerificationError as exc:
            handshake_time_ms = (time.perf_counter() - t_handshake_start) * 1000.0
            err_text = str(exc)
            if "certificate has expired" in err_text.lower():
                status = TlsHandshakeStatus.CERTIFICATE_EXPIRED
            elif "hostname mismatch" in err_text.lower() or "doesn't match" in err_text.lower():
                status = TlsHandshakeStatus.HOSTNAME_MISMATCH
            else:
                status = TlsHandshakeStatus.CERT_UNTRUSTED

            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=status,
                is_valid=False,
                handshake_time_ms=round(handshake_time_ms, 2),
                tls_version=None,
                cipher_suite=None,
                cert_subject=None,
                cert_issuer=None,
                cert_not_after=None,
                cert_days_remaining=None,
                error_message=err_text,
            )

        except socket.timeout:
            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=TlsHandshakeStatus.HANDSHAKE_TIMEOUT,
                is_valid=False,
                handshake_time_ms=None,
                tls_version=None,
                cipher_suite=None,
                cert_subject=None,
                cert_issuer=None,
                cert_not_after=None,
                cert_days_remaining=None,
                error_message=f"TLS handshake timed out after {timeout}s",
            )
        except Exception as exc:
            return TlsProbeResult(
                destination_host=destination_host,
                destination_port=destination_port,
                status=TlsHandshakeStatus.PROTOCOL_ERROR,
                is_valid=False,
                handshake_time_ms=None,
                tls_version=None,
                cipher_suite=None,
                cert_subject=None,
                cert_issuer=None,
                cert_not_after=None,
                cert_days_remaining=None,
                error_message=str(exc),
            )
        finally:
            try:
                tls_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            tls_sock.close()

