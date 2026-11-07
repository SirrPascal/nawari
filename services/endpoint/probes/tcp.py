"""TCP 3-way handshake latency and reachability probe with failure classification."""

from __future__ import annotations

import asyncio
import errno
import socket
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TcpConnectStatus(str, Enum):
    SUCCESS = "SUCCESS"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    TIMEOUT = "TIMEOUT"
    HOST_UNREACHABLE = "HOST_UNREACHABLE"
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"
    CONNECTION_RESET = "CONNECTION_RESET"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TcpProbeResult:
    destination_ip: str
    destination_port: int
    status: TcpConnectStatus
    is_reachable: bool
    connect_time_ms: Optional[float]
    error_message: Optional[str] = None


class TcpProbe:
    """Measures TCP 3-way handshake latency (SYN -> SYN-ACK RTT) with microsecond precision."""

    def __init__(self, default_timeout_seconds: float = 3.0) -> None:
        self.default_timeout_seconds = default_timeout_seconds

    async def probe(
        self,
        destination_ip: str,
        destination_port: int,
        timeout_seconds: Optional[float] = None,
    ) -> TcpProbeResult:
        """Asynchronously execute TCP handshake probe."""
        timeout = timeout_seconds or self.default_timeout_seconds
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sync_probe,
            destination_ip,
            destination_port,
            timeout,
        )

    def _execute_sync_probe(
        self,
        destination_ip: str,
        destination_port: int,
        timeout: float,
    ) -> TcpProbeResult:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        t_start = time.perf_counter()
        try:
            sock.connect((destination_ip, destination_port))
            connect_time_ms = (time.perf_counter() - t_start) * 1000.0
            return TcpProbeResult(
                destination_ip=destination_ip,
                destination_port=destination_port,
                status=TcpConnectStatus.SUCCESS,
                is_reachable=True,
                connect_time_ms=round(connect_time_ms, 2),
                error_message=None,
            )
        except socket.timeout:
            return TcpProbeResult(
                destination_ip=destination_ip,
                destination_port=destination_port,
                status=TcpConnectStatus.TIMEOUT,
                is_reachable=False,
                connect_time_ms=None,
                error_message=f"TCP connection timed out after {timeout}s",
            )
        except OSError as exc:
            err = exc.errno
            if err in (errno.ECONNREFUSED,):
                status = TcpConnectStatus.CONNECTION_REFUSED
                err_msg = "Connection refused by target host (TCP RST received)"
            elif err in (errno.ECONNRESET,):
                status = TcpConnectStatus.CONNECTION_RESET
                err_msg = "Connection reset by peer (TCP RST)"
            elif err in (errno.EHOSTUNREACH,):
                status = TcpConnectStatus.HOST_UNREACHABLE
                err_msg = "No route to host / host unreachable"
            elif err in (errno.ENETUNREACH,):
                status = TcpConnectStatus.NETWORK_UNREACHABLE
                err_msg = "Network is unreachable"
            elif err in (errno.ETIMEDOUT,):
                status = TcpConnectStatus.TIMEOUT
                err_msg = f"Connection timed out: {exc}"
            else:
                status = TcpConnectStatus.ERROR
                err_msg = str(exc)

            return TcpProbeResult(
                destination_ip=destination_ip,
                destination_port=destination_port,
                status=status,
                is_reachable=False,
                connect_time_ms=None,
                error_message=err_msg,
            )
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            sock.close()
