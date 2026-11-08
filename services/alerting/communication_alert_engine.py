"""
Nawari Communication Alert Engine.
Evaluates operational metrics against the Communication Alert Catalogue,
manages alert lifecycles (PENDING -> FIRING -> RECOVERING -> RESOLVED),
enforces deduplication, cooldown intervals, flapping protection, and suppression.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from services.alerting.models import (
    AlertEvidence,
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertState,
)
from services.alerting.communication_alert_catalogue import COMMUNICATION_ALERT_RULES

logger = logging.getLogger("nawari.alerting")


class CommunicationAlertEngine:
    """Core evaluation engine for Communication Observability alerts."""

    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        notification_handler: Optional[Callable[[AlertInstance, str], None]] = None,
        cooldown_seconds: float = 900.0,
    ) -> None:
        self.rules: Dict[str, AlertRule] = {r.alert_id: r for r in (rules or COMMUNICATION_ALERT_RULES)}
        self.active_instances: Dict[str, AlertInstance] = {}
        self.resolved_instances: Dict[str, AlertInstance] = {}
        self.notification_handler = notification_handler
        self.cooldown_seconds = cooldown_seconds
        self.suppressed_entities: Set[str] = set()

    def add_suppression(self, entity_id: str) -> None:
        """Suppress notifications for a specific entity (e.g. maintenance window)."""
        self.suppressed_entities.add(entity_id.strip().lower())

    def remove_suppression(self, entity_id: str) -> None:
        """Remove maintenance suppression for an entity."""
        self.suppressed_entities.discard(entity_id.strip().lower())

    def is_suppressed(self, entity_id: str) -> bool:
        return entity_id.strip().lower() in self.suppressed_entities

    def evaluate_telemetry(
        self,
        entity_id: str,
        site_id: str,
        metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        current_time: Optional[float] = None,
    ) -> List[AlertInstance]:
        """
        Evaluates a batch of metric telemetry for an entity and site.
        Returns a list of active AlertInstances currently FIRING or RECOVERING.
        """
        now = current_time if current_time is not None else time.time()
        ctx = context or {}
        firing_or_updated: List[AlertInstance] = []

        for rule in self.rules.values():
            if not rule.enabled:
                continue

            val = metrics.get(rule.metric_key)
            fingerprint = f"{rule.alert_id}|{entity_id}|{site_id}"
            instance = self.active_instances.get(fingerprint)

            # Check if metric triggered condition
            is_triggered = False
            if val is not None:
                try:
                    is_triggered = rule.evaluator(val, ctx)
                except Exception as e:
                    logger.warning("Error evaluating rule %s on %s: %s", rule.alert_id, entity_id, e)

            if is_triggered:
                # Triggered path
                if instance is None:
                    # New alert instance
                    instance = AlertInstance(
                        alert_id=rule.alert_id,
                        entity_id=entity_id,
                        site_id=site_id,
                        current_state=AlertState.PENDING,
                        observed_value=val,
                        first_observed_at=now,
                        last_observed_at=now,
                        nominal_recovery_cycles=0,
                        required_recovery_cycles=3,
                        suppressed=self.is_suppressed(entity_id),
                        suppression_reason="Maintenance window" if self.is_suppressed(entity_id) else None,
                    )
                    instance.history.append({"state": AlertState.PENDING.value, "time": now, "val": val})
                    self.active_instances[fingerprint] = instance

                else:
                    # Existing alert instance
                    instance.last_observed_at = now
                    instance.observed_value = val
                    instance.nominal_recovery_cycles = 0  # reset recovery on relapse

                    # Check pending -> firing transition
                    if instance.current_state == AlertState.PENDING:
                        if (now - instance.first_observed_at) >= rule.pending_duration_seconds:
                            instance.current_state = AlertState.FIRING
                            instance.firing_started_at = now
                            instance.history.append({"state": AlertState.FIRING.value, "time": now, "val": val})
                            self._trigger_notification(instance, rule, "NEW_ALERT", now)

                    elif instance.current_state in (AlertState.FIRING, AlertState.RECOVERING):
                        instance.current_state = AlertState.FIRING
                        # Check cooldown / repeat notification
                        if instance.last_notification_sent_at and (now - instance.last_notification_sent_at) >= self.cooldown_seconds:
                            self._trigger_notification(instance, rule, "REPEAT_REMINDER", now)

                firing_or_updated.append(instance)

            else:
                # Metric is nominal or missing
                if instance is not None and instance.current_state in (AlertState.FIRING, AlertState.RECOVERING):
                    # Strict Evidence Rule: Missing or None telemetry CANNOT count toward nominal recovery!
                    if val is not None:
                        instance.nominal_recovery_cycles += 1
                        instance.last_observed_at = now
                        instance.observed_value = val
                        instance.current_state = AlertState.RECOVERING

                        if instance.nominal_recovery_cycles >= instance.required_recovery_cycles:
                            # Fully resolved
                            instance.current_state = AlertState.RESOLVED
                            instance.resolved_at = now
                            instance.history.append({"state": AlertState.RESOLVED.value, "time": now, "val": val})
                            self._trigger_notification(instance, rule, "RECOVERY", now)
                            self.resolved_instances[fingerprint] = instance
                            del self.active_instances[fingerprint]
                        else:
                            firing_or_updated.append(instance)
                    else:
                        # Missing telemetry: hold current state, reset recovery cycles
                        instance.nominal_recovery_cycles = 0
                        firing_or_updated.append(instance)

                elif instance is not None and instance.current_state == AlertState.PENDING:
                    # Cancelled before firing
                    del self.active_instances[fingerprint]

        return firing_or_updated

    def _trigger_notification(
        self,
        instance: AlertInstance,
        rule: AlertRule,
        event_type: str,
        now: float,
    ) -> None:
        """Dispatches notification via registered handler if not suppressed."""
        if instance.suppressed or self.is_suppressed(instance.entity_id):
            logger.info("Alert %s suppressed for entity %s", rule.alert_id, instance.entity_id)
            return

        instance.last_notification_sent_at = now
        instance.notification_count += 1

        if self.notification_handler:
            try:
                self.notification_handler(instance, event_type)
            except Exception as e:
                logger.error("Failed to execute notification handler for %s: %s", rule.alert_id, e)
