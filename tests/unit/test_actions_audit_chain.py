"""Unit tests for Cryptographically Chained Immutable Audit Trail (Workstream 12G)."""

import pytest
from services.actions.audit_chain import OperationalAuditLedger


def test_audit_chain_hashing_and_verification():
    ledger = OperationalAuditLedger()

    # Genesis block check
    assert len(ledger.chain) == 1
    assert ledger.chain[0].block_index == 0
    assert ledger.chain[0].previous_hash == "0" * 64

    # Append 3 audit records
    b1 = ledger.record_event(
        action_id="ACT-001",
        incident_id="INC-101",
        operator_id="operator_alice",
        event_type="ACTION_PROPOSED",
        payload={"risk_tier": "HIGH_RISK", "playbook": "carrier_failover"},
    )
    b2 = ledger.record_event(
        action_id="ACT-001",
        incident_id="INC-101",
        operator_id="manager_bob",
        event_type="ACTION_APPROVED",
        payload={"token_id": "TOK-ABC12345"},
    )
    b3 = ledger.record_event(
        action_id="ACT-001",
        incident_id="INC-101",
        operator_id="system_executor",
        event_type="ACTION_COMPLETED",
        payload={"verification_mos": 4.15, "restoration": "CONFIRMED"},
    )

    assert len(ledger.chain) == 4
    # Block linkage verification
    assert b1.previous_hash == ledger.chain[0].block_hash
    assert b2.previous_hash == b1.block_hash
    assert b3.previous_hash == b2.block_hash

    # Clean integrity check
    is_valid, msg = ledger.verify_integrity()
    assert is_valid is True
    assert msg == "CHAIN_INTEGRITY_VERIFIED"


def test_modified_audit_record_fails_cryptographic_verification():
    ledger = OperationalAuditLedger()

    ledger.record_event(
        action_id="ACT-001",
        incident_id="INC-101",
        operator_id="operator_alice",
        event_type="ACTION_PROPOSED",
        payload={"target": "primary_safaricom"},
    )
    ledger.record_event(
        action_id="ACT-001",
        incident_id="INC-101",
        operator_id="manager_bob",
        event_type="ACTION_APPROVED",
        payload={"approved": True},
    )

    # Malicious tampering: modify operator ID on block 1
    ledger.chain[1].operator_id = "attacker_mallory"

    # Integrity verification must fail!
    is_valid, msg = ledger.verify_integrity()
    assert is_valid is False
    assert "BLOCK_HASH_TAMPERED at block 1" in msg

