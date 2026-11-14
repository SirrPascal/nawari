"""
services/endpoint/experience/correlation_engine.py

Nawari EU-NEM Infrastructure Correlation and Diagnostic Hypothesis Engine.
Correlates multi-endpoint telemetry with core network infrastructure, access points,
DNS services, and enterprise applications to generate actionable root-cause hypotheses.
"""

from __future__ import annotations

import collections
import time
from typing import Any, Dict, List, Optional

from services.endpoint.experience.lifecycle_classifier import EndpointLifecycleClassifier
from services.endpoint.experience.models import (
    CorporatePresenceState,
    DiagnosticHypothesis,
    EndpointEvaluationResult,
    EndpointLifecycleState,
    EndpointTelemetrySnapshot,
    FleetCorrelationResult,
)


class EndUserExperienceService:
    """Core analytical service for End-User Network Experience Monitoring."""

    def __init__(self, classifier: Optional[EndpointLifecycleClassifier] = None):
        self.classifier = classifier or EndpointLifecycleClassifier()

    def evaluate_fleet(
        self,
        snapshots: List[EndpointTelemetrySnapshot],
        infrastructure_telemetry: Optional[Dict[str, Any]] = None,
    ) -> FleetCorrelationResult:
        """
        Evaluate all reporting endpoints, cluster symptoms by topology, and
        derive diagnostic hypotheses.
        """
        infra = infrastructure_telemetry or {}
        evaluations: List[EndpointEvaluationResult] = []

        # 1. Classify individual endpoints
        for snap in snapshots:
            res = self.classifier.classify(snap)
            evaluations.append(res)

        total = len(evaluations)
        counts = collections.Counter(e.lifecycle_state for e in evaluations)

        # 2. Group degraded and failing endpoints by topology attributes
        degraded_endpoints = [
            (snap, ev)
            for snap, ev in zip(snapshots, evaluations)
            if ev.lifecycle_state in (
                EndpointLifecycleState.DEGRADED,
                EndpointLifecycleState.NETWORK_FAILURE,
            )
            and ev.presence_state in (
                CorporatePresenceState.CORPORATE_CONFIRMED,
                CorporatePresenceState.CORPORATE_DEGRADED,
            )
        ]

        hypotheses: List[Dict[str, Any]] = []

        if not degraded_endpoints:
            hypotheses.append({
                "hypothesis": DiagnosticHypothesis.FLEET_HEALTHY.value,
                "confidence": 1.0,
                "description": "All monitored corporate endpoints report nominal network experience.",
                "affected_endpoints": [],
                "target_infrastructure": "All Systems Nominal",
            })
        else:
            # Analyze failure patterns across degraded endpoints
            ap_groups = collections.defaultdict(list)
            vlan_groups = collections.defaultdict(list)
            dns_failures = []
            service_failures = collections.defaultdict(list)
            gateway_failures = []

            for snap, ev in degraded_endpoints:
                net = snap.network
                if net.wifi_bssid:
                    ap_groups[net.wifi_bssid].append(snap.endpoint_id)
                if net.gateway_ip:
                    vlan_groups[net.gateway_ip].append(snap.endpoint_id)
                if not net.dns_success:
                    dns_failures.append(snap.endpoint_id)
                if not net.gateway_reachable or net.gateway_loss_pct >= 20.0:
                    gateway_failures.append(snap.endpoint_id)
                for s_name, s_ok in net.services_tested.items():
                    if not s_ok:
                        service_failures[s_name].append(snap.endpoint_id)

            # Hypothesis 1: DNS Infrastructure Problem
            # Multiple endpoints fail DNS while their default gateways are reachable
            if len(dns_failures) >= 2 and all(
                s.network.gateway_reachable for s, _ in degraded_endpoints if s.endpoint_id in dns_failures
            ):
                hypotheses.append({
                    "hypothesis": DiagnosticHypothesis.DNS_INFRASTRUCTURE_ISSUE.value,
                    "confidence": 0.95,
                    "description": (
                        f"{len(dns_failures)} endpoints have healthy gateway reachability but cannot "
                        f"resolve internal corporate records on corporate DNS resolvers."
                    ),
                    "affected_endpoints": dns_failures,
                    "target_infrastructure": "Corporate DNS Resolvers (10.2.1.10 / 10.2.1.11)",
                    "recommended_action": "Verify BIND/Active Directory DNS service on Pride Center core.",
                })

            # Hypothesis 2: Shared Access Point / RF Issue
            # Multiple endpoints on the same Wi-Fi BSSID suffer packet loss
            for bssid, ep_ids in ap_groups.items():
                if len(ep_ids) >= 2:
                    hypotheses.append({
                        "hypothesis": DiagnosticHypothesis.ACCESS_POINT_RF_ISSUE.value,
                        "confidence": 0.90,
                        "description": (
                            f"{len(ep_ids)} endpoints associated with Access Point [{bssid}] "
                            f"experience high packet loss or latency."
                        ),
                        "affected_endpoints": ep_ids,
                        "target_infrastructure": f"Wireless Access Point {bssid}",
                        "recommended_action": "Inspect AP uplink cable, channel interference, and client density.",
                    })

            # Hypothesis 3: VLAN / Core Gateway Issue
            for gw_ip, ep_ids in vlan_groups.items():
                if len(ep_ids) >= 3 and len(gateway_failures) >= 3:
                    hypotheses.append({
                        "hypothesis": DiagnosticHypothesis.VLAN_SWITCH_ISSUE.value,
                        "confidence": 0.92,
                        "description": (
                            f"{len(ep_ids)} endpoints on gateway subnet {gw_ip} experience gateway loss."
                        ),
                        "affected_endpoints": ep_ids,
                        "target_infrastructure": f"Distribution Gateway / Core Switch ({gw_ip})",
                        "recommended_action": "Check distribution switch trunk link and ARP table capacity.",
                    })

            # Hypothesis 4: Specific Application Service Issue
            for s_name, ep_ids in service_failures.items():
                if len(ep_ids) >= 2 and len(gateway_failures) == 0 and len(dns_failures) == 0:
                    hypotheses.append({
                        "hypothesis": DiagnosticHypothesis.SERVICE_APPLICATION_ISSUE.value,
                        "confidence": 0.94,
                        "description": (
                            f"{len(ep_ids)} endpoints have healthy network & DNS, but TCP port checks "
                            f"to application service [{s_name}] fail."
                        ),
                        "affected_endpoints": ep_ids,
                        "target_infrastructure": f"Enterprise Application Service: {s_name}",
                        "recommended_action": "Verify server daemon status and firewall security rules.",
                    })

            # Hypothesis 5: Isolated Local Endpoint Issue
            # Exactly 1 endpoint is degraded while all others on the same network/AP are healthy
            for snap, ev in degraded_endpoints:
                is_clustered = (
                    snap.endpoint_id in dns_failures and len(dns_failures) >= 2
                    or (snap.network.wifi_bssid and len(ap_groups.get(snap.network.wifi_bssid, [])) >= 2)
                    or len(vlan_groups.get(snap.network.gateway_ip, [])) >= 3
                )
                if not is_clustered:
                    hypotheses.append({
                        "hypothesis": DiagnosticHypothesis.LOCAL_ENDPOINT_ISSUE.value,
                        "confidence": 0.85,
                        "description": (
                            f"Degradation isolated to single endpoint [{snap.endpoint_id}] "
                            f"({ev.primary_symptom}). Neighboring endpoints report healthy network."
                        ),
                        "affected_endpoints": [snap.endpoint_id],
                        "target_infrastructure": f"Endpoint Hardware / OS: {snap.hostname}",
                        "recommended_action": "Inspect endpoint Wi-Fi adapter driver, physical antenna, or background CPU load.",
                    })

        return FleetCorrelationResult(
            evaluated_at=time.time(),
            total_endpoints=total,
            healthy_count=counts[EndpointLifecycleState.HEALTHY],
            degraded_count=counts[EndpointLifecycleState.DEGRADED],
            network_failure_count=counts[EndpointLifecycleState.NETWORK_FAILURE],
            expected_shutdown_count=counts[EndpointLifecycleState.EXPECTED_SHUTDOWN],
            sleeping_count=counts[EndpointLifecycleState.SLEEPING],
            off_net_count=counts[EndpointLifecycleState.OUTSIDE_CORPORATE_NETWORK],
            unclassified_count=counts[EndpointLifecycleState.UNREACHABLE_UNCLASSIFIED],
            agent_failure_count=counts[EndpointLifecycleState.AGENT_FAILURE],
            evaluations=evaluations,
            hypotheses=hypotheses,
        )

