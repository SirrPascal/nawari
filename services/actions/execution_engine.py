"""Action Execution Service, Concurrency Locks & Circuit Breakers (Workstream 12D).

Dedicated, isolated action execution service enforcing strict allowlists, zero shell execution,
entity-level concurrency locks, timeouts, idempotency keys, and dead-man circuit breakers.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from services.actions.action_framework import (
    ActionRegistry,
    ActionRiskTier,
    ActionState,
    OperationalAction,
)
from services.actions.rollback_engine import RollbackEngine


class CircuitBreakerStatus:
    def __init__(self, failure_threshold: int = 3, window_seconds: float = 900.0):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recent_failures: list[float] = []
        self.is_tripped: bool = False

    def record_failure(self) -> None:
        now = time.time()
        self.recent_failures.append(now)
        # Purge failures outside the window
        self.recent_failures = [t for t in self.recent_failures if now - t <= self.window_seconds]
        if len(self.recent_failures) >= self.failure_threshold:
            self.is_tripped = True

    def record_success(self) -> None:
        self.recent_failures.clear()
        self.is_tripped = False

    def reset(self) -> None:
        self.recent_failures.clear()
        self.is_tripped = False


class ActionExecutionService:
    """Isolated execution engine enforcing strict safety boundaries and idempotency."""

    def __init__(self, registry: Optional[ActionRegistry] = None):
        self.registry = registry or ActionRegistry()
        self.circuit_breaker = CircuitBreakerStatus(failure_threshold=3, window_seconds=900.0)
        # Entity-level concurrency locks: entity_id -> action_id
        self._entity_locks: dict[str, str] = {}
        # Idempotency journal: idempotency_key -> OperationalAction
        self._idempotency_journal: dict[str, OperationalAction] = {}
        self.service_id = "nawari-action-executor-v1"

    def execute_action(
        self,
        action: OperationalAction,
        execution_context: Optional[dict[str, Any]] = None,
    ) -> OperationalAction:
        """Executes an approved action with transactional step logging, locks, and verification."""
        # 1. Idempotency Check: if identical idempotency key exists, return recorded action
        if action.idempotency_key in self._idempotency_journal:
            recorded = self._idempotency_journal[action.idempotency_key]
            action.transition_to(recorded.state, "Idempotent duplicate request; returning existing execution journal")
            return recorded

        # Record in journal
        self._idempotency_journal[action.idempotency_key] = action

        # 2. Circuit Breaker Check
        if self.circuit_breaker.is_tripped:
            action.transition_to(ActionState.BLOCKED, "Execution suppressed: Dead-Man Circuit Breaker is TRIPPED")
            return action

        # 3. Action State Check: must be APPROVED before execution
        if action.state != ActionState.APPROVED:
            action.transition_to(ActionState.BLOCKED, f"Cannot execute action in state {action.state.value}; must be APPROVED")
            return action

        # 4. Concurrency Lock: strictly 1 mutating action per physical entity
        target = action.target_entity
        if target in self._entity_locks:
            locking_action = self._entity_locks[target]
            action.transition_to(ActionState.BLOCKED, f"Concurrency lock conflict: target '{target}' locked by action {locking_action}")
            return action

        # Acquire lock
        self._entity_locks[target] = action.action_id

        # 5. Registry Lookup: verify playbook is registered (strict allowlist)
        playbook_meta = self.registry.get(action.playbook_name, action.playbook_version)
        if not playbook_meta:
            self._release_lock(target)
            action.transition_to(ActionState.BLOCKED, f"Playbook '{action.playbook_name}' (v{action.playbook_version}) not found in allowlisted registry")
            return action

        handler = playbook_meta.handler
        ctx = dict(action.parameters)
        if execution_context:
            ctx.update(execution_context)

        try:
            # 6. Precondition Verification
            pre_ok, pre_msg = handler.check_preconditions(ctx)
            if not pre_ok:
                self._release_lock(target)
                action.transition_to(ActionState.FAILED, f"Preconditions failed: {pre_msg}")
                self.circuit_breaker.record_failure()
                return action

            # 7. Snapshot Pre-State
            action.pre_state_snapshot = handler.capture_pre_state(ctx)

            # 8. Execution Stage
            action.transition_to(ActionState.EXECUTING, f"Executing playbook {action.playbook_name}")
            start_exec_time = time.time()
            exec_result = handler.execute(ctx)
            action.post_state_snapshot = exec_result

            # Check timeout
            if time.time() - start_exec_time > action.timeout_seconds:
                self._release_lock(target)
                action.transition_to(ActionState.TIMED_OUT, f"Execution exceeded timeout limit ({action.timeout_seconds}s)")
                self.circuit_breaker.record_failure()
                RollbackEngine.safe_rollback(action, handler, ctx)
                return action

            # 9. Independent Post-Action Verification Stage
            action.transition_to(ActionState.VERIFYING, "Running independent post-action service verification")
            post_ok, post_msg = handler.check_postconditions(ctx)
            action.verification_evidence = {"postcondition_status": post_ok, "verification_details": post_msg}

            if not post_ok:
                # Post-verification failed! Do not declare victory. Execute rollback.
                self.circuit_breaker.record_failure()
                action.transition_to(ActionState.FAILED, f"Post-action verification failed: {post_msg}")
                RollbackEngine.safe_rollback(action, handler, ctx)
                return action

            # 10. Successful Completion
            action.transition_to(ActionState.COMPLETED, f"Action completed and independently verified: {post_msg}")
            self.circuit_breaker.record_success()
            return action

        except Exception as ex:
            self.circuit_breaker.record_failure()
            action.transition_to(ActionState.FAILED, f"Execution exception occurred: {str(ex)}")
            RollbackEngine.safe_rollback(action, handler, ctx)
            return action

        finally:
            self._release_lock(target)

    def _release_lock(self, target_entity: str) -> None:
        if target_entity in self._entity_locks:
            del self._entity_locks[target_entity]

