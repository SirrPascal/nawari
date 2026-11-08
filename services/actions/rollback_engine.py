"""Automated Rollback Engine & Recovery Verification for Nawari (Workstream 12E).

Enforces rollback precondition verification before attempting unrolling.
Halts and escalates if rollback preconditions are not satisfied, preventing unsafe blind reverts.
"""

from __future__ import annotations

import time
from typing import Any

from services.actions.action_framework import ActionState, OperationalAction


class RollbackEngine:
    """Safely executes rollback procedures or escalates when rollback is unsafe."""

    @classmethod
    def safe_rollback(
        cls,
        action: OperationalAction,
        handler: Any,
        context: dict[str, Any],
    ) -> bool:
        """Evaluates rollback safety and executes inverse unrolling or escalates to Tier-3.

        Returns True if rolled back safely, False if rollback was unsafe or failed.
        """
        # 1. Check Rollback Preconditions
        can_rollback, reason = handler.check_rollback_preconditions(context)

        if not can_rollback:
            # Unsafe to rollback! Halt and escalate to Tier-3
            escalate_res = handler.escalate(context, reason)
            action.transition_to(
                ActionState.ROLLBACK_FAILED,
                f"Rollback aborted: {reason}. Escalated to Tier-3 operations.",
            )
            action.metadata["escalation"] = escalate_res
            return False

        # 2. Execute Rollback
        try:
            rollback_res = handler.rollback(context)
            action.transition_to(
                ActionState.ROLLED_BACK,
                "Operational changes reverted cleanly according to verified rollback procedure.",
            )
            action.metadata["rollback_result"] = rollback_res
            return True
        except Exception as ex:
            # Rollback itself failed! High-severity escalation
            action.transition_to(
                ActionState.ROLLBACK_FAILED,
                f"CRITICAL: Rollback execution threw exception: {str(ex)}. Escalating to NOC Incident Commander.",
            )
            action.metadata["rollback_exception"] = str(ex)
            return False

