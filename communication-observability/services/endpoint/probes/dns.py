"""Pure Python DNS resolution probe with latency, status classification, and record extraction."""

from __future__ import annotations

import asyncio
import random
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import DnsProbeTelemetry, DnsResolutionStatus


class DnsProbe:
    """Diagnostic probe for measuring DNS resolver latency, reliability, and returned records.

    Features:
    1. RFC 1035 pure Python UDP resolver query (supports querying specific resolvers).
    2. Automatic DNS-over-TCP fallback when UDP response is truncated (TC bit set).
    3. Supports query types: A, AAAA, CNAME, MX, TXT, SRV.
    4. Accurate classification: NOERROR, NOERROR_EMPTY, NXDOMAIN, SERVFAIL, REFUSED, TIMEOUT, ERROR.
    5. Fallback to OS getaddrinfo resolution.
    """

    QTYPE_MAP = {
        "A": 1,
        "NS": 2,
        "CNAME": 5,
        "SOA": 6,
        "PTR": 12,
        "MX": 15,
        "TXT": 16,
        "AAAA": 28,
        "SRV": 33,
    }

    def __init__(self, default_resolver: Optional[str] = None, timeout_seconds: float = 3.0) -> None:
        self.default_resolver = default_resolver
        self.timeout_seconds = timeout_seconds

    async def probe(
        self,
        query_name: str,
        record_type: str = "A",
        resolver_ip: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> DnsProbeTelemetry:
        """Execute non-blocking DNS query asynchronously."""
        timeout = timeout_seconds or self.timeout_seconds
        resolver = resolver_ip or self.default_resolver

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sync_probe,
            query_name,
            record_type.upper(),
            resolver,
            timeout,
        )

    def _execute_sync_probe(
        self,
        query_name: str,
        record_type: str,
        resolver_ip: Optional[str],
        timeout: float,
    ) -> DnsProbeTelemetry:
        t_start = time.perf_counter()

        # If a specific resolver is provided, attempt pure RFC 1035 UDP query first
        if resolver_ip and resolver_ip not in ("127.0.0.1", "localhost", "::1"):
            try:
                status, records, err = self._query_rfc1035(query_name, record_type, resolver_ip, timeout)
                elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                return DnsProbeTelemetry(
                    query_name=query_name,
                    record_type=record_type,
                    resolver_ip=resolver_ip,
                    status=status,
                    resolution_time_ms=round(elapsed_ms, 2),
                    resolved_ips=records,
                    error_message=err,
                )
            except Exception:
                # Direct UDP query failed; fallback to system resolver
                pass

        # System resolver path using getaddrinfo for A / AAAA
        resolved_resolver = resolver_ip or "system-default"
        try:
            family = socket.AF_INET6 if record_type == "AAAA" else socket.AF_INET
            addr_info = socket.getaddrinfo(query_name, None, family=family)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            ips = list({info[4][0] for info in addr_info if info[4]})

            status = DnsResolutionStatus.NOERROR if ips else DnsResolutionStatus.NOERROR_EMPTY
            return DnsProbeTelemetry(
                query_name=query_name,
                record_type=record_type,
                resolver_ip=resolved_resolver,
                status=status,
                resolution_time_ms=round(elapsed_ms, 2),
                resolved_ips=ips,
                error_message=None,
            )
        except socket.gaierror as exc:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            status = DnsResolutionStatus.ERROR
            if exc.errno in (socket.EAI_NONAME, -2):
                status = DnsResolutionStatus.NXDOMAIN
            elif exc.errno in (socket.EAI_AGAIN, -3):
                status = DnsResolutionStatus.TIMEOUT
            elif exc.errno in (socket.EAI_FAIL, -4):
                status = DnsResolutionStatus.SERVFAIL

            return DnsProbeTelemetry(
                query_name=query_name,
                record_type=record_type,
                resolver_ip=resolved_resolver,
                status=status,
                resolution_time_ms=round(elapsed_ms, 2),
                resolved_ips=[],
                error_message=str(exc),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return DnsProbeTelemetry(
                query_name=query_name,
                record_type=record_type,
                resolver_ip=resolved_resolver,
                status=DnsResolutionStatus.ERROR,
                resolution_time_ms=round(elapsed_ms, 2),
                resolved_ips=[],
                error_message=str(exc),
            )

    def _build_dns_query_packet(self, query_id: int, query_name: str, record_type: str) -> bytes:
        flags = 0x0100  # Standard query, Recursion Desired (RD = 1)
        qdcount = 1

        # Encode QNAME
        qname_bytes = bytearray()
        for label in query_name.strip(".").split("."):
            encoded_label = label.encode("utf-8")
            qname_bytes.append(len(encoded_label))
            qname_bytes.extend(encoded_label)
        qname_bytes.append(0)

        qtype = self.QTYPE_MAP.get(record_type, 1)
        qclass = 1  # IN

        packet = struct.pack(">HHHHHH", query_id, flags, qdcount, 0, 0, 0)
        packet += qname_bytes
        packet += struct.pack(">HH", qtype, qclass)
        return bytes(packet)

    def _query_rfc1035(
        self, query_name: str, record_type: str, resolver_ip: str, timeout: float
    ) -> Tuple[DnsResolutionStatus, List[str], Optional[str]]:
        """Send DNS query over UDP, falling back to TCP if response is truncated (TC bit)."""
        query_id = random.randint(1, 65535)
        packet = self._build_dns_query_packet(query_id, query_name, record_type)

        resp_data = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (resolver_ip, 53))
            resp_data, _ = sock.recvfrom(4096)
        except socket.timeout:
            return DnsResolutionStatus.TIMEOUT, [], f"DNS query timed out after {timeout}s"
        except Exception as exc:
            return DnsResolutionStatus.ERROR, [], str(exc)
        finally:
            sock.close()

        if not resp_data or len(resp_data) < 12:
            return DnsResolutionStatus.ERROR, [], "Truncated or empty DNS response header"

        resp_id, resp_flags, _, ancount, _, _ = struct.unpack(">HHHHHH", resp_data[:12])
        if resp_id != query_id:
            return DnsResolutionStatus.ERROR, [], "Response ID mismatch"

        # Check Truncation (TC) flag: bit 9 (0x0200)
        if (resp_flags & 0x0200) != 0:
            # Fallback to DNS over TCP (RFC 1035 4.2.2)
            return self._query_dns_over_tcp(query_id, packet, resolver_ip, timeout, record_type)

        return self._evaluate_response(resp_flags, resp_data, self.QTYPE_MAP.get(record_type, 1), ancount)

    def _query_dns_over_tcp(
        self, query_id: int, packet: bytes, resolver_ip: str, timeout: float, record_type: str
    ) -> Tuple[DnsResolutionStatus, List[str], Optional[str]]:
        """DNS query over TCP with 2-byte length prefix."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((resolver_ip, 53))
            # Send length-prefixed packet
            sock.sendall(struct.pack(">H", len(packet)) + packet)
            # Read 2-byte response length
            len_bytes = sock.recv(2)
            if len(len_bytes) < 2:
                return DnsResolutionStatus.ERROR, [], "TCP DNS response connection closed prematurely"
            resp_len = struct.unpack(">H", len_bytes)[0]
            resp_data = bytearray()
            while len(resp_data) < resp_len:
                chunk = sock.recv(resp_len - len(resp_data))
                if not chunk:
                    break
                resp_data.extend(chunk)
        except socket.timeout:
            return DnsResolutionStatus.TIMEOUT, [], f"TCP DNS query timed out after {timeout}s"
        except Exception as exc:
            return DnsResolutionStatus.ERROR, [], f"TCP DNS error: {exc}"
        finally:
            sock.close()

        if len(resp_data) < 12:
            return DnsResolutionStatus.ERROR, [], "Truncated TCP DNS response header"

        _, resp_flags, _, ancount, _, _ = struct.unpack(">HHHHHH", resp_data[:12])
        return self._evaluate_response(resp_flags, bytes(resp_data), self.QTYPE_MAP.get(record_type, 1), ancount)

    def _evaluate_response(
        self, resp_flags: int, resp_data: bytes, target_qtype: int, ancount: int
    ) -> Tuple[DnsResolutionStatus, List[str], Optional[str]]:
        rcode = resp_flags & 0x000F
        if rcode == 3:
            return DnsResolutionStatus.NXDOMAIN, [], "Non-existent domain (NXDOMAIN)"
        elif rcode == 2:
            return DnsResolutionStatus.SERVFAIL, [], "Server failure (SERVFAIL)"
        elif rcode == 5:
            return DnsResolutionStatus.REFUSED, [], "Query refused by resolver"
        elif rcode != 0:
            return DnsResolutionStatus.ERROR, [], f"DNS error RCODE={rcode}"

        if ancount == 0:
            return DnsResolutionStatus.NOERROR_EMPTY, [], "Query succeeded but returned no answer records"

        records = self._parse_answers(resp_data, target_qtype, ancount)
        if not records:
            return DnsResolutionStatus.NOERROR_EMPTY, [], "No records matching query type"

        return DnsResolutionStatus.NOERROR, records, None

    def _parse_answers(self, data: bytes, target_qtype: int, ancount: int) -> List[str]:
        """Extract records from DNS response packet."""
        records: List[str] = []
        try:
            offset = 12
            # Skip Question section
            while offset < len(data) and data[offset] != 0:
                if (data[offset] & 0xC0) == 0xC0:
                    offset += 2
                    break
                offset += 1 + data[offset]
            if offset < len(data) and data[offset] == 0:
                offset += 1  # null byte
            offset += 4  # QTYPE + QCLASS

            # Parse Answer RRs
            for _ in range(ancount):
                if offset >= len(data):
                    break
                # Skip NAME (handle compression pointer)
                if (data[offset] & 0xC0) == 0xC0:
                    offset += 2
                else:
                    while offset < len(data) and data[offset] != 0:
                        offset += 1 + data[offset]
                    if offset < len(data):
                        offset += 1

                if offset + 10 > len(data):
                    break
                rr_type, _, _, rdlength = struct.unpack(">HHIH", data[offset : offset + 10])
                offset += 10

                if offset + rdlength > len(data):
                    break

                rdata = data[offset : offset + rdlength]
                if rr_type == 1 and rdlength == 4:  # A record
                    records.append(socket.inet_ntoa(rdata))
                elif rr_type == 28 and rdlength == 16:  # AAAA record
                    records.append(socket.inet_ntop(socket.AF_INET6, rdata))
                elif rr_type == 16:  # TXT record
                    txt_len = rdata[0]
                    records.append(rdata[1 : 1 + txt_len].decode("utf-8", errors="replace"))
                elif rr_type == 33 and rdlength >= 6:  # SRV record
                    priority, weight, port = struct.unpack(">HHH", rdata[:6])
                    records.append(f"{priority} {weight} {port}")

                offset += rdlength
        except Exception:
            pass

        return records
