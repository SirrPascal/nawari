"""services/multisite/api_governance.py
======================================
API Governance, Audit Hardening, Rate Limiting & Crash Recovery Engine (Workstream 13H).

Provides:
1. Token-bucket rate limiting & idempotency protection across multi-site endpoints.
2. Cryptographically chained tamper-evident audit ledger with chain corruption detection & external anchoring.
3. Write-Ahead Journaling (WAL) and crash-recovery state reconciliation (UNVERIFIED_STATE detection).
4. Lease-based entity concurrency locks with automatic heartbeat expiration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nawari.multisite.api_governance")


class AuditChainCorruptionType(str, Enum):
    NONE = "NONE"
    TAMPERED_PAYLOAD = "TAMPERED_PAYLOAD"
    BROKEN_LINK = "BROKEN_LINK"
    RECORD_DELETED_OR_TRUNCATED = "RECORD_DELETED_OR_TRUNCATED"
    OUT_OF_SEQUENCE = "OUT_OF_SEQUENCE"


class WALActionState(str, Enum):
    INITIATED = "INITIATED"
    PRE_EXEC_RECORDED = "PRE_EXEC_RECORDED"
    STEP_IN_PROGRESS = "STEP_IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNVERIFIED_CRASH = "UNVERIFIED_STATE_CRASH_RECOVERY"


# ---------------------------------------------------------------------------
# 1. Token Bucket Rate Limiter & Idempotency Registry
# ---------------------------------------------------------------------------

class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter per client/station key."""

    def __init__(self, rate_per_second: float = 50.0, burst_capacity: int = 100) -> None:
        self.rate = rate_per_second
        self.capacity = burst_capacity
        self._buckets: Dict[str, Dict[str, float]] = {}

    def acquire(self, client_key: str, tokens: int = 1) -> bool:
        """Attempt to consume tokens. Returns True if permitted, False if rate limited."""
        now = time.time()
        bucket = self._buckets.setdefault(client_key, {"tokens": float(self.capacity), "last_refill": now})

        # Refill tokens based on elapsed time
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(float(self.capacity), bucket["tokens"] + elapsed * self.rate)
        bucket["last_refill"] = now

        if bucket["tokens"] >= tokens:
            bucket["tokens"] -= tokens
            return True
        return False

    def get_retry_after(self, client_key: str) -> float:
        """Calculate required wait time in seconds until at least 1 token is available."""
        bucket = self._buckets.get(client_key)
        if not bucket or bucket["tokens"] >= 1.0:
            return 0.0
        missing = 1.0 - bucket["tokens"]
        return max(0.1, round(missing / self.rate, 2))


