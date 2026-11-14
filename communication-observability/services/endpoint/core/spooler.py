"""Resilient local disk spooler for endpoint telemetry with bounds and corruption recovery."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any, Dict, List

from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.delivery import record_id

logger = setup_agent_logger()


class DiskSpooler:
    """Manages offline telemetry spooling to local disk.

    Features:
    1. Bounded record storage: Automatically trims oldest records when capacity is reached.
    2. Atomic append: Appends JSONL records with fsync.
    3. Corruption resilience: Skips malformed lines rather than failing replay.
    4. Secure permissions: Enforces 0600 file modes.
    """

    def __init__(
        self,
        spool_dir: str,
        max_records: int = 1000,
        max_record_age_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.spool_dir = Path(spool_dir).expanduser().resolve()
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.spool_file = self.spool_dir / "telemetry_spool.jsonl"
        self.max_records = max_records
        self.max_record_age_seconds = max_record_age_seconds
        self._lock = RLock()

    def spool(self, record: Dict[str, Any]) -> bool:
        """Append a telemetry record to the spool file."""
        try:
            self._purge_expired()
            stored_record = dict(record)
            stored_record.setdefault("_spooled_at_ns", time.time_ns())
            line = json.dumps(stored_record, allow_nan=False) + "\n"
            with self._lock:
                self._enforce_capacity()
                fd = os.open(self.spool_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as f:
                    if hasattr(os, "fchmod"):
                        os.fchmod(f.fileno(), 0o600)
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())

            return True
        except Exception as exc:
            logger.error(f"Failed to spool telemetry record: {exc}")
            return False

    def get_pending_count(self) -> int:
        """Return the number of spooled records pending transmission."""
        if not self.spool_file.exists():
            return 0
        try:
            with open(self.spool_file, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def peek(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read up to `limit` records from the spool without removing them."""
        self._purge_expired()
        if not self.spool_file.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(self.spool_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        record.pop("_spooled_at_ns", None)
                        records.append(record)
                        if len(records) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning(f"Error reading spool file: {exc}")

        return records

    def purge(self, count: int) -> int:
        """Remove the oldest records for explicit spool administration."""
        if count <= 0:
            return 0
        return self._remove(lambda line, removed: bool(line.strip()) and removed < count)

    dequeue = purge  # Compatibility for explicit capacity and administrative operations.

    def acknowledge(self, record_ids: set[str]) -> int:
        """Remove only wire reports with an explicit successful receipt."""
        if not record_ids:
            return 0

        def matches(line, _removed):
            try:
                stored_record = json.loads(line)
                stored_record.pop("_spooled_at_ns", None)
                return record_id(stored_record) in record_ids
            except (ValueError, TypeError):
                return False

        return self._remove(matches)

    def _remove(self, matches) -> int:
        with self._lock:
            if not self.spool_file.exists():
                return 0
            tmp_file = None
            removed = 0
            try:
                with self.spool_file.open(encoding="utf-8") as source, NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.spool_dir, delete=False,
                ) as target:
                    tmp_file = Path(target.name)
                    for line in source:
                        if matches(line, removed):
                            removed += 1
                        else:
                            target.write(line)
                    target.flush()
                    os.fsync(target.fileno())
                if removed:
                    tmp_file.replace(self.spool_file)
                return removed
            except (OSError, UnicodeError):
                logger.warning("Failed to update endpoint telemetry spool")
                return 0
            finally:
                if tmp_file is not None:
                    tmp_file.unlink(missing_ok=True)

    def clear(self) -> None:
        """Clear all spooled records."""
        with self._lock:
            try:
                self.spool_file.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to clear endpoint telemetry spool")

    def _enforce_capacity(self) -> None:
        """Trim the oldest 20% of records if total records exceed max_records."""
        current_count = self.get_pending_count()
        if current_count >= self.max_records:
            trim_target = max(1, int(self.max_records * 0.2))
            logger.warning(
                f"Spool limit reached ({current_count}/{self.max_records}). Purging oldest {trim_target} records."
            )
            self.purge(trim_target)

    def _purge_expired(self) -> int:
        """Remove records past their seven-day receipt/observation deadline."""
        if self.max_record_age_seconds <= 0 or not self.spool_file.exists():
            return 0
        cutoff_ns = time.time_ns() - self.max_record_age_seconds * 1_000_000_000

        def expired(line: str, _removed: int) -> bool:
            try:
                stored_record = json.loads(line)
                timestamp_ns = int(
                    stored_record.get("timestamp_ns")
                    or stored_record.get("_spooled_at_ns", 0)
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                return False
            return timestamp_ns > 0 and timestamp_ns < cutoff_ns

        return self._remove(expired)
