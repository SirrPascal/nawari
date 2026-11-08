"""tests/unit/test_multisite_edge_forwarder.py
============================================
Unit tests for outstation edge telemetry buffering and store-and-forward (Workstream 13D).
"""

import os
import tempfile
import time
import pytest
from services.multisite.edge_forwarder import (
    EdgeSpoolDatabase,
    EdgeStoreAndForwardManager,
    SpoolItemStatus,
)


@pytest.fixture
def temp_spool_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)
    # Also clean up any WAL/SHM files
    wal_path = f"{db_path}-wal"
    shm_path = f"{db_path}-shm"
    if os.path.exists(wal_path):
        os.remove(wal_path)
    if os.path.exists(shm_path):
        os.remove(shm_path)


def test_edge_spool_database_crud_and_capacity_pruning(temp_spool_db):
    # Set capacity to 5 for test
    db = EdgeSpoolDatabase(db_path=temp_spool_db, max_records=5)

    # 1. Enqueue 4 items
    for i in range(4):
        db.enqueue(
            station_id="MBA-STATION",
            payload_type="metric",
            payload={"metric": "interface.in_bytes", "val": 1000 + i},
        )

    stats = db.get_stats()
    assert stats["buffered_count"] == 4
    assert stats["total_records"] == 4

    # 2. Get pending batch
    batch = db.get_pending_batch(limit=2)
    assert len(batch) == 2
    assert batch[0].payload["val"] == 1000

    # 3. Mark in-flight
    spool_ids = [item.spool_id for item in batch]
    db.mark_in_flight(spool_ids=spool_ids, batch_id="B-001")
    stats_inflight = db.get_stats()
    assert stats_inflight["in_flight_count"] == 2
    assert stats_inflight["buffered_count"] == 2

    # 4. Acknowledge batch
    acked = db.acknowledge_batch(batch_id="B-001")
    assert acked == 2
    stats_acked = db.get_stats()
    assert stats_acked["acknowledged_count"] == 2

    # 5. Test capacity pruning
    # Add 10 more items to trigger capacity overflow (max_records=5)
    for i in range(10):
        db.enqueue(
            station_id="MBA-STATION",
            payload_type="alert",
            payload={"alert_id": f"ALT-{i}", "severity": "P2_HIGH"},
        )

    stats_pruned = db.get_stats()
    # Oldest buffered items should have been pruned to DROPPED_PRUNED
    assert stats_pruned["dropped_count"] >= 1


def test_edge_store_and_forward_partition_and_replay(temp_spool_db):
    manager = EdgeStoreAndForwardManager(
        station_id="MBA-STATION",
        db_path=temp_spool_db,
        rate_limit_per_second=20,
    )

    # 1. Synchronize clock: edge clock is 250ms behind hub NTP
    now_ms = int(time.time() * 1000)
    drift = manager.synchronize_clock(hub_ntp_timestamp_ms=now_ms + 250, local_receive_ms=now_ms)
    assert drift == 250
    assert manager.clock_drift_ms == 250

    # 2. Simulate WAN partition (circuit down)
    manager.set_wan_connection(is_connected=False)
    assert manager.is_wan_connected is False

    # 3. Generate telemetry while partitioned
    for i in range(5):
        manager.record_telemetry(
            payload_type="metric",
            payload={"component_id": f"SW-MBA-0{i}", "status": "UP", "cpu_pct": 22.5},
        )

    # Attempt to drain while partitioned -> must buffer and not forward
    res_partitioned = manager.drain_and_forward()
    assert res_partitioned["status"] == "WAN_PARTITIONED"
    assert res_partitioned["forwarded_count"] == 0
    assert res_partitioned["stats"]["buffered_count"] == 5

    # 4. WAN circuit restored
    manager.set_wan_connection(is_connected=True)
    assert manager.is_wan_connected is True

    # 5. Capture dispatched batches
    forwarded_batches = []

    def mock_hub_receiver(batch):
        forwarded_batches.append(batch)
        return True

    res_drain = manager.drain_and_forward(batch_size=10, forward_handler=mock_hub_receiver)
    assert res_drain["status"] == "FORWARDED"
    assert res_drain["forwarded_count"] == 5
    assert len(forwarded_batches) == 1
    assert len(forwarded_batches[0]) == 5

    # 6. Verify payload decoration and REPLAYED attribute
    for item in forwarded_batches[0]:
        assert item["telemetry_quality"] == "REPLAYED"
        assert "_forwarding_metadata" in item
        meta = item["_forwarding_metadata"]
        assert meta["is_replayed"] is True
        assert meta["telemetry_quality"] == "REPLAYED"
        assert meta["station_id"] == "MBA-STATION"
        assert meta["clock_drift_ms"] == 250
        assert meta["compensated_hub_timestamp_ms"] == meta["original_edge_timestamp_ms"] + 250


def test_edge_forwarder_nack_reverts_batch(temp_spool_db):
    manager = EdgeStoreAndForwardManager(
        station_id="KIS-STATION",
        db_path=temp_spool_db,
    )

    manager.record_telemetry("alert", {"alert": "High Temperature"})

    # Forward handler returns False (e.g. Hub 503 Service Unavailable)
    def failing_hub_receiver(batch):
        return False

    res_fail = manager.drain_and_forward(forward_handler=failing_hub_receiver)
    assert res_fail["status"] == "FORWARD_FAILED"
    assert res_fail["forwarded_count"] == 0

    # Ensure item reverted to BUFFERED with incremented retry count
    pending = manager.spool_db.get_pending_batch(limit=10)
    assert len(pending) == 1
    assert pending[0].status == SpoolItemStatus.BUFFERED
    assert pending[0].retry_count == 1

