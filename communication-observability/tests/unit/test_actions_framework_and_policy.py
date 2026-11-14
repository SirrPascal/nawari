"""Unit tests for Action Framework, Policy Boundaries & Production Deny Rules (Workstream 12A)."""

import pytest
from services.actions.action_framework import (
    ActionRegistry,
    ActionRiskTier,
    ActionState,
    AutomationPolicyEngine,
    OperationalAction,
)


def test_target_outside_allowlist_blocked():
    action = OperationalAction(
        action_id="ACT-001",
        playbook_name="interface_dampening",
        playbook_version="1.0.0",
        target_entity="unauthorized_host_ext99",  # Not in allowlist
        risk_tier=ActionRiskTier.MODERATE_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
    )
    is_permitted, msg = AutomationPolicyEngine.evaluate_policy(action)
    assert is_permitted is False
    assert msg == "TARGET_OUTSIDE_ALLOWLIST"
    assert action.state == ActionState.BLOCKED


def test_production_target_in_simulation_mode_blocked():
    action = OperationalAction(
        action_id="ACT-002",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::live_production_carrier",  # Contains production deny keyword
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-1002",
        incident_id="INC-2002",
        hypothesis_id="HYP-3002",
    )
    # Under simulation mode, production targets are strictly denied
    is_permitted, msg = AutomationPolicyEngine.evaluate_policy(action, simulation_mode=True)
    assert is_permitted is False
    assert msg == "HARD_PRODUCTION_DENY"
    assert action.state == ActionState.BLOCKED


def test_change_freeze_blocks_mutations_but_allows_diagnostics():
    # 1. High-risk route change during freeze window must be blocked
    action_high = OperationalAction(
        action_id="ACT-003",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-1003",
        incident_id="INC-2003",
        hypothesis_id="HYP-3003",
    )
    is_perm, msg = AutomationPolicyEngine.evaluate_policy(action_high, is_change_freeze=True)
    assert is_perm is False
    assert msg == "PROHIBITED_CHANGE_FREEZE"
    assert action_high.state == ActionState.BLOCKED

    # 2. Low-risk diagnostic test call during freeze window is permitted
    action_diag = OperationalAction(
        action_id="ACT-004",
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1004",
        incident_id="INC-2004",
        hypothesis_id="HYP-3004",
    )
    is_perm_diag, msg_diag = AutomationPolicyEngine.evaluate_policy(action_diag, is_change_freeze=True)
    assert is_perm_diag is True
    assert msg_diag == "PRE_AUTHORIZED_AUTOMATED"
    assert action_diag.state == ActionState.APPROVED


def test_high_blast_radius_blocked_for_automated_actions():
    action = OperationalAction(
        action_id="ACT-005",
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="sw-jkia-core01",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1005",
        incident_id="INC-2005",
        hypothesis_id="HYP-3005",
    )
    # Blast radius = 12 nodes (exceeds automated limit of 5)
    is_permitted, msg = AutomationPolicyEngine.evaluate_policy(action, blast_radius_nodes=12)
    assert is_permitted is False
    assert msg == "PROHIBITED_HIGH_BLAST_RADIUS"
    assert action.state == ActionState.BLOCKED

