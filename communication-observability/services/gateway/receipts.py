"""Bounded gateway receipts for verified downstream acceptance."""

from collections import OrderedDict
from contextlib import closing
import sqlite3
from threading import Lock

from services.endpoint.delivery import RETRY, TARGET_ACCEPTED


class DeliveryReceipts:
    """Suppress concurrent and recently completed replays in one gateway process."""

    def __init__(self, path: str | None, limit: int):
        if limit < 1:
            raise ValueError("Receipt capacity must be positive")
        self.path = path
        self.limit = limit
        self._completed: OrderedDict[str, None] = OrderedDict()
        self._in_flight: set[str] = set()
        self._lock = Lock()
        if path:
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS endpoint_receipts (record_id TEXT NOT NULL UNIQUE)"
                )

    def _accepted(self, identifier: str) -> bool:
        if self.path:
            with closing(sqlite3.connect(self.path)) as connection:
                return connection.execute(
                    "SELECT 1 FROM endpoint_receipts WHERE record_id = ?", (identifier,)
                ).fetchone() is not None
        return identifier in self._completed

    def _remember(self, identifier: str) -> None:
        if self.path:
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute(
                    "INSERT OR IGNORE INTO endpoint_receipts (record_id) VALUES (?)", (identifier,)
                )
                connection.execute(
                    "DELETE FROM endpoint_receipts WHERE rowid IN "
                    "(SELECT rowid FROM endpoint_receipts ORDER BY rowid DESC LIMIT -1 OFFSET ?)",
                    (self.limit,),
                )
        else:
            self._completed[identifier] = None
            if len(self._completed) > self.limit:
                self._completed.popitem(last=False)

    def deliver(self, identifier, forward):
        with self._lock:
            if identifier in self._in_flight:
                return RETRY
            if self._accepted(identifier):
                return TARGET_ACCEPTED
            self._in_flight.add(identifier)

        try:
            if not forward():
                return RETRY
            with self._lock:
                self._remember(identifier)
            return TARGET_ACCEPTED
        finally:
            with self._lock:
                self._in_flight.remove(identifier)
