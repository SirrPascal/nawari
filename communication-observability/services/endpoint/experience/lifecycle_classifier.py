"""
services/endpoint/experience/lifecycle_classifier.py

Endpoint Lifecycle State Machine and Anti-False-Positive Classifier.
Distinguishes legitimate planned shutdowns, sleep/hibernate states, and off-net
telemetry from genuine enterprise network failures.
"""

from __future__ import annotations

import time
from typing import Optional

from services.endpoint.experience.models import (
    CorporatePresenceState,
    EndpointEvaluationResult,
    EndpointLifecycleState,
    EndpointTelemetrySnapshot,
)
from services.endpoint.experience.presence_detector import CorporatePresenceDetector


class EndpointLifecycleClassifier:
    """Classifies endpoint telemetry against the 9-state EU-NEM lifecycle model."""

    def __init__(self, presence_detector: Optional[CorporatePresenceDetector] = None):
        self.presence_detector = presence_detector or CorporatePresenceDetector()

    def classify(
        self,
        snapshot: EndpointTelemetrySnapshot,
        last_heartbeat_age_sec: float = 0.0,
    ) -> EndpointEvaluationResult:
        """
        Evaluate an endpoint telemetry snapshot and determine authoritative state.
        """
        # Step 1: Evaluate Corporate Presence
        presence_state, presence_conf = self.presence_detector.evaluate(snapshot.network)

        # Step 2: Check for Recent Planned Shutdown Events
        # Windows Event 1074: Planned shutdown/restart
        # Windows Event 6006: EventLog service stopped cleanly
        recent_events = snapshot.lifecycle_events
        has_planned_shutdown = any(
            e.is_planned_shutdown or e.event_id in (1074, 6006) for e in recent_events
        )
        has_sleep_event = any(e.is_sleep for e in recent_events)
        has_wake_event = any(e.is_wake for e in recent_events)

        # If sleep occurred after wake, endpoint is sleeping
        if has_sleep_event and not has_wake_event:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.SLEEPING,
                primary_symptom="Endpoint entered sleep/hibernate state",
                confidence_score=0.95,
                recommended_action="No action required (endpoint in sleep mode)",
            )

        if has_planned_shutdown:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.EXPECTED_SHUTDOWN,
                primary_symptom="Planned OS shutdown or restart initiated",
                confidence_score=1.0,
                recommended_action="No action required (user-initiated clean shutdown)",
            )

        # Step 3: Handle Missing Telemetry (Agent Silent Guard)
        if last_heartbeat_age_sec > 180.0:  # > 3 minutes silent
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.UNREACHABLE_UNCLASSIFIED,
                primary_symptom=f"Agent silent for {int(last_heartbeat_age_sec)}s without shutdown record",
                confidence_score=0.7,
                recommended_action="Wait for local persistent buffer spool recovery upon reconnect",
            )

        # Step 4: Off-Net Filter
        # If the laptop is at home or on public Wi-Fi, do not raise corporate network alarms
        if presence_state == CorporatePresenceState.OFF_NET_REMOTE:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.OUTSIDE_CORPORATE_NETWORK,
                primary_symptom="Connected to non-corporate network / home Wi-Fi",
                confidence_score=presence_conf,
                recommended_action="Informational only (remote mobile worker)",
            )

        # Step 5: Evaluate Corporate Network Performance & Failures
        net = snapshot.network

        # Case A: Local Gateway Failure
        if not net.gateway_reachable or net.gateway_loss_pct >= 50.0:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.NETWORK_FAILURE,
                primary_symptom=f"Default gateway {net.gateway_ip} unreachable (Loss: {net.gateway_loss_pct}%)",
                confidence_score=0.95,
                recommended_action="Investigate local Wi-Fi AP association or edge switch port",
            )

        # Case B: Significant Gateway Degradation (Packet loss or high RTT)
        if net.gateway_loss_pct > 15.0 or net.gateway_rtt_ms > 120.0:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.DEGRADED,
                primary_symptom=f"Gateway degradation (RTT: {net.gateway_rtt_ms:.1f}ms, Loss: {net.gateway_loss_pct}%)",
                confidence_score=0.90,
                recommended_action="Check Wi-Fi channel interference or switch port buffer drops",
            )

        # Case C: DNS Resolution Failure (Gateway healthy, but DNS fails)
        if not net.dns_success:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.DEGRADED,
                primary_symptom=f"Internal DNS resolution failed on server {net.dns_server_ip}",
                confidence_score=0.95,
                recommended_action="Inspect corporate DNS resolver health at Pride Center DC",
            )

        # Case D: Slow DNS Latency (> 300ms)
        if net.dns_latency_ms > 300.0:
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.DEGRADED,
                primary_symptom=f"Elevated DNS query latency ({net.dns_latency_ms:.1f}ms)",
                confidence_score=0.85,
                recommended_action="Check DNS server queue depth and corporate WAN link",
            )

        # Case E: Corporate Application Connectivity Failure
        if not net.internal_services_ok:
            failed_services = [s for s, ok in net.services_tested.items() if not ok]
            return EndpointEvaluationResult(
                endpoint_id=snapshot.endpoint_id,
                presence_state=presence_state,
                presence_confidence=presence_conf,
                lifecycle_state=EndpointLifecycleState.DEGRADED,
                primary_symptom=f"Corporate application reachability failure: {', '.join(failed_services)}",
                confidence_score=0.90,
                recommended_action="Inspect application server listener and core routing ACLs",
            )

        # Case F: Healthy
        return EndpointEvaluationResult(
            endpoint_id=snapshot.endpoint_id,
            presence_state=presence_state,
            presence_confidence=presence_conf,
            lifecycle_state=EndpointLifecycleState.HEALTHY,
            primary_symptom=None,
            confidence_score=1.0,
            recommended_action="None (operating within nominal parameters)",
        )

