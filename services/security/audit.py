"""
Nawari Phase 8 — Tamper-Resistant Audit Logging (Workstream 8C)
Provides cryptographically chained (SHA-256) immutable audit records for
security-sensitive operations, enrollment, role assignment, and incident actions.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple


GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


@dataclass
class AuditRecord:
    index: int
    timestamp: float
    actor: str
    role: str
    action: str
    target_type: str
    target_id: str
    client_ip: str
    status: str
    details: dict
    prev_hash: str
    signature: str = ""

    def calculate_hash(self) -> str:
        payload = f"{self.index}|{self.timestamp:.6f}|{self.actor}|{self.role}|{self.action}|{self.target_type}|{self.target_id}|{self.client_ip}|{self.status}|{json.dumps(self.details, sort_keys=True)}|{self.prev_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLogger:
    def __init__(self, log_path: Optional[str] = None):
        self._log_path = log_path
        self._records: List[AuditRecord] = []
        self._latest_hash = GENESIS_HASH
        self._index = 0

        if self._log_path and os.path.exists(self._log_path):
            self._load_and_verify_chain()

    def _load_and_verify_chain(self) -> None:
        if not self._log_path or not os.path.exists(self._log_path):
            return

        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                rec = AuditRecord(**data)
                self._records.append(rec)
                self._latest_hash = rec.signature
                self._index = rec.index + 1

    def log_event(
        self,
        actor: str,
        role: str,
        action: str,
        target_type: str,
        target_id: str,
        client_ip: str,
        status: str,
        details: Optional[dict] = None,
    ) -> AuditRecord:
        now = time.time()
        details_dict = details or {}

        rec = AuditRecord(
            index=self._index,
            timestamp=now,
            actor=actor,
            role=role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            client_ip=client_ip,
            status=status,
            details=details_dict,
            prev_hash=self._latest_hash,
        )
        rec.signature = rec.calculate_hash()

        self._records.append(rec)
        self._latest_hash = rec.signature
        self._index += 1

        if self._log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self._log_path)), exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec)) + "\n")

        return rec

    def verify_integrity(self) -> Tuple[bool, str]:
        expected_prev_hash = GENESIS_HASH
        for i, rec in enumerate(self._records):
            if rec.index != i:
                return False, f"Broken sequence index at position {i}: expected {i}, got {rec.index}"
            if rec.prev_hash != expected_prev_hash:
                return False, f"Hash chain broken at index {i}: prev_hash mismatch"
            calculated = rec.calculate_hash()
            if rec.signature != calculated:
                return False, f"Signature mismatch at index {i}: record content modified!"
            expected_prev_hash = rec.signature
        return True, f"Integrity verified: all {len(self._records)} records valid and untampered."

    @staticmethod
    def verify_file(log_path: str) -> Tuple[bool, str]:
        if not os.path.exists(log_path):
            return False, f"Log file does not exist: {log_path}"
        logger = AuditLogger(log_path)
        return logger.verify_integrity()
