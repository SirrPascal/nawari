"""tests/unit/test_multisite_site_rbac.py
=======================================
Unit tests for Multi-Site Scoped RBAC and Three-Identity Interlocks (Workstream 13E).
"""

import time
import pytest
from services.multisite.site_rbac import (
    ActionOperationalEnvelope,
    ActionRiskTier,
    InsufficientRolePermission,
    RBACScope,
    ScopeAuthorizationError,
    SiteAwareRBACEngine,
    ThreeIdentityCardinalityViolation,
    TokenExpiredOrReplayed,
    TokenTamperedOrInvalid,
    UserProfile,
    UserRole,
)


@pytest.fixture
def rbac_engine():
    return SiteAwareRBACEngine(is_simulation_mode=True)


@pytest.fixture
def sample_envelope():
    return ActionOperationalEnvelope(
        action_id="ACT-FAILOVER-TRUNK-01",
        incident_id="INC-MBA-VOICE-01",
        alert_id="ALT-SIP-TRUNK-DOWN",
        playbook_id="PB-VOICE-TRUNK-FAILOVER",
        playbook_version="1.2.0",
        plan_hash="sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
        target_env="STAGING",
        risk_tier=ActionRiskTier.TIER_3_HIGH,
        change_window_id="CW-2026-11-08-01",
        parameters_hash="sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        target_station_id="MBA-STATION",
        target_domain="VOICE",
    )


def test_station_and_regional_geographic_scoping(rbac_engine):
    # 1. Mombasa station lead can access MBA-STATION
    assert rbac_engine.authorize_operator_action(
        user_id="USR-MOMBASA-LEAD",
        target_station_id="MBA-STATION",
        target_domain="VOICE",
    ) is True

    # 2. Mombasa station lead is strictly DENIED access to Kisumu station
    with pytest.raises(ScopeAuthorizationError) as exc_info:
        rbac_engine.authorize_operator_action(
            user_id="USR-MOMBASA-LEAD",
            target_station_id="KIS-STATION",
        )
    assert "not authorized for target station 'KIS-STATION'" in str(exc_info.value)

    # 3. Regional manager East Africa can access MBA and KIS
    assert rbac_engine.authorize_operator_action(
        user_id="USR-REGIONAL-EA",
        target_station_id="MBA-STATION",
    ) is True
    assert rbac_engine.authorize_operator_action(
        user_id="USR-REGIONAL-EA",
        target_station_id="KIS-STATION",
    ) is True

    # Regional manager East Africa cannot access London Heathrow
    with pytest.raises(ScopeAuthorizationError):
        rbac_engine.authorize_operator_action(
            user_id="USR-REGIONAL-EA",
            target_station_id="LHR-STATION",
        )

    # 4. Global Admin has unrestricted access everywhere
    assert rbac_engine.authorize_operator_action(
        user_id="USR-GLOBAL-ADMIN",
        target_station_id="LHR-STATION",
    ) is True


def test_domain_specialization_scoping(rbac_engine):
    # Voice specialist can operate in VOICE domain
    assert rbac_engine.authorize_operator_action(
        user_id="USR-VOICE-ENG",
        target_domain="VOICE",
    ) is True

    # Voice specialist CANNOT touch NETWORK infrastructure
    with pytest.raises(ScopeAuthorizationError) as exc_info:
        rbac_engine.authorize_operator_action(
            user_id="USR-VOICE-ENG",
            target_domain="NETWORK",
        )
    assert "not authorized for infrastructure domain 'NETWORK'" in str(exc_info.value)


def test_role_escalation_and_revocation(rbac_engine):
    # 1. Read-only auditor cannot perform mutating action
    with pytest.raises(InsufficientRolePermission) as exc:
        rbac_engine.authorize_operator_action(
            user_id="USR-READONLY-AUDIT",
            target_station_id="JKIA-HUB",
            risk_tier=ActionRiskTier.TIER_1_LOW,
        )
    assert "Read-only auditor" in str(exc.value)

    # 2. Revoked user cannot perform any actions
    assert rbac_engine.revoke_user("USR-VOICE-ENG") is True
    with pytest.raises(InsufficientRolePermission) as exc_rev:
        rbac_engine.authorize_operator_action(
            user_id="USR-VOICE-ENG",
            target_domain="VOICE",
        )
    assert "account is REVOKED" in str(exc_rev.value)

    # 3. Unauthenticated / unknown user
    with pytest.raises(ScopeAuthorizationError) as exc_unauth:
        rbac_engine.authorize_operator_action(user_id="NONEXISTENT-OPERATOR")
    assert "not found" in str(exc_unauth.value)


def test_production_action_blocked_in_simulation_mode(rbac_engine, sample_envelope):
    with pytest.raises(PermissionError) as exc:
        rbac_engine.authorize_operator_action(
            user_id="USR-GLOBAL-ADMIN",
            target_station_id="MBA-STATION",
            target_env="PRODUCTION",  # Target env is production
        )
    assert "Production action blocked: system is running in simulation/staging mode" in str(exc.value)


