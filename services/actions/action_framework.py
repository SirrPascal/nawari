"""Action Framework, Registry & Automation Policy Engine for Nawari (Workstream 12A).

Enforces canonical operational action contracts, typed risk tiers, state machines,
incident traceability links, and strict production-target deny rules.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ActionRiskTier(str, Enum):
    LOW_RISK = "LOW_RISK"            # Diagnostic probes, synthetic calls, telemetry sync (Automated)
    MODERATE_RISK = "MODERATE_RISK"  # Monitoring restart, probe tuning, endpoint self-repair (Single approval)
    HIGH_RISK = "HIGH_RISK"          # Route shift, interface toggle, carrier trunk failover (Two-person rule)


class ActionState(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"
    ESCALATED = "ESCALATED"


@dataclass
class OperationalAction:
    """Canonical operational action contract with full incident and evidence traceability."""

    action_id: str
    playbook_name: str
    playbook_version: str
    target_entity: str
    risk_tier: ActionRiskTier
    # End-to-End Alerting & Incident Traceability
    alert_id: str
    incident_id: str
    hypothesis_id: str
    state: ActionState = ActionState.PROPOSED
    parameters: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    proposer_id: str = "system"
    approver_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    timeout_seconds: float = 60.0
    execution_log: list[str] = field(default_factory=list)
    pre_state_snapshot: dict[str, Any] = field(default_factory=dict)
    post_state_snapshot: dict[str, Any] = field(default_factory=dict)
    verification_evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def parameters_hash(self) -> str:
        """Deterministic SHA-256 hash of action parameters for approval binding."""
        encoded = json.dumps(self.parameters, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def transition_to(self, new_state: ActionState, reason: str = "") -> None:
        """Transitions action to a new state and logs timestamped reason."""
        self.state = new_state
        self.updated_at = time.time()
        log_entry = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.updated_at))}] {new_state.value}: {reason}"
        self.execution_log.append(log_entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "playbook_name": self.playbook_name,
            "playbook_version": self.playbook_version,
            "target_entity": self.target_entity,
            "risk_tier": self.risk_tier.value,
            "alert_id": self.alert_id,
            "incident_id": self.incident_id,
            "hypothesis_id": self.hypothesis_id,
            "state": self.state.value,
            "parameters": dict(self.parameters),
            "parameters_hash": self.parameters_hash,
            "idempotency_key": self.idempotency_key,
            "proposer_id": self.proposer_id,
            "approver_ids": list(self.approver_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "timeout_seconds": self.timeout_seconds,
            "execution_log": list(self.execution_log),
            "verification_evidence": dict(self.verification_evidence),
            "metadata": dict(self.metadata),
        }


@dataclass
class PlaybookMetadata:
    name: str
    version: str
    risk_tier: ActionRiskTier
    description: str
    handler: Any
    is_recommendation_only_default: bool = False


class ActionRegistry:
    """Central registry for predefined and validated operational playbooks."""

    def __init__(self):
        self._playbooks: dict[tuple[str, str], PlaybookMetadata] = {}

    def register(
        self,
        name: str,
        version: str,
        risk_tier: ActionRiskTier,
        description: str,
        handler: Any,
        is_recommendation_only_default: bool = False,
    ) -> None:
        self._playbooks[(name, version)] = PlaybookMetadata(
            name=name,
            version=version,
            risk_tier=risk_tier,
            description=description,
            handler=handler,
            is_recommendation_only_default=is_recommendation_only_default,
        )

    def get(self, name: str, version: Optional[str] = None) -> Optional[PlaybookMetadata]:
        if version:
            return self._playbooks.get((name, version))
        # Return latest registered version
        matches = [p for (n, v), p in self._playbooks.items() if n == name]
        return matches[-1] if matches else None

    def list_playbooks(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "version": p.version,
                "risk_tier": p.risk_tier.value,
                "description": p.description,
                "is_recommendation_only_default": p.is_recommendation_only_default,
            }
            for p in self._playbooks.values()
        ]


class AutomationPolicyEngine:
    """Enforces execution boundaries, risk gates, change freeze, and production deny rules."""

    MAX_AUTO_BLAST_RADIUS_NODES: int = 5

    # Production targets that CANNOT be mutated under simulation mode
    PRODUCTION_TARGET_DENY_PATTERNS: tuple[str, ...] = (
        "live_production",
        "live_core",
        "prod_avaya_live",
        "live_telco_trunk",
    )

    # Allowlisted entities for automated diagnostic testing
    ALLOWED_ENTITY_PREFIXES: tuple[str, ...] = (
        "voice_trunk::",
        "sw-",
        "sbce-",
        "laptop-",
        "endpoint::",
        "test::",
        "mock::",
    )

    @classmethod
    def is_target_allowlisted(cls, target_entity: str) -> bool:
        return any(target_entity.startswith(prefix) for prefix in cls.ALLOWED_ENTITY_PREFIXES)

    @classmethod
    def is_production_denied(cls, target_entity: str) -> bool:
        lower = target_entity.lower()
        return any(pat in lower for pat in cls.PRODUCTION_TARGET_DENY_PATTERNS)

    @classmethod
    def evaluate_policy(
        cls,
        action: OperationalAction,
        is_in_change_window: bool = True,
        blast_radius_nodes: int = 1,
        is_change_freeze: bool = False,
        simulation_mode: bool = True,
    ) -> tuple[bool, str]:
        """Evaluates whether an operational action can proceed according to policy.

        Returns: (is_permitted, policy_decision_message)
        """
        # 1. Hard Production Target Deny Check
        if simulation_mode and cls.is_production_denied(action.target_entity):
            action.transition_to(ActionState.BLOCKED, f"Hard deny: target '{action.target_entity}' is a production device blocked under simulation mode")
            return False, "HARD_PRODUCTION_DENY"

        # 2. Allowlisted Entity Check
        if not cls.is_target_allowlisted(action.target_entity):
            action.transition_to(ActionState.BLOCKED, f"Target '{action.target_entity}' is outside operational allowlist")
            return False, "TARGET_OUTSIDE_ALLOWLIST"

        # 3. Change Freeze Policy: All non-diagnostic mutations are blocked
        if is_change_freeze and action.risk_tier != ActionRiskTier.LOW_RISK:
            action.transition_to(ActionState.BLOCKED, "Blocked by enterprise Change Freeze window")
            return False, "PROHIBITED_CHANGE_FREEZE"

        # 4. Blast Radius Enforcement
        if blast_radius_nodes > cls.MAX_AUTO_BLAST_RADIUS_NODES:
            if action.risk_tier == ActionRiskTier.LOW_RISK:
                action.transition_to(ActionState.BLOCKED, f"Blast radius {blast_radius_nodes} exceeds automated limit {cls.MAX_AUTO_BLAST_RADIUS_NODES}")
                return False, "PROHIBITED_HIGH_BLAST_RADIUS"

        # 5. High-Risk Change Window Enforcement
        if action.risk_tier == ActionRiskTier.HIGH_RISK and not is_in_change_window:
            action.transition_to(ActionState.BLOCKED, "High-risk action attempted outside approved Change Window")
            return False, "PROHIBITED_OUTSIDE_CHANGE_WINDOW"

        # 6. Low-Risk: Pre-authorized by policy
        if action.risk_tier == ActionRiskTier.LOW_RISK:
            action.transition_to(ActionState.APPROVED, "Pre-authorized by Low-Risk automated policy")
            return True, "PRE_AUTHORIZED_AUTOMATED"

        # 7. Moderate & High-Risk: Requires explicit operator approval
        action.transition_to(ActionState.PENDING_APPROVAL, f"Awaiting operator approval for {action.risk_tier.value}")
        return True, "APPROVAL_REQUIRED"
