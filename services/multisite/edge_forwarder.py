"""services/multisite/edge_forwarder.py
======================================
Trans-WAN Communications & Edge Telemetry Store-and-Forward Buffering (Workstream 13D).

Provides outstation edge telemetry capture, persistent SQLite disk-backed spooling,
partition detection, rate-limited replay upon circuit restoration, priority-based
disk exhaustion protection, corrupted record quarantine, backpressure mitigation,
and clock drift compensation with explicit 'REPLAYED' telemetry labeling.
"""

from __future__ import annotations

import json
import logging
import os
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("nawari.multisite.edge_forwarder")


class SpoolItemStatus(str, Enum):
    BUFFERED = "BUFFERED"
    IN_FLIGHT = "IN_FLIGHT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DROPPED_PRUNED = "DROPPED_PRUNED"
    CORRUPTED = "CORRUPTED"


class SpoolItemPriority(int, Enum):
    CRITICAL = 0    # P1/P2 Alerts, Voice Trunk Failovers, EFB Sync
    STANDARD = 1    # Interface telemetry, Periodic SNMP counters
    DIAGNOSTIC = 2  # Debug traces, high-frequency ping logs


@dataclass
class SpoolItem:
    """Represents a discrete telemetry payload stored in the outstation spool."""
    spool_id: str
    station_id: str
    payload_type: str
    payload: Dict[str, Any]
    edge_timestamp_ms: int
    spooled_at_utc: str
    status: SpoolItemStatus
    priority: int = SpoolItemPriority.STANDARD.value
    retry_count: int = 0
    clock_drift_ms: int = 0
    batch_id: Optional[str] = None
    created_at_epoch: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spool_id": self.spool_id,
            "station_id": self.station_id,
            "payload_type": self.payload_type,
            "payload": self.payload,
            "edge_timestamp_ms": self.edge_timestamp_ms,
            "spooled_at_utc": self.spooled_at_utc,
            "status": self.status.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "clock_drift_ms": self.clock_drift_ms,
            "batch_id": self.batch_id,
            "created_at_epoch": self.created_at_epoch,
        }


