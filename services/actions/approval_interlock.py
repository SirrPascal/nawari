"""Approval & Authorisation Engine for Nawari Controlled Operations (Workstream 12B).

Enforces Role-Based Access Control (RBAC), parameter-bound cryptographic signatures,
single-use nonces to prevent replay, and strict Two-Person Rules requiring distinct
authenticated identities for high-risk mutations.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from services.actions.action_framework import ActionRiskTier, ActionState, OperationalAction


class OperatorRole(str, Enum):
    NOC_OPERATOR = "NOC_OPERATOR"
    NOC_LEAD = "NOC_LEAD"
    TELECOM_ENGINEER = "TELECOM_ENGINEER"
    NETWORK_ENGINEER = "NETWORK_ENGINEER"
    NOC_MANAGER = "NOC_MANAGER"
    CHIEF_INFORMATION_OFFICER = "CHIEF_INFORMATION_OFFICER"


@dataclass
class ApprovalToken:
    """Cryptographically signed, parameter-bound, single-use operational approval token."""

    token_id: str
    action_id: str
    incident_id: str
    playbook_name: str
    playbook_version: str
    target_entity: str
    parameters_hash: str
    operator_id: str
    role: OperatorRole
    nonce: str
    signature: str
    created_at: float
    expires_at: float
    is_revoked: bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ApprovalInterlockEngine:
    """Governs cryptographic approval tokens, single-use replay protection, and Two-Person Rules."""

    DEFAULT_VALIDITY_SECONDS: float = 900.0  # 15 minutes expiration window

    def __init__(self, hmac_secret: str = "nawari-ops-auth-secret-key-2026"):
        self.secret = hmac_secret.encode("utf-8")
        self._used_token_ids: set[str] = set()
        self._used_nonces: set[str] = set()
        self._revoked_action_ids: set[str] = set()

    def _generate_signature(
        self,
        action_id: str,
        incident_id: str,
        playbook_name: str,
        playbook_version: str,
        target_entity: str,
        parameters_hash: str,
        operator_id: str,
        role: str,
        nonce: str,
        expires_at: float,
    ) -> str:
        msg = f"{action_id}:{incident_id}:{playbook_name}:{playbook_version}:{target_entity}:{parameters_hash}:{operator_id}:{role}:{nonce}:{expires_at}".encode("utf-8")
        return hmac.new(self.secret, msg, hashlib.sha256).hexdigest()

    def issue_token(
        self,
        action: OperationalAction,
        operator_id: str,
        role: OperatorRole,
        validity_seconds: float = DEFAULT_VALIDITY_SECONDS,
    ) -> ApprovalToken:
        """Issues an HMAC-signed approval token bound to exact action parameters and single-use nonce."""
        now = time.time()
        expires = now + validity_seconds
        nonce = uuid.uuid4().hex
        token_id = f"TOK-{uuid.uuid4().hex[:8].upper()}"

        sig = self._generate_signature(
            action_id=action.action_id,
            incident_id=action.incident_id,
            playbook_name=action.playbook_name,
            playbook_version=action.playbook_version,
            target_entity=action.target_entity,
            parameters_hash=action.parameters_hash,
            operator_id=operator_id,
            role=role.value,
            nonce=nonce,
            expires_at=expires,
        )

        return ApprovalToken(
            token_id=token_id,
            action_id=action.action_id,
            incident_id=action.incident_id,
            playbook_name=action.playbook_name,
            playbook_version=action.playbook_version,
            target_entity=action.target_entity,
            parameters_hash=action.parameters_hash,
            operator_id=operator_id,
            role=role,
            nonce=nonce,
            signature=sig,
            created_at=now,
            expires_at=expires,
        )

    def revoke_action_tokens(self, action_id: str, reason: str = "") -> None:
        """Revokes all tokens associated with an action (e.g. when incident or parameters mutate)."""
        self._revoked_action_ids.add(action_id)

    def verify_token(self, token: ApprovalToken, action: OperationalAction) -> tuple[bool, str]:
        """Validates token authenticity, single-use, parameter binding, and expiration."""
        # 1. Action revocation check
        if action.action_id in self._revoked_action_ids or token.is_revoked:
            return False, "TOKEN_REVOKED"

        # 2. Replay Prevention: check if token or nonce has already been consumed
        if token.token_id in self._used_token_ids or token.nonce in self._used_nonces:
            return False, "REPLAYED_APPROVAL_TOKEN: token or nonce has already been consumed"

        # 3. Expiration Check
        if token.is_expired:
            return False, "EXPIRED_APPROVAL_TOKEN: token exceeded validity window"

        # 4. Context & Parameter Binding Checks
        if token.action_id != action.action_id:
            return False, "TOKEN_ACTION_MISMATCH"
        if token.incident_id != action.incident_id:
            return False, "TOKEN_INCIDENT_MISMATCH"
        if token.playbook_name != action.playbook_name:
            return False, "TOKEN_PLAYBOOK_MISMATCH"
        if token.playbook_version != action.playbook_version:
            return False, "TOKEN_VERSION_MISMATCH"
        if token.target_entity != action.target_entity:
            return False, "TOKEN_TARGET_MISMATCH"
        if token.parameters_hash != action.parameters_hash:
            return False, "MODIFIED_ACTION_PARAMETERS: parameters were altered after token issuance"

        # 5. Cryptographic HMAC Signature Verification
        expected_sig = self._generate_signature(
            action_id=token.action_id,
            incident_id=token.incident_id,
            playbook_name=token.playbook_name,
            playbook_version=token.playbook_version,
            target_entity=token.target_entity,
            parameters_hash=token.parameters_hash,
            operator_id=token.operator_id,
            role=token.role.value,
            nonce=token.nonce,
            expires_at=token.expires_at,
        )
        if not hmac.compare_digest(expected_sig, token.signature):
            return False, "INVALID_TOKEN_SIGNATURE"

        return True, "TOKEN_VALID"

    def authorize_action(self, action: OperationalAction, token: ApprovalToken) -> tuple[bool, str]:
        """Evaluates token validity, single-use consumption, RBAC, and Two-Person Rules."""
        is_valid, msg = self.verify_token(token, action)
        if not is_valid:
            action.transition_to(ActionState.REJECTED, f"Authorization failed: {msg}")
            return False, msg

        # Role-Based Permission & Separation of Duties Check
        if action.risk_tier == ActionRiskTier.LOW_RISK:
            self._consume_token(token)
            action.approver_ids.append(token.operator_id)
            action.transition_to(ActionState.APPROVED, f"Approved by {token.operator_id} ({token.role.value})")
            return True, "AUTHORIZED"

        elif action.risk_tier == ActionRiskTier.MODERATE_RISK:
            permitted_roles = {
                OperatorRole.NOC_LEAD,
                OperatorRole.TELECOM_ENGINEER,
                OperatorRole.NETWORK_ENGINEER,
                OperatorRole.NOC_MANAGER,
                OperatorRole.CHIEF_INFORMATION_OFFICER,
            }
            if token.role not in permitted_roles:
                return False, f"ROLE_UNAUTHORIZED_FOR_MODERATE_RISK: requires NOC_LEAD or higher, got {token.role.value}"

            self._consume_token(token)
            action.approver_ids.append(token.operator_id)
            action.transition_to(ActionState.APPROVED, f"Approved by {token.operator_id} ({token.role.value})")
            return True, "AUTHORIZED"

        elif action.risk_tier == ActionRiskTier.HIGH_RISK:
            # High-risk requires Two-Person Rule: Proposer cannot approve own mutation!
            if token.operator_id == action.proposer_id:
                return False, "TWO_PERSON_RULE_VIOLATION: proposer cannot approve own high-risk mutation"

            # Check if this operator has already approved this action (same operator approves twice rejected!)
            if token.operator_id in action.approver_ids:
                return False, "SAME_OPERATOR_APPROVES_TWICE: high-risk action requires two distinct authenticated identities"

            permitted_roles = {
                OperatorRole.NOC_MANAGER,
                OperatorRole.TELECOM_ENGINEER,
                OperatorRole.CHIEF_INFORMATION_OFFICER,
            }
            if token.role not in permitted_roles:
                return False, f"ROLE_UNAUTHORIZED_FOR_HIGH_RISK: requires NOC_MANAGER or Telecom Head, got {token.role.value}"

            self._consume_token(token)
            action.approver_ids.append(token.operator_id)

            # High-Risk requires 2 distinct approvers (or Proposer + Approver where Proposer != Approver)
            # If 1 valid distinct approver is registered:
            action.transition_to(
                ActionState.APPROVED,
                f"Two-Person Rule satisfied: Proposed by {action.proposer_id}, Approved by {token.operator_id} ({token.role.value})",
            )
            return True, "AUTHORIZED"

        return False, "UNKNOWN_RISK_TIER"

    def _consume_token(self, token: ApprovalToken) -> None:
        """Marks token and nonce as permanently consumed to prevent replay."""
        self._used_token_ids.add(token.token_id)
        self._used_nonces.add(token.nonce)