def test_three_distinct_identities_cardinality_enforcement(rbac_engine, sample_envelope):
    token_a1 = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    token_a2 = rbac_engine.issue_approval_token("USR-CIO-EXEC", sample_envelope)

    # 1. Successful verification with 3 distinct accounts: Proposer, A1, A2
    proposer_id = "USR-NOC-LEAD"
    res = rbac_engine.verify_three_identity_approval(
        proposer_id=proposer_id,
        approver1_token=token_a1,
        approver2_token=token_a2,
        envelope=sample_envelope,
        consume_tokens=False,
    )
    assert res["verified"] is True
    assert res["proposer"] == "USR-NOC-LEAD"
    assert res["approver_1"] == "USR-GLOBAL-ADMIN"
    assert res["approver_2"] == "USR-CIO-EXEC"

    # 2. Violation: Proposer attempts to approve their own action (P == A1)
    with pytest.raises(ThreeIdentityCardinalityViolation) as exc_info:
        rbac_engine.verify_three_identity_approval(
            proposer_id="USR-GLOBAL-ADMIN",  # Same as approver 1
            approver1_token=token_a1,
            approver2_token=token_a2,
            envelope=sample_envelope,
        )
    assert "Three Distinct Identities rule breached" in str(exc_info.value)

    # 3. Violation: Same approver signs both tokens (A1 == A2)
    token_a1_dup = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    with pytest.raises(ThreeIdentityCardinalityViolation) as exc_info:
        rbac_engine.verify_three_identity_approval(
            proposer_id=proposer_id,
            approver1_token=token_a1,
            approver2_token=token_a1_dup,
            envelope=sample_envelope,
        )
    assert "Three Distinct Identities rule breached" in str(exc_info.value)


def test_cryptographic_envelope_tamper_detection(rbac_engine, sample_envelope):
    token = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)

    # Token verifies against original envelope
    assert rbac_engine.verify_token(token, sample_envelope) is True

    # Tampering: attacker changes risk_tier from TIER_3_HIGH to TIER_1_LOW
    tampered_envelope = ActionOperationalEnvelope(
        action_id=sample_envelope.action_id,
        incident_id=sample_envelope.incident_id,
        alert_id=sample_envelope.alert_id,
        playbook_id=sample_envelope.playbook_id,
        playbook_version=sample_envelope.playbook_version,
        plan_hash=sample_envelope.plan_hash,
        target_env=sample_envelope.target_env,
        risk_tier=ActionRiskTier.TIER_1_LOW,  # TAMPERED
        change_window_id=sample_envelope.change_window_id,
        parameters_hash=sample_envelope.parameters_hash,
    )
    with pytest.raises(TokenTamperedOrInvalid) as exc_info:
        rbac_engine.verify_token(token, tampered_envelope)
    assert "Signature mismatch" in str(exc_info.value)


def test_single_use_nonce_anti_replay_and_expiration(rbac_engine, sample_envelope):
    token_a1 = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    token_a2 = rbac_engine.issue_approval_token("USR-CIO-EXEC", sample_envelope)

    # First consumption succeeds
    rbac_engine.verify_three_identity_approval(
        proposer_id="USR-NOC-LEAD",
        approver1_token=token_a1,
        approver2_token=token_a2,
        envelope=sample_envelope,
        consume_tokens=True,
    )

    # Replay attempt: using consumed token must raise TokenExpiredOrReplayed
    with pytest.raises(TokenExpiredOrReplayed) as exc_info:
        rbac_engine.verify_three_identity_approval(
            proposer_id="USR-NOC-LEAD",
            approver1_token=token_a1,
            approver2_token=token_a2,
            envelope=sample_envelope,
        )
    assert "was already consumed" in str(exc_info.value)

    # Expiration test
    expired_token = rbac_engine.issue_approval_token(
        approver_id="USR-GLOBAL-ADMIN",
        envelope=sample_envelope,
        validity_seconds=-1.0,  # Already expired
    )
    with pytest.raises(TokenExpiredOrReplayed) as exc_info:
        rbac_engine.verify_token(expired_token, sample_envelope)
    assert "has expired" in str(exc_info.value)


def test_token_cancellation_and_revocation(rbac_engine, sample_envelope):
    """Verify that explicitly cancelled approval tokens are rejected immediately."""
    token = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    assert rbac_engine.verify_token(token, sample_envelope) is True

    # Cancel token
    rbac_engine.cancel_approval_token(token.token_id, reason="Emergency freeze invoked by CISO")
    assert rbac_engine.is_token_cancelled(token.token_id) is True

    with pytest.raises(TokenTamperedOrInvalid) as exc_info:
        rbac_engine.verify_token(token, sample_envelope)
    assert "was cancelled" in str(exc_info.value)
    assert "Emergency freeze invoked by CISO" in str(exc_info.value)


