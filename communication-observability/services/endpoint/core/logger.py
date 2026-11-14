"""Structured, privacy-preserving logging for the endpoint agent."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any, Dict, Optional


class SanitizingFormatter(logging.Formatter):
    """Custom formatter that automatically scrubs sensitive credentials and masks UUIDs."""

    TOKEN_PATTERNS = [
        re.compile(r"(api[_-]?token|bearer|password|secret|auth)[\"']?\s*[:=]\s*[\"']?([^\"'\s]+)", re.IGNORECASE),
        re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    ]
    UUID_PATTERN = re.compile(r"\b([0-9a-fA-F]{4})[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}([0-9a-fA-F]{4})\b")

    def __init__(self, json_output: bool = False) -> None:
        super().__init__()
        self.json_output = json_output

    def sanitize(self, text: str) -> str:
        # Scrub tokens
        for pattern in self.TOKEN_PATTERNS:
            text = pattern.sub(r"\1=***REDACTED***", text)
        # Mask UUIDs (keep first 4 and last 4 chars)
        text = self.UUID_PATTERN.sub(r"\1****-****-****-****-****\2", text)
        return text

    def format(self, record: logging.LogRecord) -> str:
        orig_msg = record.getMessage()
        clean_msg = self.sanitize(orig_msg)

        if self.json_output:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": clean_msg,
            }
            if hasattr(record, "extra") and isinstance(record.extra, dict):
                log_entry.update(record.extra)
            return json.dumps(log_entry)
        else:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            return f"[{ts}] [{record.levelname:<5}] [{record.name}] {clean_msg}"


def setup_agent_logger(
    name: str = "nawari.endpoint",
    level: str = "INFO",
    json_output: bool = False,
) -> logging.Logger:
    """Configure and return the primary agent logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Avoid duplicate handlers if reconfigured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(SanitizingFormatter(json_output=json_output))
        logger.addHandler(handler)

    return logger
