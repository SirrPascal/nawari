"""RFC 3261 Streaming SIP Message Parser for Nawari Voice Intelligence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SIPMessageType(str, Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"


class SIPMethod(str, Enum):
    INVITE = "INVITE"
    ACK = "ACK"
    BYE = "BYE"
    CANCEL = "CANCEL"
    OPTIONS = "OPTIONS"
    REGISTER = "REGISTER"
    PRACK = "PRACK"
    INFO = "INFO"
    UPDATE = "UPDATE"
    SUBSCRIBE = "SUBSCRIBE"
    NOTIFY = "NOTIFY"
    MESSAGE = "MESSAGE"
    UNKNOWN = "UNKNOWN"


@dataclass
class SIPMessage:
    message_type: SIPMessageType
    method: SIPMethod | str
    status_code: Optional[int] = None
    reason_phrase: Optional[str] = None
    uri: Optional[str] = None
    sip_version: str = "SIP/2.0"
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    raw_message: Optional[str] = None

    @property
    def call_id(self) -> Optional[str]:
        return self.headers.get("call-id") or self.headers.get("i")

    @property
    def cseq(self) -> tuple[int, str]:
        val = self.headers.get("cseq", "0 UNKNOWN")
        parts = val.strip().split(maxsplit=1)
        try:
            seq_num = int(parts[0])
        except (ValueError, IndexError):
            seq_num = 0
        method = parts[1].upper() if len(parts) > 1 else "UNKNOWN"
        return seq_num, method

    @property
    def from_header(self) -> str:
        return self.headers.get("from") or self.headers.get("f", "")

    @property
    def to_header(self) -> str:
        return self.headers.get("to") or self.headers.get("t", "")

    @property
    def via_headers(self) -> list[str]:
        vias = []
        for k, v in self.headers.items():
            if k in ("via", "v"):
                vias.extend([x.strip() for x in v.split(",") if x.strip()])
        return vias

    @property
    def reason_header(self) -> Optional[str]:
        return self.headers.get("reason")

    @property
    def warning_header(self) -> Optional[str]:
        return self.headers.get("warning")

    @property
    def is_provisional(self) -> bool:
        return bool(self.status_code and 100 <= self.status_code < 200)

    @property
    def is_success(self) -> bool:
        return bool(self.status_code and 200 <= self.status_code < 300)

    @property
    def is_redirect(self) -> bool:
        return bool(self.status_code and 300 <= self.status_code < 400)

    @property
    def is_client_error(self) -> bool:
        return bool(self.status_code and 400 <= self.status_code < 500)

    @property
    def is_server_error(self) -> bool:
        return bool(self.status_code and 500 <= self.status_code < 600)

    @property
    def is_global_error(self) -> bool:
        return bool(self.status_code and 600 <= self.status_code < 700)


class SIPParser:
    """High-performance RFC 3261 streaming SIP message parser."""

    _FIRST_LINE_PATTERN = re.compile(
        r"^(?:(SIP/2\.0)\s+(\d{3})\s*(.*)|([A-Za-z]+)\s+([^\s]+)\s+(SIP/2\.0))\r?$"
    )

    @classmethod
    def parse(cls, raw_text: str) -> SIPMessage:
        """Parse raw text string into a structured SIPMessage."""
        if not raw_text or not raw_text.strip():
            raise ValueError("Empty SIP message cannot be parsed")

        # Split headers and body at first blank line
        parts = re.split(r"\r?\n\r?\n", raw_text, maxsplit=1)
        header_text = parts[0]
        body_text = parts[1] if len(parts) > 1 else None

        lines = header_text.splitlines()
        if not lines:
            raise ValueError("Invalid SIP message: no start line found")

        start_line = lines[0].strip()
        match = cls._FIRST_LINE_PATTERN.match(start_line)
        if not match:
            raise ValueError(f"Malformed SIP start line: '{start_line}'")

        if match.group(1):  # Response: SIP/2.0 <status_code> <reason>
            msg_type = SIPMessageType.RESPONSE
            version = match.group(1)
            status_code = int(match.group(2))
            reason_phrase = match.group(3).strip()
            method = "RESPONSE"
            uri = None
        else:  # Request: <METHOD> <URI> SIP/2.0
            msg_type = SIPMessageType.REQUEST
            method_str = match.group(4).upper()
            try:
                method = SIPMethod(method_str)
            except ValueError:
                method = method_str
            uri = match.group(5).strip()
            version = match.group(6)
            status_code = None
            reason_phrase = None

        # Parse headers with multi-line unfold support
        headers: dict[str, str] = {}
        curr_key: Optional[str] = None
        curr_val: list[str] = []

        for line in lines[1:]:
            if not line:
                continue
            # Header line continuation (starts with whitespace or tab)
            if line[0] in (" ", "\t") and curr_key:
                curr_val.append(line.strip())
            else:
                if curr_key:
                    headers[curr_key] = " ".join(curr_val)
                colon_idx = line.find(":")
                if colon_idx != -1:
                    curr_key = line[:colon_idx].strip().lower()
                    curr_val = [line[colon_idx + 1 :].strip()]
                else:
                    curr_key = None
                    curr_val = []

        if curr_key:
            headers[curr_key] = " ".join(curr_val)

        return SIPMessage(
            message_type=msg_type,
            method=method,
            status_code=status_code,
            reason_phrase=reason_phrase,
            uri=uri,
            sip_version=version,
            headers=headers,
            body=body_text if body_text and body_text.strip() else None,
            raw_message=raw_text,
        )

