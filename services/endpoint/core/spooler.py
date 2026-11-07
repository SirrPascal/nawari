"""Resilient local disk spooler for endpoint telemetry with bounds and corruption recovery."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.endpoint.core.logger import setup_agent_logger

logger = setup_agent_logger()


class DiskSpooler:
    """Manages offline telemetry spooling to local disk.

    Features:
    1. Bounded record storage: Automatically trims oldest records when capacity is reached.
    2. Atomic append: Appends JSONL records with fsync.
    3. Corruption resilience: Skips malformed lines rather than failing replay.
    4. Secure permissions: Enforces 0600 file modes.
    """

    def __init__(self, spool_dir: str, max_records: int = 1000) -> None:
        self.spool_dir = Path(spool_dir).expanduser().resolve()
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.spool_file = self.spool_dir / "telemetry_spool.jsonl"
        self.max_records = max_records

    def spool(self, record: Dict[str, Any]) -> bool:
        """Append a telemetry record to the spool file."""
        try:
            line = json.dumps(record) + "\n"
            # Check capacity before writing
            self._enforce_capacity()

            with open(self.spool_file, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

            # Secure file permissions (0600)
            try:
                os.chmod(self.spool_file, 0o600)
            except Exception:
                pass

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
                        records.append(record)
                        if len(records) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning(f"Error reading spool file: {exc}")

        return records

    def purge(self, count: int) -> int:
        """Remove the oldest `count` records from the spool after successful transmission."""
        if not self.spool_file.exists() or count <= 0:
            return 0

        tmp_file = self.spool_file.with_suffix(".tmp")
        removed = 0
        try:
            with open(self.spool_file, "r", encoding="utf-8") as fin, \
                 open(tmp_file, "w", encoding="utf-8") as fout:
                for line in fin:
                    if not line.strip():
                        continue
                    if removed < count:
                        removed += 1
                        continue
                    fout.write(line)

            tmp_file.replace(self.spool_file)
            return removed
        except Exception as exc:
            logger.error(f"Failed to purge spooled records: {exc}")
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
            return 0

    dequeue = purge  # Canonical alias for spool queue operations

    def clear(self) -> None:
        """Clear all spooled records."""
        if self.spool_file.exists():
            try:
                self.spool_file.unlink()
            except Exception:
                pass

    def _enforce_capacity(self) -> None:
        """Trim the oldest 20% of records if total records exceed max_records."""
        current_count = self.get_pending_count()
        if current_count >= self.max_records:
            trim_target = max(1, int(self.max_records * 0.2))
            logger.warning(
                f"Spool limit reached ({current_count}/{self.max_records}). Purging oldest {trim_target} records."
            )
            self.purge(trim_target)
