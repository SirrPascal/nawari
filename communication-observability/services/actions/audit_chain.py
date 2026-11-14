"""Cryptographically Chained Immutable Audit Trail for Nawari Actions (Workstream 12G).

Enforces SHA-256 block hash chaining for all operational state changes and compliance logging.
Provides automated tamper detection and cryptographic integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AuditBlock:
    """Immutable block in the operational audit chain."""

    block_index: int
    timestamp: float
    action_id: str
    incident_id: str
    operator_id: str
    event_type: str
    payload_hash: str
    previous_hash: str
    block_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_index": self.block_index,
            "timestamp": self.timestamp,
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "operator_id": self.operator_id,
            "event_type": self.event_type,
            "payload_hash": self.payload_hash,
            "previous_hash": self.previous_hash,
            "block_hash": self.block_hash,
        }


class OperationalAuditLedger:
    """Tamper-evident blockchain-style SHA-256 operational action audit ledger."""

    GENESIS_PREV_HASH: str = "0" * 64

    def __init__(self):
        self.chain: list[AuditBlock] = []
        # Create Genesis Block
        genesis = self._create_block(
            block_index=0,
            timestamp=0.0,
            action_id="GENESIS_ACTION",
            incident_id="GENESIS_INCIDENT",
            operator_id="SYSTEM_ROOT",
            event_type="GENESIS",
            payload={"system": "nawari-audit-ledger-v1"},
            previous_hash=self.GENESIS_PREV_HASH,
        )
        self.chain.append(genesis)

    @staticmethod
    def _compute_payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _compute_block_hash(
        index: int,
        timestamp: float,
        action_id: str,
        incident_id: str,
        operator_id: str,
        event_type: str,
        payload_hash: str,
        prev_hash: str,
    ) -> str:
        raw = f"{index}|{timestamp}|{action_id}|{incident_id}|{operator_id}|{event_type}|{payload_hash}|{prev_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _create_block(
        self,
        block_index: int,
        timestamp: float,
        action_id: str,
        incident_id: str,
        operator_id: str,
        event_type: str,
        payload: dict[str, Any],
        previous_hash: str,
    ) -> AuditBlock:
        p_hash = self._compute_payload_hash(payload)
        b_hash = self._compute_block_hash(
            block_index, timestamp, action_id, incident_id, operator_id, event_type, p_hash, previous_hash
        )
        return AuditBlock(
            block_index=block_index,
            timestamp=timestamp,
            action_id=action_id,
            incident_id=incident_id,
            operator_id=operator_id,
            event_type=event_type,
            payload_hash=p_hash,
            previous_hash=previous_hash,
            block_hash=b_hash,
        )

    def record_event(
        self,
        action_id: str,
        incident_id: str,
        operator_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditBlock:
        """Appends a new cryptographically chained audit record."""
        prev_block = self.chain[-1]
        now = time.time()
        new_block = self._create_block(
            block_index=len(self.chain),
            timestamp=now,
            action_id=action_id,
            incident_id=incident_id,
            operator_id=operator_id,
            event_type=event_type,
            payload=payload,
            previous_hash=prev_block.block_hash,
        )
        self.chain.append(new_block)
        return new_block

    def verify_integrity(self) -> tuple[bool, str]:
        """Validates that the entire cryptographic hash chain is uncorrupted and untampered."""
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]

            # 1. Previous hash linkage check
            if curr.previous_hash != prev.block_hash:
                return False, f"CHAIN_LINKAGE_VIOLATION at block {curr.block_index}: previous_hash does not match parent block_hash"

            # 2. Block hash computation verification
            recomputed = self._compute_block_hash(
                curr.block_index,
                curr.timestamp,
                curr.action_id,
                curr.incident_id,
                curr.operator_id,
                curr.event_type,
                curr.payload_hash,
                curr.previous_hash,
            )
            if curr.block_hash != recomputed:
                return False, f"BLOCK_HASH_TAMPERED at block {curr.block_index}: block_hash does not match recomputed SHA-256"

        return True, "CHAIN_INTEGRITY_VERIFIED"

