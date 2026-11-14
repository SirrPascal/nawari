"""Unit test suite for Stage 7B: Endpoint Connectivity, DNS, and Service Probing."""

import asyncio
import socket
import ssl
from unittest.mock import MagicMock, patch

import pytest

from services.endpoint.models import DnsResolutionStatus
from services.endpoint.probes.dns import DnsProbe
from services.endpoint.probes.http import HttpProbe, HttpStatusOutcome
from services.endpoint.probes.tcp import TcpConnectStatus, TcpProbe
from services.endpoint.probes.tls import TlsHandshakeStatus, TlsProbe


# =====================================================================
# 1. DNS Probe Tests
# =====================================================================

def test_dns_probe_localhost_success():
    """Verify standard DNS resolution of localhost returns NOERROR with 127.0.0.1."""
    async def _test():
        probe = DnsProbe(timeout_seconds=2.0)
        res = await probe.probe("localhost", record_type="A")
        assert res.status in (DnsResolutionStatus.NOERROR, DnsResolutionStatus.SUCCESS)
        assert "127.0.0.1" in res.resolved_ips
        assert res.resolution_time_ms > 0.0

    asyncio.run(_test())


def test_dns_probe_nxdomain():
    """Verify non-existent domain returns NXDOMAIN classification."""
    async def _test():
        probe = DnsProbe(timeout_seconds=2.0)
        # Use an officially reserved, non-existent RFC 2606 domain
        res = await probe.probe("invalid-nonexistent-domain-test-xyz123.invalid", record_type="A")
        assert res.status == DnsResolutionStatus.NXDOMAIN
        assert len(res.resolved_ips) == 0

    asyncio.run(_test())


def test_dns_packet_builder_rfc1035():
    """Verify RFC 1035 query packet structure, QNAME encoding, and flags."""
    probe = DnsProbe()
    pkt = probe._build_dns_query_packet(query_id=12345, query_name="sbce.kq.internal", record_type="A")

    # Header check: 12 bytes
    assert len(pkt) > 12
    # ID: 12345 (0x3039)
    assert pkt[:2] == b"\x30\x39"
    # Flags: 0x0100 (RD=1)
    assert pkt[2:4] == b"\x01\x00"
    # QDCOUNT: 1
    assert pkt[4:6] == b"\x00\x01"

    # QNAME check: \x04sbce\x02kq\x08internal\x00
    expected_qname = b"\x04sbce\x02kq\x08internal\x00"
    assert expected_qname in pkt


def test_dns_tcp_fallback_on_truncation():
    """Verify that when UDP response has TC bit set, DnsProbe falls back to TCP."""
    probe = DnsProbe()
    # Mock UDP returning TC bit set (flags = 0x8300 -> QR=1, TC=1)
    mock_udp_resp = (
        b"\x12\x34"  # ID
        b"\x83\x00"  # QR=1, TC=1
        b"\x00\x01"  # QDCOUNT=1
        b"\x00\x00"  # ANCOUNT=0
        b"\x00\x00\x00\x00"
    )

    with patch("random.randint", return_value=0x1234), patch("socket.socket") as mock_sock_cls:
        mock_udp_sock = MagicMock()
        mock_udp_sock.recvfrom.return_value = (mock_udp_resp, ("10.0.0.1", 53))

        mock_tcp_sock = MagicMock()
        # TCP response: 2-byte len + response packet (NOERROR, ANCOUNT=1)
        tcp_payload = (
            b"\x12\x34"  # ID
            b"\x81\x80"  # QR=1, RD=1, RA=1, NOERROR
            b"\x00\x01"  # QDCOUNT=1
            b"\x00\x01"  # ANCOUNT=1
            b"\x00\x00\x00\x00"
            b"\x04test\x00"  # Name
            b"\x00\x01\x00\x01"  # Type A, Class IN
            # Answer
            b"\xc0\x0c"  # Pointer to name
            b"\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04"  # Type A, Class IN, TTL 60, RDLENGTH 4
            b"\x0a\x00\x00\x01"  # 10.0.0.1
        )
        mock_tcp_sock.recv.side_effect = [
            len(tcp_payload).to_bytes(2, "big"),
            tcp_payload,
        ]

        def sock_factory(family, sock_type):
            if sock_type == socket.SOCK_DGRAM:
                return mock_udp_sock
            return mock_tcp_sock

        mock_sock_cls.side_effect = sock_factory

        status, records, err = probe._query_rfc1035("test", "A", "10.0.0.1", timeout=1.0)
        assert status == DnsResolutionStatus.NOERROR
        assert "10.0.0.1" in records


# =====================================================================
# 2. TCP Handshake Probe Tests
# =====================================================================

