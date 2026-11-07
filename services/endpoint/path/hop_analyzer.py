"""Hop Classification, CoPP Guard, Loss Localization, and Path Anomaly Engine."""

from __future__ import annotations

import hashlib
import statistics
from typing import Any, Dict, List, Optional

from services.endpoint.models import HopResponseStatus, HopTelemetry, PathTelemetry
from services.endpoint.path.models import RawHopProbe


class HopAnalyzer:
    """Performs deep topological and statistical analysis on raw traceroute hops.

    Implements:
    1. CoPP Guard: Differentiating intermediate router rate-limiting from actual outages.
    2. Loss Onset Localization: Pinpointing the exact hop where packet loss originates.
    3. Latency Jump Detection: Localizing propagation delays (Delta RTT > 40ms).
    4. Path Hashing & Churn: Detecting route shifts via SHA-256 signatures and divergent hop index.
    """

    DEFAULT_LOSS_THRESHOLD_PCT = 20.0
    DEFAULT_LATENCY_JUMP_MS = 40.0

    @classmethod
    def analyze_hops(
        cls,
        raw_hops: List[Dict[str, Any]],
        target_id: str,
        destination_ip: str,
        protocol: str = "UDP",
        previous_path_hash: Optional[str] = None,
        previous_responsive_ips: Optional[List[str]] = None,
        loss_threshold_pct: float = DEFAULT_LOSS_THRESHOLD_PCT,
        latency_jump_threshold_ms: float = DEFAULT_LATENCY_JUMP_MS,
    ) -> PathTelemetry:
        """Process raw hop dictionary data into fully classified PathTelemetry."""
        if not raw_hops:
            # Empty / unreachable trace
            empty_hash = hashlib.sha256(b"EMPTY_TRACE").hexdigest()
            return PathTelemetry(
                target_id=target_id,
                target_ip=destination_ip,
                protocol=protocol,
                total_hops=0,
                end_to_end_rtt_ms=None,
                end_to_end_loss_pct=100.0,
                path_hash=empty_hash,
                has_route_changed=bool(previous_path_hash and previous_path_hash != empty_hash),
                hops=[],
                loss_onset_hop=1,
                latency_onset_hop=None,
                divergent_hop_index=1 if previous_path_hash else None,
            )

        # 1. Pre-calculate basic statistics for each hop
        stats_list = []
        for raw in raw_hops:
            sent = raw.get("probes_sent", 3)
            rec = raw.get("probes_received", 0)
            rtts: List[float] = raw.get("rtts_ms", [])

            loss_pct = ((sent - rec) / sent * 100.0) if sent > 0 else 100.0
            rtt_min = min(rtts) if rtts else None
            rtt_avg = (sum(rtts) / len(rtts)) if rtts else None
            rtt_max = max(rtts) if rtts else None
            rtt_stddev = statistics.stdev(rtts) if len(rtts) > 1 else (0.0 if rtts else None)

            stats_list.append({
                "hop_index": raw.get("hop_index", len(stats_list) + 1),
                "ip_address": raw.get("ip_address"),
                "probes_sent": sent,
                "probes_received": rec,
                "loss_pct": loss_pct,
                "rtt_min": rtt_min,
                "rtt_avg": rtt_avg,
                "rtt_max": rtt_max,
                "rtt_stddev": rtt_stddev,
                "mpls_labels": raw.get("mpls_labels", []),
            })

        # Determine if destination was reached
        dest_reached = False
        dest_loss_pct = 100.0
        # Check last hop or any hop matching destination_ip
        for s in reversed(stats_list):
            if s["ip_address"] == destination_ip or (s["probes_received"] > 0 and s == stats_list[-1]):
                dest_reached = s["probes_received"] > 0
                dest_loss_pct = s["loss_pct"]
                break

        # 2. Evaluate CoPP Guard and Hop Status
        classified_hops: List[HopTelemetry] = []
        last_responsive_rtt: Optional[float] = None
        latency_onset_hop: Optional[int] = None

        for idx, s in enumerate(stats_list):
            hop_idx = s["hop_index"]
            rec = s["probes_received"]

            if rec > 0:
                status = HopResponseStatus.RESPONSIVE
                # Calculate Delta RTT relative to previous responsive hop
                if last_responsive_rtt is not None and s["rtt_avg"] is not None:
                    delta_rtt = round(s["rtt_avg"] - last_responsive_rtt, 3)
                else:
                    delta_rtt = s["rtt_avg"]

                if s["rtt_avg"] is not None:
                    last_responsive_rtt = s["rtt_avg"]

                # Check for Latency Jump
                if delta_rtt is not None and delta_rtt > latency_jump_threshold_ms:
                    if latency_onset_hop is None:
                        latency_onset_hop = hop_idx

                rtt_avg_val = s["rtt_avg"]
            else:
                # 0 probes received: Check CoPP Guard
                # Does any subsequent hop have successful probe responses?
                downstream_responsive = any(
                    down["probes_received"] > 0 for down in stats_list[idx + 1 :]
                )

                if downstream_responsive and dest_loss_pct < loss_threshold_pct:
                    # Non-impairing intermediate drop -> Control Plane Policing (CoPP)
                    status = HopResponseStatus.TIMEOUT_COPP
                else:
                    status = HopResponseStatus.UNREACHABLE

                # Invariant: TIMEOUT_COPP must not have valid RTT
                rtt_avg_val = None
                delta_rtt = None

            hop_telem = HopTelemetry(
                hop_index=hop_idx,
                ip_address=s["ip_address"],
                rdns_hostname=None,
                asn=None,
                as_org=None,
                rtt_min_ms=s["rtt_min"] if status == HopResponseStatus.RESPONSIVE else None,
                rtt_avg_ms=rtt_avg_val,
                rtt_max_ms=s["rtt_max"] if status == HopResponseStatus.RESPONSIVE else None,
                rtt_stddev_ms=s["rtt_stddev"] if status == HopResponseStatus.RESPONSIVE else None,
                delta_rtt_ms=delta_rtt,
                loss_pct=s["loss_pct"],
                status=status,
                mpls_labels=s["mpls_labels"],
            )
            classified_hops.append(hop_telem)

        # 3. Evaluate Loss Onset Localization
        loss_onset_hop: Optional[int] = None
        for i, h in enumerate(classified_hops):
            # Hop is candidate for loss onset if loss exceeds threshold and is not CoPP
            if h.loss_pct >= loss_threshold_pct and h.status != HopResponseStatus.TIMEOUT_COPP:
                # Check that all subsequent hops to the end also experience loss >= threshold
                subsequent_all_loss = all(
                    sub.loss_pct >= loss_threshold_pct for sub in classified_hops[i:]
                )
                if subsequent_all_loss:
                    loss_onset_hop = h.hop_index
                    break

        # 4. Path Hashing & Route Change Detection
        responsive_ips = [
            h.ip_address
            for h in classified_hops
            if h.ip_address and h.status == HopResponseStatus.RESPONSIVE
        ]
        if responsive_ips:
            path_sig = ":".join(responsive_ips)
            path_hash = hashlib.sha256(path_sig.encode("utf-8")).hexdigest()
        else:
            path_hash = hashlib.sha256(b"NO_RESPONSIVE_HOPS").hexdigest()

        has_route_changed = False
        divergent_hop_index: Optional[int] = None

        if previous_path_hash is not None and previous_path_hash != path_hash:
            has_route_changed = True
            # Calculate divergent hop index if previous IP list is supplied
            if previous_responsive_ips:
                min_len = min(len(responsive_ips), len(previous_responsive_ips))
                for k in range(min_len):
                    if responsive_ips[k] != previous_responsive_ips[k]:
                        divergent_hop_index = k + 1
                        break
                if divergent_hop_index is None and len(responsive_ips) != len(previous_responsive_ips):
                    divergent_hop_index = min_len + 1
            else:
                divergent_hop_index = 1

        # 5. End-to-End Metrics
        if dest_reached:
            # Find destination hop RTT and loss
            dest_hop = classified_hops[-1]
            for h in reversed(classified_hops):
                if h.ip_address == destination_ip or h.status == HopResponseStatus.RESPONSIVE:
                    dest_hop = h
                    break
            end_to_end_rtt = dest_hop.rtt_avg_ms
            end_to_end_loss = dest_hop.loss_pct
        else:
            end_to_end_rtt = None
            end_to_end_loss = 100.0

        return PathTelemetry(
            target_id=target_id,
            target_ip=destination_ip,
            protocol=protocol,
            total_hops=len(classified_hops),
            end_to_end_rtt_ms=end_to_end_rtt,
            end_to_end_loss_pct=end_to_end_loss,
            path_hash=path_hash,
            has_route_changed=has_route_changed,
            hops=classified_hops,
            loss_onset_hop=loss_onset_hop,
            latency_onset_hop=latency_onset_hop,
            divergent_hop_index=divergent_hop_index,
        )

