"""tests/unit/test_multisite_api_governance.py
============================================
Unit tests for API Governance, Hardened Audit Ledger & Crash Recovery (Workstream 13H).
"""

import os
import shutil
import tempfile
import time
import pytest
from services.multisite.api_governance import (
    AuditChainCorruptionType,
    HardenedAuditLedger,
    IdempotencyRegistry,
    LeaseBasedEntityLock,
    TokenBucketRateLimiter,
    WALActionState,
    WriteAheadActionJournal,
)


def test_token_bucket_rate_limiter():
    limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst_capacity=3)

    # Initial 3 burst tokens permitted
    assert limiter.acquire("MBA-OUTSTATION", tokens=1) is True
    assert limiter.acquire("MBA-OUTSTATION", tokens=1) is True
    assert limiter.acquire("MBA-OUTSTATION", tokens=1) is True

    # 4th request without delay should be denied
    assert limiter.acquire("MBA-OUTSTATION", tokens=1) is False
    assert limiter.get_retry_after("MBA-OUTSTATION") > 0.0

    # Independent client key is unaffected
    assert limiter.acquire("KIS-OUTSTATION", tokens=1) is True


def test_idempotency_registry():
    registry = IdempotencyRegistry(ttl_seconds=60.0)
    key = "IDEMP-2026-001"
    req_hash = "sha256:abc123"

    # 1. First registration returns None (needs execution)
    res = registry.check_or_register(idempotency_key=key, request_hash=req_hash)
    assert res is None

    # 2. Store response
    response_payload = {"status": "SUCCESS", "incident_id": "INC-123"}
    registry.store_response(idempotency_key=key, response=response_payload)

    # 3. Subsequent identical request returns cached response
    cached = registry.check_or_register(idempotency_key=key, request_hash=req_hash)
    assert cached == response_payload

    # 4. Reusing key with different request payload raises ValueError
    with pytest.raises(ValueError) as exc:
        registry.check_or_register(idempotency_key=key, request_hash="sha256:tampered_payload")
    assert "Idempotency key reused with mismatched" in str(exc.value)


def test_hardened_audit_ledger_integrity_and_tampering():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        ledger_path = tf.name

    try:
        ledger = HardenedAuditLedger(ledger_file_path=ledger_path)

        # 1. Append 3 blocks
        b0 = ledger.append_event("ACTION_PROPOSED", "USR-01", "JKIA-HUB", {"plan": "restart_gw"})
        b1 = ledger.append_event("ACTION_APPROVED", "USR-02", "JKIA-HUB", {"approver": "CIO"})
        b2 = ledger.append_event("ACTION_EXECUTED", "SYS-01", "MBA-STATION", {"result": "ok"})

        assert len(ledger.get_blocks()) == 3
        assert b1.previous_hash == b0.block_hash
        assert b2.previous_hash == b1.block_hash

        # 2. Verify clean chain
        verification = ledger.verify_integrity()
        assert verification["valid"] is True
        assert verification["blocks_verified"] == 3
        assert verification["corruption_type"] == AuditChainCorruptionType.NONE.value

        # 3. External Anchor Snapshot
        anchor = ledger.export_external_anchor()
        assert anchor["total_blocks"] == 3
        assert anchor["head_hash"] == b2.block_hash
        assert len(anchor["system_signature"]) == 64

        # 4. Tampering detection: modify payload of block 1
        ledger.get_blocks()[1].payload["approver"] = "ATTACKER"
        tamper_check = ledger.verify_integrity()
        assert tamper_check["valid"] is False
        assert tamper_check["failed_index"] == 1
        assert tamper_check["corruption_type"] == AuditChainCorruptionType.TAMPERED_PAYLOAD.value

    finally:
        if os.path.exists(ledger_path):
            os.remove(ledger_path)


def test_write_ahead_action_journal_and_crash_recovery():
    temp_wal_dir = tempfile.mkdtemp()
    try:
        journal = WriteAheadActionJournal(wal_dir=temp_wal_dir)

        # 1. Record completed action
        journal.record_checkpoint("ACT-DONE", WALActionState.INITIATED)
        journal.record_checkpoint("ACT-DONE", WALActionState.STEP_IN_PROGRESS, step_index=1)
        journal.mark_completed("ACT-DONE")

        # 2. Record action that crashes mid-flight at step 2
        journal.record_checkpoint("ACT-CRASHED", WALActionState.INITIATED)
        journal.record_checkpoint("ACT-CRASHED", WALActionState.STEP_IN_PROGRESS, step_index=2, metadata={"subsystem": "trunk_switch"})
        # (Process simulated crash here - no mark_completed called)

        # 3. On daemon startup, scan for crashes
        crashed_actions = journal.scan_for_crashed_actions()
        assert len(crashed_actions) == 1
        crashed = crashed_actions[0]
        assert crashed["action_id"] == "ACT-CRASHED"
        assert crashed["recovery_state"] == WALActionState.UNVERIFIED_CRASH.value
        assert crashed["step_index"] == 2
        assert crashed["metadata"]["subsystem"] == "trunk_switch"

    finally:
        shutil.rmtree(temp_wal_dir, ignore_errors=True)


def test_lease_based_entity_concurrency_lock():
    lock = LeaseBasedEntityLock(default_lease_seconds=0.2)  # short 200ms lease for test
    entity = "DEV-AVAYA-SBCE-01"

    # 1. Owner 1 acquires
    assert lock.acquire(entity_id=entity, owner_id="WORKER-A") is True
    assert lock.is_locked(entity) is True

    # 2. Owner 2 is rejected while lease is held
    assert lock.acquire(entity_id=entity, owner_id="WORKER-B") is False

    # 3. Owner 1 renews lease
    assert lock.heartbeat(entity_id=entity, owner_id="WORKER-A", extend_seconds=0.3) is True

    # 4. Wait for lease to expire (simulating Worker A crash)
    time.sleep(0.35)
    assert lock.is_locked(entity) is False

    # 5. Worker B can now acquire without permanent deadlock
    assert lock.acquire(entity_id=entity, owner_id="WORKER-B") is True
    assert lock.release(entity_id=entity, owner_id="WORKER-B") is True
    assert lock.is_locked(entity) is False