def test_tcp_probe_connect_refused():
    """Verify connecting to an unused local port returns CONNECTION_REFUSED."""
    async def _test():
        probe = TcpProbe(default_timeout_seconds=1.0)
        # Port 59999 is typically unused on localhost
        res = await probe.probe("127.0.0.1", 59999)
        assert res.status == TcpConnectStatus.CONNECTION_REFUSED
        assert res.is_reachable is False
        assert res.connect_time_ms is None
        assert "refused" in (res.error_message or "").lower()

    asyncio.run(_test())


def test_tcp_probe_timeout():
    """Verify connecting to a blackholed/non-routable IP triggers TIMEOUT."""
    async def _test():
        probe = TcpProbe(default_timeout_seconds=0.1)
        # 192.0.2.1 is TEST-NET-1 (RFC 5737), non-routable blackhole
        res = await probe.probe("192.0.2.1", 80, timeout_seconds=0.1)
        assert res.status == TcpConnectStatus.TIMEOUT
        assert res.is_reachable is False

    asyncio.run(_test())


def test_tcp_probe_port_5061_caveat():
    """Verify port 5061 TCP probe records transport connectivity, not SIP health."""
    async def _test():
        probe = TcpProbe(default_timeout_seconds=1.0)
        # Connecting to live Asterisk SIP TLS port 5061
        res = await probe.probe("127.0.0.1", 5061)
        assert res.destination_port == 5061
        # Proves transport reachability, status is SUCCESS
        assert res.status == TcpConnectStatus.SUCCESS
        assert res.connect_time_ms is not None
        assert res.connect_time_ms > 0.0

    asyncio.run(_test())


# =====================================================================
# 3. TLS Handshake Probe Tests
# =====================================================================

def test_tls_probe_connection_failed():
    """Verify TLS probe reports CONNECTION_FAILED when TCP port is closed."""
    async def _test():
        probe = TlsProbe(default_timeout_seconds=1.0)
        res = await probe.probe("127.0.0.1", 59999)
        assert res.status == TlsHandshakeStatus.CONNECTION_FAILED
        assert res.is_valid is False
        assert res.handshake_time_ms is None

    asyncio.run(_test())


def test_tls_probe_verification_default():
    """Invariant: verify_certificates is True by default."""
    probe = TlsProbe()
    assert probe.verify_certificates is True


def test_tls_probe_cert_expired_and_hostname_mismatch_mapping():
    """Verify SSL verification errors map to explicit status classifications."""
    probe = TlsProbe()

    # Expired cert mapping
    with patch("socket.socket") as mock_sock, patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_tls = MagicMock()
        mock_tls.do_handshake.side_effect = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired")
        mock_wrap.return_value = mock_tls

        res = probe._execute_sync_probe("test.kq.internal", 443, "test.kq.internal", timeout=1.0, verify=True)
        assert res.status == TlsHandshakeStatus.CERTIFICATE_EXPIRED
        assert res.is_valid is False

    # Hostname mismatch mapping
    with patch("socket.socket") as mock_sock, patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_tls = MagicMock()
        mock_tls.do_handshake.side_effect = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] Certificate hostname mismatch")
        mock_wrap.return_value = mock_tls

        res = probe._execute_sync_probe("test.kq.internal", 443, "test.kq.internal", timeout=1.0, verify=True)
        assert res.status == TlsHandshakeStatus.HOSTNAME_MISMATCH
        assert res.is_valid is False


# =====================================================================
# 4. HTTP / HTTPS Probe Tests
# =====================================================================

def test_http_probe_zabbix_web():
    """Verify HTTP probe against live container nawari-zabbix-web (Port 8088)."""
    async def _test():
        probe = HttpProbe(default_timeout_seconds=3.0)
        res = await probe.probe("http://127.0.0.1:8088/")
        assert res.status_outcome == HttpStatusOutcome.SUCCESS
        assert res.is_success is True
        assert res.status_code == 200
        assert res.tcp_time_ms is not None
        assert res.ttfb_ms is not None
        assert res.total_time_ms is not None
        assert res.response_size_bytes is not None
        assert res.response_size_bytes > 0

    asyncio.run(_test())


def test_http_probe_404_error_classification():
    """Verify HTTP 404 response maps to CLIENT_ERROR_4XX."""
    async def _test():
        probe = HttpProbe(default_timeout_seconds=3.0)
        res = await probe.probe("http://127.0.0.1:8088/nonexistent-endpoint-404-test")
        assert res.status_outcome == HttpStatusOutcome.CLIENT_ERROR_4XX
        assert res.is_success is False
        assert res.status_code == 404

    asyncio.run(_test())


def test_http_probe_invalid_scheme():
    """Verify invalid URL schemes return ERROR."""
    async def _test():
        probe = HttpProbe()
        res = await probe.probe("ftp://127.0.0.1/test")
        assert res.status_outcome == HttpStatusOutcome.ERROR
        assert res.is_success is False
        assert "Unsupported URL scheme" in (res.error_message or "")

    asyncio.run(_test())
