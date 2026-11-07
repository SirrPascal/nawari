"""Zabbix Trapper and Low-Level Discovery (LLD) Metric Mapper for Endpoint Telemetry."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import (
    DnsResolutionStatus,
    EndpointTelemetryReport,
    HopResponseStatus,
    InterfaceType,
    TelemetricEnvironment,
)
from services.voice.zabbix_sender import ZabbixMetric


class ZabbixEndpointMapper:
    """Translates canonical EndpointTelemetryReport into Zabbix Trapper metrics and LLD packets.

    Strictly enforces:
    - Invariant 1 (CoPP Guard): TIMEOUT_COPP hops omit RTT metrics; status mapped to numeric 1.
    - Invariant 2 (Wi-Fi Isolation): Wi-Fi metrics strictly omitted if interface_type != WIFI.
    - Invariant 3 (Authoritative Provenance): Injects server-verified environment.
    - Units conversion: All latency metrics normalized to seconds (Zabbix 's' unit).
    """

    @classmethod
    def map_report_to_metrics(
        cls,
        report: EndpointTelemetryReport,
        authoritative_environment: TelemetricEnvironment,
        server_received_timestamp_ns: Optional[int] = None,
    ) -> List[ZabbixMetric]:
        """Convert EndpointTelemetryReport to list of ZabbixMetric objects for trapper ingestion."""
        hostname = report.metadata.hostname
        clock = int(report.metadata.timestamp_ns / 1_000_000_000)
        metrics: List[ZabbixMetric] = []

        # -------------------------------------------------------------
        # 1. Static Metadata Items
        # -------------------------------------------------------------
        meta_dict = {
            "agent_id": report.metadata.agent_id,
            "hostname": report.metadata.hostname,
            "os_name": report.metadata.os_name,
            "os_version": report.metadata.os_version,
            "agent_version": report.metadata.agent_version,
            "environment": authoritative_environment.value,
            "timestamp_ns": report.metadata.timestamp_ns,
            "server_received_timestamp_ns": server_received_timestamp_ns,
        }
        metrics.append(
            ZabbixMetric(
                host=hostname,
                key="endpoint.info",
                value=json.dumps(meta_dict),
                clock=clock,
            )
        )

        # Environment metric: 0 = MOCK_SIMULATED, 1 = PHYSICAL_PRODUCTION
        env_val = 1 if authoritative_environment == TelemetricEnvironment.PHYSICAL_PRODUCTION else 0
        metrics.append(
            ZabbixMetric(
                host=hostname,
                key="endpoint.environment",
                value=env_val,
                clock=clock,
            )
        )

        # -------------------------------------------------------------
        # 2. Local Network Telemetry
        # -------------------------------------------------------------
        local_net = report.local_network

        # Interface type: 0=Ethernet, 1=Wi-Fi, 2=VPN, 3=Other/Loopback
        if local_net.interface_type == InterfaceType.ETHERNET:
            iface_val = 0
        elif local_net.interface_type == InterfaceType.WIFI:
            iface_val = 1
        elif local_net.interface_type == InterfaceType.VPN:
            iface_val = 2
        else:
            iface_val = 3

        metrics.append(
            ZabbixMetric(
                host=hostname,
                key="endpoint.network.interface.type",
                value=iface_val,
                clock=clock,
            )
        )

        # Gateway metrics
        if local_net.gateway_is_reachable and local_net.gateway_rtt_ms is not None:
            metrics.append(
                ZabbixMetric(
                    host=hostname,
                    key="endpoint.network.gateway.rtt",
                    value=round(local_net.gateway_rtt_ms / 1000.0, 6),
                    clock=clock,
                )
            )

        metrics.append(
            ZabbixMetric(
                host=hostname,
                key="endpoint.network.gateway.loss",
                value=round(local_net.gateway_loss_pct, 2),
                clock=clock,
            )
        )

        # Invariant 2: Wi-Fi metric isolation (strictly omitted if not Wi-Fi)
        if local_net.interface_type == InterfaceType.WIFI and local_net.wifi is not None:
            if local_net.wifi.rssi_dbm is not None:
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key="endpoint.network.wifi.rssi",
                        value=float(local_net.wifi.rssi_dbm),
                        clock=clock,
                    )
                )
            if local_net.wifi.signal_quality_pct is not None:
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key="endpoint.network.wifi.quality",
                        value=float(local_net.wifi.signal_quality_pct),
                        clock=clock,
                    )
                )

        # -------------------------------------------------------------
        # 3. DNS Probe Telemetry & LLD
        # -------------------------------------------------------------
        if report.dns_probes:
            # LLD discovery rule
            dns_lld = [{"{#TARGET}": p.query_name} for p in report.dns_probes]
            # Deduplicate targets
            unique_targets = {p["{#TARGET}"]: p for p in dns_lld}.values()
            metrics.append(
                ZabbixMetric(
                    host=hostname,
                    key="nawari.endpoint.dns.discovery",
                    value=json.dumps(list(unique_targets)),
                    clock=clock,
                )
            )

            # DNS probe items
            for p in report.dns_probes:
                t = p.query_name
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.dns.latency[{t}]",
                        value=round(p.resolution_time_ms / 1000.0, 6),
                        clock=clock,
                    )
                )

                # Status mapping: 0=Success, 1=NXDomain, 2=ServFail, 3=Timeout, 4=Refused, 5=Error
                status_map = {
                    DnsResolutionStatus.NOERROR: 0,
                    DnsResolutionStatus.SUCCESS: 0,
                    DnsResolutionStatus.NOERROR_EMPTY: 0,
                    DnsResolutionStatus.NXDOMAIN: 1,
                    DnsResolutionStatus.SERVFAIL: 2,
                    DnsResolutionStatus.TIMEOUT: 3,
                    DnsResolutionStatus.REFUSED: 4,
                    DnsResolutionStatus.ERROR: 5,
                }
                status_val = status_map.get(p.status, 5)
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.dns.status[{t}]",
                        value=status_val,
                        clock=clock,
                    )
                )

        # -------------------------------------------------------------
        # 4. Service Connectivity Telemetry & LLD
        # -------------------------------------------------------------
        if report.service_probes:
            # LLD discovery rule
            service_lld = [
                {"{#TARGET}": s.target_id, "{#TARGET_NAME}": s.target_name}
                for s in report.service_probes
            ]
            metrics.append(
                ZabbixMetric(
                    host=hostname,
                    key="nawari.endpoint.service.discovery",
                    value=json.dumps(service_lld),
                    clock=clock,
                )
            )

            for s in report.service_probes:
                t = s.target_id
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.service.reachable[{t}]",
                        value=1 if s.is_reachable else 0,
                        clock=clock,
                    )
                )

                if s.tcp_connect_time_ms is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.service.tcp_connect[{t}]",
                            value=round(s.tcp_connect_time_ms / 1000.0, 6),
                            clock=clock,
                        )
                    )

                if s.tls_handshake_time_ms is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.service.tls_handshake[{t}]",
                            value=round(s.tls_handshake_time_ms / 1000.0, 6),
                            clock=clock,
                        )
                    )

                if s.http_status_code is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.service.http_status[{t}]",
                            value=int(s.http_status_code),
                            clock=clock,
                        )
                    )

                if s.http_ttfb_ms is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.service.http_ttfb[{t}]",
                            value=round(s.http_ttfb_ms / 1000.0, 6),
                            clock=clock,
                        )
                    )

                if s.http_total_time_ms is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.service.http_total[{t}]",
                            value=round(s.http_total_time_ms / 1000.0, 6),
                            clock=clock,
                        )
                    )

        # -------------------------------------------------------------
        # 5. Network Path Telemetry & Dynamic Hop LLD
        # -------------------------------------------------------------
        if report.path_traces:
            path_lld = [
                {"{#TARGET}": p.target_id, "{#TARGET_IP}": p.target_ip}
                for p in report.path_traces
            ]
            metrics.append(
                ZabbixMetric(
                    host=hostname,
                    key="nawari.endpoint.path.discovery",
                    value=json.dumps(path_lld),
                    clock=clock,
                )
            )

            for path in report.path_traces:
                t = path.target_id
                if path.end_to_end_rtt_ms is not None:
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"endpoint.path.e2e_rtt[{t}]",
                            value=round(path.end_to_end_rtt_ms / 1000.0, 6),
                            clock=clock,
                        )
                    )

                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.path.e2e_loss[{t}]",
                        value=round(path.end_to_end_loss_pct, 2),
                        clock=clock,
                    )
                )

                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.path.route_changed[{t}]",
                        value=1 if path.has_route_changed else 0,
                        clock=clock,
                    )
                )

                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"endpoint.path.total_hops[{t}]",
                        value=int(path.total_hops),
                        clock=clock,
                    )
                )

                # Dynamic Hop LLD
                hop_lld = [
                    {"{#TARGET}": t, "{#HOP_INDEX}": str(h.hop_index)}
                    for h in path.hops
                ]
                metrics.append(
                    ZabbixMetric(
                        host=hostname,
                        key=f"nawari.endpoint.hop.discovery[{t}]",
                        value=json.dumps(hop_lld),
                        clock=clock,
                    )
                )

                # Hop prototype metrics
                for h in path.hops:
                    hop_idx = h.hop_index
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"nawari.path.hop.ip[{t},{hop_idx}]",
                            value=h.ip_address or "*",
                            clock=clock,
                        )
                    )

                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"nawari.path.hop.loss[{t},{hop_idx}]",
                            value=round(h.loss_pct, 2),
                            clock=clock,
                        )
                    )

                    # Status mapping: 0=Responsive, 1=CoPP Rate-Limited, 2=Unreachable, 3=Anonymous MPLS
                    status_map = {
                        HopResponseStatus.RESPONSIVE: 0,
                        HopResponseStatus.TIMEOUT_COPP: 1,
                        HopResponseStatus.UNREACHABLE: 2,
                        HopResponseStatus.ANONYMOUS_MPLS: 3,
                    }
                    metrics.append(
                        ZabbixMetric(
                            host=hostname,
                            key=f"nawari.path.hop.status[{t},{hop_idx}]",
                            value=status_map.get(h.status, 2),
                            clock=clock,
                        )
                    )

                    # Invariant 1 (CoPP Guard): TIMEOUT_COPP or None RTT is strictly omitted!
                    if h.status != HopResponseStatus.TIMEOUT_COPP and h.rtt_avg_ms is not None:
                        metrics.append(
                            ZabbixMetric(
                                host=hostname,
                                key=f"nawari.path.hop.rtt[{t},{hop_idx}]",
                                value=round(h.rtt_avg_ms / 1000.0, 6),
                                clock=clock,
                            )
                        )

        return metrics

