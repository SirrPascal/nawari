"""Cross-Domain Voice & Endpoint Service Assurance Incident Correlation Engine.

Correlates signaling transactions, bidirectional RTP media telemetry, endpoint edge probes,
hop-by-hop network path analysis, and Zabbix infrastructure alarms into calibrated causal
root-cause hypotheses and actionable service assurance reports.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

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
from services.endpoint.models import (
    DnsResolutionStatus,
    EndpointTelemetryReport,
    HopResponseStatus,
    InterfaceType,
)
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent


class CrossDomainCorrelator:
    """Correlates voice quality telemetry, endpoint experience, and infrastructure monitoring state."""

    def __init__(
        self,
        zabbix_client: Optional[Any] = None,
        topology_graph: Optional[Any] = None,
        topology_engine: Optional[Any] = None,
    ):
        self.zabbix_client = zabbix_client
        self.topology_graph = topology_graph
        self.topology_engine = topology_engine

    def fetch_active_problems(
        self,
        host_names: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Query active unacknowledged problems from live Zabbix API."""
        if not self.zabbix_client:
            return []

        try:
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
        voice_event: Optional[CanonicalVoiceEvent] = None,
        active_problems: Optional[list[dict[str, Any]]] = None,
        infrastructure_metrics: Optional[dict[str, Any]] = None,
        endpoint_reports: Optional[list[EndpointTelemetryReport]] = None,
        topology_changes: Optional[list[Any]] = None,
    ) -> ServiceAssuranceReport:
        """Execute multi-domain correlation and synthesize an assurance report."""
        if active_problems is None:
            active_problems = self.fetch_active_problems()

        infra = infrastructure_metrics or {}
        now_epoch = time.time()
        reports = endpoint_reports or []

        # -------------------------------------------------------------
        # 1. Voice Domain Extraction
        # -------------------------------------------------------------
        if voice_event is not None:
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
            event_time = voice_event.collection_timestamp or now_epoch
            is_stale = (now_epoch - event_time) > 900.0 if (event_time > 0 and now_epoch > event_time) else False
            is_physical = (
                any(k in voice_event.event_source.lower() for k in ("physical", "production"))
                or "physical" in voice_event.device_id.lower()
            )
            target_host = voice_event.device_id
            service_id = voice_event.service_id
        else:
            signaling = None
            media = None
            sig_summary = {}
            media_summary = {}
            event_time = now_epoch
            is_stale = False
            is_physical = False
            target_host = reports[0].metadata.hostname if reports else "nawari-assurance-engine"
            service_id = "cross-domain-assurance"

        # Check environment from endpoint reports if present
        if reports and any(
            r.metadata.environment == TelemetricEnvironment.PHYSICAL_PRODUCTION for r in reports
        ):
            is_physical = True

        environment = (
            TelemetricEnvironment.PHYSICAL_PRODUCTION if is_physical else TelemetricEnvironment.MOCK_SIMULATED
        )

        # -------------------------------------------------------------
        # 2. Infrastructure & Zabbix Problems Scan
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # 3. Endpoint & Path Domain Summarization
        # -------------------------------------------------------------
        endpoint_summary: dict[str, Any] = {
            "total_endpoints": len(reports),
            "degraded_endpoints": 0,
            "isolated_endpoint_failures": [],
            "dns_failures": 0,
            "service_failures": 0,
            "path_failures": 0,
        }
        path_summary: dict[str, Any] = {
            "total_traces": 0,
            "routes_diverged": 0,
            "hops_with_loss": 0,
            "bottleneck_hops": [],
        }

        hypotheses: list[IncidentHypothesis] = []

        # =============================================================
        # 4. Multi-Domain Correlation Rules (Stage 7F 6 Failure Scenarios)
        # =============================================================

        # -------------------------------------------------------------
        # Scenario 1: Local Endpoint Problem (Isolated Wi-Fi / Edge Link)
        # -------------------------------------------------------------
        degraded_endpoints = []
        healthy_endpoints = []
        for r in reports:
            net = r.local_network
            is_deg = False
            deg_reasons = []

            if not net.gateway_is_reachable:
                is_deg = True
                deg_reasons.append("Default gateway unreachable")
            elif net.gateway_loss_pct > 20.0:
                is_deg = True
                deg_reasons.append(f"Gateway packet loss {net.gateway_loss_pct}%")
            elif net.gateway_rtt_ms and net.gateway_rtt_ms > 50.0:
                is_deg = True
                deg_reasons.append(f"Gateway latency {net.gateway_rtt_ms:.1f}ms")

            if net.interface_type == InterfaceType.WIFI and net.wifi:
                if net.wifi.signal_quality_pct is not None and net.wifi.signal_quality_pct < 40.0:
                    is_deg = True
                    deg_reasons.append(f"Poor Wi-Fi quality ({net.wifi.signal_quality_pct}%)")
                elif net.wifi.rssi_dbm is not None and net.wifi.rssi_dbm < -75.0:
                    is_deg = True
                    deg_reasons.append(f"Weak Wi-Fi RSSI ({net.wifi.rssi_dbm}dBm)")

            if is_deg:
                degraded_endpoints.append((r, deg_reasons))
            else:
                healthy_endpoints.append(r)

        endpoint_summary["degraded_endpoints"] = len(degraded_endpoints)
        endpoint_summary["isolated_endpoint_failures"] = [r.metadata.hostname for r, _ in degraded_endpoints]

        if degraded_endpoints:
            for rep, reasons in degraded_endpoints:
                net = rep.local_network
                is_wifi = net.interface_type == InterfaceType.WIFI and net.wifi is not None
                is_isolated = len(healthy_endpoints) >= 1 or (len(degraded_endpoints) == 1 and len(reports) == 1)

                has_direct_proof = (
                    is_wifi
                    and net.wifi
                    and net.wifi.signal_quality_pct is not None
                    and net.wifi.signal_quality_pct < 30.0
                ) or (len(healthy_endpoints) >= 1)

                status = HypothesisStatus.CONFIRMED if has_direct_proof else HypothesisStatus.PROBABLE
                ev_items = [
                    EvidenceItem(
                        domain=EvidenceDomain.ENDPOINT,
                        source=f"endpoint.{rep.metadata.hostname}",
                        identifier="Local Edge Impairment",
                        severity="HIGH" if status == HypothesisStatus.CONFIRMED else "WARNING",
                        description=f"Endpoint {rep.metadata.hostname} experiencing local link degradation: {', '.join(reasons)}.",
                        value=rep.metadata.hostname,
                    )
                ]
                if is_wifi and net.wifi:
                    ev_items.append(
                        EvidenceItem(
                            domain=EvidenceDomain.ENDPOINT,
                            source=f"endpoint.{rep.metadata.hostname}.wifi",
                            identifier=f"Wi-Fi PHY Quality: {net.wifi.signal_quality_pct}%",
                            severity="HIGH" if (net.wifi.signal_quality_pct or 0) < 30 else "WARNING",
                            description=f"Wi-Fi link signal quality {net.wifi.signal_quality_pct}%, RSSI {net.wifi.rssi_dbm} dBm.",
                            value=net.wifi.signal_quality_pct,
                        )
                    )
                if healthy_endpoints:
                    ev_items.append(
                        EvidenceItem(
                            domain=EvidenceDomain.ENDPOINT,
                            source="fleet.peer_comparison",
                            identifier="Peer Endpoints Healthy",
                            severity="INFO",
                            description=f"{len(healthy_endpoints)} peer endpoint(s) report healthy gateway connectivity.",
                            value=len(healthy_endpoints),
                        )
                    )

                hypotheses.append(
                    IncidentHypothesis(
                        status=status,
                        root_cause_domain=RootCauseDomain.LOCAL_ENDPOINT,
                        title=f"Local Edge Degradation on {rep.metadata.hostname} (Wi-Fi / LAN)" if status == HypothesisStatus.CONFIRMED else f"Probable Local Endpoint Degradation: {rep.metadata.hostname}",
                        summary=f"First-hop edge network degradation isolated to endpoint {rep.metadata.hostname}. Default gateway or Wi-Fi PHY is impaired while peer infrastructure remains operational.",
                        confidence=0.92 if status == HypothesisStatus.CONFIRMED else 0.82,
                        evidence=ev_items,
                        remediation_recommendations=[
                            f"Inspect physical Wi-Fi AP signal coverage, SNR, and channel utilization near {rep.metadata.hostname}.",
                            "Verify local Ethernet patch cord and wall jack integrity.",
                            "Check workstation network adapter driver, energy-efficient ethernet, and power savings.",
                        ],
                    )
                )

        # -------------------------------------------------------------
        # Scenario 2: DNS Infrastructure Problem
        # -------------------------------------------------------------
        dns_failures = []
        for r in reports:
            for p in r.dns_probes:
                is_failed = p.status not in (
                    DnsResolutionStatus.NOERROR,
                    DnsResolutionStatus.SUCCESS,
                    DnsResolutionStatus.NOERROR_EMPTY,
                ) or p.resolution_time_ms > 500.0
                if is_failed:
                    dns_failures.append((r, p))

        endpoint_summary["dns_failures"] = len(dns_failures)
        if dns_failures:
            transport_ok = any(r.local_network.gateway_is_reachable for r, _ in dns_failures)
            has_explicit_rcode = any(
                p.status in (DnsResolutionStatus.NXDOMAIN, DnsResolutionStatus.SERVFAIL, DnsResolutionStatus.REFUSED)
                for _, p in dns_failures
            )
            status = HypothesisStatus.CONFIRMED if (has_explicit_rcode and transport_ok) else HypothesisStatus.PROBABLE

            dns_evidence = []
            for rep, p in dns_failures:
                dns_evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.DNS,
                        source=f"endpoint.{rep.metadata.hostname}.dns",
                        identifier=f"DNS Failure: {p.query_name} ({p.status.value})",
                        severity="HIGH" if status == HypothesisStatus.CONFIRMED else "WARNING",
                        description=f"Query for '{p.query_name}' failed with status {p.status.value} (latency: {p.resolution_time_ms:.1f}ms).",
                        value=p.status.value,
                    )
                )

            hypotheses.append(
                IncidentHypothesis(
                    status=status,
                    root_cause_domain=RootCauseDomain.DNS_INFRASTRUCTURE,
                    title="Corporate DNS Infrastructure Resolution Failure" if status == HypothesisStatus.CONFIRMED else "Probable DNS Server Resolution Failure",
                    summary="Endpoints experiencing DNS resolution failures (NXDOMAIN, SERVFAIL, or timeout) while local network gateway and IP transport are functional.",
                    confidence=0.94 if status == HypothesisStatus.CONFIRMED else 0.84,
                    evidence=dns_evidence,
                    remediation_recommendations=[
                        "Verify health and responsiveness of primary and secondary corporate DNS resolvers.",
                        "Inspect recursive DNS forwarders and upstream authoritative zone servers.",
                        "Audit firewall and security perimeter rules for blocked UDP/TCP port 53 traffic.",
                    ],
                )
            )

        # -------------------------------------------------------------
        # Scenario 3: Network Infrastructure Problem (WAN / Transit Hop Failure)
        # -------------------------------------------------------------
        path_bottlenecks = []
        for r in reports:
            for path in r.path_traces:
                path_summary["total_traces"] += 1
                if path.has_route_changed:
                    path_summary["routes_diverged"] += 1

                for hop in path.hops:
                    if hop.status != HopResponseStatus.TIMEOUT_COPP:
                        if hop.loss_pct >= 20.0 or (path.end_to_end_loss_pct >= 20.0 and hop.hop_index == path.total_hops):
                            path_bottlenecks.append((r, path, hop))
                            path_summary["hops_with_loss"] += 1
                        elif hop.rtt_avg_ms and hop.rtt_avg_ms > 60.0:
                            path_bottlenecks.append((r, path, hop))

        if path_bottlenecks:
            has_zabbix_match = len(link_problems) > 0 or infra.get("link_down", False)
            status = HypothesisStatus.CONFIRMED if has_zabbix_match else HypothesisStatus.PROBABLE

            path_evidence = []
            for rep, path, hop in path_bottlenecks:
                path_evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.PATH,
                        source=f"endpoint.{rep.metadata.hostname}.path",
                        identifier=f"Hop {hop.hop_index} ({hop.ip_address or '*'}) Loss/Delay",
                        severity="HIGH" if hop.loss_pct >= 20 else "WARNING",
                        description=f"Transit hop {hop.hop_index} ({hop.ip_address or '*'}) to {path.target_id} has {hop.loss_pct}% loss, {hop.rtt_avg_ms or 0:.1f}ms RTT.",
                        value=hop.loss_pct,
                    )
                )
            for lp in link_problems:
                path_evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.NETWORK,
                        source="zabbix.problem",
                        identifier=lp.get("name", "Interface Link Alarm"),
                        severity="HIGH",
                        description=f"Active Zabbix network alarm: {lp.get('name')}",
                        value=lp.get("eventid"),
                    )
                )

            hypotheses.append(
                IncidentHypothesis(
                    status=status,
                    root_cause_domain=RootCauseDomain.NETWORK_TRANSIT_PATH,
                    title="Network Infrastructure Failure: Transit Hop Packet Loss Correlated with Core Alarm" if status == HypothesisStatus.CONFIRMED else "Probable WAN Transit Hop Degradation",
                    summary="Network path trace indicates packet loss or severe latency jump localized to transit router hops, coinciding with core network telemetry.",
                    confidence=0.93 if status == HypothesisStatus.CONFIRMED else 0.81,
                    evidence=path_evidence,
                    remediation_recommendations=[
                        "Inspect intermediate router physical interfaces, CRC error counters, and optical light levels.",
                        "Check WAN traffic shaping, policing, and egress queue drops on the identified hop.",
                        "Engage transit carrier / ISP with the hop IP and packet loss telemetry.",
                    ],
                )
            )

        # -------------------------------------------------------------
        # Scenario 4: Avaya Signaling Problem (Transport Healthy, SIP Fails)
        # -------------------------------------------------------------
        tcp_voice_ok = False
        if reports:
            for r in reports:
                for s in r.service_probes:
                    if "5061" in s.target_id or "sbce" in s.target_id or "voice" in s.target_id or s.port == 5061:
                        if s.is_reachable:
                            tcp_voice_ok = True

        if voice_event is not None and signaling is not None:
            sig_failed = signaling.outcome in (CallOutcome.FAILED, CallOutcome.TIMEOUT, CallOutcome.CONGESTION) or (
                signaling.sip_status_code is not None and signaling.sip_status_code >= 400 and signaling.sip_status_code != 486
            )
            # Only trigger VOICE_SIGNALING when underlying transport is proven operational via endpoint probing
            if sig_failed and tcp_voice_ok and not (cpu_problems or link_problems or infra.get("link_down", False)):
                has_sip_err = signaling.sip_status_code in (500, 502, 503, 504, 408)
                status = HypothesisStatus.CONFIRMED if has_sip_err else HypothesisStatus.PROBABLE

                sig_evidence = [
                    EvidenceItem(
                        domain=EvidenceDomain.SIGNALING,
                        source="voice.synthetic.signaling",
                        identifier=f"SIP Outcome: {signaling.outcome.value} (SIP {signaling.sip_status_code})",
                        severity="HIGH",
                        description=f"Synthetic SIP transaction failed with code {signaling.sip_status_code} ({signaling.outcome.value}).",
                        value=signaling.sip_status_code,
                    ),
                    EvidenceItem(
                        domain=EvidenceDomain.SERVICE,
                        source="endpoint.service.probe",
                        identifier="Avaya SBCE Port 5061 Reachable",
                        severity="INFO",
                        description="Underlying TCP/TLS transport socket to PBX/SBCE port 5061 is operational.",
                        value=1,
                    )
                ]

                hypotheses.append(
                    IncidentHypothesis(
                        status=status,
                        root_cause_domain=RootCauseDomain.VOICE_SIGNALING,
                        title=f"Avaya Telephony Signaling Outage (SIP {signaling.sip_status_code or 'Failure'}) with Operational Transport",
                        summary="Perimeter transport (TCP port 5061) is operational, but SIP signaling failed. Indicates application-level telephony or Session Manager authentication/routing failure.",
                        confidence=0.95 if status == HypothesisStatus.CONFIRMED else 0.85,
                        evidence=sig_evidence,
                        remediation_recommendations=[
                            "Check Avaya Session Manager (ASM) and Communication Manager (ACM) service and trunk status.",
                            "Verify SIP User Agent authentication credentials and TLS certificates on the SBCE.",
                            "Review ASM routing policies and ACM dial plan / hunt group configurations.",
                        ],
                    )
                )

        # -------------------------------------------------------------
        # Scenario 5: Voice Media Problem (SIP OK, One-Way Audio or High Jitter)
        # -------------------------------------------------------------
        if voice_event is not None and signaling is not None and media is not None:
            if signaling.outcome == CallOutcome.ANSWERED:
                # One-way audio
                if media.verification_level in (
                    MediaVerificationLevel.TRANSMIT_ONLY,
                    MediaVerificationLevel.RECEIVE_ONLY,
                ) or media.verification_level == MediaVerificationLevel.NO_MEDIA:
                    hypotheses.append(
                        IncidentHypothesis(
                            status=HypothesisStatus.PROBABLE,
                            root_cause_domain=RootCauseDomain.FIREWALL_NAT_ASYMMETRY,
                            title="Probable Firewall RTP Drop or NAT Asymmetry (One-Way Audio)",
                            summary="Signaling plane is functional (200 OK), but RTP audio stream was only verified in one direction. Probable stateful firewall UDP timeout or asymmetric routing.",
                            confidence=0.80,
                            evidence=[
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
                            ],
                            remediation_recommendations=[
                                "Inspect firewall stateful UDP timeout for RTP port ranges (10000-20000).",
                                "Verify NAT traversal and symmetric RTP settings on Avaya SBCE.",
                                "Audit routing tables for asymmetric path returns across firewall interfaces.",
                            ],
                        )
                    )
                # Media quality degradation (high jitter / packet loss / low MOS)
                elif media.estimated_mos and media.estimated_mos < 3.8 and not (link_problems or cpu_problems):
                    # If endpoint reports show path issues, classify as VOICE_MEDIA; otherwise classic NETWORK_LINK queueing
                    hypotheses.append(
                        IncidentHypothesis(
                            status=HypothesisStatus.PROBABLE,
                            root_cause_domain=RootCauseDomain.NETWORK_LINK,
                            title="Probable Network Queueing or Jitter Impairing Voice Quality",
                            summary="Bidirectional media is active, but network transport queueing, packet loss, or jitter is impairing voice quality.",
                            confidence=0.78,
                            evidence=[
                                EvidenceItem(
                                    domain=EvidenceDomain.MEDIA,
                                    source="voice.synthetic.media",
                                    identifier=f"Degraded MOS: {media.estimated_mos}",
                                    severity="WARNING",
                                    description=f"Estimated MOS ({media.estimated_mos}) is below 3.8 SLA threshold (Jitter: {media.jitter_ms}ms, Loss: {media.loss_pct}%).",
                                    value=media.estimated_mos,
                                )
                            ],
                            remediation_recommendations=[
                                "Verify end-to-end DSCP markings (EF for voice RTP, CS3 for SIP signaling).",
                                "Inspect WAN edge router queue drops and traffic shaping policies.",
                                "Check for bufferbloat or microburst congestion on intermediate switch links.",
                            ],
                        )
                    )

        # -------------------------------------------------------------
        # Scenario 6: Application Service Problem (DNS/TCP/TLS OK, HTTP 5xx or High TTFB)
        # -------------------------------------------------------------
        app_failures = []
        for r in reports:
            for s in r.service_probes:
                if s.http_status_code is not None or s.http_ttfb_ms is not None:
                    tcp_fast = s.tcp_connect_time_ms is not None and s.tcp_connect_time_ms < 200.0
                    tls_fast = s.tls_handshake_time_ms is None or s.tls_handshake_time_ms < 300.0
                    if (s.http_status_code and s.http_status_code >= 500) or (s.http_ttfb_ms and s.http_ttfb_ms > 1000.0):
                        app_failures.append((r, s, tcp_fast and tls_fast))

        if app_failures:
            has_5xx = any(s.http_status_code and s.http_status_code >= 500 for _, s, _ in app_failures)
            status = HypothesisStatus.CONFIRMED if has_5xx else HypothesisStatus.PROBABLE

            app_evidence = []
            for rep, s, transport_good in app_failures:
                app_evidence.append(
                    EvidenceItem(
                        domain=EvidenceDomain.SERVICE,
                        source=f"endpoint.{rep.metadata.hostname}.service",
                        identifier=f"HTTP Failure: {s.target_id} ({s.http_status_code or 'TTFB Spike'})",
                        severity="HIGH" if (s.http_status_code and s.http_status_code >= 500) else "WARNING",
                        description=f"HTTP service {s.target_id} returned status {s.http_status_code} with TTFB {s.http_ttfb_ms or 0:.1f}ms.",
                        value=s.http_status_code,
                    )
                )
                if transport_good:
                    app_evidence.append(
                        EvidenceItem(
                            domain=EvidenceDomain.SERVICE,
                            source=f"endpoint.{rep.metadata.hostname}.service",
                            identifier=f"TCP/TLS Transport Healthy: {s.target_id}",
                            severity="INFO",
                            description=f"Underlying TCP connect ({s.tcp_connect_time_ms or 0:.1f}ms) and TLS handshake ({s.tls_handshake_time_ms or 0:.1f}ms) were fast.",
                            value=s.tcp_connect_time_ms,
                        )
                    )

            hypotheses.append(
                IncidentHypothesis(
                    status=status,
                    root_cause_domain=RootCauseDomain.APPLICATION_SERVICE,
                    title="Application Backend Failure (HTTP 5xx Server Error)" if status == HypothesisStatus.CONFIRMED else "Probable Application Service Degradation (High TTFB)",
                    summary="L3/L4 network transport, TCP connection, and TLS session establishment are healthy, but application service returns HTTP 5xx errors or high TTFB latency.",
                    confidence=0.95 if status == HypothesisStatus.CONFIRMED else 0.83,
                    evidence=app_evidence,
                    remediation_recommendations=[
                        "Inspect application backend server logs, web framework error traces, and daemon status.",
                        "Verify backend database connection pool exhaustion and query response times.",
                        "Check reverse proxy (Nginx / Ingress) upstream timeout and backend node health checks.",
                    ],
                )
            )

        # -------------------------------------------------------------
        # Phase 6 Legacy Rules (Network Link, Appliance Overload, Carrier)
        # -------------------------------------------------------------
        if voice_event is not None and signaling is not None and media is not None:
            # Network Link Failure on SBCE or switch
            if (
                signaling.outcome in (CallOutcome.FAILED, CallOutcome.TIMEOUT, CallOutcome.CONGESTION)
                or media.verification_level == MediaVerificationLevel.NO_MEDIA
            ) and (link_problems or infra.get("link_down", False)):
                has_direct_proof = infra.get("direct_causality", False) or "EHOSTUNREACH" in (signaling.hangup_cause_txt or "")
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

            # Appliance Overload / CPU Saturation
            if (
                signaling.setup_time_ms > 3000
                or signaling.outcome in (CallOutcome.CONGESTION, CallOutcome.TIMEOUT)
                or (media.estimated_mos and media.estimated_mos < 3.5)
            ) and (cpu_problems or (infra.get("cpu_utilization") and infra["cpu_utilization"] > 85)):
                evidence = [
                    EvidenceItem(
                        domain=EvidenceDomain.SIGNALING,
                        source="voice.synthetic.signaling",
                        identifier="High Setup Latency / Call Failure",
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

            # Upstream Carrier / Trunk Congestion (SIP 503 while local infra is healthy)
            if (
                signaling.outcome == CallOutcome.CONGESTION
                and signaling.sip_status_code == 503
                and not (link_problems or cpu_problems)
                and not hypotheses
            ):
                hypotheses.append(
                    IncidentHypothesis(
                        status=HypothesisStatus.PROBABLE,
                        root_cause_domain=RootCauseDomain.UPSTREAM_CARRIER,
                        title="Probable Upstream Carrier / SIP Trunk Congestion",
                        summary="SIP 503 Service Unavailable returned by carrier/ITSP while all local network interfaces and SBCE CPU are nominal.",
                        confidence=0.80,
                        evidence=[
                            EvidenceItem(
                                domain=EvidenceDomain.SIGNALING,
                                source="voice.synthetic.signaling",
                                identifier="SIP 503 Service Unavailable",
                                severity="HIGH",
                                description="SIP 503 Service Unavailable received from upstream SIP entity.",
                                value=503,
                            )
                        ],
                        remediation_recommendations=[
                            "Inspect carrier SIP trunk operational status in Avaya SBCE / SM management.",
                            "Contact upstream ITSP / carrier to verify SIP trunk capacity limits and maintenance windows.",
                            "Review failover trunk routing policies to secondary PSTN / SIP route.",
                        ],
                    )
                )

            # Clean / Healthy Voice Execution
            if (
                signaling.outcome == CallOutcome.ANSWERED
                and media.verification_level == MediaVerificationLevel.BIDIRECTIONAL
                and (media.estimated_mos is None or media.estimated_mos >= 3.8)
                and not (link_problems or cpu_problems)
                and not is_stale
                and not hypotheses
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

        # Clean / Healthy Endpoint Fleet Execution (when no voice event and no degradations)
        if not hypotheses and not is_stale:
            if reports and all(r.local_network.gateway_is_reachable for r in reports):
                hypotheses.append(
                    IncidentHypothesis(
                        status=HypothesisStatus.HEALTHY,
                        root_cause_domain=RootCauseDomain.HEALTHY,
                        title="Endpoint Fleet Nominal and Healthy",
                        summary=f"All {len(reports)} monitored endpoint(s) report healthy edge connectivity, low gateway latency, fast DNS, and available services.",
                        confidence=1.0,
                        evidence=[
                            EvidenceItem(
                                domain=EvidenceDomain.ENDPOINT,
                                source="fleet.health_check",
                                identifier="All Endpoints Healthy",
                                severity="INFO",
                                description=f"{len(reports)} endpoint(s) reporting nominal telemetry.",
                                value=len(reports),
                            )
                        ],
                        remediation_recommendations=[],
                    )
                )

        # Stale Telemetry Guard
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

        # -------------------------------------------------------------
        # Scenario 7: Topology-Aware Network Dependency & Change Correlation
        # -------------------------------------------------------------
        changes = topology_changes or []
        if changes:
            # Check if any changes correlate with existing network/transport hypotheses
            for ch in changes:
                ch_type = getattr(ch, "change_type", str(ch))
                target_id = getattr(ch, "target_entity_id", "")
                target_type = getattr(ch, "target_entity_type", "")

                for hyp in hypotheses:
                    if hyp.root_cause_domain in (
                        RootCauseDomain.NETWORK_LINK,
                        RootCauseDomain.NETWORK_TRANSIT,
                        RootCauseDomain.LOCAL_NETWORK,
                    ):
                        hyp.status = HypothesisStatus.CONFIRMED
                        hyp.confidence = max(hyp.confidence, 0.98)
                        hyp.evidence.append(
                            EvidenceItem(
                                domain=EvidenceDomain.NETWORK,
                                source="topology.change_detector",
                                identifier=f"Topological Change: {ch_type} on {target_id}",
                                severity="CRITICAL" if ("DOWN" in ch_type or "LOST" in ch_type) else "HIGH",
                                description=f"Corroborated by physical network change ({ch_type}) on {target_type} {target_id}.",
                                value=ch_type,
                            )
                        )

            # If no hypotheses yet and we have high-impact link/neighbour changes
            if not hypotheses:
                down_changes = [
                    c for c in changes
                    if getattr(c, "change_type", "") in ("LINK_DOWN", "NEIGHBOUR_LOST", "UPLINK_FLAP")
                ]
                if down_changes:
                    ch0 = down_changes[0]
                    ch_type = getattr(ch0, "change_type", "LINK_DOWN")
                    target_id = getattr(ch0, "target_entity_id", "unknown")
                    hypotheses.append(
                        IncidentHypothesis(
                            status=HypothesisStatus.CONFIRMED,
                            root_cause_domain=RootCauseDomain.NETWORK_LINK,
                            title=f"Physical Network Link Outage ({ch_type} on {target_id})",
                            summary=f"Automated topology change detector identified critical state transition: {ch_type} on {target_id}.",
                            confidence=0.98,
                            evidence=[
                                EvidenceItem(
                                    domain=EvidenceDomain.NETWORK,
                                    source="topology.change_detector",
                                    identifier=f"{ch_type}: {target_id}",
                                    severity="CRITICAL",
                                    description=f"Physical link or neighbor outage detected on {target_id}.",
                                    value=ch_type,
                                )
                            ],
                            remediation_recommendations=[
                                f"Inspect physical cable, optical transceiver, or patch panel for {target_id}.",
                                "Verify Spanning Tree and port status on adjacent switch.",
                            ],
                        )
                    )

        # Default fallback if no specific scenario matched
        if not hypotheses:
            hypotheses.append(
                IncidentHypothesis(
                    status=HypothesisStatus.INCONCLUSIVE,
                    root_cause_domain=RootCauseDomain.UNKNOWN,
                    title="Inconclusive Telemetry Analysis",
                    summary="Telemetry patterns did not match known failure signatures. Further telemetry collection required.",
                    confidence=0.50,
                    evidence=[],
                    remediation_recommendations=["Review raw logs and device alarms for abnormal disconnect reasons."],
                )
            )

        # -------------------------------------------------------------
        # 5. Compute Overall Health State & Health Score
        # -------------------------------------------------------------
        primary = max(hypotheses, key=lambda h: h.confidence)
        if is_stale and primary.status != HypothesisStatus.HEALTHY and not (link_problems or cpu_problems):
            health_state = ServiceHealthState.UNKNOWN
            health_score = 50.0
        elif primary.status == HypothesisStatus.HEALTHY:
            health_state = ServiceHealthState.HEALTHY
            health_score = 98.0
            if media and media.estimated_mos:
                health_score = min(100.0, 80.0 + (media.estimated_mos / 4.5) * 20.0)
        elif primary.root_cause_domain in (
            RootCauseDomain.NETWORK_LINK,
            RootCauseDomain.FIREWALL_NAT_ASYMMETRY,
            RootCauseDomain.APPLIANCE_OVERLOAD,
            RootCauseDomain.UPSTREAM_CARRIER,
            RootCauseDomain.VOICE_SIGNALING,
            RootCauseDomain.APPLICATION_SERVICE,
            RootCauseDomain.DNS_INFRASTRUCTURE,
        ) and (
            (signaling and signaling.outcome != CallOutcome.ANSWERED)
            or (media and media.verification_level in (MediaVerificationLevel.TRANSMIT_ONLY, MediaVerificationLevel.RECEIVE_ONLY))
            or primary.status == HypothesisStatus.CONFIRMED
        ):
            health_state = ServiceHealthState.CRITICAL
            health_score = 15.0
        elif primary.root_cause_domain in (
            RootCauseDomain.NETWORK_LINK,
            RootCauseDomain.APPLIANCE_OVERLOAD,
            RootCauseDomain.LOCAL_ENDPOINT,
            RootCauseDomain.NETWORK_TRANSIT_PATH,
            RootCauseDomain.VOICE_MEDIA,
            RootCauseDomain.APPLICATION_SERVICE,
            RootCauseDomain.DNS_INFRASTRUCTURE,
        ) or (media and media.estimated_mos and media.estimated_mos < 3.8):
            health_state = ServiceHealthState.DEGRADED
            health_score = 65.0
        else:
            health_state = ServiceHealthState.UNKNOWN
            health_score = 50.0

        now = (voice_event.collection_timestamp if voice_event else None) or time.time()
        return ServiceAssuranceReport(
            timestamp=now,
            service_id=service_id,
            target_host=target_host,
            environment=environment,
            is_stale=is_stale,
            health_state=health_state,
            health_score=health_score,
            signaling_summary=sig_summary,
            media_summary=media_summary,
            infrastructure_summary=infra_summary,
            endpoint_summary=endpoint_summary,
            path_summary=path_summary,
            hypotheses=hypotheses,
            active_problems=active_problems,
        )
