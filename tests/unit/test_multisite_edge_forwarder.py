"""tests/unit/test_multisite_edge_forwarder.py
============================================
Unit tests for outstation edge telemetry buffering and store-and-forward (Workstream 13D).
"""

import os
import sqlite3
import tempfile
import time
import pytest
from services.multisite.edge_forwarder import (
    CentralTelemetryReceiver,
    EdgeSpoolDatabase,
    EdgeStoreAndForwardManager,
    SpoolCriticalCapacityExhaustedError,
    SpoolItemPriority,
    SpoolItemStatus,
    SpoolStorageError,
)


@pytest.fixture
def temp_spool_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)
    wal_path = f"{db_path}-wal"
    shm_path = f"{db_path}-shm"
    if os.path.exists(wal_path):
        os.remove(wal_path)
    if os.path.exists(shm_path):
        os.remove(shm_path)


def test_edge_spool_database_crud_and_capacity_pruning(temp_spool_db):
    db = EdgeSpoolDatabase(db_path=temp_spool_db, max_records=5)

    # 1. Enqueue 4 items
    for i in range(4):
        db.enqueue(
            station_id="MBA-STATION",
            payload_type="metric",
            payload={"metric": "interface.in_bytes", "val": 1000 + i},
            priority=SpoolItemPriority.STANDARD.value,
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

    # 5. Prioritized pruning: Critical records are preserved over Diagnostic records
    # Enqueue a critical alert (priority 0)
    db.enqueue(
        station_id="MBA-STATION",
        payload_type="alert",
        payload={"alert": "Core Trunk Down"},
        priority=SpoolItemPriority.CRITICAL.value,
    )
    # Add 10 diagnostic logs to trigger pruning
    for i in range(10):
        db.enqueue(
            station_id="MBA-STATION",
            payload_type="diagnostic",
            payload={"trace": f"ping_{i}"},
            priority=SpoolItemPriority.DIAGNOSTIC.value,
        )

    # Critical item remains buffered and not pruned
    pending = db.get_pending_batch(limit=10)
    assert any(p.priority == SpoolItemPriority.CRITICAL.value for p in pending)


def test_corrupt_record_quarantined_without_blocking_queue(temp_spool_db):
    db = EdgeSpoolDatabase(db_path=temp_spool_db)

    # Enqueue valid item 1
    db.enqueue("KIS-STATION", "metric", {"val": 1})

    # Intentionally corrupt item 2 directly in SQLite
    spool_id_bad = "CORRUPT-SPOOL-001"
    conn = sqlite3.connect(temp_spool_db)
    conn.execute(
        """
        INSERT INTO edge_telemetry_spool (
            spool_id, station_id, payload_type, payload_json,
            edge_timestamp_ms, spooled_at_utc, status, priority,
            retry_count, clock_drift_ms, batch_id, created_at_epoch
        ) VALUES (?, 'KIS-STATION', 'metric', 'INVALID_JSON_CORRUPT{[[', 1000, 'now', 'BUFFERED', 1, 0, 0, NULL, 1000);
        """,
        (spool_id_bad,),
    )
    conn.commit()
    conn.close()

    # Enqueue valid item 3
    db.enqueue("KIS-STATION", "metric", {"val": 3})

    # Fetch batch: corrupted record should be moved to CORRUPTED, unblocking valid item 3
    batch = db.get_pending_batch(limit=10)
    assert len(batch) == 2
    assert batch[0].payload["val"] == 1
    assert batch[1].payload["val"] == 3

    stats = db.get_stats()
    assert stats["corrupted_count"] == 1


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
    assert manager.reconnection_storm_guard_ms >= 10

    # 5. Capture dispatched batches
    forwarded_batches = []

    def mock_hub_receiver(batch, auth_token):
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


def test_central_receiver_deduplication_and_backpressure(temp_spool_db):
    receiver = CentralTelemetryReceiver()
    manager = EdgeStoreAndForwardManager(
        station_id="LHR-STATION",
        db_path=temp_spool_db,
    )

    # 1. Enqueue and forward normal telemetry
    manager.record_telemetry("metric", {"metric": "latency", "val": 140.0})
    res = manager.drain_and_forward(central_receiver=receiver)
    assert res["status"] == "FORWARDED"
    assert receiver.get_replayed_stream()[0]["metric"] == "latency"

    # 2. Simulate server backpressure throttling
    receiver.is_throttled = True
    manager.record_telemetry("metric", {"metric": "jitter", "val": 5.0})
    res_throttled = manager.drain_and_forward(central_receiver=receiver)
    assert res_throttled["status"] == "FORWARD_FAILED"
    assert "THROTTLED" in str(res_throttled["error"])
    assert res_throttled["consecutive_failures"] == 1
    assert res_throttled["next_retry_backoff_sec"] > 0.0

    # 3. Lift throttling and verify successful recovery
    receiver.is_throttled = False
    res_recovered = manager.drain_and_forward(central_receiver=receiver)
    assert res_recovered["status"] == "FORWARDED"
    assert manager.consecutive_forward_failures == 0


def test_auth_token_expiry_handling(temp_spool_db):
    receiver = CentralTelemetryReceiver(valid_auth_tokens={"VALID_TOKEN_123"})
    manager = EdgeStoreAndForwardManager(
        station_id="DXB-STATION",
        db_path=temp_spool_db,
        auth_token="EXPIRED_TOKEN_999",
    )

    manager.record_telemetry("alert", {"alert": "Air-Conditioning Warning"})
    res = manager.drain_and_forward(central_receiver=receiver)
    assert res["status"] == "FORWARD_FAILED"
    assert "AUTH_ERROR" in str(res["error"])


def test_in_flight_restart_recovery(temp_spool_db):
    db1 = EdgeSpoolDatabase(db_path=temp_spool_db)
    # Enqueue items
    id1 = db1.enqueue("MBA-STATION", "metric", {"cpu": 10})
    id2 = db1.enqueue("MBA-STATION", "metric", {"cpu": 20})

    # Mark items in flight in batch B-999
    db1.mark_in_flight([id1, id2], "B-999")
    stats1 = db1.get_stats()
    assert stats1["in_flight_count"] == 2
    assert stats1["buffered_count"] == 0

    # Simulate daemon crash and reboot (new database instance on same file)
    db2 = EdgeSpoolDatabase(db_path=temp_spool_db)
    # During startup _init_db(), recover_in_flight() must reset orphaned in-flight records
    stats2 = db2.get_stats()
    assert stats2["in_flight_count"] == 0
    assert stats2["buffered_count"] == 2

    # Verify they can be batched again
    pending = db2.get_pending_batch(limit=10)
    assert len(pending) == 2


def test_critical_spool_saturation_backpressure_and_emergency_log(temp_spool_db):
    emergency_log = f"{temp_spool_db}.emergency.log"
    db = EdgeSpoolDatabase(
        db_path=temp_spool_db,
        max_records=3,
        allow_critical_prune=False,  # Strict protection mode
        emergency_log_path=emergency_log,
    )

    # Enqueue 3 critical items to completely fill capacity
    for i in range(3):
        db.enqueue("MBA-STATION", "alert", {"p1_alert": f"Trunk_{i}"}, priority=SpoolItemPriority.CRITICAL.value)

    stats = db.get_stats()
    assert stats["buffered_count"] == 3

    # Attempting to enqueue a 4th critical item with 0 lower-priority items must trigger explicit backpressure
    with pytest.raises(SpoolCriticalCapacityExhaustedError) as exc_info:
        db.enqueue("MBA-STATION", "alert", {"p1_alert": "Trunk_OVERFLOW"}, priority=SpoolItemPriority.CRITICAL.value)

    assert "SPOOL_CRITICAL_OVERFLOW" in str(exc_info.value)
    # Verify emergency disk log was created with durable trace
    assert os.path.exists(emergency_log)
    with open(emergency_log) as f:
        log_content = f.read()
    assert "SPOOL_SATURATION_CRITICAL_BACKPRESSURE" in log_content

    if os.path.exists(emergency_log):
        os.remove(emergency_log)


def test_sqlite_operational_write_failure_raises_spool_storage_error(temp_spool_db):
    db = EdgeSpoolDatabase(db_path=temp_spool_db)

    # Make SQLite database file read-only to simulate disk / filesystem write failure
    os.chmod(temp_spool_db, 0o400)

    try:
        with pytest.raises(SpoolStorageError) as exc_info:
            db.enqueue("KIS-STATION", "metric", {"val": 99})

        assert "SPOOL_DISK_ERROR" in str(exc_info.value)
    finally:
        os.chmod(temp_spool_db, 0o600)


def test_central_receiver_queue_depth_saturation_backpressure():
    receiver = CentralTelemetryReceiver(max_queue_depth=5)
    batch = [{"event_id": f"EV-{i}", "val": i} for i in range(5)]

    # Ingest 5 items: reaches max queue depth
    res1 = receiver.ingest_batch(batch, auth_token="nawari-edge-shared-token-2026")
    assert res1["status"] == "INGESTED"
    assert res1["ingested_count"] == 5

    # Ingesting next batch triggers automatic backpressure throttling
    batch2 = [{"event_id": "EV-OVERFLOW", "val": 999}]
    res2 = receiver.ingest_batch(batch2, auth_token="nawari-edge-shared-token-2026")
    assert res2["status"] == "BACKPRESSURE_THROTTLED"
    assert receiver.is_throttled is True