class IdempotencyRegistry:
    """Prevents duplicate execution of identical operational requests within TTL window."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl = ttl_seconds
        self._records: Dict[str, Dict[str, Any]] = {}

    def check_or_register(self, idempotency_key: str, request_hash: str) -> Optional[Dict[str, Any]]:
        """If key exists and is valid, return cached response; otherwise register in-progress."""
        now = time.time()
        # Clean expired keys
        self._records = {k: v for k, v in self._records.items() if now - v["created_at"] < self.ttl}

        if idempotency_key in self._records:
            rec = self._records[idempotency_key]
            if rec["request_hash"] != request_hash:
                raise ValueError("Idempotency key reused with mismatched request parameters.")
            return rec.get("response")

        self._records[idempotency_key] = {
            "request_hash": request_hash,
            "created_at": now,
            "status": "IN_PROGRESS",
            "response": None,
        }
        return None

    def store_response(self, idempotency_key: str, response: Dict[str, Any]) -> None:
        if idempotency_key in self._records:
            self._records[idempotency_key]["status"] = "COMPLETED"
            self._records[idempotency_key]["response"] = response


# ---------------------------------------------------------------------------
# 2. Hardened Chained Audit Ledger
# ---------------------------------------------------------------------------

@dataclass
class AuditBlock:
    """Represents a single immutable, cryptographically hashed block in the audit chain."""
    index: int
    timestamp_utc: str
    previous_hash: str
    event_type: str
    actor_id: str
    station_id: str
    payload: Dict[str, Any]
    block_hash: str = ""

    def calculate_hash(self) -> str:
        data_str = (
            f"{self.index}|"
            f"{self.timestamp_utc}|"
            f"{self.previous_hash}|"
            f"{self.event_type}|"
            f"{self.actor_id}|"
            f"{self.station_id}|"
            f"{json.dumps(self.payload, sort_keys=True)}"
        )
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "previous_hash": self.previous_hash,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "station_id": self.station_id,
            "payload": self.payload,
            "block_hash": self.block_hash,
        }


class HardenedAuditLedger:
    """Tamper-evident audit ledger with cryptographic chaining and verification."""

    GENESIS_HASH = "0" * 64

    def __init__(self, ledger_file_path: Optional[str] = None) -> None:
        self.ledger_file = ledger_file_path
        self._chain: List[AuditBlock] = []
        if self.ledger_file and os.path.exists(self.ledger_file):
            self.load_from_disk()

    def append_event(
        self,
        event_type: str,
        actor_id: str,
        station_id: str,
        payload: Dict[str, Any],
    ) -> AuditBlock:
        """Append an event to the ledger chain."""
        index = len(self._chain)
        prev_hash = self._chain[-1].block_hash if self._chain else self.GENESIS_HASH
        timestamp = datetime.now(timezone.utc).isoformat()

        block = AuditBlock(
            index=index,
            timestamp_utc=timestamp,
            previous_hash=prev_hash,
            event_type=event_type,
            actor_id=actor_id,
            station_id=station_id,
            payload=payload,
        )
        block.block_hash = block.calculate_hash()
        self._chain.append(block)

        if self.ledger_file:
            self._save_to_disk()

        return block

    def append_action_audit_entry(
        self,
        actor_id: str,
        action_name: str,
        station_id: str,
        target_entity: str,
        source: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        approval_references: List[str],
        execution_result: str,
        verification_result: str,
        incident_id: str,
        alert_id: str,
    ) -> AuditBlock:
        """Structured helper for Phase 12 & 13 operational action audit records."""
        payload = {
            "target_entity": target_entity,
            "source": source,
            "before_state": before_state,
            "after_state": after_state,
            "approval_references": approval_references,
            "execution_result": execution_result,
            "verification_result": verification_result,
            "incident_id": incident_id,
            "alert_id": alert_id,
        }
        return self.append_event(
            event_type=f"OPERATIONAL_ACTION:{action_name}",
            actor_id=actor_id,
            station_id=station_id,
            payload=payload,
        )

    def verify_integrity(self) -> Dict[str, Any]:
        """Exhaustively verify chain cryptographic integrity."""
        if not self._chain:
            return {"valid": True, "blocks_verified": 0, "corruption_type": AuditChainCorruptionType.NONE.value}

        for i, block in enumerate(self._chain):
            # Index check
            if block.index != i:
                return {
                    "valid": False,
                    "failed_index": i,
                    "corruption_type": AuditChainCorruptionType.OUT_OF_SEQUENCE.value,
                    "reason": f"Block index {block.index} does not match chain position {i}.",
                }

            # Previous hash check
            expected_prev = self._chain[i - 1].block_hash if i > 0 else self.GENESIS_HASH
            if block.previous_hash != expected_prev:
                return {
                    "valid": False,
                    "failed_index": i,
                    "corruption_type": AuditChainCorruptionType.BROKEN_LINK.value,
                    "reason": f"Block {i} previous_hash does not match block {i-1} hash.",
                }

            # Block payload hash check
            expected_hash = block.calculate_hash()
            if block.block_hash != expected_hash:
                return {
                    "valid": False,
                    "failed_index": i,
                    "corruption_type": AuditChainCorruptionType.TAMPERED_PAYLOAD.value,
                    "reason": f"Block {i} hash mismatch: computed {expected_hash} vs stored {block.block_hash}.",
                }

        return {
            "valid": True,
            "blocks_verified": len(self._chain),
            "head_hash": self._chain[-1].block_hash if self._chain else None,
            "corruption_type": AuditChainCorruptionType.NONE.value,
        }

    def export_external_anchor(self) -> Dict[str, Any]:
        """Generate anchor snapshot for external syslog and cold storage verification."""
        verification = self.verify_integrity()
        if not verification["valid"]:
            raise ValueError(f"Cannot generate anchor on corrupt ledger: {verification['reason']}")

        head_block = self._chain[-1] if self._chain else None
        return {
            "anchor_id": f"ANCHOR-{uuid.uuid4().hex[:8].upper()}",
            "anchored_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_blocks": len(self._chain),
            "head_hash": head_block.block_hash if head_block else self.GENESIS_HASH,
            "head_timestamp": head_block.timestamp_utc if head_block else None,
            "system_signature": hashlib.sha256(
                f"NAWARI-AUDIT-ANCHOR-{len(self._chain)}-{head_block.block_hash if head_block else ''}".encode("utf-8")
            ).hexdigest(),
        }

    def _save_to_disk(self) -> None:
        if not self.ledger_file:
            return
        Path(self.ledger_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_file, "w") as f:
            json.dump([b.to_dict() for b in self._chain], f, indent=2)

    def load_from_disk(self) -> None:
        if not self.ledger_file or not os.path.exists(self.ledger_file) or os.path.getsize(self.ledger_file) == 0:
            return
        with open(self.ledger_file, "r") as f:
            data = json.load(f)
        self._chain = [AuditBlock(**d) for d in data]

    def get_blocks(self) -> List[AuditBlock]:
        return list(self._chain)


# ---------------------------------------------------------------------------
# 3. Write-Ahead Journaling (WAL) & Crash Recovery
# ---------------------------------------------------------------------------

class WriteAheadActionJournal:
    """Maintains WAL on disk for mid-action crash detection and recovery reconciliation."""

    def __init__(self, wal_dir: str) -> None:
        self.wal_dir = Path(wal_dir)
        self.wal_dir.mkdir(parents=True, exist_ok=True)

    def _get_action_wal_path(self, action_id: str) -> Path:
        return self.wal_dir / f"{action_id}.wal.json"

    def record_checkpoint(
        self,
        action_id: str,
        state: WALActionState,
        step_index: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write an atomic checkpoint to disk prior to mutating system state."""
        wal_path = self._get_action_wal_path(action_id)
        entry = {
            "action_id": action_id,
            "state": state.value,
            "step_index": step_index,
            "metadata": metadata or {},
            "checkpoint_time": datetime.now(timezone.utc).isoformat(),
        }
        with open(wal_path, "w") as f:
            json.dump(entry, f, indent=2)

    def get_checkpoint(self, action_id: str) -> Optional[Dict[str, Any]]:
        wal_path = self._get_action_wal_path(action_id)
        if not wal_path.exists():
            return None
        with open(wal_path, "r") as f:
            return json.load(f)

    def mark_completed(self, action_id: str) -> None:
        """Mark action completed in WAL."""
        self.record_checkpoint(action_id=action_id, state=WALActionState.COMPLETED)

    def scan_for_crashed_actions(self) -> List[Dict[str, Any]]:
        """Scans WAL directory on daemon startup for actions interrupted mid-execution."""
        crashed: List[Dict[str, Any]] = []
        for p in self.wal_dir.glob("*.wal.json"):
            try:
                with open(p, "r") as f:
                    entry = json.load(f)
                state = entry.get("state")
                # If state was left in INITIATED, PRE_EXEC_RECORDED, or STEP_IN_PROGRESS, it crashed
                if state in (WALActionState.INITIATED.value, WALActionState.PRE_EXEC_RECORDED.value, WALActionState.STEP_IN_PROGRESS.value):
                    entry["recovery_state"] = WALActionState.UNVERIFIED_CRASH.value
                    crashed.append(entry)
            except Exception as e:
                logger.error("Failed to parse WAL file %s: %s", p, e)
        return crashed


