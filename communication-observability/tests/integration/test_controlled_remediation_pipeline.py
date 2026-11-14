"""Integration test for Nawari Controlled Remediation Pipeline (Workstream 12H).

Validates end-to-end operational journey:
Alert -> Incident -> Phase 11 Diagnosis -> Action Proposal -> Policy Gating ->
Two-Person Authorization -> Execution Engine -> Independent Verification ->
Rollback & Escalation -> Immutable Chained Audit Trail.
"""

import time
import pytest
from services.actions.action_framework import (
    ActionRegistry,
    ActionRiskTier,
    ActionState,
    AutomationPolicyEngine,
    OperationalAction,
)
from services.actions.approval_interlock import (
    ApprovalInterlockEngine,
    OperatorRole,
)
from services.actions.audit_chain import OperationalAuditLedger
from services.actions.execution_engine import ActionExecutionService
from services.actions.integrations import ITSMIntegrationAdapter
from services.actions.playbooks.carrier_failover import CarrierFailoverPlaybook


def test_end_to_end_controlled_remediation_success():
    # 1. Initialize Pipeline Services
    registry = ActionRegistry()
    registry.register(
        name="carrier_failover",
        version="1.0.0",
        risk_tier=ActionRiskTier.HIGH_RISK,
        description="Outbound carrier trunk failover",
        handler=CarrierFailoverPlaybook,
        is_recommendation_only_default=True,
    )
    exec_service = ActionExecutionService(registry=registry)
    approval_engine = ApprovalInterlockEngine(hmac_secret="kq-prod-remediation-secret")
    itsm = ITSMIntegrationAdapter()
    audit_ledger = OperationalAuditLedger()

    # 2. Step 1: Alert & Incident Creation
    alert_id = "ALT-VOICE-SAF-991"
    incident = itsm.create_incident(
        alert_id=alert_id,
        title="Critical Telco Trunk PDD & MOS Degradation on Safaricom PRI",
        severity="P1_CRITICAL",
        target_entity="voice_trunk::primary_safaricom",
    )
    assert incident.state == "OPEN"

    # 3. Step 2: Phase 11 Diagnosis & Action Proposal
    hypothesis_id = "HYP_CARRIER_TRUNK_CONGESTION"
    action = OperationalAction(
        action_id="ACT-REM-1001",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id=alert_id,
        incident_id=incident.incident_id,
        hypothesis_id=hypothesis_id,
        proposer_id="telecom_engineer_alice",
        parameters={
            "active_trunk": "primary_safaricom",
            "backup_trunk": "secondary_airtel",
            "primary_trunk_degraded": True,
            "secondary_trunk_reachable": True,
            "post_verification_synthetic_call_passed": True,
            "post_failover_mos": 4.10,
        },
    )

    # 4. Step 3: Policy Gating Evaluation
    is_permitted, policy_msg = AutomationPolicyEngine.evaluate_policy(
        action=action,
        is_in_change_window=True,
        blast_radius_nodes=2,
    )
    assert is_permitted is True
    assert policy_msg == "APPROVAL_REQUIRED"
    assert action.state == ActionState.PENDING_APPROVAL

    audit_ledger.record_event(
        action_id=action.action_id,
        incident_id=action.incident_id,
        operator_id=action.proposer_id,
        event_type="ACTION_PROPOSED",
        payload=action.to_dict(),
    )

    # 5. Step 4: Two-Person Rule Authorization Token
    # Proposer Alice cannot approve; NOC Manager Bob approves
    approval_token = approval_engine.issue_token(
        action=action,
        operator_id="noc_manager_bob",
        role=OperatorRole.NOC_MANAGER,
        validity_seconds=600.0,
    )
    is_auth, auth_msg = approval_engine.authorize_action(action, approval_token)
    assert is_auth is True
    assert auth_msg == "AUTHORIZED"
    assert action.state == ActionState.APPROVED
    assert "noc_manager_bob" in action.approver_ids

    audit_ledger.record_event(
        action_id=action.action_id,
        incident_id=action.incident_id,
        operator_id="noc_manager_bob",
        event_type="ACTION_APPROVED",
        payload={"token_id": approval_token.token_id, "role": "NOC_MANAGER"},
    )
    itsm.append_work_note(incident.incident_id, f"Action {action.action_id} authorized by noc_manager_bob")

    # 6. Step 5: Action Execution & Independent Verification
    completed_action = exec_service.execute_action(action)
    assert completed_action.state == ActionState.COMPLETED
    assert completed_action.verification_evidence["postcondition_status"] is True
    assert "INDEPENDENT_SERVICE_RESTORATION_VERIFIED" in completed_action.verification_evidence["verification_details"]

    audit_ledger.record_event(
        action_id=action.action_id,
        incident_id=action.incident_id,
        operator_id=exec_service.service_id,
        event_type="ACTION_COMPLETED_VERIFIED",
        payload=completed_action.verification_evidence,
    )

    # 7. Step 6: Incident Resolution
    itsm.resolve_incident(
        incident_id=incident.incident_id,
        resolution_code="RESOLVED_VIA_CONTROLLED_CARRIER_FAILOVER",
    )
    assert incident.state == "RESOLVED"

    # 8. Step 7: Cryptographic Audit Chain Integrity Verification
    is_chain_valid, chain_msg = audit_ledger.verify_integrity()
    assert is_chain_valid is True
    assert chain_msg == "CHAIN_INTEGRITY_VERIFIED"


def test_post_action_verification_failure_triggers_rollback_and_escalation():
    registry = ActionRegistry()
    registry.register(
        name="carrier_failover",
        version="1.0.0",
        risk_tier=ActionRiskTier.HIGH_RISK,
        description="Outbound carrier trunk failover",
        handler=CarrierFailoverPlaybook,
    )
    exec_service = ActionExecutionService(registry=registry)
    itsm = ITSMIntegrationAdapter()

    incident = itsm.create_incident(
        alert_id="ALT-002",
        title="Safaricom signaling drop",
        severity="P1",
        target_entity="voice_trunk::primary_safaricom",
    )

    # Context where independent post-action verification FAILS
    # (e.g. secondary trunk synthetic test call fails)
    action = OperationalAction(
        action_id="ACT-FAIL-VERIFY",
        playbook_name="carrier_failover",
        playbook_version="1.0.0",
        target_entity="voice_trunk::primary_safaricom",
        risk_tier=ActionRiskTier.HIGH_RISK,
        alert_id="ALT-002",
        incident_id=incident.incident_id,
        hypothesis_id="HYP-3001",
        state=ActionState.APPROVED,
        parameters={
            "primary_trunk_degraded": True,
            "secondary_trunk_reachable": True,
            "post_verification_synthetic_call_passed": False,  # Verification fails!
            "primary_trunk_stabilized": True,
            "active_emergency_calls": 0,
        },
    )

    result_action = exec_service.execute_action(action)

    # Post-action verification failure must trigger safe rollback
    assert result_action.state == ActionState.ROLLED_BACK
    assert "Post-action verification failed" in result_action.execution_log[-2]
    assert "Operational changes reverted cleanly" in result_action.execution_log[-1]

    # Incident remains OPEN! Exit code 0 is never sufficient; failure to restore leaves incident open.
    itsm.append_work_note(incident.incident_id, "Remediation verification failed; changes rolled back; escalating to Tier-3")
    assert incident.state == "OPEN"

