"""Nawari Stage 1 Active SIP OPTIONS Availability & Responsiveness Probe.

Measures SIP endpoint reachability, round-trip latency (RTT), and response
codes for Avaya SBCEs, Session Managers, and carrier perimeter interfaces.
Feeds Homer/Heplify telemetry and gates Stage 2 controlled test calls.
"""

import logging
import socket
import time
import uuid
from typing import Optional

from services.voice.config import VoiceSettings, get_voice_settings
from services.voice.models import SipOptionsResult
from services.voice.safety import CallSafetyManager

logger = logging.getLogger("nawari.voice.options_probe")


class SipOptionsProbe:
    """Active SIP OPTIONS prober for Stage 1 voice availability testing."""

    def __init__(
        self,
        settings: Optional[VoiceSettings] = None,
        safety: Optional[CallSafetyManager] = None,
    ):
        self.settings = settings or get_voice_settings()
        self.safety = safety or CallSafetyManager(self.settings)

    def probe(
        self,
        target_peer: str = "avaya-sbce-primary",
        host: Optional[str] = None,
        port: Optional[int] = None,
        simulate: bool = False,
        mock_status: int = 200,
        mock_rtt_ms: float = 14.2,
    ) -> SipOptionsResult:
        """Execute a low-rate SIP OPTIONS qualification probe against target."""
        # Resolve target host/port
        resolved_host = host
        resolved_port = port or self.settings.avaya_sip_port

        if not resolved_host:
            if target_peer == "avaya-sbce-primary":
                resolved_host = self.settings.avaya_sbce_primary_ip
            elif target_peer == "avaya-sbce-secondary":
                resolved_host = self.settings.avaya_sbce_secondary_ip
            elif target_peer == "avaya-sm-primary":
                resolved_host = self.settings.avaya_sm_primary_ip
            else:
                resolved_host = target_peer

        if simulate:
            logger.info("Executing simulated SIP OPTIONS probe to %s:%s", resolved_host, resolved_port)
            status_reason = "OK" if mock_status == 200 else ("Forbidden" if mock_status == 403 else "Response")
            is_reachable = mock_status in {200, 403, 404, 484}
            res = SipOptionsResult(
                target_host=resolved_host,
                target_port=resolved_port,
                status_code=mock_status,
                status_reason=status_reason,
                rtt_ms=mock_rtt_ms,
                is_reachable=is_reachable,
                provenance="SYNTHETIC_AVTEST",
                timestamp=time.time(),
            )
            self.safety.record_options_status(
                target_peer=target_peer,
                is_reachable=res.is_reachable,
                rtt_ms=res.rtt_ms,
                status_code=res.status_code,
                status_reason=res.status_reason,
            )
            return res

        # Live network probe
        return self._send_udp_sip_options(
            target_peer=target_peer,
            host=resolved_host,
            port=resolved_port,
            timeout=self.settings.options_ping_timeout_seconds,
        )

    def _send_udp_sip_options(
        self,
        target_peer: str,
        host: str,
        port: int,
        timeout: float,
    ) -> SipOptionsResult:
        """Send RFC 3261 compliant SIP OPTIONS message over UDP and measure RTT."""
        call_id = f"{uuid.uuid4()}@nawari-avtest"
        branch = f"z9hG4bK.{uuid.uuid4().hex[:12]}"
        tag = uuid.uuid4().hex[:8]

        sip_packet = (
            f"OPTIONS sip:{host}:{port} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch};rport\r\n"
            f"Max-Forwards: 70\r\n"
            f"From: <sip:nawari-probe@127.0.0.1>;tag={tag}\r\n"
            f"To: <sip:{host}:{port}>\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: 1 OPTIONS\r\n"
            f"Contact: <sip:nawari-probe@127.0.0.1:5060>\r\n"
            f"Accept: application/sdp\r\n"
            f"X-Nawari-Origin: AVTEST_ASTERISK\r\n"
            f"X-Nawari-Stage: STAGE_1_SIP_OPTIONS\r\n"
            f"User-Agent: Nawari-AVTEST-ActiveProbe/1.0\r\n"
            f"Content-Length: 0\r\n\r\n"
        ).encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        start_time = time.time()
        try:
            sock.sendto(sip_packet, (host, port))
            data, _ = sock.recvfrom(4096)
            rtt_ms = round((time.time() - start_time) * 1000.0, 2)
            response_text = data.decode("utf-8", errors="replace")

            # Parse status line (e.g. 'SIP/2.0 200 OK')
            status_code = 0
            status_reason = "Unknown"
            first_line = response_text.split("\r\n")[0]
            parts = first_line.split(" ", 2)
            if len(parts) >= 2 and parts[1].isdigit():
                status_code = int(parts[1])
                status_reason = parts[2] if len(parts) > 2 else ""

            # Standard SIP reachability: 200 OK, 403 Forbidden, 404 Not Found, 484 Address Incomplete
            # all prove signaling stack responsiveness!
            is_reachable = status_code in {200, 403, 404, 484, 405}

            res = SipOptionsResult(
                target_host=host,
                target_port=port,
                status_code=status_code,
                status_reason=status_reason,
                rtt_ms=rtt_ms,
                is_reachable=is_reachable,
                provenance="SYNTHETIC_AVTEST",
                timestamp=time.time(),
            )
            self.safety.record_options_status(
                target_peer=target_peer,
                is_reachable=res.is_reachable,
                rtt_ms=res.rtt_ms,
                status_code=res.status_code,
                status_reason=res.status_reason,
            )
            return res

        except socket.timeout:
            rtt_ms = round((time.time() - start_time) * 1000.0, 2)
            res = SipOptionsResult(
                target_host=host,
                target_port=port,
                status_code=408,
                status_reason="Request Timeout",
                rtt_ms=rtt_ms,
                is_reachable=False,
                provenance="SYNTHETIC_AVTEST",
                error_message=f"Socket timeout after {timeout}s",
                timestamp=time.time(),
            )
            self.safety.record_options_status(
                target_peer=target_peer,
                is_reachable=False,
                rtt_ms=rtt_ms,
                status_code=408,
                status_reason="Request Timeout",
            )
            return res

        except Exception as e:
            res = SipOptionsResult(
                target_host=host,
                target_port=port,
                status_code=500,
                status_reason="Network Error",
                rtt_ms=0.0,
                is_reachable=False,
                provenance="SYNTHETIC_AVTEST",
                error_message=str(e),
                timestamp=time.time(),
            )
            self.safety.record_options_status(
                target_peer=target_peer,
                is_reachable=False,
                rtt_ms=0.0,
                status_code=500,
                status_reason="Network Error",
            )
            return res

        finally:
            sock.close()