def test_hmac_secret_key_rotation_grace_period(sample_envelope):
    """Verify that during secret rotation, tokens signed with the old secret remain valid
    during grace period, but are rejected once the grace period expires.
    """
    engine = SiteAwareRBACEngine(hmac_secret="initial-secret-key-1", is_simulation_mode=True)
    token_old = engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    assert engine.verify_token(token_old, sample_envelope) is True

    # Rotate secret with 1-hour grace period
    engine.rotate_signing_secret(new_secret="new-rotated-secret-key-2", grace_period_seconds=3600.0)

    # Token signed with old key remains valid during grace period
    assert engine.verify_token(token_old, sample_envelope) is True

    # New token signed with new key is valid
    token_new = engine.issue_approval_token("USR-CIO-EXEC", sample_envelope)
    assert engine.verify_token(token_new, sample_envelope) is True

    # Expire grace period
    engine._previous_secret_expiry = time.time() - 10.0

    # Old token must now be rejected
    with pytest.raises(TokenTamperedOrInvalid) as exc_info:
        engine.verify_token(token_old, sample_envelope)
    assert "Signature mismatch" in str(exc_info.value)

    # New token remains valid
    assert engine.verify_token(token_new, sample_envelope) is True


def test_revoked_approver_token_rejected(rbac_engine, sample_envelope):
    """Verify that tokens issued to an approver who is subsequently revoked cannot be verified."""
    token = rbac_engine.issue_approval_token("USR-CIO-EXEC", sample_envelope)
    assert rbac_engine.verify_token(token, sample_envelope) is True

    # Revoke user
    rbac_engine.revoke_user("USR-CIO-EXEC")

    # Verifying token must fail due to account revocation
    with pytest.raises(InsufficientRolePermission) as exc_info:
        rbac_engine.verify_token(token, sample_envelope)
    assert "has been revoked" in str(exc_info.value)


def test_parameter_tampering_comprehensive(rbac_engine, sample_envelope):
    """Verify that altering any canonical parameter in the envelope invalidates token signature."""
    sample_envelope.target_entity_id = "SW-MBA-01"
    token = rbac_engine.issue_approval_token("USR-GLOBAL-ADMIN", sample_envelope)
    assert rbac_engine.verify_token(token, sample_envelope) is True

    # 1. Tampering target_entity_id
    tampered_entity = ActionOperationalEnvelope(
        action_id=sample_envelope.action_id,
        incident_id=sample_envelope.incident_id,
        alert_id=sample_envelope.alert_id,
        playbook_id=sample_envelope.playbook_id,
        playbook_version=sample_envelope.playbook_version,
        plan_hash=sample_envelope.plan_hash,
        target_env=sample_envelope.target_env,
        risk_tier=sample_envelope.risk_tier,
        change_window_id=sample_envelope.change_window_id,
        parameters_hash=sample_envelope.parameters_hash,
        target_entity_id="SW-MBA-02",  # TAMPERED
    )
    with pytest.raises(TokenTamperedOrInvalid):
        rbac_engine.verify_token(token, tampered_entity)

    # 2. Tampering change_window_id
    tampered_cw = ActionOperationalEnvelope(
        action_id=sample_envelope.action_id,
        incident_id=sample_envelope.incident_id,
        alert_id=sample_envelope.alert_id,
        playbook_id=sample_envelope.playbook_id,
        playbook_version=sample_envelope.playbook_version,
        plan_hash=sample_envelope.plan_hash,
        target_env=sample_envelope.target_env,
        risk_tier=sample_envelope.risk_tier,
        change_window_id="CW-TAMPERED-ID",  # TAMPERED
        parameters_hash=sample_envelope.parameters_hash,
        target_entity_id=sample_envelope.target_entity_id,
    )
    with pytest.raises(TokenTamperedOrInvalid):
        rbac_engine.verify_token(token, tampered_cw)

    # 3. Tampering target_env
    tampered_env = ActionOperationalEnvelope(
        action_id=sample_envelope.action_id,
        incident_id=sample_envelope.incident_id,
        alert_id=sample_envelope.alert_id,
        playbook_id=sample_envelope.playbook_id,
        playbook_version=sample_envelope.playbook_version,
        plan_hash=sample_envelope.plan_hash,
        target_env="PRODUCTION",  # TAMPERED
        risk_tier=sample_envelope.risk_tier,
        change_window_id=sample_envelope.change_window_id,
        parameters_hash=sample_envelope.parameters_hash,
        target_entity_id=sample_envelope.target_entity_id,
    )
    with pytest.raises(TokenTamperedOrInvalid):
        rbac_engine.verify_token(token, tampered_env)

    # 4. Tampering playbook_version
    tampered_ver = ActionOperationalEnvelope(
        action_id=sample_envelope.action_id,
        incident_id=sample_envelope.incident_id,
        alert_id=sample_envelope.alert_id,
        playbook_id=sample_envelope.playbook_id,
        playbook_version="9.9.9",  # TAMPERED
        plan_hash=sample_envelope.plan_hash,
        target_env=sample_envelope.target_env,
        risk_tier=sample_envelope.risk_tier,
        change_window_id=sample_envelope.change_window_id,
        parameters_hash=sample_envelope.parameters_hash,
        target_entity_id=sample_envelope.target_entity_id,
    )
    with pytest.raises(TokenTamperedOrInvalid):
        rbac_engine.verify_token(token, tampered_ver)
