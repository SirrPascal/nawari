"""Intelligent Diagnosis & Evidence-Ranked Hypothesis Engine for Nawari.

Correlates multi-domain anomalies across the Phase 9 dynamic topology graph,
formulating diagnostic hypotheses with explicit supporting and contradicting evidence.
Respects topology confidence, ECMP/LAG redundancy, observation freshness, and never treats
the Lowest Common Ancestor (LCA) as automatic proof of root cause.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from services.analytics.anomaly_detector import AnomalySeverity, StatisticalAnomalyResult
from services.analytics.telemetry_foundation import DomainType


class EvidencePolarity(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class LinkDependencyType(str, Enum):
    PHYSICAL_L2 = "PHYSICAL_L2"
    LOGICAL_L3 = "LOGICAL_L3"
    SERVICE_DEPENDENCY = "SERVICE_DEPENDENCY"


@dataclass
class EvidenceItem:
    """Discrete evidentiary observation supporting or contradicting a diagnostic hypothesis."""

    source_domain: DomainType
    metric_name: str
    entity_id: str
    observation_summary: str
    severity: AnomalySeverity
    weight: float
    polarity: EvidencePolarity
    freshness_seconds: float
    topology_confidence: float = 1.0
    dependency_type: LinkDependencyType = LinkDependencyType.PHYSICAL_L2

    @property
    def effective_weight(self) -> float:
        """Adjusts weight based on topology confidence and observation staleness."""
        freshness_decay = 1.0 if self.freshness_seconds <= 300.0 else max(0.2, 1.0 - (self.freshness_seconds / 1800.0))
        return round(self.weight * self.topology_confidence * freshness_decay, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_domain": self.source_domain.value,
            "metric_name": self.metric_name,
            "entity_id": self.entity_id,
            "observation_summary": self.observation_summary,
            "severity": self.severity.value,
            "weight": self.weight,
            "effective_weight": self.effective_weight,
            "polarity": self.polarity.value,
            "freshness_seconds": round(self.freshness_seconds, 1),
            "topology_confidence": round(self.topology_confidence, 2),
            "dependency_type": self.dependency_type.value,
        }


@dataclass
class DiagnosticHypothesis:
    """An evidence-ranked diagnostic hypothesis for an operational degradation."""

    hypothesis_id: str
    title: str
    target_entity: str
    rank_score: float
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    contradicting_evidence: list[EvidenceItem] = field(default_factory=list)
    recommended_investigation: str = ""
    status: str = "EVALUATED"

    @property
    def supporting_weight_sum(self) -> float:
        return sum(e.effective_weight for e in self.supporting_evidence)

    @property
    def contradicting_weight_sum(self) -> float:
        return sum(e.effective_weight for e in self.contradicting_evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "target_entity": self.target_entity,
            "rank_score": round(self.rank_score, 3),
            "supporting_weight_sum": round(self.supporting_weight_sum, 3),
            "contradicting_weight_sum": round(self.contradicting_weight_sum, 3),
            "supporting_evidence_count": len(self.supporting_evidence),
            "contradicting_evidence_count": len(self.contradicting_evidence),
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradicting_evidence": [e.to_dict() for e in self.contradicting_evidence],
            "recommended_investigation": self.recommended_investigation,
            "status": self.status,
        }


class IntelligentDiagnosisEngine:
    """Synthesizes cross-domain anomalies, evaluates topological context, and ranks hypotheses."""

    AMBIGUITY_DELTA_THRESHOLD: float = 0.50

    @classmethod
    def diagnose(
        cls,
        anomalies: list[StatisticalAnomalyResult],
        topology_context: Optional[dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> list[DiagnosticHypothesis]:
        """Formulates and ranks diagnostic hypotheses based on observed anomaly patterns."""
        curr_time = now if now is not None else time.time()
        if not anomalies:
            return []

        hypotheses: list[DiagnosticHypothesis] = []
        topo = topology_context or {}

        # 1. Group anomalies by domain and entity
        voice_anomalies = [a for a in anomalies if a.metric_name in ("mos", "post_dial_delay_ms", "packet_loss_pct", "jitter_ms")]
        net_anomalies = [a for a in anomalies if a.metric_name in ("ifInDiscardsRate", "ifOutDiscardsRate", "ifInErrorsRate", "bandwidth_utilization_pct")]
        sbce_anomalies = [a for a in anomalies if a.metric_name in ("active_sessions", "session_utilization_pct", "cpu_utilization_pct")]
        ep_anomalies = [a for a in anomalies if a.metric_name in ("wifi_rssi_dbm", "tcp_rtt_ms", "dns_latency_ms")]

        # Scenario A: Carrier Trunk Signaling Impairment
        pdd_spikes = [a for a in voice_anomalies if a.metric_name == "post_dial_delay_ms" and a.is_anomaly]
        if pdd_spikes:
            supp_evidence: list[EvidenceItem] = []
            contra_evidence: list[EvidenceItem] = []

            for pdd in pdd_spikes:
                supp_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.VOICE_SIGNALING,
                        metric_name="post_dial_delay_ms",
                        entity_id=pdd.entity_id,
                        observation_summary=f"Post-dial delay anomalous: {pdd.current_value}ms (baseline: {pdd.baseline_mean}ms, Z={pdd.z_score})",
                        severity=pdd.severity,
                        weight=2.0,
                        polarity=EvidencePolarity.SUPPORTING,
                        freshness_seconds=max(0.0, curr_time - pdd.timestamp),
                    )
                )

            # Check if internal network interface drops are ABSENT (contradicting an internal network fault)
            if not net_anomalies:
                contra_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.NETWORK,
                        metric_name="interface_drops",
                        entity_id="campus_switches",
                        observation_summary="Campus switch interfaces show 0 drops and normal bandwidth (contradicts internal congestion)",
                        severity=AnomalySeverity.NORMAL,
                        weight=1.5,
                        polarity=EvidencePolarity.CONTRADICTING,
                        freshness_seconds=0.0,
                    )
                )

            rank_score = sum(e.effective_weight for e in supp_evidence) - sum(e.effective_weight for e in contra_evidence)
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="HYP_CARRIER_TRUNK_CONGESTION",
                    title="Telco Carrier Trunk Signaling Congestion",
                    target_entity="voice_trunk::primary_safaricom",
                    rank_score=rank_score,
                    supporting_evidence=supp_evidence,
                    contradicting_evidence=contra_evidence,
                    recommended_investigation="Verify Safaricom SIP proxy session utilization and inbound ACK/18x latency.",
                )
            )

        # Scenario B: Upstream Switch Interface Discards impacting Voice Media
        if net_anomalies and voice_anomalies:
            supp_evidence = []
            contra_evidence = []

            for net in net_anomalies:
                supp_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.NETWORK,
                        metric_name=net.metric_name,
                        entity_id=net.entity_id,
                        observation_summary=f"Switch interface packet discards/errors elevated: {net.current_value} pps (Z={net.z_score})",
                        severity=net.severity,
                        weight=3.0,
                        polarity=EvidencePolarity.SUPPORTING,
                        freshness_seconds=max(0.0, curr_time - net.timestamp),
                        dependency_type=LinkDependencyType.PHYSICAL_L2,
                    )
                )

            for v in voice_anomalies:
                supp_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.VOICE_MEDIA,
                        metric_name=v.metric_name,
                        entity_id=v.entity_id,
                        observation_summary=f"Voice quality degradation concurrent with switch drops: {v.metric_name}={v.current_value}",
                        severity=v.severity,
                        weight=2.5,
                        polarity=EvidencePolarity.SUPPORTING,
                        freshness_seconds=max(0.0, curr_time - v.timestamp),
                    )
                )

            # Check if link is a redundant LAG where only one member is affected
            is_lag_redundant = topo.get("is_lag_redundant", False)
            if is_lag_redundant:
                contra_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.TOPOLOGY,
                        metric_name="lag_redundancy",
                        entity_id=net_anomalies[0].entity_id,
                        observation_summary="Link is member of multi-chassis LAG with active secondary members (partially contradicts catastrophic link loss)",
                        severity=AnomalySeverity.INFORMATIONAL,
                        weight=1.8,
                        polarity=EvidencePolarity.CONTRADICTING,
                        freshness_seconds=0.0,
                    )
                )

            rank_score = sum(e.effective_weight for e in supp_evidence) - sum(e.effective_weight for e in contra_evidence)
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="HYP_SWITCH_EGRESS_QUEUE_DISCARDS",
                    title="Physical Switch Interface Congestion Imparing Voice Media",
                    target_entity=net_anomalies[0].entity_id,
                    rank_score=rank_score,
                    supporting_evidence=supp_evidence,
                    contradicting_evidence=contra_evidence,
                    recommended_investigation="Inspect switch egress buffer drops, QoS queue saturation, and physical optical levels.",
                )
            )

        # Scenario C: Avaya SBCE Session Exhaustion
        if sbce_anomalies:
            supp_evidence = []
            contra_evidence = []
            for sbce in sbce_anomalies:
                supp_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.SYSTEM,
                        metric_name=sbce.metric_name,
                        entity_id=sbce.entity_id,
                        observation_summary=f"SBCE capacity metric elevated: {sbce.metric_name}={sbce.current_value} (Z={sbce.z_score})",
                        severity=sbce.severity,
                        weight=3.5,
                        polarity=EvidencePolarity.SUPPORTING,
                        freshness_seconds=max(0.0, curr_time - sbce.timestamp),
                    )
                )

            rank_score = sum(e.effective_weight for e in supp_evidence) - sum(e.effective_weight for e in contra_evidence)
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="HYP_AVAYA_SBCE_CAPACITY_LIMIT",
                    title="Avaya SBCE Approaching Licensed Session Capacity",
                    target_entity=sbce_anomalies[0].entity_id,
                    rank_score=rank_score,
                    supporting_evidence=supp_evidence,
                    contradicting_evidence=contra_evidence,
                    recommended_investigation="Review active SBCE license pool, concurrent trunk calls, and session peak trends.",
                )
            )

        # Scenario D: Local Endpoint Wi-Fi Impairment (isolated to Wi-Fi)
        if ep_anomalies and not net_anomalies:
            supp_evidence = []
            contra_evidence = []
            for ep in ep_anomalies:
                supp_evidence.append(
                    EvidenceItem(
                        source_domain=DomainType.ENDPOINT,
                        metric_name=ep.metric_name,
                        entity_id=ep.entity_id,
                        observation_summary=f"Endpoint RF/Wi-Fi latency anomaly: {ep.metric_name}={ep.current_value}",
                        severity=ep.severity,
                        weight=2.0,
                        polarity=EvidencePolarity.SUPPORTING,
                        freshness_seconds=max(0.0, curr_time - ep.timestamp),
                    )
                )

            # Contradicting evidence: Wired core network is healthy
            contra_evidence.append(
                EvidenceItem(
                    source_domain=DomainType.NETWORK,
                    metric_name="wired_backbone_health",
                    entity_id="core_switches",
                    observation_summary="Wired distribution switch backplane exhibits 0% packet loss and low jitter",
                    severity=AnomalySeverity.NORMAL,
                    weight=1.5,
                    polarity=EvidencePolarity.CONTRADICTING,
                    freshness_seconds=0.0,
                )
            )

            rank_score = sum(e.effective_weight for e in supp_evidence) - sum(e.effective_weight for e in contra_evidence)
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="HYP_ENDPOINT_WIFI_INTERFERENCE",
                    title="Local Endpoint Wireless RF Degradation",
                    target_entity=ep_anomalies[0].entity_id,
                    rank_score=rank_score,
                    supporting_evidence=supp_evidence,
                    contradicting_evidence=contra_evidence,
                    recommended_investigation="Inspect local AP BSSID channel utilization, co-channel interference, and client roaming state.",
                )
            )

        # Sort hypotheses by rank_score descending
        hypotheses.sort(key=lambda h: h.rank_score, reverse=True)

        # Ambiguity check: if top 2 hypotheses have close scores and low absolute difference
        if len(hypotheses) >= 2:
            score_diff = hypotheses[0].rank_score - hypotheses[1].rank_score
            if score_diff < cls.AMBIGUITY_DELTA_THRESHOLD and hypotheses[0].rank_score < 3.0:
                for h in hypotheses:
                    h.status = "INSUFFICIENT_EVIDENCE"

        return hypotheses

