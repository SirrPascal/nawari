"""Cross-Domain Voice Service Assurance Incident Correlation Engine.

Correlates signaling transactions, bidirectional RTP media telemetry, and Zabbix
infrastructure alarms (network link status, SBCE CPU/memory) into causal root-cause
hypotheses and actionable service assurance reports.
"""

import time
from typing import Any, Optional

from services.assurance.models import (
    EvidenceDomain,
    EvidenceItem,
    HypothesisStatus,
    IncidentHypothesis,
    RootCauseDomain,
    ServiceAssuranceReport,
    ServiceHealthState,
    TelemetricEnvironment,
)
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent


class CrossDomainCorrelator:
    """Correlates voice quality telemetry with network and appliance monitoring state."""

    def __init__(self, zabbix_client: Optional[Any] = None):
        self.zabbix_client = zabbix_client

    def fetch_active_problems(
        self,
        host_names: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Query active unacknowledged problems from live Zabbix API."""
        if not self.zabbix_client:
            return []

        try:
            # Query problems from Zabbix API
            params: dict[str, Any] = {
                "output": ["eventid", "name", "severity", "clock", "r_eventid"],
                "recent": True,
                "sortfield": ["eventid"],
                "sortorder": "DESC",
            }
            if hasattr(self.zabbix_client, "call"):
                problems = self.zabbix_client.call("problem.get", params)
            elif hasattr(self.zabbix_client, "request"):
                problems = self.zabbix_client.request("problem.get", params)
            else:
                problems = []
            return problems if isinstance(problems, list) else []
        except Exception:
            return []

    def correlate(
        self,
        voice_event: CanonicalVoiceEvent,
        active_problems: Optional[list[dict[str, Any]]] = None,
        infrastructure_metrics: Optional[dict[str, Any]] = None,
    ) -> ServiceAssuranceReport:
        """Execute multi-domain correlation and synthesize an assurance report."""
        # 1. Gather active problems
        if active_problems is None:
            active_problems = self.fetch_active_problems()

        infra = infrastructure_metrics or {}

        # 2. Extract key domain observations
        signaling = voice_event.signaling
        media = voice_event.media

        sig_summary = {
            "outcome": signaling.outcome.value,
            "sip_status_code": signaling.sip_status_code,
            "setup_time_ms": signaling.setup_time_ms,
            "duration_seconds": signaling.duration_seconds,
        }

        media_summary = {
            "verification_level": media.verification_level.value,
            "estimated_mos": media.estimated_mos,
            "r_factor": media.r_factor,
            "jitter_ms": media.jitter_ms,
            "loss_pct": media.loss_pct,
            "rtt_ms": media.rtt_ms,
            "one_way_delay_ms": media.estimated_one_way_delay_ms,
        }

        # Scan active Zabbix problems for domain-specific indicators
        link_problems = []
        cpu_problems = []
        voice_problems = []
        other_problems = []

        for p in active_problems:
            name = p.get("name", "").lower()
            if any(k in name for k in ("link down", "operstatus", "interface down", "link down on")):
                link_problems.append(p)
            elif any(k in name for k in ("high cpu", "cpu utilization", "processor load", "memory")):
                cpu_problems.append(p)
            elif any(k in name for k in ("voice", "synthetic", "mos", "one-way")):
                voice_problems.append(p)
            else:
                other_problems.append(p)

        infra_summary = {
            "active_problems_count": len(active_problems),
            "link_problems_count": len(link_problems),
            "cpu_problems_count": len(cpu_problems),
            "interface_states": infra.get("interfaces", {}),
            "cpu_utilization": infra.get("cpu_utilization"),
        }

        hypotheses: list[IncidentHypothesis] = []

        # 3. Rule Evaluation & Hypothesis Generation
        now_epoch = time.time()
        event_time = voice_event.collection_timestamp or now_epoch
        is_stale = (now_epoch - event_time) > 900.0 if (event_time > 0 and now_epoch > event_time) else False

        # Environment provenance
        is_physical = any(k in voice_event.event_source.lower() for k in ("physical", "production")) or "physical" in voice_event.device_id.lower()
        environment = TelemetricEnvironment.PHYSICAL_PRODUCTION if is_physical else TelemetricEnvironment.MOCK_SIMULATED

        # Scenario A: Network Link Failure on SBCE or switch
        if (
            signaling.outcome in (CallOutcome.FAILED, CallOutcome.TIMEOUT, CallOutcome.CONGESTION)
            or media.verification_level == MediaVerificationLevel.NO_MEDIA
        ) and (link_problems or infra.get("link_down", False)):
            evidence = [
                EvidenceItem(
                    domain=EvidenceDomain.SIGNALING,
                    source="voice.synthetic.signaling",
                    identifier=f"Call Outcome: {signaling.outcome.value}",
                    severity="HIGH",
                    description=f"Synthetic voice call aborted with {signaling.outcome.value} (SIP {signaling.sip_status_code or 'none'}).",
                    value=signaling.outcome.value,
                ),
            ]
            for lp in link_problems:
                evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.NETWORK,
                        source="zabbix.problem",
                        identifier=lp.get("name", "Interface Link Down"),
                        severity="HIGH",
                        description=f"Active infrastructure problem: {lp.get('name')}",
                        value=lp.get("eventid"),
                    )
                )

            # Distinguish Confirmed (direct deterministic trace) from Probable (multi-domain correlation)
            has_direct_proof = infra.get("direct_causality", False) or "EHOSTUNREACH" in (signaling.hangup_cause_txt or "")
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.CONFIRMED if has_direct_proof else HypothesisStatus.PROBABLE,
                    root_cause_domain=RootCauseDomain.NETWORK_LINK,
                    title="Voice Failure Due to Network Interface Outage" if has_direct_proof else "Probable Network-Path Failure: Interface Outage Correlated with Call Timeout",
                    summary="Direct network socket error confirmed link failure" if has_direct_proof else "Multiple independent indicators support network transport failure: SBCE interface link down alarm observed alongside synthetic call timeout.",
                    confidence=0.95 if has_direct_proof else 0.85,
                    evidence=evidence,
                    remediation_recommendations=[
                        "Inspect physical layer connection and optical transceiver (SFP) on SBCE interface.",
                        "Verify upstream switch port operational status and VLAN trunking configuration.",
                        "Check switch interface error counters (CRC, frame alignment, discards).",
                    ],
                )
            )

        # Scenario B: Appliance Overload / CPU Saturation
        if (
            signaling.setup_time_ms > 3000
            or signaling.outcome in (CallOutcome.CONGESTION, CallOutcome.TIMEOUT)
            or (media.estimated_mos and media.estimated_mos < 3.5)
        ) and (cpu_problems or (infra.get("cpu_utilization") and infra["cpu_utilization"] > 85)):
            evidence = [
                EvidenceItem(
                    domain=EvidenceDomain.SIGNALING,
                    source="voice.synthetic.signaling",
                    identifier=f"High Setup Latency / Call Failure",
                    severity="HIGH",
                    description=f"Call setup latency {signaling.setup_time_ms}ms or outcome {signaling.outcome.value}.",
                    value=signaling.setup_time_ms,
                ),
            ]
            for cp in cpu_problems:
                evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.APPLIANCE,
                        source="zabbix.problem",
                        identifier=cp.get("name", "High CPU Utilization"),
                        severity="HIGH",
                        description=f"Active appliance problem: {cp.get('name')}",
                        value=cp.get("eventid"),
                    )
                )

            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.PROBABLE,
                    root_cause_domain=RootCauseDomain.APPLIANCE_OVERLOAD,
                    title="Probable SBCE Resource Saturation Impairing Voice Service",
                    summary="Multiple independent indicators support appliance overload: SBCE CPU/load problem observed alongside elevated setup latency or call timeout.",
                    confidence=0.82,
                    evidence=evidence,
                    remediation_recommendations=[
                        "Review active process list and worker thread utilization on SBCE appliance.",
                        "Check TLS cryptographic offloading and session renegotiation rate.",
                        "Verify total concurrent active calls against SBCE hardware license limits.",
                    ],
                )
            )

        # Scenario C: One-Way Audio / NAT / Firewall Asymmetry
        if media.verification_level in (
            MediaVerificationLevel.TRANSMIT_ONLY,
            MediaVerificationLevel.RECEIVE_ONLY,
        ) or (
            signaling.outcome == CallOutcome.ANSWERED
            and media.verification_level == MediaVerificationLevel.NO_MEDIA
        ):
            evidence = [
                EvidenceItem(
                    domain=EvidenceDomain.MEDIA,
                    source="voice.synthetic.media",
                    identifier=f"One-Way Audio: {media.verification_level.value}",
                    severity="HIGH",
                    description=f"SIP 200 OK established, but RTP audio flow is strictly unidirectional ({media.verification_level.value}).",
                    value=media.verification_level.value,
                ),
                EvidenceItem(
                    domain=EvidenceDomain.SIGNALING,
                    source="voice.synthetic.signaling",
                    identifier="SIP Signaling Answered",
                    severity="INFO",
                    description="SIP signaling established successfully while media flow failed.",
                    value=signaling.sip_status_code,
                ),
            ]
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.PROBABLE,
                    root_cause_domain=RootCauseDomain.FIREWALL_NAT_ASYMMETRY,
                    title="Probable Firewall RTP Drop or NAT Asymmetry (One-Way Audio)",
                    summary="Signaling plane is functional (200 OK), but RTP audio stream was only verified in one direction. Probable stateful firewall UDP timeout or asymmetric routing.",
                    confidence=0.80,
                    evidence=evidence,
                    remediation_recommendations=[
                        "Inspect firewall UDP state table and verify RTP port range (e.g. 35000-40000) is open bi-directionally.",
                        "Verify SBCE Signaling Interface vs Media Interface NAT public IP mappings.",
                        "Examine asymmetric routing paths between perimeter DMZ and inside core voice network.",
                    ],
                )
            )

        # Scenario D: Upstream Carrier / Trunk Congestion (Clean Local Infrastructure)
        if (
            signaling.outcome in (CallOutcome.CONGESTION, CallOutcome.TIMEOUT, CallOutcome.FAILED)
            or signaling.sip_status_code in (503, 408)
        ) and not (link_problems or cpu_problems or infra.get("link_down", False)):
            evidence = [
                EvidenceItem(
                    domain=EvidenceDomain.SIGNALING,
                    source="voice.synthetic.signaling",
                    identifier=f"SIP Status {signaling.sip_status_code or signaling.outcome.value}",
                    severity="HIGH",
                    description=f"Upstream entity rejected call with SIP {signaling.sip_status_code or 'none'} ({signaling.outcome.value}).",
                    value=signaling.sip_status_code or signaling.outcome.value,
                ),
                EvidenceItem(
                    domain=EvidenceDomain.NETWORK,
                    source="zabbix.infrastructure",
                    identifier="Local Infrastructure Healthy",
                    severity="INFO",
                    description="Local network interfaces are UP and SBCE CPU is within normal operating parameters.",
                    value=0,
                ),
            ]
            has_carrier_header = "congestion" in (signaling.sip_status_reason or "").lower()
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.CONFIRMED if has_carrier_header else HypothesisStatus.PROBABLE,
                    root_cause_domain=RootCauseDomain.UPSTREAM_CARRIER,
                    title="External Carrier Trunk Congestion (Confirmed SIP 503)" if has_carrier_header else "Probable Upstream Carrier / Trunk Congestion",
                    summary="Local SBCE appliance and interfaces are healthy, but upstream carrier trunk returned SIP 503 Service Unavailable or failed to respond.",
                    confidence=0.90 if has_carrier_header else 0.82,
                    evidence=evidence,
                    remediation_recommendations=[
                        "Contact telecom carrier / ITSP (Safaricom / Airtel) to verify trunk circuit health.",
                        "Inspect Avaya Session Manager SIP entity routing and verify failover trunk group status.",
                        "Check concurrent trunk channel utilization against subscribed CIR.",
                    ],
                )
            )

        # Scenario E: Voice Quality Degradation (MOS < 3.8, high jitter/loss, but answered & bidirectional)
        if (
            media.verification_level == MediaVerificationLevel.BIDIRECTIONAL
            and media.estimated_mos is not None
            and media.estimated_mos < 3.8
            and not (link_problems or cpu_problems)
        ):
            evidence = [
                EvidenceItem(
                    domain=EvidenceDomain.MEDIA,
                    source="voice.synthetic.media",
                    identifier=f"Degraded MOS: {media.estimated_mos}",
                    severity="WARNING",
                    description=f"Estimated MOS ({media.estimated_mos}) is below 3.8 SLA threshold (Jitter: {media.jitter_ms}ms, Loss: {media.loss_pct}%).",
                    value=media.estimated_mos,
                )
            ]
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.PROBABLE,
                    root_cause_domain=RootCauseDomain.NETWORK_LINK,
                    title="Probable Network Queueing or Jitter Impairing Voice Quality",
                    summary="Bidirectional media is active, but network transport queueing, packet loss, or jitter is impairing voice quality.",
                    confidence=0.78,
                    evidence=evidence,
                    remediation_recommendations=[
                        "Verify end-to-end DSCP markings (EF for voice RTP, CS3 for SIP signaling).",
                        "Inspect WAN edge router queue drops and traffic shaping policies.",
                        "Check for bufferbloat or microburst congestion on intermediate switch links.",
                    ],
                )
            )

        # Scenario F: Clean / Healthy Execution
        if (
            signaling.outcome == CallOutcome.ANSWERED
            and media.verification_level == MediaVerificationLevel.BIDIRECTIONAL
            and (media.estimated_mos is None or media.estimated_mos >= 3.8)
            and not (link_problems or cpu_problems)
            and not is_stale
        ):
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.HEALTHY,
                    root_cause_domain=RootCauseDomain.HEALTHY,
                    title="Voice Service Nominal and Healthy",
                    summary="Signaling established, bidirectional media confirmed, voice quality within SLA, and infrastructure alarms clear.",
                    confidence=1.0,
                    evidence=[
                        EvidenceItem(
                            domain=EvidenceDomain.SIGNALING,
                            source="voice.synthetic.signaling",
                            identifier="Call Answered",
                            severity="INFO",
                            description="SIP signaling established within expected latency.",
                            value=signaling.setup_time_ms,
                        ),
                        EvidenceItem(
                            domain=EvidenceDomain.MEDIA,
                            source="voice.synthetic.media",
                            identifier="Bidirectional Media Verified",
                            severity="INFO",
                            description=f"Bidirectional audio confirmed (MOS: {media.estimated_mos or 'N/A'}).",
                            value=media.estimated_mos,
                        ),
                    ],
                    remediation_recommendations=[],
                )
            )

        # Scenario G: Stale Telemetry Guard
        if is_stale:
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.SUSPECTED,
                    root_cause_domain=RootCauseDomain.UNKNOWN,
                    title="Stale Voice Telemetry: Probe Ingestion Delayed or Offline",
                    summary="Latest synthetic voice telemetry is older than 15 minutes. Current operational health cannot be assured.",
                    confidence=0.70,
                    evidence=[
                        EvidenceItem(
                            domain=EvidenceDomain.SIGNALING,
                            source="voice.synthetic",
                            identifier="Telemetry Staleness",
                            severity="WARNING",
                            description=f"Telemetry age exceeds 15 minutes ({int((now_epoch - event_time)/60)}m elapsed).",
                            value=int(now_epoch - event_time),
                        )
                    ],
                    remediation_recommendations=[
                        "Verify whether Asterisk synthetic voice scheduler or cron task is actively executing.",
                        "Inspect Zabbix Sender logs and verify TCP 10051 reachability.",
                    ],
                )
            )

        # Default fallback if no specific scenario matched
        if not hypotheses:
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.INCONCLUSIVE,
                    root_cause_domain=RootCauseDomain.UNKNOWN,
                    title="Inconclusive Voice Telemetry Analysis",
                    summary="Telemetry patterns did not match known failure signatures. Further telemetry collection required.",
                    confidence=0.50,
                    evidence=[],
                    remediation_recommendations=["Review raw SIP and RTCP logs for abnormal disconnect reasons."],
                )
            )

        # 4. Compute Health State and Health Score
        primary = max(hypotheses, key=lambda h: h.confidence)
        if is_stale and primary.status != HypothesisStatus.HEALTHY and not (link_problems or cpu_problems):
            health_state = ServiceHealthState.UNKNOWN
            health_score = 50.0
        elif primary.status == HypothesisStatus.HEALTHY:
            health_state = ServiceHealthState.HEALTHY
            health_score = 98.0
            if media.estimated_mos:
                health_score = min(100.0, 80.0 + (media.estimated_mos / 4.5) * 20.0)
        elif primary.root_cause_domain in (
            RootCauseDomain.NETWORK_LINK,
            RootCauseDomain.FIREWALL_NAT_ASYMMETRY,
            RootCauseDomain.APPLIANCE_OVERLOAD,
            RootCauseDomain.UPSTREAM_CARRIER,
        ) and (
            signaling.outcome != CallOutcome.ANSWERED
            or media.verification_level in (MediaVerificationLevel.TRANSMIT_ONLY, MediaVerificationLevel.RECEIVE_ONLY)
        ):
            health_state = ServiceHealthState.CRITICAL
            health_score = 15.0
        elif primary.root_cause_domain in (
            RootCauseDomain.NETWORK_LINK,
            RootCauseDomain.APPLIANCE_OVERLOAD,
        ) or (media.estimated_mos and media.estimated_mos < 3.8):
            health_state = ServiceHealthState.DEGRADED
            health_score = 65.0
        else:
            health_state = ServiceHealthState.UNKNOWN
            health_score = 50.0

        now = voice_event.collection_timestamp or time.time()
        return ServiceAssuranceReport(
            timestamp=now,
            service_id=voice_event.service_id,
            target_host=voice_event.device_id,
            environment=environment,
            is_stale=is_stale,
            health_state=health_state,
            health_score=health_score,
            signaling_summary=sig_summary,
            media_summary=media_summary,
            infrastructure_summary=infra_summary,
            hypotheses=hypotheses,
            active_problems=active_problems,
        )