class EdgeSpoolDatabase:
    """Persistent, thread-safe SQLite-backed disk queue for outstation edge buffering.

    Features:
    - 50 MB default disk size protection with prioritized pruning (Diagnostic -> Standard -> Critical).
    - Corrupt record quarantine without queue deadlock.
    - Transactional in-flight tracking with atomic batch acknowledgement.
    """

    DEFAULT_MAX_SPOOL_SIZE_MB: float = 50.0

    def __init__(
        self,
        db_path: str,
        max_records: int = 50000,
        max_spool_size_mb: float = DEFAULT_MAX_SPOOL_SIZE_MB,
    ) -> None:
        self.db_path = db_path
        self.max_records = max_records
        self.max_spool_size_mb = max_spool_size_mb
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edge_telemetry_spool (
                    spool_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    payload_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    edge_timestamp_ms INTEGER NOT NULL,
                    spooled_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 1,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    clock_drift_ms INTEGER NOT NULL DEFAULT 0,
                    batch_id TEXT,
                    created_at_epoch INTEGER NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spool_status ON edge_telemetry_spool(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spool_priority ON edge_telemetry_spool(priority);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spool_created ON edge_telemetry_spool(created_at_epoch);")
            conn.commit()

    def get_disk_size_bytes(self) -> int:
        """Calculate total SQLite file size on disk including WAL and SHM."""
        total = 0
        for ext in ["", "-wal", "-shm"]:
            f = f"{self.db_path}{ext}"
            if os.path.exists(f):
                total += os.path.getsize(f)
        return total

    def _enforce_capacity_guard(self, conn: sqlite3.Connection) -> None:
        """Prune lower-priority buffered records if disk size or record count limits are exceeded."""
        cur = conn.execute("SELECT COUNT(*) as cnt FROM edge_telemetry_spool WHERE status != 'ACKNOWLEDGED';")
        count = cur.fetchone()["cnt"]

        disk_bytes = self.get_disk_size_bytes()
        max_bytes = int(self.max_spool_size_mb * 1024 * 1024)

        if count >= self.max_records or disk_bytes >= max_bytes:
            prune_qty = max(1, min(10, max(1, int(self.max_records * 0.10))))
            # Prioritized FIFO pruning: prune DIAGNOSTIC (2) and STANDARD (1) first, protecting CRITICAL (0)
            cur_prune = conn.execute(
                """
                UPDATE edge_telemetry_spool
                SET status = 'DROPPED_PRUNED'
                WHERE spool_id IN (
                    SELECT spool_id FROM edge_telemetry_spool
                    WHERE status = 'BUFFERED' AND priority > 0
                    ORDER BY priority DESC, created_at_epoch ASC
                    LIMIT ?
                );
                """,
                (prune_qty,),
            )
            pruned_count = cur_prune.rowcount
            if pruned_count < prune_qty:
                # If only CRITICAL items remain and limit still breached, prune oldest critical as absolute last resort
                conn.execute(
                    """
                    UPDATE edge_telemetry_spool
                    SET status = 'DROPPED_PRUNED'
                    WHERE spool_id IN (
                        SELECT spool_id FROM edge_telemetry_spool
                        WHERE status = 'BUFFERED'
                        ORDER BY created_at_epoch ASC
                        LIMIT ?
                    );
                    """,
                    (prune_qty - pruned_count,),
                )
            logger.warning(
                "Spool capacity exceeded (records=%d/%d, disk=%d/%d bytes); pruned oldest low-priority items.",
                count, self.max_records, disk_bytes, max_bytes,
            )

    def enqueue(
        self,
        station_id: str,
        payload_type: str,
        payload: Dict[str, Any],
        priority: int = SpoolItemPriority.STANDARD.value,
        edge_timestamp_ms: Optional[int] = None,
        clock_drift_ms: int = 0,
    ) -> str:
        """Enqueue an item into the local spool with priority assignment."""
        spool_id = str(uuid.uuid4())
        now_epoch = int(time.time() * 1000)
        edge_ts = edge_timestamp_ms if edge_timestamp_ms is not None else now_epoch
        spooled_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            self._enforce_capacity_guard(conn)

            conn.execute(
                """
                INSERT INTO edge_telemetry_spool (
                    spool_id, station_id, payload_type, payload_json,
                    edge_timestamp_ms, spooled_at_utc, status, priority,
                    retry_count, clock_drift_ms, batch_id, created_at_epoch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    spool_id,
                    station_id,
                    payload_type,
                    json.dumps(payload),
                    edge_ts,
                    spooled_at,
                    SpoolItemStatus.BUFFERED.value,
                    priority,
                    0,
                    clock_drift_ms,
                    None,
                    now_epoch,
                ),
            )
            conn.commit()
        return spool_id

    def get_pending_batch(self, limit: int = 100) -> List[SpoolItem]:
        """Fetch oldest pending buffered items, ordered by priority ASC (Critical first) then FIFO."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM edge_telemetry_spool
                WHERE status = 'BUFFERED'
                ORDER BY priority ASC, created_at_epoch ASC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()
            items = []
            for r in rows:
                try:
                    payload_dict = json.loads(r["payload_json"])
                except Exception as exc:
                    # Quarantine corrupted record immediately
                    conn.execute(
                        "UPDATE edge_telemetry_spool SET status = 'CORRUPTED' WHERE spool_id = ?;",
                        (r["spool_id"],),
                    )
                    conn.commit()
                    logger.error("Quarantined corrupt spool record %s: %s", r["spool_id"], exc)
                    continue

                items.append(
                    SpoolItem(
                        spool_id=r["spool_id"],
                        station_id=r["station_id"],
                        payload_type=r["payload_type"],
                        payload=payload_dict,
                        edge_timestamp_ms=r["edge_timestamp_ms"],
                        spooled_at_utc=r["spooled_at_utc"],
                        status=SpoolItemStatus(r["status"]),
                        priority=r["priority"],
                        retry_count=r["retry_count"],
                        clock_drift_ms=r["clock_drift_ms"],
                        batch_id=r["batch_id"],
                        created_at_epoch=r["created_at_epoch"],
                    )
                )
            return items

    def mark_in_flight(self, spool_ids: List[str], batch_id: str) -> None:
        """Mark items as in-flight within a transmission batch."""
        if not spool_ids:
            return
        placeholders = ",".join(["?"] * len(spool_ids))
        with self._get_connection() as conn:
            conn.execute(
                f"""
                UPDATE edge_telemetry_spool
                SET status = 'IN_FLIGHT', batch_id = ?
                WHERE spool_id IN ({placeholders});
                """,
                [batch_id] + spool_ids,
            )
            conn.commit()

    def acknowledge_batch(self, batch_id: str) -> int:
        """Mark all items in a batch as ACKNOWLEDGED."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE edge_telemetry_spool
                SET status = 'ACKNOWLEDGED'
                WHERE batch_id = ? AND status = 'IN_FLIGHT';
                """,
                (batch_id,),
            )
            conn.commit()
            return cur.rowcount

    def nack_batch(self, batch_id: str) -> int:
        """Revert items in a failed batch back to BUFFERED, incrementing retry count."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE edge_telemetry_spool
                SET status = 'BUFFERED', retry_count = retry_count + 1, batch_id = NULL
                WHERE batch_id = ? AND status = 'IN_FLIGHT';
                """,
                (batch_id,),
            )
            conn.commit()
            return cur.rowcount

    def purge_acknowledged(self, older_than_ms: int = 86400000) -> int:
        """Purge acknowledged records older than given threshold."""
        threshold = int(time.time() * 1000) - older_than_ms
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM edge_telemetry_spool
                WHERE status = 'ACKNOWLEDGED' AND created_at_epoch < ?;
                """,
                (threshold,),
            )
            conn.commit()
            return cur.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Retrieve queue diagnostics."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT status, COUNT(*) as cnt FROM edge_telemetry_spool GROUP BY status;")
            counts = {r["status"]: r["cnt"] for r in cur.fetchall()}
            file_size_bytes = self.get_disk_size_bytes()
            return {
                "buffered_count": counts.get(SpoolItemStatus.BUFFERED.value, 0),
                "in_flight_count": counts.get(SpoolItemStatus.IN_FLIGHT.value, 0),
                "acknowledged_count": counts.get(SpoolItemStatus.ACKNOWLEDGED.value, 0),
                "dropped_count": counts.get(SpoolItemStatus.DROPPED_PRUNED.value, 0),
                "corrupted_count": counts.get(SpoolItemStatus.CORRUPTED.value, 0),
                "total_records": sum(counts.values()),
                "file_size_bytes": file_size_bytes,
                "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
            }


class CentralTelemetryReceiver:
    """Central Hub ingestion receiver with authentication, duplicate rejection, and backpressure."""

    def __init__(
        self,
        valid_auth_tokens: Optional[Set[str]] = None,
        max_queue_depth: int = 10000,
    ) -> None:
        self.valid_tokens = valid_auth_tokens or {"nawari-edge-shared-token-2026"}
        self.max_queue_depth = max_queue_depth
        self._seen_event_ids: Set[str] = set()
        self._live_telemetry_stream: List[Dict[str, Any]] = []
        self._historical_replayed_stream: List[Dict[str, Any]] = []
        self.is_throttled: bool = False

    def ingest_batch(self, batch: List[Dict[str, Any]], auth_token: str) -> Dict[str, Any]:
        """Ingest batch from edge forwarder with idempotency and stream segregation."""
        if auth_token not in self.valid_tokens:
            raise PermissionError("INVALID_OR_EXPIRED_TOKEN: Telemetry ingestion authentication failed.")

        if self.is_throttled:
            return {
                "status": "BACKPRESSURE_THROTTLED",
                "message": "Central hub ingestion capacity saturated; back off.",
                "retry_after_seconds": 5.0,
                "ingested_count": 0,
            }

        ingested = 0
        duplicates = 0
        for record in batch:
            event_id = record.get("_forwarding_metadata", {}).get("spool_id") or record.get("event_id")
            if event_id and event_id in self._seen_event_ids:
                duplicates += 1
                continue

            if event_id:
                self._seen_event_ids.add(event_id)

            # Route segregation: Live vs Replayed
            if record.get("telemetry_quality") == "REPLAYED" or record.get("_forwarding_metadata", {}).get("is_replayed"):
                self._historical_replayed_stream.append(record)
            else:
                self._live_telemetry_stream.append(record)
            ingested += 1

        return {
            "status": "INGESTED",
            "ingested_count": ingested,
            "duplicate_count": duplicates,
            "live_count": len(self._live_telemetry_stream),
            "replayed_count": len(self._historical_replayed_stream),
        }

    def get_live_stream(self) -> List[Dict[str, Any]]:
        return list(self._live_telemetry_stream)

    def get_replayed_stream(self) -> List[Dict[str, Any]]:
        return list(self._historical_replayed_stream)


class EdgeStoreAndForwardManager:
    """Manages outstation edge telemetry buffering, partition transitions,

    rate-limited draining, reconnection jitter, and clock drift compensation.
    """

    def __init__(
        self,
        station_id: str,
        db_path: str,
        hub_endpoint: str = "https://nawari-core.internal.kenya-airways.com/api/v1/telemetry",
        auth_token: str = "nawari-edge-shared-token-2026",
        rate_limit_per_second: int = 50,
        max_records: int = 50000,
        max_spool_size_mb: float = 50.0,
    ) -> None:
        self.station_id = station_id
        self.db_path = db_path
        self.hub_endpoint = hub_endpoint
        self.auth_token = auth_token
        self.rate_limit_per_second = rate_limit_per_second
        self.spool_db = EdgeSpoolDatabase(
            db_path=db_path,
            max_records=max_records,
            max_spool_size_mb=max_spool_size_mb,
        )
        self.is_wan_connected: bool = True
        self.clock_drift_ms: int = 0
        self.consecutive_forward_failures: int = 0
        self.reconnection_storm_guard_ms: int = 0

    def set_wan_connection(self, is_connected: bool) -> None:
        """Simulate or record WAN connectivity changes with reconnection storm jitter."""
        self.is_wan_connected = is_connected
        if is_connected:
            # Reconnection storm protection: introduce randomized jitter (10-250ms)
            self.reconnection_storm_guard_ms = random.randint(10, 250)
            logger.info("Station %s WAN restored; reconnection jitter set to %d ms", self.station_id, self.reconnection_storm_guard_ms)
        else:
            logger.info("Station %s WAN link severed; transitioning to local spool buffering.", self.station_id)

    def calculate_backoff_delay(self) -> float:
        """Calculate exponential backoff delay with randomized jitter."""
        if self.consecutive_forward_failures == 0:
            return 0.0
        base = min(60.0, 1.0 * (2 ** (self.consecutive_forward_failures - 1)))
        jitter = random.uniform(0.85, 1.15)
        return round(base * jitter, 2)

    def synchronize_clock(self, hub_ntp_timestamp_ms: int, local_receive_ms: Optional[int] = None) -> int:
        """Compute clock drift delta relative to central hub NTP time:

        drift_ms = hub_time - local_time
        Positive drift means local edge clock is behind hub clock.
        """
        local_ts = local_receive_ms if local_receive_ms is not None else int(time.time() * 1000)
        self.clock_drift_ms = hub_ntp_timestamp_ms - local_ts
        logger.info("Station %s clock drift synchronized: %d ms", self.station_id, self.clock_drift_ms)
        return self.clock_drift_ms

    def record_telemetry(
        self,
        payload_type: str,
        payload: Dict[str, Any],
        priority: int = SpoolItemPriority.STANDARD.value,
    ) -> str:
        """Capture telemetry point at the edge. Always persists to local spool for resilience."""
        return self.spool_db.enqueue(
            station_id=self.station_id,
            payload_type=payload_type,
            payload=payload,
            priority=priority,
            clock_drift_ms=self.clock_drift_ms,
        )

    def drain_and_forward(
        self,
        batch_size: int = 100,
        forward_handler: Optional[Callable[[List[Dict[str, Any]], str], bool]] = None,
        central_receiver: Optional[CentralTelemetryReceiver] = None,
    ) -> Dict[str, Any]:
        """Drain buffered spool records in rate-limited batches across the WAN.

        Decorates replayed records with REPLAYED attribution, original edge timestamp,
        and compensated hub timestamp.
        """
        if not self.is_wan_connected:
            return {
                "status": "WAN_PARTITIONED",
                "message": f"WAN link down for station {self.station_id}; telemetry buffered locally.",
                "forwarded_count": 0,
                "stats": self.spool_db.get_stats(),
            }

        effective_limit = min(batch_size, self.rate_limit_per_second)
        pending_items = self.spool_db.get_pending_batch(limit=effective_limit)
        if not pending_items:
            self.consecutive_forward_failures = 0
            return {
                "status": "IDLE",
                "message": "No pending telemetry in outstation spool.",
                "forwarded_count": 0,
                "stats": self.spool_db.get_stats(),
            }

        batch_id = f"BATCH-{self.station_id}-{uuid.uuid4().hex[:8]}"
        spool_ids = [item.spool_id for item in pending_items]
        self.spool_db.mark_in_flight(spool_ids=spool_ids, batch_id=batch_id)

        now_epoch_ms = int(time.time() * 1000)
        prepared_batch: List[Dict[str, Any]] = []
        for item in pending_items:
            compensated_ts = item.edge_timestamp_ms + item.clock_drift_ms
            age_seconds = round((now_epoch_ms - item.edge_timestamp_ms) / 1000.0, 2)

            enriched = dict(item.payload)
            enriched["_forwarding_metadata"] = {
                "is_replayed": True,
                "telemetry_quality": "REPLAYED",
                "station_id": self.station_id,
                "spool_id": item.spool_id,
                "priority": item.priority,
                "batch_id": batch_id,
                "original_edge_timestamp_ms": item.edge_timestamp_ms,
                "clock_drift_ms": item.clock_drift_ms,
                "compensated_hub_timestamp_ms": compensated_ts,
                "spooled_age_seconds": age_seconds,
            }
            enriched["telemetry_quality"] = "REPLAYED"
            prepared_batch.append(enriched)

        # Dispatch via receiver or custom forward handler
        success = True
        error_msg = None
        if central_receiver:
            try:
                res = central_receiver.ingest_batch(prepared_batch, auth_token=self.auth_token)
                if res.get("status") == "BACKPRESSURE_THROTTLED":
                    success = False
                    error_msg = "SERVER_BACKPRESSURE_THROTTLED"
                else:
                    success = True
            except PermissionError as p_err:
                success = False
                error_msg = f"AUTH_ERROR: {p_err}"
            except Exception as exc:
                success = False
                error_msg = str(exc)
        elif forward_handler:
            try:
                success = forward_handler(prepared_batch, self.auth_token)
            except Exception as exc:
                logger.error("Exception during forwarding batch %s: %s", batch_id, exc)
                success = False
                error_msg = str(exc)

        if success:
            acked_count = self.spool_db.acknowledge_batch(batch_id=batch_id)
            self.consecutive_forward_failures = 0
            return {
                "status": "FORWARDED",
                "batch_id": batch_id,
                "forwarded_count": acked_count,
                "rate_limit_enforced": effective_limit,
                "sample_payload": prepared_batch[0] if prepared_batch else None,
                "stats": self.spool_db.get_stats(),
            }
        else:
            self.consecutive_forward_failures += 1
            self.spool_db.nack_batch(batch_id=batch_id)
            backoff_delay = self.calculate_backoff_delay()
            return {
                "status": "FORWARD_FAILED",
                "batch_id": batch_id,
                "forwarded_count": 0,
                "error": error_msg,
                "consecutive_failures": self.consecutive_forward_failures,
                "next_retry_backoff_sec": backoff_delay,
                "stats": self.spool_db.get_stats(),
            }