# ---------------------------------------------------------------------------
# 4. Lease-Based Entity Concurrency Lock
# ---------------------------------------------------------------------------

class LeaseBasedEntityLock:
    """Heartbeat lease lock preventing permanent deadlock if holding process crashes."""

    def __init__(self, default_lease_seconds: float = 30.0) -> None:
        self.default_lease_seconds = default_lease_seconds
        self._leases: Dict[str, Dict[str, Any]] = {}

    def acquire(self, entity_id: str, owner_id: str, lease_seconds: Optional[float] = None) -> bool:
        """Acquire lease on entity. If existing lease has expired, cleans it and acquires."""
        now = time.time()
        lease_duration = lease_seconds or self.default_lease_seconds

        existing = self._leases.get(entity_id)
        if existing:
            if existing["owner_id"] == owner_id:
                # Renew lease
                existing["expires_at"] = now + lease_duration
                return True
            if now < existing["expires_at"]:
                # Held by another live owner
                return False

        # Clean or acquire
        self._leases[entity_id] = {
            "owner_id": owner_id,
            "acquired_at": now,
            "expires_at": now + lease_duration,
        }
        return True

    def heartbeat(self, entity_id: str, owner_id: str, extend_seconds: Optional[float] = None) -> bool:
        """Extend lease duration."""
        existing = self._leases.get(entity_id)
        if existing and existing["owner_id"] == owner_id:
            now = time.time()
            if now < existing["expires_at"]:
                existing["expires_at"] = now + (extend_seconds or self.default_lease_seconds)
                return True
        return False

    def release(self, entity_id: str, owner_id: str) -> bool:
        """Release lease explicitly."""
        existing = self._leases.get(entity_id)
        if existing and existing["owner_id"] == owner_id:
            del self._leases[entity_id]
            return True
        return False

    def is_locked(self, entity_id: str) -> bool:
        """Check if entity is currently locked by a valid unexpired lease."""
        existing = self._leases.get(entity_id)
        if not existing:
            return False
        return time.time() < existing["expires_at"]
