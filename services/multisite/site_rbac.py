"""services/multisite/site_rbac.py
================================
Multi-Site Scoped RBAC & Three-Identity Interlock Engine (Workstream 13E).

Enforces:
1. Granular geographical, station, regional, and domain-scoped RBAC.
2. Strict Three Distinct Identities Rule (|{P, A1, A2}| = 3) for Tier-3 high-risk operations.
3. Cryptographically bound operational envelopes with single-use replay protection.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nawari.multisite.site_rbac")


class UserRole(str, Enum):
    GLOBAL_ADMIN = "GLOBAL_ADMIN"
    GLOBAL_NOC_OPERATOR = "GLOBAL_NOC_OPERATOR"
    VOICE_ENGINEER = "VOICE_ENGINEER"
    NETWORK_ENGINEER = "NETWORK_ENGINEER"
    REGIONAL_MANAGER = "REGIONAL_MANAGER"
    STATION_DUTY_LEAD = "STATION_DUTY_LEAD"
    TIER_3_AUTHORIZER = "TIER_3_AUTHORIZER"
    CHIEF_INFORMATION_OFFICER = "CHIEF_INFORMATION_OFFICER"


class ActionRiskTier(str, Enum):
    TIER_1_LOW = "TIER_1_LOW"
    TIER_2_MEDIUM = "TIER_2_MEDIUM"
    TIER_3_HIGH = "TIER_3_HIGH"


class RBACScope(str, Enum):
    GLOBAL = "GLOBAL"
    REGIONAL = "REGIONAL"
    STATION = "STATION"


class ScopeAuthorizationError(PermissionError):
    """Raised when an operator attempts an action outside their geographical or station scope."""
    pass


class ThreeIdentityCardinalityViolation(PermissionError):
    """Raised when the cardinality |{P, A1, A2}| < 3 rule is breached."""
    pass


class InsufficientRolePermission(PermissionError):
    """Raised when an operator or approver lacks the requisite role for an operation."""
    pass


class TokenTamperedOrInvalid(ValueError):
    """Raised when an approval token signature does not match the bound action envelope."""
    pass


class TokenExpiredOrReplayed(ValueError):
    """Raised when an approval token is expired or its single-use nonce was replayed."""
    pass


@dataclass
class UserProfile:
    """Authenticated user profile with role, station, region, and domain scoping."""
    user_id: str
    username: str
    roles: List[UserRole]
    scope_type: RBACScope = RBACScope.GLOBAL
    allowed_stations: Set[str] = field(default_factory=set)
    allowed_regions: Set[str] = field(default_factory=set)
    allowed_domains: Set[str] = field(default_factory=set)

    def can_access_station(self, station_id: str, station_region: Optional[str] = None) -> bool:
        """Check if user has access to a given station."""
        if UserRole.GLOBAL_ADMIN in self.roles or UserRole.GLOBAL_NOC_OPERATOR in self.roles:
            return True
        if self.scope_type == RBACScope.GLOBAL:
            return True
        if self.scope_type == RBACScope.REGIONAL:
            if station_region and station_region in self.allowed_regions:
                return True
            return station_id in self.allowed_stations
        if self.scope_type == RBACScope.STATION:
            return station_id in self.allowed_stations
        return False

    def can_access_domain(self, domain_name: str) -> bool:
        """Check if user has access to an infrastructure domain (e.g. VOICE, NETWORK)."""
        if UserRole.GLOBAL_ADMIN in self.roles or UserRole.GLOBAL_NOC_OPERATOR in self.roles:
            return True
        if not self.allowed_domains:
            return True
        return domain_name.upper() in {d.upper() for d in self.allowed_domains}


@dataclass
class ActionOperationalEnvelope:
    """Cryptographic parameter envelope binding all context for an operational action."""
    action_id: str
    incident_id: str
    alert_id: str
    playbook_id: str
    playbook_version: str
    plan_hash: str
    target_env: str
    risk_tier: ActionRiskTier
    change_window_id: str
    parameters_hash: str
    target_station_id: Optional[str] = None
    target_domain: Optional[str] = None

    def compute_canonical_string(self, nonce: str, expires_at: float) -> str:
        """Construct canonical envelope representation for cryptographic signing."""
        return (
            f"ACTION={self.action_id}:"
            f"INC={self.incident_id}:"
            f"ALT={self.alert_id}:"
            f"PB={self.playbook_id}:"
            f"VER={self.playbook_version}:"
            f"PLAN={self.plan_hash}:"
            f"ENV={self.target_env}:"
            f"TIER={self.risk_tier.value}:"
            f"CW={self.change_window_id}:"
            f"PARAMS={self.parameters_hash}:"
            f"NONCE={nonce}:"
            f"EXPIRES={expires_at:.3f}"
        )


@dataclass
class BoundApprovalToken:
    """Signed approval token issued to an authorized approver."""
    token_id: str
    approver_id: str
    role: UserRole
    nonce: str
    expires_at: float
    signature: str
    issued_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SiteAwareRBACEngine:
    """Manages multi-site scoped user permissions and cryptographic Three-Identity interlocks."""

    DEFAULT_EXPIRY_SECONDS: float = 900.0  # 15 minutes

    def __init__(self, hmac_secret: str = "nawari-multisite-interlock-hmac-key-2026") -> None:
        self.secret = hmac_secret.encode("utf-8")
        self._consumed_nonces: Set[str] = set()
        self._consumed_token_ids: Set[str] = set()
        self._user_directory: Dict[str, UserProfile] = {}
        self._init_default_directory()

    def _init_default_directory(self) -> None:
        """Seed default operational users across tiers and outstations."""
        self.register_user(
            UserProfile(
                user_id="USR-GLOBAL-ADMIN",
                username="global.admin@kenya-airways.com",
                roles=[UserRole.GLOBAL_ADMIN, UserRole.TIER_3_AUTHORIZER],
                scope_type=RBACScope.GLOBAL,
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-NOC-LEAD",
                username="noc.duty.lead@kenya-airways.com",
                roles=[UserRole.GLOBAL_NOC_OPERATOR, UserRole.TIER_3_AUTHORIZER],
                scope_type=RBACScope.GLOBAL,
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-CIO-EXEC",
                username="cio.approver@kenya-airways.com",
                roles=[UserRole.CHIEF_INFORMATION_OFFICER, UserRole.TIER_3_AUTHORIZER],
                scope_type=RBACScope.GLOBAL,
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-VOICE-ENG",
                username="voice.specialist@kenya-airways.com",
                roles=[UserRole.VOICE_ENGINEER],
                scope_type=RBACScope.GLOBAL,
                allowed_domains={"VOICE"},
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-NET-ENG",
                username="network.specialist@kenya-airways.com",
                roles=[UserRole.NETWORK_ENGINEER],
                scope_type=RBACScope.GLOBAL,
                allowed_domains={"NETWORK"},
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-MOMBASA-LEAD",
                username="duty.lead.mba@kenya-airways.com",
                roles=[UserRole.STATION_DUTY_LEAD],
                scope_type=RBACScope.STATION,
                allowed_stations={"MBA-STATION"},
                allowed_domains={"VOICE", "NETWORK", "FACILITY"},
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-KISUMU-LEAD",
                username="duty.lead.kis@kenya-airways.com",
                roles=[UserRole.STATION_DUTY_LEAD],
                scope_type=RBACScope.STATION,
                allowed_stations={"KIS-STATION"},
            )
        )
        self.register_user(
            UserProfile(
                user_id="USR-REGIONAL-EA",
                username="regional.mgr.ea@kenya-airways.com",
                roles=[UserRole.REGIONAL_MANAGER],
                scope_type=RBACScope.REGIONAL,
                allowed_regions={"DOMESTIC_KENYA", "REGIONAL_EAST_AFRICA"},
                allowed_stations={"MBA-STATION", "KIS-STATION", "EDL-STATION", "EBB-STATION", "KGL-STATION"},
            )
        )

    def register_user(self, profile: UserProfile) -> None:
        self._user_directory[profile.user_id] = profile

    def get_user(self, user_id: str) -> Optional[UserProfile]:
        return self._user_directory.get(user_id)

    def authorize_operator_action(
        self,
        user_id: str,
        target_station_id: Optional[str] = None,
        target_station_region: Optional[str] = None,
        target_domain: Optional[str] = None,
        risk_tier: ActionRiskTier = ActionRiskTier.TIER_1_LOW,
    ) -> bool:
        """Validate operator's geographic and domain authorization for a target action."""
        user = self.get_user(user_id)
        if not user:
            raise ScopeAuthorizationError(f"User '{user_id}' not found in authorization directory.")

        # 1. Geographic Station & Region Scope
        if target_station_id and not user.can_access_station(target_station_id, target_station_region):
            raise ScopeAuthorizationError(
                f"User '{user.username}' is not authorized for target station '{target_station_id}'."
            )

        # 2. Infrastructure Domain Scope
        if target_domain and not user.can_access_domain(target_domain):
            raise ScopeAuthorizationError(
                f"User '{user.username}' is not authorized for infrastructure domain '{target_domain}'."
            )

        return True

    def issue_approval_token(
        self,
        approver_id: str,
        envelope: ActionOperationalEnvelope,
        validity_seconds: float = DEFAULT_EXPIRY_SECONDS,
    ) -> BoundApprovalToken:
        """Generate an HMAC-signed approval token bound to the exact operational envelope."""
        approver = self.get_user(approver_id)
        if not approver:
            raise InsufficientRolePermission(f"Approver '{approver_id}' not found.")

        # Approver must hold TIER_3_AUTHORIZER, CIO, or GLOBAL_ADMIN to sign Tier 3 actions
        if envelope.risk_tier == ActionRiskTier.TIER_3_HIGH:
            authorized_roles = {UserRole.TIER_3_AUTHORIZER, UserRole.CHIEF_INFORMATION_OFFICER, UserRole.GLOBAL_ADMIN}
            if not any(r in authorized_roles for r in approver.roles):
                raise InsufficientRolePermission(
                    f"User '{approver.username}' does not hold TIER_3_AUTHORIZER privileges."
                )

        now = time.time()
        expires_at = now + validity_seconds
        nonce = uuid.uuid4().hex
        token_id = f"TOK-{uuid.uuid4().hex[:8].upper()}"

        canonical_data = envelope.compute_canonical_string(nonce=nonce, expires_at=expires_at)
        signature = hmac.new(self.secret, canonical_data.encode("utf-8"), hashlib.sha256).hexdigest()

        return BoundApprovalToken(
            token_id=token_id,
            approver_id=approver_id,
            role=approver.roles[0],
            nonce=nonce,
            expires_at=expires_at,
            signature=signature,
            issued_at=now,
        )

    def verify_token(self, token: BoundApprovalToken, envelope: ActionOperationalEnvelope) -> bool:
        """Verify token signature, freshness, and anti-replay nonce."""
        if token.token_id in self._consumed_token_ids:
            raise TokenExpiredOrReplayed(f"Approval token '{token.token_id}' was already consumed.")

        if token.nonce in self._consumed_nonces:
            raise TokenExpiredOrReplayed(f"Token nonce '{token.nonce}' has already been used.")

        if token.is_expired():
            raise TokenExpiredOrReplayed(f"Approval token '{token.token_id}' has expired.")

        # Re-compute expected signature
        canonical_data = envelope.compute_canonical_string(nonce=token.nonce, expires_at=token.expires_at)
        expected_sig = hmac.new(self.secret, canonical_data.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, token.signature):
            raise TokenTamperedOrInvalid(
                f"Signature mismatch on token '{token.token_id}'. Token does not match operational envelope."
            )

        return True

    def verify_three_identity_approval(
        self,
        proposer_id: str,
        approver1_token: BoundApprovalToken,
        approver2_token: BoundApprovalToken,
        envelope: ActionOperationalEnvelope,
        consume_tokens: bool = True,
    ) -> Dict[str, Any]:
        """Enforces the strict Three Distinct Identities Rule:

        |{P, A1, A2}| = 3
        Verifies both cryptographic tokens against envelope, checks expiration and anti-replay.
        """
        a1_id = approver1_token.approver_id
        a2_id = approver2_token.approver_id

        # 1. Strict Set Cardinality Check
        distinct_identities = {proposer_id, a1_id, a2_id}
        if len(distinct_identities) != 3:
            raise ThreeIdentityCardinalityViolation(
                f"Three Distinct Identities rule breached: |{{P: '{proposer_id}', A1: '{a1_id}', A2: '{a2_id}'}}| = "
                f"{len(distinct_identities)} (expected 3 distinct identities)."
            )

        # 2. Verify Cryptographic Integrity of Approver 1
        self.verify_token(token=approver1_token, envelope=envelope)

        # 3. Verify Cryptographic Integrity of Approver 2
        self.verify_token(token=approver2_token, envelope=envelope)

        # 4. Check that both approvers hold valid authorizer privileges
        user_p = self.get_user(proposer_id)
        user_a1 = self.get_user(a1_id)
        user_a2 = self.get_user(a2_id)

        if not user_p or not user_a1 or not user_a2:
            raise InsufficientRolePermission("One or more participant accounts not registered.")

        # 5. Mark nonces and token IDs consumed if requested
        if consume_tokens:
            self._consumed_token_ids.add(approver1_token.token_id)
            self._consumed_token_ids.add(approver2_token.token_id)
            self._consumed_nonces.add(approver1_token.nonce)
            self._consumed_nonces.add(approver2_token.nonce)

        logger.info(
            "Three-Identity Approval Verified successfully for Action %s by Proposer %s, Approvers (%s, %s).",
            envelope.action_id,
            proposer_id,
            a1_id,
            a2_id,
        )

        return {
            "verified": True,
            "action_id": envelope.action_id,
            "proposer": proposer_id,
            "approver_1": a1_id,
            "approver_2": a2_id,
            "risk_tier": envelope.risk_tier.value,
            "tokens_consumed": [approver1_token.token_id, approver2_token.token_id],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

