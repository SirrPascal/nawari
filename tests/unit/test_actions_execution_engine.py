"""Unit tests for Action Execution Service, Idempotency & Circuit Breakers (Workstream 12D)."""

import time
import pytest
from services.actions.action_framework import (
    ActionRegistry,
    ActionRiskTier,
    ActionState,
    OperationalAction,
)
from services.actions.execution_engine import ActionExecutionService
from services.actions.playbooks.synthetic_reverify import SyntheticReverificationPlaybook


@pytest.fixture
def execution_service():
    registry = ActionRegistry()
    registry.register(
        name="synthetic_reverify",
        version="1.0.0",
        risk_tier=ActionRiskTier.LOW_RISK,
        description="Synthetic re-verification probe",
        handler=SyntheticReverificationPlaybook,
    )
    return ActionExecutionService(registry=registry)


def test_idempotent_duplicate_request_returns_recorded_journal(execution_service):
    action = OperationalAction(
        action_id="ACT-IDEMP-01",
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        state=ActionState.APPROVED,
        idempotency_key="UNIQUE-IDEMP-KEY-9999",
    )

    # First execution: completes successfully
    res1 = execution_service.execute_action(action)
    assert res1.state == ActionState.COMPLETED

    # Duplicate request with same idempotency key
    action_duplicate = OperationalAction(
        action_id="ACT-IDEMP-02",  # Different action ID
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        state=ActionState.APPROVED,
        idempotency_key="UNIQUE-IDEMP-KEY-9999",  # Exact same idempotency key
    )
    res2 = execution_service.execute_action(action_duplicate)
    # Returns existing completed record without re-executing
    assert res2.state == ActionState.COMPLETED
    assert res2.action_id == "ACT-IDEMP-01"


def test_execution_timeout_safely_stopped_and_escalated(execution_service):
    # Create an action with 0.001s timeout
    action = OperationalAction(
        action_id="ACT-TIMEOUT-01",
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        state=ActionState.APPROVED,
        timeout_seconds=0.001,  # Short timeout to trigger TIMED_OUT
        parameters={"simulate_sleep": 0.01},
    )
    res = execution_service.execute_action(action)
    assert res.state in (ActionState.TIMED_OUT, ActionState.ROLLED_BACK)
    assert any("TIMED_OUT" in log for log in res.execution_log)
    assert "timeout limit" in res.execution_log[-2]


def test_dead_man_circuit_breaker_trips_after_failures(execution_service):
    # Simulate 3 consecutive failures
    assert execution_service.circuit_breaker.is_tripped is False

    for i in range(3):
        failing_action = OperationalAction(
            action_id=f"ACT-FAIL-{i}",
            playbook_name="synthetic_reverify",
            playbook_version="1.0.0",
            target_entity=f"voice_trunk::target_{i}",
            risk_tier=ActionRiskTier.LOW_RISK,
            alert_id="ALT-1001",
            incident_id="INC-2001",
            hypothesis_id="HYP-3001",
            state=ActionState.APPROVED,
            parameters={"target_extension": "9999_UNALLOWLISTED"},  # Preconditions fail
        )
        execution_service.execute_action(failing_action)

    # Circuit breaker must be tripped!
    assert execution_service.circuit_breaker.is_tripped is True

    # Subsequent valid actions must be BLOCKED by circuit breaker
    valid_action = OperationalAction(
        action_id="ACT-VALID-BLOCKED",
        playbook_name="synthetic_reverify",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.LOW_RISK,
        alert_id="ALT-1001",
        incident_id="INC-2001",
        hypothesis_id="HYP-3001",
        state=ActionState.APPROVED,
        parameters={"target_extension": "1001"},
    )
    res = execution_service.execute_action(valid_action)
    assert res.state == ActionState.BLOCKED
    assert "Dead-Man Circuit Breaker is TRIPPED" in res.execution_log[-1]
