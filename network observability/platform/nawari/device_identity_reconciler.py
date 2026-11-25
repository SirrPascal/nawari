"""Deterministic Multi-Source Device Identity Reconciliation Engine for Nawari.

Reconciles network device identities across SolarWinds, Zabbix, Grafana, and Nawari.
Enforces the 8-category match taxonomy, strict HA/cluster separation, switch-stack
awareness, and safety checks before proposing visible name changes.
Includes continuous drift detection.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .solarwinds_inventory_importer import SolarWindsNodeRecord
    from .zabbix_inventory_collector import ZabbixHostRecord
except ImportError:
    from solarwinds_inventory_importer import SolarWindsNodeRecord
    from zabbix_inventory_collector import ZabbixHostRecord

logger = logging.getLogger("nawari.device.reconciler")


class MatchConfidence(str, enum.Enum):
    """Authoritative taxonomy for cross-inventory device matching."""
    EXACT_VERIFIED_MATCH = "EXACT_VERIFIED_MATCH"
    HIGH_CONFIDENCE_MATCH = "HIGH_CONFIDENCE_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    CONFLICTING_MATCH = "CONFLICTING_MATCH"
    SOLARWINDS_ONLY = "SOLARWINDS_ONLY"
    ZABBIX_ONLY = "ZABBIX_ONLY"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


@dataclasses.dataclass
class ReconciliationItem:
    """Reconciliation proposal and evidence for a single device identity."""
    canonical_id: str
    confidence: MatchConfidence
    solarwinds_node: Optional[SolarWindsNodeRecord]
    zabbix_host: Optional[ZabbixHostRecord]
    current_zabbix_host: str  # Technical hostname (MUST be preserved)
    current_zabbix_visible_name: str
    proposed_zabbix_visible_name: str
    matching_evidence: str
    is_safe_to_rename: bool
    requires_manual_review: bool
    conflict_reason: Optional[str] = None
    is_ha_cluster_node: bool = False
    is_switch_stack: bool = False
    rename_operation: str = "NOOP"  # RENAME, NOOP, REVIEW, BLOCKED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "confidence": self.confidence.value,
            "current_zabbix_host": self.current_zabbix_host,
            "current_zabbix_visible_name": self.current_zabbix_visible_name,
            "proposed_zabbix_visible_name": self.proposed_zabbix_visible_name,
            "solarwinds_node_id": self.solarwinds_node.node_id if self.solarwinds_node else None,
            "solarwinds_caption": self.solarwinds_node.caption if self.solarwinds_node else None,
            "solarwinds_ip": self.solarwinds_node.ip_address if self.solarwinds_node else None,
            "zabbix_host_id": self.zabbix_host.host_id if self.zabbix_host else None,
            "zabbix_primary_ip": self.zabbix_host.primary_ip if self.zabbix_host else None,
            "matching_evidence": self.matching_evidence,
            "is_safe_to_rename": self.is_safe_to_rename,
            "requires_manual_review": self.requires_manual_review,
            "conflict_reason": self.conflict_reason,
            "is_ha_cluster_node": self.is_ha_cluster_node,
            "is_switch_stack": self.is_switch_stack,
            "rename_operation": self.rename_operation,
        }


@dataclasses.dataclass
class DriftReport:
    """Findings from periodic device identity drift detection."""
    timestamp: float
    new_solarwinds_devices: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    new_zabbix_hosts: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    caption_changes: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    ip_changes: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    missing_in_solarwinds: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    conflicting_identities: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    total_drift_items: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


class DeviceIdentityReconciler:
    """Engine for correlating SolarWinds nodes and Zabbix hosts."""

    def __init__(self, ha_cluster_vips: Optional[Set[str]] = None):
        self.ha_cluster_vips = ha_cluster_vips or {
            "10.2.156.40",  # HQ-SBCE-HA-VIP
            "10.2.1.1",     # HQ Core Gateway HSRP VIP
            "10.102.10.25", # Avaya CM Active Processor VIP
        }

    @staticmethod
    def derive_canonical_id(ip: Optional[str], serial: Optional[str], caption: str) -> str:
        """Derive deterministic canonical device ID."""
        if serial and serial.strip():
            seed = f"sn:{serial.strip().upper()}"
        elif ip and ip.strip() and ip != "127.0.0.1" and ip != "mock-snmp":
            seed = f"ip:{ip.strip()}"
        else:
            clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", caption.strip().lower())
            seed = f"name:{clean_name}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"dev-{digest}"

    def reconcile(
        self,
        solarwinds_nodes: List[SolarWindsNodeRecord],
        zabbix_hosts: List[ZabbixHostRecord],
    ) -> List[ReconciliationItem]:
        """Perform comprehensive device reconciliation across both inventories."""
        # Index SolarWinds by IP, Serial, Caption
        sw_by_ip: Dict[str, List[SolarWindsNodeRecord]] = {}
        sw_by_serial: Dict[str, List[SolarWindsNodeRecord]] = {}
        sw_by_caption: Dict[str, List[SolarWindsNodeRecord]] = {}

        for sw in solarwinds_nodes:
            if sw.ip_address:
                sw_by_ip.setdefault(sw.ip_address, []).append(sw)
            if sw.serial_number:
                sw_by_serial.setdefault(sw.serial_number.upper(), []).append(sw)
            if sw.caption:
                sw_by_caption.setdefault(sw.caption.upper(), []).append(sw)

        # Index Zabbix by IP
        zbx_by_ip: Dict[str, List[ZabbixHostRecord]] = {}
        for zbx in zabbix_hosts:
            for ip in zbx.all_ips:
                if ip and ip != "127.0.0.1" and ip != "mock-snmp":
                    zbx_by_ip.setdefault(ip, []).append(zbx)

        matched_sw_nodes: Set[str] = set()
        matched_zbx_hosts: Set[str] = set()
        reconciliation_items: List[ReconciliationItem] = []

        # Match from Zabbix perspective
        for zbx in zabbix_hosts:
            primary_ip = zbx.primary_ip
            # Skip non-network monitoring server hosts
            if zbx.technical_host.lower() in ('zabbix server', '127.0.0.1') or not primary_ip or primary_ip in ('127.0.0.1', '::1', 'mock-snmp'):
                matched_zbx_hosts.add(zbx.host_id)
                reconciliation_items.append(ReconciliationItem(
                    canonical_id=self.derive_canonical_id(primary_ip, None, zbx.visible_name),
                    confidence=MatchConfidence.ZABBIX_ONLY,
                    solarwinds_node=None,
                    zabbix_host=zbx,
                    current_zabbix_host=zbx.technical_host,
                    current_zabbix_visible_name=zbx.visible_name,
                    proposed_zabbix_visible_name=zbx.visible_name,
                    matching_evidence="Monitoring system server host / internal loopback (excluded from switch reconciliation)",
                    is_safe_to_rename=False,
                    requires_manual_review=False,
                    rename_operation="NOOP",
                ))
                continue

            zbx_serial = zbx.inventory.get("serialno_a")
            if zbx_serial:
                zbx_serial = str(zbx_serial).strip().upper()

            # A. Check for Hardware Serial Number Match (highest fidelity)
            serial_matches = sw_by_serial.get(zbx_serial, []) if zbx_serial else []
            if len(serial_matches) == 1:
                sw = serial_matches[0]
                matched_sw_nodes.add(sw.node_id)
                matched_zbx_hosts.add(zbx.host_id)
                item = self._build_exact_match(
                    sw, zbx, f"Exact hardware serial number match: {zbx_serial}"
                )
                reconciliation_items.append(item)
                continue

            # B. Match by Primary Management IP
            ip_sw_matches = sw_by_ip.get(primary_ip, []) if primary_ip else []

            if len(ip_sw_matches) == 1:
                sw = ip_sw_matches[0]
                matched_sw_nodes.add(sw.node_id)
                matched_zbx_hosts.add(zbx.host_id)

                # Check if this IP is associated with multiple Zabbix hosts (duplicate candidate)
                zbx_with_ip = zbx_by_ip.get(primary_ip, [])
                if len(zbx_with_ip) > 1:
                    item = self._build_conflicting_item(
                        sw, zbx, MatchConfidence.DUPLICATE_CANDIDATE,
                        f"Multiple Zabbix hosts share IP {primary_ip}: {[h.host_id for h in zbx_with_ip]}"
                    )
                    reconciliation_items.append(item)
                    continue

                # Check for HA Cluster VIP
                if primary_ip in self.ha_cluster_vips or "vip" in sw.caption.lower() or "cluster" in sw.caption.lower():
                    item = self._build_ha_cluster_item(
                        sw, zbx, f"Management IP {primary_ip} matches designated HA cluster/VIP architecture"
                    )
                    reconciliation_items.append(item)
                    continue

                # Check for Switch Stack
                is_stack = "stack" in sw.machine_type.lower() or "stack" in sw.caption.lower()
                
                # Check Name and SysName Alignment
                caption_norm = re.sub(r"[^a-zA-Z0-9]", "", sw.caption.lower())
                zbx_name_norm = re.sub(r"[^a-zA-Z0-9]", "", zbx.visible_name.lower())
                zbx_host_norm = re.sub(r"[^a-zA-Z0-9]", "", zbx.technical_host.lower())

                is_generic_candidate = (
                    "candidate" in zbx.visible_name.lower() or 
                    ("switch" in zbx.visible_name.lower() and primary_ip in zbx.visible_name) or
                    zbx.visible_name.startswith("cisco-switch-")
                )

                if sw.serial_number or caption_norm in zbx_name_norm or caption_norm in zbx_host_norm or is_generic_candidate:
                    conf = MatchConfidence.EXACT_VERIFIED_MATCH if sw.serial_number else MatchConfidence.HIGH_CONFIDENCE_MATCH
                    item = ReconciliationItem(
                        canonical_id=self.derive_canonical_id(primary_ip, sw.serial_number, sw.caption),
                        confidence=conf,
                        solarwinds_node=sw,
                        zabbix_host=zbx,
                        current_zabbix_host=zbx.technical_host,
                        current_zabbix_visible_name=zbx.visible_name,
                        proposed_zabbix_visible_name=sw.caption,
                        matching_evidence=f"Management IP {primary_ip} matched; SolarWinds Caption: '{sw.caption}'; Model: {sw.machine_type}",
                        is_safe_to_rename=True,
                        requires_manual_review=False,
                        is_switch_stack=is_stack,
                        rename_operation="RENAME" if zbx.visible_name != sw.caption else "NOOP",
                    )
                else:
                    item = ReconciliationItem(
                        canonical_id=self.derive_canonical_id(primary_ip, sw.serial_number, sw.caption),
                        confidence=MatchConfidence.POSSIBLE_MATCH,
                        solarwinds_node=sw,
                        zabbix_host=zbx,
                        current_zabbix_host=zbx.technical_host,
                        current_zabbix_visible_name=zbx.visible_name,
                        proposed_zabbix_visible_name=sw.caption,
                        matching_evidence=f"Management IP {primary_ip} matched but names differ: '{sw.caption}' vs '{zbx.visible_name}'",
                        is_safe_to_rename=False,
                        requires_manual_review=True,
                        rename_operation="REVIEW",
                    )
                reconciliation_items.append(item)

            elif len(ip_sw_matches) > 1:
                matched_zbx_hosts.add(zbx.host_id)
                item = self._build_conflicting_item(
                    ip_sw_matches[0], zbx, MatchConfidence.CONFLICTING_MATCH,
                    f"Multiple SolarWinds nodes ({[s.node_id for s in ip_sw_matches]}) registered for IP {primary_ip}"
                )
                reconciliation_items.append(item)

            else:
                matched_zbx_hosts.add(zbx.host_id)
                item = ReconciliationItem(
                    canonical_id=self.derive_canonical_id(primary_ip, zbx_serial, zbx.visible_name),
                    confidence=MatchConfidence.ZABBIX_ONLY,
                    solarwinds_node=None,
                    zabbix_host=zbx,
                    current_zabbix_host=zbx.technical_host,
                    current_zabbix_visible_name=zbx.visible_name,
                    proposed_zabbix_visible_name=zbx.visible_name,
                    matching_evidence=f"No matching SolarWinds node found for IP {primary_ip} or hostname '{zbx.technical_host}'",
                    is_safe_to_rename=False,
                    requires_manual_review=False,
                    rename_operation="NOOP",
                )
                reconciliation_items.append(item)

        for sw in solarwinds_nodes:
            if sw.node_id not in matched_sw_nodes:
                item = ReconciliationItem(
                    canonical_id=self.derive_canonical_id(sw.ip_address, sw.serial_number, sw.caption),
                    confidence=MatchConfidence.SOLARWINDS_ONLY,
                    solarwinds_node=sw,
                    zabbix_host=None,
                    current_zabbix_host="",
                    current_zabbix_visible_name="",
                    proposed_zabbix_visible_name=sw.caption,
                    matching_evidence=f"SolarWinds NodeID {sw.node_id} ({sw.caption}) has no corresponding Zabbix host for IP {sw.ip_address}",
                    is_safe_to_rename=False,
                    requires_manual_review=False,
                    rename_operation="NOOP",
                )
                reconciliation_items.append(item)

        return reconciliation_items

    def _build_exact_match(self, sw: SolarWindsNodeRecord, zbx: ZabbixHostRecord, evidence: str) -> ReconciliationItem:
        return ReconciliationItem(
            canonical_id=self.derive_canonical_id(sw.ip_address, sw.serial_number, sw.caption),
            confidence=MatchConfidence.EXACT_VERIFIED_MATCH,
            solarwinds_node=sw,
            zabbix_host=zbx,
            current_zabbix_host=zbx.technical_host,
            current_zabbix_visible_name=zbx.visible_name,
            proposed_zabbix_visible_name=sw.caption,
            matching_evidence=evidence,
            is_safe_to_rename=True,
            requires_manual_review=False,
            rename_operation="RENAME" if zbx.visible_name != sw.caption else "NOOP",
        )

    def _build_ha_cluster_item(self, sw: SolarWindsNodeRecord, zbx: ZabbixHostRecord, evidence: str) -> ReconciliationItem:
        return ReconciliationItem(
            canonical_id=self.derive_canonical_id(sw.ip_address, sw.serial_number, sw.caption),
            confidence=MatchConfidence.MANUAL_REVIEW_REQUIRED,
            solarwinds_node=sw,
            zabbix_host=zbx,
            current_zabbix_host=zbx.technical_host,
            current_zabbix_visible_name=zbx.visible_name,
            proposed_zabbix_visible_name=sw.caption,
            matching_evidence=f"{evidence}; HA VIP must not overwrite physical node identity",
            is_safe_to_rename=False,
            requires_manual_review=True,
            is_ha_cluster_node=True,
            rename_operation="REVIEW",
            conflict_reason="HA Cluster VIP / Multi-Node Pair",
        )

    def _build_conflicting_item(
        self, sw: SolarWindsNodeRecord, zbx: ZabbixHostRecord, conf: MatchConfidence, reason: str
    ) -> ReconciliationItem:
        return ReconciliationItem(
            canonical_id=self.derive_canonical_id(sw.ip_address, sw.serial_number, sw.caption),
            confidence=conf,
            solarwinds_node=sw,
            zabbix_host=zbx,
            current_zabbix_host=zbx.technical_host,
            current_zabbix_visible_name=zbx.visible_name,
            proposed_zabbix_visible_name=sw.caption,
            matching_evidence=reason,
            is_safe_to_rename=False,
            requires_manual_review=True,
            conflict_reason=reason,
            rename_operation="BLOCKED",
        )


class DeviceDriftDetector:
    """Detects inventory drift, caption changes, IP shifts, and missing nodes over time."""

    @classmethod
    def detect_drift(
        cls,
        baseline_plan: Dict[str, Any],
        new_solarwinds_nodes: List[SolarWindsNodeRecord],
        new_zabbix_hosts: List[ZabbixHostRecord],
    ) -> DriftReport:
        """Compare latest SolarWinds and Zabbix states against baseline reconciled plan."""
        now = time.time()
        report = DriftReport(timestamp=now)

        baseline_items = baseline_plan.get("items", [])
        mapped_sw_ids = {
            item["solarwinds_node_id"]: item
            for item in baseline_items if item.get("solarwinds_node_id")
        }
        mapped_zbx_ids = {
            item["zabbix_host_id"]: item
            for item in baseline_items if item.get("zabbix_host_id")
        }

        # 1. New SolarWinds devices
        for sw in new_solarwinds_nodes:
            if sw.node_id not in mapped_sw_ids:
                report.new_solarwinds_devices.append({
                    "node_id": sw.node_id,
                    "caption": sw.caption,
                    "ip_address": sw.ip_address,
                    "model": sw.machine_type,
                })
            else:
                # Check for caption changes
                old_caption = mapped_sw_ids[sw.node_id].get("solarwinds_caption")
                if old_caption and old_caption != sw.caption:
                    report.caption_changes.append({
                        "node_id": sw.node_id,
                        "old_caption": old_caption,
                        "new_caption": sw.caption,
                        "canonical_id": mapped_sw_ids[sw.node_id].get("canonical_id"),
                    })
                # Check for IP address changes
                old_ip = mapped_sw_ids[sw.node_id].get("solarwinds_ip")
                if old_ip and old_ip != sw.ip_address:
                    report.ip_changes.append({
                        "node_id": sw.node_id,
                        "caption": sw.caption,
                        "old_ip": old_ip,
                        "new_ip": sw.ip_address,
                        "canonical_id": mapped_sw_ids[sw.node_id].get("canonical_id"),
                    })

        # 2. New Zabbix hosts
        for zbx in new_zabbix_hosts:
            if zbx.host_id not in mapped_zbx_ids:
                report.new_zabbix_hosts.append({
                    "host_id": zbx.host_id,
                    "technical_host": zbx.technical_host,
                    "visible_name": zbx.visible_name,
                    "primary_ip": zbx.primary_ip,
                })

        # 3. Missing SolarWinds devices (nodes present in baseline but missing in current export)
        current_sw_ids = {sw.node_id for sw in new_solarwinds_nodes}
        for sw_id, item in mapped_sw_ids.items():
            if sw_id not in current_sw_ids:
                report.missing_in_solarwinds.append({
                    "node_id": sw_id,
                    "caption": item.get("solarwinds_caption"),
                    "canonical_id": item.get("canonical_id"),
                    "status": "marked_stale_preserved",
                })

        report.total_drift_items = (
            len(report.new_solarwinds_devices)
            + len(report.new_zabbix_hosts)
            + len(report.caption_changes)
            + len(report.ip_changes)
            + len(report.missing_in_solarwinds)
        )
        return report
