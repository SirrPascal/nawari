"""Pure Python implementation of the Zabbix Sender protocol.

Transmits active voice telemetry and synthetic call results to Zabbix Server trappers
over TCP 10051 without external C binaries or third-party client dependencies.
"""

import json
import logging
import os
import re
import socket
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from services.voice.models import SyntheticCallResult

logger = logging.getLogger("nawari.voice.zabbix_sender")
ZABBIX_HEADER = b"ZBXD\x01"


class ZabbixSenderError(Exception):
    """Raised when communication with Zabbix trapper fails."""

    def __init__(self, message: str, spooled: bool = False):
        super().__init__(message)
        self.spooled = spooled


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
    counts_reported: bool = True

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
            counts_reported=bool(m_proc and m_fail and m_tot),
        )


class ZabbixSender:
    """Client for dispatching metrics to Zabbix Server Trapper items with retries and spooling."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 10051,
        timeout: float = 5.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        spool_file: Optional[Path] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.spool_file = spool_file

    def send(self, metrics: list[ZabbixMetric]) -> ZabbixSenderResponse:
        """Transmit a batch of metrics to Zabbix Server with retries and spooling."""
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

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
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
                last_err = e
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(sleep_time)

        # Retries exhausted - check spooling
        if self.spool_file:
            try:
                self.spool_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.spool_file, "a", encoding="utf-8") as f:
                    for item in data_list:
                        f.write(json.dumps(item) + "\n")
                logger.warning(
                    f"Zabbix server unreachable at {self.host}:{self.port}. Spooled {len(data_list)} metrics to {self.spool_file}"
                )
                raise ZabbixSenderError(
                    f"Failed to transmit data to Zabbix after {self.max_retries+1} attempts ({last_err}); spooled to disk",
                    spooled=True,
                )
            except Exception as spool_err:
                if isinstance(spool_err, ZabbixSenderError):
                    raise spool_err
                raise ZabbixSenderError(f"Failed to transmit to Zabbix and spooling failed: {spool_err}")

        raise ZabbixSenderError(
            f"Failed to transmit data to Zabbix server at {self.host}:{self.port} after {self.max_retries+1} attempts: {last_err}"
        )

    def replay_spool(self, spool_file: Optional[Path] = None) -> int:
        """Read and transmit previously spooled metrics to Zabbix."""
        target_spool = spool_file or self.spool_file
        if not target_spool or not target_spool.exists():
            return 0

        metrics: list[ZabbixMetric] = []
        with open(target_spool, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    metrics.append(
                        ZabbixMetric(
                            host=d["host"],
                            key=d["key"],
                            value=d["value"],
                            clock=d.get("clock"),
                        )
                    )
                except Exception:
                    pass

        if not metrics:
            target_spool.unlink(missing_ok=True)
            return 0

        # Send without spooling to avoid recursive spooling loop
        original_spool = self.spool_file
        try:
            self.spool_file = None
            resp = self.send(metrics)
            if resp.response == "success":
                target_spool.unlink(missing_ok=True)
                logger.info(f"Successfully replayed {len(metrics)} spooled metrics to Zabbix")
                return len(metrics)
            return 0
        finally:
            self.spool_file = original_spool

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
            ZabbixMetric(host, "voice.synthetic.environment", "MOCK_SIMULATED", now),
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
