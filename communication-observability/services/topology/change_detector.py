"""Network Topology Change Detector and Causal Timeline Analyzer for Nawari."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from services.topology.models import (
    ChangeType,
    Device,
    Interface,
    Layer2Link,
    RoutingAdjacency,
    TargetEntityType,
    TopologyChange,
)


class TopologyChangeDetector:
    """Detects structural modifications and operational transitions between topology snapshots."""

    def __init__(self, flap_threshold: int = 3, flap_window_seconds: int = 300) -> None:
        self.flap_threshold = flap_threshold
        self.flap_window_seconds = flap_window_seconds
        # interface_id -> list of float timestamps of state changes
        self._transition_history: dict[str, list[float]] = defaultdict(list)
        # In-memory change audit log
        self.changes_log: list[TopologyChange] = []

    def diff_snapshots(
        self,
        prev_devices: dict[str, Device],
        curr_devices: dict[str, Device],
        prev_interfaces: dict[str, Interface],
        curr_interfaces: dict[str, Interface],
        prev_links: dict[str, Layer2Link],
        curr_links: dict[str, Layer2Link],
        prev_adjacencies: dict[str, RoutingAdjacency] | None = None,
        curr_adjacencies: dict[str, RoutingAdjacency] | None = None,
    ) -> list[TopologyChange]:
        """Compare previous and current topology snapshots and return list of detected TopologyChange events."""
        detected_changes: list[TopologyChange] = []
        now_ts = datetime.now(timezone.utc).timestamp()

        # 1. Device additions and removals
        for did, dev in curr_devices.items():
            if did not in prev_devices:
                change = TopologyChange(
                    change_type=ChangeType.DEVICE_ADDED,
                    target_entity_type=TargetEntityType.DEVICE,
                    target_entity_id=did,
                    after_state=dev.to_dict(),
                    detected_by="TOPOLOGY_DIFF_ENGINE",
                )
                detected_changes.append(change)

        for did, dev in prev_devices.items():
            if did not in curr_devices:
                change = TopologyChange(
                    change_type=ChangeType.DEVICE_REMOVED,
                    target_entity_type=TargetEntityType.DEVICE,
                    target_entity_id=did,
                    before_state=dev.to_dict(),
                    detected_by="TOPOLOGY_DIFF_ENGINE",
                )
                detected_changes.append(change)

        # 2. Interface state, speed, and VLAN changes
        for if_id, curr_if in curr_interfaces.items():
            prev_if = prev_interfaces.get(if_id)
            if not prev_if:
                continue

            # OperStatus transition (LINK_UP / LINK_DOWN)
            if curr_if.oper_status != prev_if.oper_status:
                self._record_transition(if_id, now_ts)
                c_type = ChangeType.LINK_UP if curr_if.oper_status == 1 else ChangeType.LINK_DOWN
                change = TopologyChange(
                    change_type=c_type,
                    target_entity_type=TargetEntityType.INTERFACE,
                    target_entity_id=if_id,
                    before_state={"oper_status": prev_if.oper_status, "speed_bps": prev_if.speed_bps},
                    after_state={"oper_status": curr_if.oper_status, "speed_bps": curr_if.speed_bps},
                    detected_by="IF_MIB_POLLER",
                )
                detected_changes.append(change)

            # Link speed degradation
            if (
                prev_if.speed_bps
                and curr_if.speed_bps
                and curr_if.speed_bps < prev_if.speed_bps
            ):
                change = TopologyChange(
                    change_type=ChangeType.SPEED_CHANGED,
                    target_entity_type=TargetEntityType.INTERFACE,
                    target_entity_id=if_id,
                    before_state={"speed_bps": prev_if.speed_bps},
                    after_state={"speed_bps": curr_if.speed_bps},
                    detected_by="IF_MIB_POLLER",
                )
                detected_changes.append(change)

            # VLAN changes on trunks
            if prev_if.tagged_vlans != curr_if.tagged_vlans:
                change = TopologyChange(
                    change_type=ChangeType.VLAN_MEMBERSHIP_CHANGED,
                    target_entity_type=TargetEntityType.INTERFACE,
                    target_entity_id=if_id,
                    before_state={"tagged_vlans": prev_if.tagged_vlans},
                    after_state={"tagged_vlans": curr_if.tagged_vlans},
                    detected_by="VLAN_MIB_POLLER",
                )
                detected_changes.append(change)

        # 3. Layer 2 Links (NEIGHBOUR_LOST / NEIGHBOUR_ADDED)
        for lid, link in curr_links.items():
            if lid not in prev_links:
                change = TopologyChange(
                    change_type=ChangeType.NEIGHBOUR_ADDED,
                    target_entity_type=TargetEntityType.LINK,
                    target_entity_id=lid,
                    after_state=link.to_dict(),
                    detected_by="LLDP_DISCOVERY",
                )
                detected_changes.append(change)

        for lid, link in prev_links.items():
            if lid not in curr_links:
                change = TopologyChange(
                    change_type=ChangeType.NEIGHBOUR_LOST,
                    target_entity_type=TargetEntityType.LINK,
                    target_entity_id=lid,
                    before_state=link.to_dict(),
                    detected_by="LLDP_DISCOVERY",
                )
                detected_changes.append(change)

        # 4. Routing Adjacencies
        if prev_adjacencies and curr_adjacencies:
            for aid, curr_adj in curr_adjacencies.items():
                prev_adj = prev_adjacencies.get(aid)
                if prev_adj and prev_adj.state != curr_adj.state:
                    change = TopologyChange(
                        change_type=ChangeType.ROUTE_CHANGED,
                        target_entity_type=TargetEntityType.ADJACENCY,
                        target_entity_id=aid,
                        before_state={"state": prev_adj.state, "metric": prev_adj.metric},
                        after_state={"state": curr_adj.state, "metric": curr_adj.metric},
                        detected_by="ROUTING_POLLER",
                    )
                    detected_changes.append(change)

        self.changes_log.extend(detected_changes)
        return detected_changes

    def _record_transition(self, if_id: str, ts: float) -> None:
        history = self._transition_history[if_id]
        history.append(ts)
        # Purge transitions outside window
        cutoff = ts - self.flap_window_seconds
        self._transition_history[if_id] = [t for t in history if t >= cutoff]

    def is_interface_flapping(self, if_id: str, current_ts: float | None = None) -> bool:
        """Check if interface exceeded flap threshold in rolling window."""
        ts = current_ts or datetime.now(timezone.utc).timestamp()
        cutoff = ts - self.flap_window_seconds
        flaps = [t for t in self._transition_history.get(if_id, []) if t >= cutoff]
        return len(flaps) >= self.flap_threshold

    def find_recent_changes_for_entity(
        self,
        entity_id: str,
        within_seconds: int = 900,
        reference_time_iso: str | None = None,
    ) -> list[TopologyChange]:
        """Find topology changes affecting an entity (or its links) within a time window."""
        if reference_time_iso:
            try:
                ref_dt = datetime.fromisoformat(reference_time_iso.replace("Z", "+00:00"))
            except ValueError:
                ref_dt = datetime.now(timezone.utc)
        else:
            ref_dt = datetime.now(timezone.utc)

        ref_ts = ref_dt.timestamp()
        matches = []

        for ch in self.changes_log:
            if entity_id in ch.target_entity_id:
                try:
                    ch_dt = datetime.fromisoformat((ch.timestamp or "").replace("Z", "+00:00"))
                    ch_ts = ch_dt.timestamp()
                except ValueError:
                    ch_ts = ref_ts

                if 0 <= (ref_ts - ch_ts) <= within_seconds:
                    matches.append(ch)

        return matches

