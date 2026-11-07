"""Pure Python implementation of the Zabbix Sender protocol.

Transmits active voice telemetry and synthetic call results to Zabbix Server trappers
over TCP 10051 without external C binaries or third-party client dependencies.
"""

import json
import re
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any, Optional

from services.voice.models import SyntheticCallResult

ZABBIX_HEADER = b"ZBXD\x01"


class ZabbixSenderError(Exception):
    """Raised when communication with Zabbix trapper fails."""


@dataclass
class ZabbixMetric:
    """A single metric measurement to be dispatched to a Zabbix trapper item."""

    host: str
    key: str
    value: Any
    clock: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "host": self.host,
            "key": self.key,
            "value": str(self.value) if not isinstance(self.value, (int, float)) else self.value,
        }
        if self.clock is not None:
            item["clock"] = int(self.clock)
        return item


@dataclass
class ZabbixSenderResponse:
    """Response returned by Zabbix Server upon receiving sender data."""

    response: str
    info: str
    processed: int = 0
    failed: int = 0
    total: int = 0
    seconds_spent: float = 0.0

    @classmethod
    def parse(cls, raw_json: str) -> "ZabbixSenderResponse":
        data = json.loads(raw_json)
        info = data.get("info", "")
        # Info format: "processed: 4; failed: 0; total: 4; seconds spent: 0.000045"
        processed = 0
        failed = 0
        total = 0
        seconds = 0.0

        m_proc = re.search(r"processed:\s*(\d+)", info)
        m_fail = re.search(r"failed:\s*(\d+)", info)
        m_tot = re.search(r"total:\s*(\d+)", info)
        m_sec = re.search(r"seconds spent:\s*([\d\.]+)", info)

        if m_proc:
            processed = int(m_proc.group(1))
        if m_fail:
            failed = int(m_fail.group(1))
        if m_tot:
            total = int(m_tot.group(1))
        if m_sec:
            seconds = float(m_sec.group(1))

        return cls(
            response=data.get("response", "failed"),
            info=info,
            processed=processed,
            failed=failed,
            total=total,
            seconds_spent=seconds,
        )


class ZabbixSender:
    """Client for dispatching metrics to Zabbix Server Trapper items."""

    def __init__(self, host: str = "127.0.0.1", port: int = 10051, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, metrics: list[ZabbixMetric]) -> ZabbixSenderResponse:
        """Transmit a batch of metrics to Zabbix Server."""
        if not metrics:
            return ZabbixSenderResponse(response="success", info="processed: 0; failed: 0; total: 0; seconds spent: 0.0")

        now = int(time.time())
        data_list = []
        for m in metrics:
            d = m.to_dict()
            if "clock" not in d:
                d["clock"] = now
            data_list.append(d)

        payload = json.dumps({"request": "sender data", "data": data_list}).encode("utf-8")
        packet = ZABBIX_HEADER + struct.pack("<Q", len(payload)) + payload

        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(packet)

                # Read header (13 bytes: 5 byte magic + 8 byte length)
                hdr = sock.recv(13)
                if len(hdr) < 13:
                    raise ZabbixSenderError(f"Incomplete Zabbix header: received {len(hdr)} bytes")

                if not hdr.startswith(b"ZBXD"):
                    raise ZabbixSenderError(f"Invalid Zabbix protocol magic: {hdr[:4]}")

                expected_len = struct.unpack("<Q", hdr[5:13])[0]
                resp_bytes = b""
                while len(resp_bytes) < expected_len:
                    chunk = sock.recv(min(4096, expected_len - len(resp_bytes)))
                    if not chunk:
                        break
                    resp_bytes += chunk

                raw_json = resp_bytes.decode("utf-8", errors="replace")
                return ZabbixSenderResponse.parse(raw_json)

        except Exception as e:
            raise ZabbixSenderError(f"Failed to transmit data to Zabbix server at {self.host}:{self.port}: {e}")

    def send_call_result(
        self,
        result: SyntheticCallResult,
        host: str = "nawari-voice-probe-01",
    ) -> ZabbixSenderResponse:
        """Convert a SyntheticCallResult into Zabbix metrics and send to Zabbix server."""
        now = int(result.timestamp_end)
        metrics: list[ZabbixMetric] = [
            ZabbixMetric(host, "voice.synthetic.outcome", result.outcome.value, now),
            ZabbixMetric(host, "voice.synthetic.duration", result.duration_seconds, now),
        ]

        if result.signaling.sip_status_code is not None:
            metrics.append(ZabbixMetric(host, "voice.synthetic.sip_status", result.signaling.sip_status_code, now))

        if result.signaling.setup_time_ms > 0:
            metrics.append(ZabbixMetric(host, "voice.synthetic.setup_time", result.signaling.setup_time_ms, now))

        # Media Telemetry
        metrics.append(ZabbixMetric(host, "voice.synthetic.media_status", result.media.verification_level.value, now))

        if result.media.is_valid:
            if result.media.estimated_mos is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.mos", result.media.estimated_mos, now))
            if result.media.r_factor is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.r_factor", result.media.r_factor, now))
            if result.media.jitter_ms is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.jitter", result.media.jitter_ms, now))
            if result.media.loss_pct is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.packet_loss", result.media.loss_pct, now))
            if result.media.rtt_ms is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.rtt", result.media.rtt_ms, now))
            if result.media.one_way_delay_ms is not None:
                metrics.append(ZabbixMetric(host, "voice.synthetic.one_way_delay", result.media.one_way_delay_ms, now))

        return self.send(metrics)

    def send_voice_event(
        self,
        event: Any,
        host: Optional[str] = None,
    ) -> ZabbixSenderResponse:
        """Transmit a CanonicalVoiceEvent to Zabbix trapper items."""
        metrics = event.to_zabbix_metrics(host=host)
        return self.send(metrics)
