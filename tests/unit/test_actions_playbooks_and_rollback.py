"""Unit tests for Remediation Playbooks & Rollback Preconditions (Workstreams 12C & 12E)."""

import pytest
from services.actions.action_framework import (
    ActionRiskTier,
    ActionState,
    OperationalAction,
)
from services.actions.playbooks.carrier_failover import CarrierFailoverPlaybook
from services.actions.playbooks.interface_dampening import InterfaceDampeningPlaybook
from services.actions.playbooks.synthetic_reverify import SyntheticReverificationPlaybook
from services.actions.rollback_engine import RollbackEngine


def test_carrier_failover_playbook_lifecycle():
    ctx = {
        "primary_trunk_degraded": True,
        "secondary_trunk_reachable": True,
        "emergency_routing_impacted": False,
        "active_trunk": "primary_safaricom",
        "backup_trunk": "secondary_airtel",
        "post_verification_synthetic_call_passed": True,
        "post_failover_mos": 4.15,
        "primary_trunk_stabilized": True,
        "active_emergency_calls": 0,
    }

    # 1. Preconditions
    pre_ok, pre_msg = CarrierFailoverPlaybook.check_preconditions(ctx)
    assert pre_ok is True

    # 2. Snapshot
    pre_state = CarrierFailoverPlaybook.capture_pre_state(ctx)
    assert pre_state["active_outbound_trunk"] == "primary_safaricom"

    # 3. Execution
    exec_res = CarrierFailoverPlaybook.execute(ctx)
    assert exec_res["new_trunk"] == "secondary_airtel"

    # 4. Independent Postconditions Verification
    post_ok, post_msg = CarrierFailoverPlaybook.check_postconditions(ctx)
    assert post_ok is True
    assert "INDEPENDENT_SERVICE_RESTORATION_VERIFIED" in post_msg

    # 5. Rollback Preconditions & Rollback Execution
    rb_pre_ok, _ = CarrierFailoverPlaybook.check_rollback_preconditions(ctx)
    assert rb_pre_ok is True
    rb_res = CarrierFailoverPlaybook.rollback(ctx)
    assert rb_res["active_trunk"] == "primary_safaricom"


def test_rollback_preconditions_fail_escalates_without_unsafe_rollback():
    action = OperationalAction(
        action_id="ACT-ROLLBACK-01",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        state=ActionState.EXECUTING,
    )

    # Primary trunk has NOT stabilized and 3 emergency calls are active!
    unsafe_context = {
        "primary_trunk_stabilized": False,
        "active_emergency_calls": 3,
    }

    # Attempt safe rollback
    success = RollbackEngine.safe_rollback(
        action=action,
        handler=CarrierFailoverPlaybook,
        context=unsafe_context,
    )

    # Blind rollback must be aborted; action transitions to ROLLBACK_FAILED and escalates
    assert success is False
    assert action.state == ActionState.ROLLBACK_FAILED
    assert "Rollback aborted" in action.execution_log[-1]
    assert action.metadata.get("escalation", {}).get("escalation_status") == "ESCALATED_TO_TIER3"


def test_interface_dampening_rollback_preconditions():
    # If physical link is still flapping/unstable, rollback preconditions must fail
    unstable_context = {
        "target_interface": "GigabitEthernet1/0/24",
        "physical_link_stable": False,
    }
    can_rb, reason = InterfaceDampeningPlaybook.check_rollback_preconditions(unstable_context)
    assert can_rb is False
    assert "ROLLBACK_PRECONDITION_FAILED" in reason


def test_synthetic_reverification_playbook():
    ctx = {"target_extension": "1001", "trunk_name": "primary_safaricom"}
    pre_ok, _ = SyntheticReverificationPlaybook.check_preconditions(ctx)
    assert pre_ok is True
    res = SyntheticReverificationPlaybook.execute(ctx)
    assert res["sip_status_code"] == 200
    assert res["mos"] >= 3.80
    post_ok, _ = SyntheticReverificationPlaybook.check_postconditions(ctx)
    assert post_ok is True

