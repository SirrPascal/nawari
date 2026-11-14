"""Unit tests for Approval Tokens, Replay Protection, RBAC & Two-Person Rules (Workstream 12B)."""

import time
import pytest
from services.actions.action_framework import (
    ActionRiskTier,
    ActionState,
    OperationalAction,
)
from services.actions.approval_interlock import (
    ApprovalInterlockEngine,
    OperatorRole,
)


@pytest.fixture
def approval_engine():
    return ApprovalInterlockEngine(hmac_secret="test-auth-secret-kq")


@pytest.fixture
def high_risk_action():
    return OperationalAction(
        action_id="ACT-FAILOVER-01",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        proposer_id="operator_alice",  # Alice proposed
        parameters={"active_trunk": "primary_safaricom", "target_trunk": "secondary_airtel"},
    )


def test_expired_approval_token_rejected(approval_engine, high_risk_action):
    # Issue token with negative validity (already expired)
    token = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="manager_bob",
        role=OperatorRole.NOC_MANAGER,
        validity_seconds=-10.0,
    )
    is_authorized, msg = approval_engine.authorize_action(high_risk_action, token)
    assert is_authorized is False
    assert "EXPIRED_APPROVAL_TOKEN" in msg
    assert high_risk_action.state == ActionState.REJECTED


def test_replayed_approval_token_rejected(approval_engine, high_risk_action):
    token = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="manager_bob",
        role=OperatorRole.NOC_MANAGER,
        validity_seconds=600.0,
    )
    # First use: Authorized successfully
    is_auth1, msg1 = approval_engine.authorize_action(high_risk_action, token)
    assert is_auth1 is True
    assert msg1 == "AUTHORIZED"

    # Second use (replay attack with exact same token): Strictly rejected!
    is_auth2, msg2 = approval_engine.authorize_action(high_risk_action, token)
    assert is_auth2 is False
    assert "REPLAYED_APPROVAL_TOKEN" in msg2


def test_same_operator_approves_twice_rejected(approval_engine, high_risk_action):
    # Proposer Alice cannot approve her own high-risk mutation
    token_alice = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="operator_alice",
        role=OperatorRole.NOC_MANAGER,
    )
    is_auth_alice, msg_alice = approval_engine.authorize_action(high_risk_action, token_alice)
    assert is_auth_alice is False
    assert "TWO_PERSON_RULE_VIOLATION" in msg_alice

    # If Bob approves once, a second token from Bob cannot act as the second approver
    token_bob1 = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="manager_bob",
        role=OperatorRole.NOC_MANAGER,
    )
    is_auth_bob1, _ = approval_engine.authorize_action(high_risk_action, token_bob1)
    assert is_auth_bob1 is True

    token_bob2 = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="manager_bob",
        role=OperatorRole.NOC_MANAGER,
    )
    is_auth_bob2, msg_bob2 = approval_engine.authorize_action(high_risk_action, token_bob2)
    assert is_auth_bob2 is False
    assert "SAME_OPERATOR_APPROVES_TWICE" in msg_bob2


def test_modified_action_parameters_invalidates_approval(approval_engine, high_risk_action):
    # Issue token for original parameters
    token = approval_engine.issue_token(
        action=high_risk_action,
        operator_id="manager_bob",
        role=OperatorRole.NOC_MANAGER,
    )

    # Malicious or accidental modification of parameters after approval token issuance
    high_risk_action.parameters["target_trunk"] = "rogue_untrusted_carrier"

    # Token verification must detect the parameter hash mismatch!
    is_auth, msg = approval_engine.authorize_action(high_risk_action, token)
    assert is_auth is False
    assert "MODIFIED_ACTION_PARAMETERS" in msg

