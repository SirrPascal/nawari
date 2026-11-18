"""Enterprise Network Infrastructure & Topology Engine for Nawari.

Implements:
- Canonical network infrastructure model (devices, interfaces, segments, links, associations)
- Evidence-backed discovery adapters (Zabbix SNMP, LLDP, CDP, FDB, ARP, Wireless, Endpoint)
- Idempotent topology reconciliation engine with roaming and port-change tracking
- Time-bounded telemetry-to-infrastructure correlation
- Multi-hop path resolution (Endpoint -> AP/Switch -> Dist -> Core -> Firewall/Gateway -> Internet)
- Blast-radius and shared-infrastructure degradation impact analysis
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from . import contracts, identity

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------
DEVICE_ROLES = {
    "access_switch", "distribution_switch", "core_switch", "router",
    "wireless_ap", "wireless_controller", "firewall", "gateway",
    "server", "synthetic_probe", "other"
}

ROLE_TIER: Dict[str, int] = {
    "firewall": 5,
    "gateway": 5,
    "router": 5,
    "core_switch": 4,
    "distribution_switch": 3,
    "wireless_controller": 3,
    "access_switch": 2,
    "wireless_ap": 1,
    "access_point": 1,
    "server": 1,
    "synthetic_probe": 1,
    "endpoint": 1,
    "other": 1,
}

INTERFACE_TYPES = {"ETHERNET", "WIFI", "VIRTUAL", "LOOPBACK", "AGGREGATE", "CELLULAR", "OTHER"}

RELATIONSHIP_CLASSES = {
    "discovered_l2_topology",  # LLDP, CDP, direct switchport
    "controller_association",  # Wi-Fi AP association from WLC
    "measured_l3_path",        # Traceroute / path hop
    "configured_dependency",   # Explicit cabling / configuration
    "inferred_relationship",   # Heuristic / gateway matching
}

PREDICATES = {
    "connected_to_l2",         # Physical L2 connection (switchport, patch)
    "adjacent_to",             # Physical/logical L2 neighbor adjacency (LLDP/CDP)
    "attached_to",             # Endpoint associated with access port or AP (FDB, WLC)
    "associated_ap",           # Wireless client -> AP association
    "uplink_to",               # Explicit upstream hierarchical dependency
    "forwarding_dependency",   # Network forwarding dependency (STP, route)
    "default_gateway_for",     # Gateway -> Host / Subnet
    "next_hop_via",            # Next hop routing relationship
    "routes_to",               # Router -> Next Hop
    "member_of_segment",       # Interface/Host -> Subnet/VLAN
    "depends_on",              # Service / App -> Infrastructure device
    "service_depends_on",      # Explicit business service dependency
    "potentially_reachable_via", # Inferred / plausible path without full confirmation
}

CONFIDENCE_LLDP_CDP = 0.95
CONFIDENCE_WLC_ASSOC = 0.90
CONFIDENCE_FDB_CAM = 0.85
CONFIDENCE_ARP = 0.75
CONFIDENCE_ENDPOINT_PATH = 0.70
CONFIDENCE_INFERRED = 0.50


# -------------------------------------------------------------------------
# Data Models
# -------------------------------------------------------------------------
@dataclasses.dataclass
class NetworkDevice:
    tenant: str
    device_id: str
    name: str
    device_role: str
    site_id: str
    routing_domain_id: str
    management_ip: Optional[str] = None
    serial_number: Optional[str] = None
    chassis_uuid: Optional[str] = None
    mac_address: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    os_version: Optional[str] = None
    snmp_sys_name: Optional[str] = None
    snmp_sys_descr: Optional[str] = None
    snmp_sys_object_id: Optional[str] = None
    zabbix_hostid: Optional[str] = None
    health_status: str = "unknown"
    health_details: Dict[str, Any] = dataclasses.field(default_factory=dict)
    observed_at: float = 0.0

    def __post_init__(self):
        contracts.identifier(self.tenant)
        contracts.identifier(self.device_id)
        if self.device_role not in DEVICE_ROLES:
            raise ValueError(f"invalid_device_role: {self.device_role}")
        if not self.observed_at:
            self.observed_at = time.time()


@dataclasses.dataclass
class NetworkInterface:
    tenant: str
    interface_id: str
    device_id: str
    interface_name: str
    interface_type: str = "ETHERNET"
    if_index: Optional[int] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    admin_status: str = "up"
    oper_status: str = "up"
    speed_bps: Optional[int] = None
    vlan_id: Optional[int] = None
    duplex: Optional[str] = None
    attributes: Dict[str, Any] = dataclasses.field(default_factory=dict)
    observed_at: float = 0.0

    def __post_init__(self):
        contracts.identifier(self.tenant)
        contracts.identifier(self.interface_id)
        contracts.identifier(self.device_id)
        if self.interface_type not in INTERFACE_TYPES:
            raise ValueError(f"invalid_interface_type: {self.interface_type}")
        if not self.observed_at:
            self.observed_at = time.time()


@dataclasses.dataclass
class NetworkSegment:
    tenant: str
    segment_id: str
    site_id: str
    routing_domain_id: str
    name: str
    cidr: str
    vlan_id: Optional[int] = None
    gateway_ip: Optional[str] = None
    segment_type: str = "corporate_lan"
    attributes: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        contracts.identifier(self.tenant)
        contracts.identifier(self.segment_id)


@dataclasses.dataclass
class TopologyRelationship:
    tenant: str
    relationship_id: str
    subject_id: str
    predicate: str
    object_id: str
    relationship_class: str
    provenance_source: str
    provenance_object_id: str
    valid_from: float
    valid_until: float
    confidence: float = 1.0
    first_observed: float = 0.0
    last_observed: float = 0.0
    attributes: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        contracts.identifier(self.tenant)
        contracts.identifier(self.relationship_id)
        contracts.identifier(self.subject_id)
        contracts.identifier(self.object_id)
        if self.relationship_class not in RELATIONSHIP_CLASSES:
            raise ValueError(f"invalid_relationship_class: {self.relationship_class}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence_out_of_range: {self.confidence}")
        if not self.first_observed:
            self.first_observed = self.valid_from
        if not self.last_observed:
            self.last_observed = self.first_observed


# -------------------------------------------------------------------------
# Topology Reconciliation Engine
# -------------------------------------------------------------------------
class TopologyReconciler:
    """Idempotent enterprise network topology reconciliation and correlation."""

    def __init__(self, stale_threshold_seconds: float = 86400 * 7):
        self.stale_threshold_seconds = stale_threshold_seconds

    def reconcile_device(self, session: Any, device: NetworkDevice, now: float) -> str:
        """Upsert a network infrastructure device and its canonical topology entity."""
        contracts.identifier(device.tenant)
        contracts.identifier(device.device_id)

        # 1. Ensure entity exists in topology_entities
        attrs = {
            "name": device.name,
            "device_role": device.device_role,
            "vendor": device.vendor,
            "model": device.model,
            "os_version": device.os_version,
            "health_status": device.health_status,
        }
        session.execute(
            "INSERT INTO topology_entities VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT (tenant, entity_id) DO UPDATE SET "
            "site_id=excluded.site_id, routing_domain_id=excluded.routing_domain_id, "
            "attributes=excluded.attributes",
            (
                device.tenant,
                device.device_id,
                device.device_role,
                "zabbix" if device.zabbix_hostid else "manual_inventory",
                device.zabbix_hostid or device.device_id,
                device.site_id,
                device.routing_domain_id,
                json.dumps(attrs),
            ),
        )

        # 2. Upsert network_devices
        existing = session.one(
            "SELECT * FROM network_devices WHERE tenant=? AND device_id=?",
            (device.tenant, device.device_id),
        )
        if existing:
            session.execute(
                "UPDATE network_devices SET name=?, device_role=?, management_ip=?, "
                "serial_number=COALESCE(?, serial_number), chassis_uuid=COALESCE(?, chassis_uuid), "
                "mac_address=COALESCE(?, mac_address), model=COALESCE(?, model), vendor=COALESCE(?, vendor), "
                "os_version=COALESCE(?, os_version), site_id=?, routing_domain_id=?, "
                "snmp_sys_name=COALESCE(?, snmp_sys_name), snmp_sys_descr=COALESCE(?, snmp_sys_descr), "
                "snmp_sys_object_id=COALESCE(?, snmp_sys_object_id), zabbix_hostid=COALESCE(?, zabbix_hostid), "
                "health_status=?, health_details=?, updated_at=?, last_seen_at=MAX(last_seen_at, ?) "
                "WHERE tenant=? AND device_id=?",
                (
                    device.name, device.device_role, device.management_ip,
                    device.serial_number, device.chassis_uuid, device.mac_address,
                    device.model, device.vendor, device.os_version,
                    device.site_id, device.routing_domain_id,
                    device.snmp_sys_name, device.snmp_sys_descr, device.snmp_sys_object_id,
                    device.zabbix_hostid, device.health_status, json.dumps(device.health_details),
                    now, device.observed_at,
                    device.tenant, device.device_id,
                ),
            )
        else:
            session.execute(
                "INSERT INTO network_devices ("
                "tenant, device_id, name, device_role, management_ip, serial_number, chassis_uuid, "
                "mac_address, model, vendor, os_version, site_id, routing_domain_id, "
                "snmp_sys_name, snmp_sys_descr, snmp_sys_object_id, zabbix_hostid, "
                "health_status, health_details, created_at, updated_at, last_seen_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    device.tenant, device.device_id, device.name, device.device_role,
                    device.management_ip, device.serial_number, device.chassis_uuid,
                    device.mac_address, device.model, device.vendor, device.os_version,
                    device.site_id, device.routing_domain_id,
                    device.snmp_sys_name, device.snmp_sys_descr, device.snmp_sys_object_id,
                    device.zabbix_hostid, device.health_status, json.dumps(device.health_details),
                    now, now, device.observed_at,
                ),
            )

        # Backwards compatibility: mirror into assets
        session.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?) "
            "ON CONFLICT (tenant, asset_id) DO UPDATE SET "
            "name=excluded.name, site_id=excluded.site_id, routing_domain_id=excluded.routing_domain_id",
            (device.tenant, device.device_id, device.name, device.site_id, device.routing_domain_id),
        )

        return device.device_id

    def reconcile_interface(self, session: Any, iface: NetworkInterface, now: float) -> str:
        """Upsert a network interface on a device or endpoint."""
        contracts.identifier(iface.tenant)
        contracts.identifier(iface.interface_id)
        contracts.identifier(iface.device_id)

        # Ensure parent entity exists
        parent = session.one(
            "SELECT entity_id FROM topology_entities WHERE tenant=? AND entity_id=?",
            (iface.tenant, iface.device_id),
        )
        if not parent:
            # If not in topology_entities, check endpoint_registry
            ep = session.one(
                "SELECT endpoint_id FROM endpoint_registry WHERE tenant=? AND endpoint_id=?",
                (iface.tenant, iface.device_id),
            )
            if not ep:
                raise ValueError(f"parent_device_not_found: {iface.device_id}")

        existing = session.one(
            "SELECT * FROM network_interfaces WHERE tenant=? AND interface_id=?",
            (iface.tenant, iface.interface_id),
        )
        if existing:
            session.execute(
                "UPDATE network_interfaces SET interface_name=?, if_index=COALESCE(?, if_index), "
                "interface_type=?, mac_address=COALESCE(?, mac_address), ip_address=COALESCE(?, ip_address), "
                "subnet_mask=COALESCE(?, subnet_mask), admin_status=?, oper_status=?, "
                "speed_bps=COALESCE(?, speed_bps), vlan_id=COALESCE(?, vlan_id), duplex=COALESCE(?, duplex), "
                "attributes=?, last_seen_at=MAX(last_seen_at, ?) WHERE tenant=? AND interface_id=?",
                (
                    iface.interface_name, iface.if_index, iface.interface_type,
                    iface.mac_address, iface.ip_address, iface.subnet_mask,
                    iface.admin_status, iface.oper_status, iface.speed_bps,
                    iface.vlan_id, iface.duplex, json.dumps(iface.attributes),
                    iface.observed_at, iface.tenant, iface.interface_id,
                ),
            )
        else:
            session.execute(
                "INSERT INTO network_interfaces VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    iface.tenant, iface.interface_id, iface.device_id, iface.interface_name,
                    iface.if_index, iface.interface_type, iface.mac_address, iface.ip_address,
                    iface.subnet_mask, iface.admin_status, iface.oper_status, iface.speed_bps,
                    iface.vlan_id, iface.duplex, json.dumps(iface.attributes), iface.observed_at,
                ),
            )

        return iface.interface_id

    def reconcile_relationship(self, session: Any, rel: TopologyRelationship, now: float) -> str:
        """Idempotently upsert an active network topology relationship.

        If an active relationship already connects the same subject, predicate, and object,
        update its last_observed and extend valid_until without creating duplicates.
        """
        contracts.identifier(rel.tenant)
        contracts.identifier(rel.subject_id)
        contracts.identifier(rel.object_id)

        # Cross-tenant boundary check
        subj = session.one("SELECT tenant, entity_id FROM topology_entities WHERE tenant=? AND entity_id=?", (rel.tenant, rel.subject_id))
        obj = session.one("SELECT tenant, entity_id FROM topology_entities WHERE tenant=? AND entity_id=?", (rel.tenant, rel.object_id))

        if not obj:
            # Fallback resolution within the same tenant (e.g. LLDP neighbor hostname/sysName/MAC resolution)
            target_hints = [rel.object_id]
            if rel.object_id.startswith("dev-zbx-"):
                target_hints.append(rel.object_id[len("dev-zbx-"):])
            if rel.attributes and isinstance(rel.attributes, dict):
                if rel.attributes.get("remote_sysname"):
                    target_hints.append(str(rel.attributes["remote_sysname"]))
                if rel.attributes.get("remote_chassis_id"):
                    target_hints.append(str(rel.attributes["remote_chassis_id"]))

            for hint in target_hints:
                cand_lower = hint.lower()
                dev_obj = session.one(
                    "SELECT device_id FROM network_devices WHERE tenant=? AND ("
                    "LOWER(name)=? OR LOWER(snmp_sys_name)=? OR LOWER(mac_address)=? OR LOWER(device_id)=?"
                    ")",
                    (rel.tenant, cand_lower, cand_lower, cand_lower, cand_lower),
                )
                if dev_obj:
                    rel.object_id = dev_obj["device_id"]
                    obj = session.one("SELECT tenant, entity_id FROM topology_entities WHERE tenant=? AND entity_id=?", (rel.tenant, rel.object_id))
                    break

        if not subj or not obj:
            raise ValueError("subject_or_object_entity_not_found_in_tenant")

        # Resolve canonical local and remote interface IDs on the subject and object devices
        if rel.attributes and isinstance(rel.attributes, dict):
            if "local_interface_id" not in rel.attributes:
                local_candidates = session.all(
                    "SELECT interface_id, interface_name, if_index FROM network_interfaces "
                    "WHERE tenant=? AND device_id=?",
                    (rel.tenant, rel.subject_id),
                )
                local_p = str(rel.attributes.get("local_port") or "").lower().strip()
                local_num = rel.attributes.get("local_port_num")
                for lc in local_candidates:
                    lc_name = lc["interface_name"].lower().strip()
                    if (local_p and (lc_name == local_p or lc_name.replace("/", "_") == local_p.replace("/", "_"))) or \
                       (local_num is not None and lc.get("if_index") == local_num):
                        rel.attributes["local_interface_id"] = lc["interface_id"]
                        break

            if "remote_interface_id" not in rel.attributes:
                remote_candidates = session.all(
                    "SELECT interface_id, interface_name, if_index, mac_address FROM network_interfaces "
                    "WHERE tenant=? AND device_id=?",
                    (rel.tenant, rel.object_id),
                )
                rem_p = str(rel.attributes.get("remote_port") or "").lower().strip()
                rem_desc = str(rel.attributes.get("remote_port_desc") or "").lower().strip()
                rem_mac = str(rel.attributes.get("remote_chassis_id") or "").lower().strip()

                matched_iface = None
                for rc in remote_candidates:
                    rc_name = rc["interface_name"].lower().strip()
                    if rem_p and (rc_name == rem_p or rc_name.replace("/", "_") == rem_p.replace("/", "_")):
                        matched_iface = rc["interface_id"]
                        break
                    if rem_p.isdigit() and rc.get("if_index") == int(rem_p):
                        matched_iface = rc["interface_id"]
                        break
                if not matched_iface and rem_desc:
                    for rc in remote_candidates:
                        rc_name = rc["interface_name"].lower().strip()
                        if rc_name and rc_name in rem_desc:
                            matched_iface = rc["interface_id"]
                            break
                if not matched_iface and rem_mac:
                    for rc in remote_candidates:
                        if rc.get("mac_address") and rc["mac_address"].lower().strip() == rem_mac:
                            matched_iface = rc["interface_id"]
                            break
                if matched_iface:
                    rel.attributes["remote_interface_id"] = matched_iface

        # Check existing active relationship between subject, predicate, and object
        existing = session.one(
            "SELECT * FROM topology_relationships "
            "WHERE tenant=? AND subject_id=? AND predicate=? AND object_id=? "
            "AND valid_until > ? ORDER BY valid_until DESC LIMIT 1",
            (rel.tenant, rel.subject_id, rel.predicate, rel.object_id, rel.valid_from),
        )

        # Check reciprocal relationship for bidirectional confirmation
        reciprocal = session.one(
            "SELECT * FROM topology_relationships "
            "WHERE tenant=? AND subject_id=? AND object_id=? AND valid_until > ? "
            "LIMIT 1",
            (rel.tenant, rel.object_id, rel.subject_id, rel.valid_from),
        )
        if reciprocal:
            rel.attributes["bidirectional_confirmed"] = True
            rel.confidence = max(rel.confidence, 0.98)
            rec_attrs = json.loads(reciprocal["attributes"]) if isinstance(reciprocal["attributes"], str) else dict(reciprocal["attributes"])
            rec_attrs["bidirectional_confirmed"] = True
            if "remote_interface_id" not in rec_attrs and rel.attributes.get("local_interface_id"):
                rec_attrs["remote_interface_id"] = rel.attributes["local_interface_id"]
            if "local_interface_id" not in rec_attrs and rel.attributes.get("remote_interface_id"):
                rec_attrs["local_interface_id"] = rel.attributes["remote_interface_id"]
            session.execute(
                "UPDATE topology_relationships SET confidence=MAX(confidence, 0.98), attributes=? "
                "WHERE tenant=? AND relationship_id=?",
                (json.dumps(rec_attrs), rel.tenant, reciprocal["relationship_id"]),
            )
        else:
            if "bidirectional_confirmed" not in rel.attributes:
                rel.attributes["bidirectional_confirmed"] = False

        if existing:
            # Update existing relationship
            session.execute(
                "UPDATE topology_relationships SET last_observed=MAX(last_observed, ?), "
                "valid_until=MAX(valid_until, ?), confidence=?, attributes=? "
                "WHERE tenant=? AND relationship_id=?",
                (
                    rel.last_observed, rel.valid_until, rel.confidence,
                    json.dumps(rel.attributes), rel.tenant, existing["relationship_id"],
                ),
            )
            return existing["relationship_id"]

        # Insert new relationship
        session.execute(
            "INSERT INTO topology_relationships VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rel.tenant, rel.relationship_id, rel.subject_id, rel.predicate,
                rel.object_id, rel.relationship_class, rel.provenance_source,
                rel.provenance_object_id, rel.valid_from, rel.valid_until,
                rel.first_observed, rel.last_observed, rel.confidence,
                json.dumps(rel.attributes),
            ),
        )
        return rel.relationship_id

    def roam_client(self, session: Any, tenant: str, endpoint_id: str, new_ap_id: str,
                    ssid: str, bssid: str, now: float, rssi: Optional[int] = None) -> str:
        """Handles client Wi-Fi roaming between APs without erasing historical association."""
        contracts.identifier(tenant)
        contracts.identifier(endpoint_id)
        contracts.identifier(new_ap_id)

        # Expire current active association to any AP if different from new_ap_id
        active_assocs = session.all(
            "SELECT * FROM topology_relationships "
            "WHERE tenant=? AND subject_id=? AND predicate='associated_ap' AND valid_until > ?",
            (tenant, endpoint_id, now),
        )
        for assoc in active_assocs:
            if assoc["object_id"] != new_ap_id:
                exp_until = max(now, assoc["valid_from"] + 0.001)
                exp_last = max(assoc["first_observed"], min(now, exp_until))
                session.execute(
                    "UPDATE topology_relationships SET valid_until=?, last_observed=? WHERE tenant=? AND relationship_id=?",
                    (exp_until, exp_last, tenant, assoc["relationship_id"]),
                )

        # Record new association
        rel_id = f"rel-{hashlib.sha256(f'{tenant}:{endpoint_id}:assoc:{new_ap_id}:{now}'.encode()).hexdigest()[:16]}"
        rel = TopologyRelationship(
            tenant=tenant,
            relationship_id=rel_id,
            subject_id=endpoint_id,
            predicate="associated_ap",
            object_id=new_ap_id,
            relationship_class="controller_association",
            provenance_source="wireless_controller",
            provenance_object_id=bssid,
            valid_from=now,
            valid_until=now + 86400 * 3,  # 3 days active window unless updated
            confidence=CONFIDENCE_WLC_ASSOC,
            first_observed=now,
            last_observed=now,
            attributes={"ssid": ssid, "bssid": bssid, "rssi": rssi, "roamed_at": now},
        )
        return self.reconcile_relationship(session, rel, now)

    def update_switchport(self, session: Any, tenant: str, endpoint_id: str, switch_id: str,
                          port_name: str, vlan_id: Optional[int], now: float,
                          discovery_source: str = "switch_fdb") -> str:
        """Handles endpoint switchport movement or re-patching with historical validity."""
        contracts.identifier(tenant)
        contracts.identifier(endpoint_id)
        contracts.identifier(switch_id)

        # Close existing switch connection if to a different switch or port
        active_conns = session.all(
            "SELECT * FROM topology_relationships "
            "WHERE tenant=? AND subject_id=? AND predicate='connected_to_l2' AND valid_until > ?",
            (tenant, endpoint_id, now),
        )
        for conn in active_conns:
            attrs = json.loads(conn["attributes"]) if isinstance(conn["attributes"], str) else conn["attributes"]
            if conn["object_id"] != switch_id or attrs.get("port") != port_name:
                exp_until = max(now, conn["valid_from"] + 0.001)
                exp_last = max(conn["first_observed"], min(now, exp_until))
                session.execute(
                    "UPDATE topology_relationships SET valid_until=?, last_observed=? WHERE tenant=? AND relationship_id=?",
                    (exp_until, exp_last, tenant, conn["relationship_id"]),
                )

        rel_id = f"rel-{hashlib.sha256(f'{tenant}:{endpoint_id}:l2:{switch_id}:{port_name}:{now}'.encode()).hexdigest()[:16]}"
        rel = TopologyRelationship(
            tenant=tenant,
            relationship_id=rel_id,
            subject_id=endpoint_id,
            predicate="connected_to_l2",
            object_id=switch_id,
            relationship_class="discovered_l2_topology",
            provenance_source=discovery_source,
            provenance_object_id=f"{switch_id}:{port_name}",
            valid_from=now,
            valid_until=now + 86400 * 7,
            confidence=CONFIDENCE_LLDP_CDP if discovery_source in {"lldp_neighbor", "cdp_neighbor"} else CONFIDENCE_FDB_CAM,
            first_observed=now,
            last_observed=now,
            attributes={"port": port_name, "vlan": vlan_id},
        )
        return self.reconcile_relationship(session, rel, now)

    def get_endpoint_topology(self, session: Any, tenant: str, endpoint_id: str, timestamp: float) -> Dict[str, Any]:
        """Resolves the multi-hop path and access relationships for an endpoint at a specific time.

        Traverses:
        Endpoint -> Access Switch / Wi-Fi AP -> Distribution Switch -> Core Switch -> Gateway/Firewall -> WAN/Internet
        """
        contracts.identifier(tenant)
        contracts.identifier(endpoint_id)

        ep = session.one("SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?", (tenant, endpoint_id))
        if not ep:
            return {"error": "endpoint_not_found"}

        # Find active network relationships at timestamp
        rels = session.all(
            "SELECT * FROM topology_relationships "
            "WHERE tenant=? AND (subject_id=? OR object_id=?) "
            "AND valid_from <= ? AND valid_until >= ? "
            "ORDER BY confidence DESC, last_observed DESC",
            (tenant, endpoint_id, endpoint_id, timestamp, timestamp),
        )

        hops: List[Dict[str, Any]] = []
        hops.append({
            "node": ep["primary_hostname"],
            "entity_id": endpoint_id,
            "kind": "endpoint",
            "role": ep["device_kind"],
            "confidence": 1.0,
            "provenance": "endpoint_registry",
        })

        visited: Set[str] = {endpoint_id}
        current_id = endpoint_id

        # Walk upstream relationships
        while True:
            upstream = session.one(
                "SELECT r.*, e.entity_kind, e.attributes as entity_attrs FROM topology_relationships r "
                "JOIN topology_entities e ON (e.tenant=r.tenant AND e.entity_id=r.object_id) "
                "WHERE r.tenant=? AND r.subject_id=? AND r.predicate IN ('associated_ap', 'connected_to_l2', 'uplink_to', 'default_gateway_for') "
                "AND r.valid_from <= ? AND r.valid_until >= ? "
                "ORDER BY r.confidence DESC LIMIT 1",
                (tenant, current_id, timestamp, timestamp),
            )
            if not upstream or upstream["object_id"] in visited:
                break

            target_id = upstream["object_id"]
            visited.add(target_id)

            # Retrieve device metadata and health
            dev = session.one("SELECT * FROM network_devices WHERE tenant=? AND device_id=?", (tenant, target_id))
            name = dev["name"] if dev else target_id
            role = dev["device_role"] if dev else upstream["entity_kind"]
            health = dev["health_status"] if dev else "unknown"

            hops.append({
                "node": name,
                "entity_id": target_id,
                "kind": "infrastructure",
                "role": role,
                "health": health,
                "relationship_class": upstream["relationship_class"],
                "predicate": upstream["predicate"],
                "confidence": upstream["confidence"],
                "provenance": upstream["provenance_source"],
                "attributes": json.loads(upstream["attributes"]) if isinstance(upstream["attributes"], str) else upstream["attributes"],
            })
            current_id = target_id

        return {
            "tenant": tenant,
            "endpoint_id": endpoint_id,
            "primary_hostname": ep["primary_hostname"],
            "timestamp": timestamp,
            "hops": hops,
            "total_hops": len(hops),
            "access_layer": hops[1] if len(hops) > 1 else None,
            "relationships": rels,
        }

    def compute_blast_radius(self, session: Any, tenant: str, device_id: str, timestamp: float) -> Dict[str, Any]:
        """Computes all downstream endpoints and business services affected if this device is degraded."""
        contracts.identifier(tenant)
        contracts.identifier(device_id)

        target_dev = session.one("SELECT * FROM network_devices WHERE tenant=? AND device_id=?", (tenant, device_id))
        if not target_dev:
            target_dev = session.one("SELECT * FROM topology_entities WHERE tenant=? AND entity_id=?", (tenant, device_id))
            if not target_dev:
                return {"error": "device_not_found"}

        target_role = target_dev.get("device_role", target_dev.get("entity_kind", "other"))
        target_tier = ROLE_TIER.get(target_role, 1)

        confirmed_devices: List[Dict[str, Any]] = []
        potentially_affected_devices: List[Dict[str, Any]] = []
        adjacent_peer_devices: List[Dict[str, Any]] = []
        unknown_impact_devices: List[Dict[str, Any]] = []

        confirmed_endpoints: List[Dict[str, Any]] = []
        potentially_affected_endpoints: List[Dict[str, Any]] = []

        seen_endpoints: Set[str] = set()
        seen_downstream: Set[str] = set()
        seen_peers: Set[str] = set()

        def analyze_redundancy(candidate_id: str) -> Tuple[str, List[str]]:
            """Determines whether candidate device has redundant active uplinks to higher or equal tier."""
            active_links = session.all(
                "SELECT * FROM topology_relationships WHERE tenant=? AND (subject_id=? OR object_id=?) "
                "AND predicate IN ('connected_to_l2', 'uplink_to', 'routes_to', 'default_gateway_for', 'forwarding_dependency') "
                "AND valid_from <= ? AND valid_until >= ?",
                (tenant, candidate_id, candidate_id, timestamp, timestamp),
            )
            other_uplinks: List[str] = []
            for l in active_links:
                peer = l["object_id"] if l["subject_id"] == candidate_id else l["subject_id"]
                if peer != device_id and peer != candidate_id:
                    peer_dev = session.one("SELECT * FROM network_devices WHERE tenant=? AND device_id=?", (tenant, peer))
                    peer_role = peer_dev["device_role"] if peer_dev else "other"
                    if ROLE_TIER.get(peer_role, 1) >= target_tier:
                        other_uplinks.append(peer)

            if len(other_uplinks) > 0:
                return "potentially_affected", other_uplinks
            return "confirmed_affected", []

        # 1. Incoming relationships (subject -> target)
        incoming = session.all(
            "SELECT r.*, e.entity_kind, e.attributes as entity_attrs FROM topology_relationships r "
            "JOIN topology_entities e ON (e.tenant=r.tenant AND e.entity_id=r.subject_id) "
            "WHERE r.tenant=? AND r.object_id=? "
            "AND r.valid_from <= ? AND r.valid_until >= ?",
            (tenant, device_id, timestamp, timestamp),
        )

        for rel in incoming:
            subj_id = rel["subject_id"]
            if subj_id == device_id:
                continue

            # Check if subject is endpoint
            ep = session.one("SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?", (tenant, subj_id))
            if ep:
                if subj_id not in seen_endpoints:
                    seen_endpoints.add(subj_id)
                    ep_summary = {
                        "endpoint_id": subj_id,
                        "hostname": ep["primary_hostname"],
                        "site_id": ep["site_id"],
                        "relationship_class": rel["relationship_class"],
                        "confidence": rel["confidence"],
                        "provenance": rel["provenance_source"],
                        "link_type": rel["predicate"],
                        "dependency_type": "confirmed",
                    }
                    confirmed_endpoints.append(ep_summary)
            else:
                dev = session.one("SELECT * FROM network_devices WHERE tenant=? AND device_id=?", (tenant, subj_id))
                dev_role = dev["device_role"] if dev else rel.get("entity_kind", "other")
                subj_tier = ROLE_TIER.get(dev_role, 1)
                pred = rel["predicate"]

                dev_summary = {
                    "device_id": subj_id,
                    "name": dev["name"] if dev else subj_id,
                    "device_role": dev_role,
                    "health_status": dev["health_status"] if dev else "unknown",
                    "relationship_class": rel["relationship_class"],
                    "confidence": rel["confidence"],
                    "link_type": pred,
                }

                if pred in ("uplink_to", "default_gateway_for", "routes_to", "forwarding_dependency", "service_depends_on"):
                    impact_cat, redundant_paths = analyze_redundancy(subj_id)
                    dev_summary["redundant_paths"] = redundant_paths
                    dev_summary["impact_category"] = impact_cat
                    if subj_id not in seen_downstream:
                        seen_downstream.add(subj_id)
                        if impact_cat == "confirmed_affected":
                            confirmed_devices.append(dev_summary)
                        else:
                            potentially_affected_devices.append(dev_summary)
                elif pred == "connected_to_l2":
                    if target_tier > subj_tier:
                        impact_cat, redundant_paths = analyze_redundancy(subj_id)
                        dev_summary["redundant_paths"] = redundant_paths
                        dev_summary["impact_category"] = impact_cat
                        if subj_id not in seen_downstream:
                            seen_downstream.add(subj_id)
                            if impact_cat == "confirmed_affected":
                                confirmed_devices.append(dev_summary)
                            else:
                                potentially_affected_devices.append(dev_summary)
                    else:
                        dev_summary["impact_category"] = "adjacent_peer"
                        if subj_id not in seen_peers and subj_id not in seen_downstream:
                            seen_peers.add(subj_id)
                            adjacent_peer_devices.append(dev_summary)
                elif pred == "adjacent_to":
                    dev_summary["impact_category"] = "adjacent_peer"
                    if subj_id not in seen_peers and subj_id not in seen_downstream:
                        seen_peers.add(subj_id)
                        adjacent_peer_devices.append(dev_summary)
                else:
                    dev_summary["impact_category"] = "unknown_impact"
                    if subj_id not in seen_downstream and subj_id not in seen_peers:
                        unknown_impact_devices.append(dev_summary)

        # 2. Outgoing L2 peer relationships (target -> object)
        outgoing = session.all(
            "SELECT r.*, e.entity_kind, e.attributes as entity_attrs FROM topology_relationships r "
            "JOIN topology_entities e ON (e.tenant=r.tenant AND e.entity_id=r.object_id) "
            "WHERE r.tenant=? AND r.subject_id=? AND r.predicate IN ('connected_to_l2', 'adjacent_to', 'forwarding_dependency') "
            "AND r.valid_from <= ? AND r.valid_until >= ?",
            (tenant, device_id, timestamp, timestamp),
        )

        for rel in outgoing:
            obj_id = rel["object_id"]
            if obj_id == device_id or obj_id in seen_endpoints or obj_id in seen_downstream or obj_id in seen_peers:
                continue

            dev = session.one("SELECT * FROM network_devices WHERE tenant=? AND device_id=?", (tenant, obj_id))
            dev_role = dev["device_role"] if dev else rel.get("entity_kind", "other")
            obj_tier = ROLE_TIER.get(dev_role, 1)

            dev_summary = {
                "device_id": obj_id,
                "name": dev["name"] if dev else obj_id,
                "device_role": dev_role,
                "health_status": dev["health_status"] if dev else "unknown",
                "relationship_class": rel["relationship_class"],
                "confidence": rel["confidence"],
                "link_type": rel["predicate"],
            }

            if rel["predicate"] == "forwarding_dependency":
                impact_cat, redundant_paths = analyze_redundancy(obj_id)
                dev_summary["redundant_paths"] = redundant_paths
                dev_summary["impact_category"] = impact_cat
                seen_downstream.add(obj_id)
                if impact_cat == "confirmed_affected":
                    confirmed_devices.append(dev_summary)
                else:
                    potentially_affected_devices.append(dev_summary)
            elif rel["predicate"] == "connected_to_l2":
                if target_tier > obj_tier:
                    impact_cat, redundant_paths = analyze_redundancy(obj_id)
                    dev_summary["redundant_paths"] = redundant_paths
                    dev_summary["impact_category"] = impact_cat
                    seen_downstream.add(obj_id)
                    if impact_cat == "confirmed_affected":
                        confirmed_devices.append(dev_summary)
                    else:
                        potentially_affected_devices.append(dev_summary)
                else:
                    dev_summary["impact_category"] = "adjacent_peer"
                    seen_peers.add(obj_id)
                    adjacent_peer_devices.append(dev_summary)
            else:
                dev_summary["impact_category"] = "adjacent_peer"
                seen_peers.add(obj_id)
                adjacent_peer_devices.append(dev_summary)

        # 3. Propagate impact to endpoints attached to downstream devices
        for d in confirmed_devices:
            d_id = d["device_id"]
            ep_conns = session.all(
                "SELECT * FROM topology_relationships WHERE tenant=? AND object_id=? AND predicate='connected_to_l2' "
                "AND valid_from <= ? AND valid_until >= ?",
                (tenant, d_id, timestamp, timestamp),
            )
            for ep_rel in ep_conns:
                ep_subj = ep_rel["subject_id"]
                if ep_subj not in seen_endpoints:
                    ep_rec = session.one("SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?", (tenant, ep_subj))
                    if ep_rec:
                        seen_endpoints.add(ep_subj)
                        confirmed_endpoints.append({
                            "endpoint_id": ep_subj,
                            "hostname": ep_rec["primary_hostname"],
                            "site_id": ep_rec["site_id"],
                            "relationship_class": ep_rel["relationship_class"],
                            "confidence": ep_rel["confidence"],
                            "provenance": ep_rel["provenance_source"],
                            "link_type": ep_rel["predicate"],
                            "dependency_type": "confirmed",
                            "via_device": d_id,
                        })

        for d in potentially_affected_devices:
            d_id = d["device_id"]
            ep_conns = session.all(
                "SELECT * FROM topology_relationships WHERE tenant=? AND object_id=? AND predicate='connected_to_l2' "
                "AND valid_from <= ? AND valid_until >= ?",
                (tenant, d_id, timestamp, timestamp),
            )
            for ep_rel in ep_conns:
                ep_subj = ep_rel["subject_id"]
                if ep_subj not in seen_endpoints:
                    ep_rec = session.one("SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?", (tenant, ep_subj))
                    if ep_rec:
                        seen_endpoints.add(ep_subj)
                        potentially_affected_endpoints.append({
                            "endpoint_id": ep_subj,
                            "hostname": ep_rec["primary_hostname"],
                            "site_id": ep_rec["site_id"],
                            "relationship_class": ep_rel["relationship_class"],
                            "confidence": ep_rel["confidence"],
                            "provenance": ep_rel["provenance_source"],
                            "link_type": ep_rel["predicate"],
                            "dependency_type": "potential",
                            "via_device": d_id,
                        })

        all_affected_devices = confirmed_devices + potentially_affected_devices
        all_affected_endpoints = confirmed_endpoints + potentially_affected_endpoints

        return {
            "tenant": tenant,
            "target_device_id": device_id,
            "target_device_name": target_dev.get("name", device_id),
            "target_device_role": target_role,
            "health_status": target_dev.get("health_status", "unknown"),
            "direct_affected_endpoint_count": len(confirmed_endpoints),
            "direct_affected_device_count": len(all_affected_devices),
            "adjacent_peer_device_count": len(adjacent_peer_devices),
            "confirmed_affected_devices": confirmed_devices,
            "potentially_affected_devices": potentially_affected_devices,
            "adjacent_peer_devices": adjacent_peer_devices,
            "unknown_impact_devices": unknown_impact_devices,
            "confirmed_affected_endpoints": confirmed_endpoints,
            "potentially_affected_endpoints": potentially_affected_endpoints,
            "affected_endpoints": all_affected_endpoints,
            "affected_downstream_devices": all_affected_devices,
        }


# -------------------------------------------------------------------------
# Reusable Discovery Adapters
# -------------------------------------------------------------------------
class ZabbixDiscoveryAdapter:
    """Ingests Zabbix SNMP inventory, interface tables, and device health."""

    @staticmethod
    def parse_host(tenant: str, host_payload: Dict[str, Any], now: float) -> Tuple[NetworkDevice, List[NetworkInterface]]:
        contracts.identifier(tenant)
        hostid = str(host_payload["hostid"])
        device_id = f"dev-zbx-{hostid}"
        name = host_payload.get("host", host_payload.get("name", f"zabbix-host-{hostid}"))

        # Determine role from inventory or name heuristic
        role = host_payload.get("device_role")
        if not role or role not in DEVICE_ROLES:
            lname = name.lower()
            if "ap" in lname or "wap" in lname:
                role = "wireless_ap"
            elif "core" in lname:
                role = "core_switch"
            elif "dist" in lname:
                role = "distribution_switch"
            elif "sw" in lname or "switch" in lname:
                role = "access_switch"
            elif "gw" in lname or "gateway" in lname or "rtr" in lname or "router" in lname:
                role = "gateway"
            elif "fw" in lname or "firewall" in lname:
                role = "firewall"
            else:
                role = "other"

        health = "healthy"
        if host_payload.get("available") == "2" or host_payload.get("snmp_available") == "2":
            health = "unreachable"
        elif host_payload.get("has_active_triggers") or host_payload.get("problem_count", 0) > 0:
            health = "critical" if host_payload.get("critical_problems", 0) > 0 else "warning"

        dev = NetworkDevice(
            tenant=tenant,
            device_id=device_id,
            name=name,
            device_role=role,
            site_id=host_payload.get("site_id", "default"),
            routing_domain_id=host_payload.get("routing_domain_id", "default"),
            management_ip=host_payload.get("ip") or host_payload.get("interfaces", [{}])[0].get("ip"),
            serial_number=host_payload.get("serial_number"),
            model=host_payload.get("model"),
            vendor=host_payload.get("vendor"),
            snmp_sys_name=host_payload.get("snmp_sys_name", name),
            snmp_sys_descr=host_payload.get("snmp_sys_descr"),
            zabbix_hostid=hostid,
            health_status=health,
            health_details=host_payload.get("health_details", {}),
            observed_at=now,
        )

        interfaces: List[NetworkInterface] = []
        for raw_if in host_payload.get("snmp_interfaces", []):
            if_index = raw_if.get("if_index") or raw_if.get("ifIndex")
            if_name = raw_if.get("if_name") or raw_if.get("ifDescr", f"port-{if_index}")
            if_id = f"if-{device_id}-{if_index or hashlib.sha256(if_name.encode()).hexdigest()[:8]}"
            itype = raw_if.get("if_type", "ETHERNET")
            if itype not in INTERFACE_TYPES:
                itype = "ETHERNET"

            interfaces.append(NetworkInterface(
                tenant=tenant,
                interface_id=if_id,
                device_id=device_id,
                interface_name=if_name,
                interface_type=itype,
                if_index=int(if_index) if if_index is not None else None,
                mac_address=raw_if.get("mac_address"),
                ip_address=raw_if.get("ip_address"),
                admin_status=raw_if.get("admin_status", "up"),
                oper_status=raw_if.get("oper_status", "up"),
                speed_bps=raw_if.get("speed_bps"),
                vlan_id=raw_if.get("vlan_id"),
                observed_at=now,
            ))

        return dev, interfaces

    @staticmethod
    def parse_lldp_items(
        tenant: str,
        local_device_id: str,
        items: List[Dict[str, Any]],
        now: float,
        is_synthetic: bool = False,
        validity_ttl_seconds: Optional[float] = None,
    ) -> List[TopologyRelationship]:
        """Parses IEEE 802.1AB LLDP items collected by Zabbix into verified topology relationships.

        Observation freshness: relationships remain active for the duration of the validity TTL
        (defaulting to observation interval or 7-day upper bound), expiring cleanly once polling ceases.
        """
        contracts.identifier(tenant)
        contracts.identifier(local_device_id)

        import re
        by_idx: Dict[str, Dict[str, str]] = {}
        for it in items:
            k = it.get("key_", "")
            v = str(it.get("lastvalue") or "").strip('"').strip()
            if not v:
                continue
            match = re.search(r"lldpRem(\w+)\.([\d.]+)", k)
            if match:
                prop, idx = match.group(1), match.group(2)
                if idx not in by_idx:
                    by_idx[idx] = {}
                by_idx[idx][prop.lower()] = v

        ttl = validity_ttl_seconds if validity_ttl_seconds is not None else (86400 * 7)

        relationships: List[TopologyRelationship] = []
        for idx, entry in by_idx.items():
            rem_sysname = entry.get("sysname")
            rem_portid = entry.get("portid", f"port-{idx}")
            rem_portdesc = entry.get("portdesc", "")
            rem_chassisid = entry.get("chassisid", "")
            if rem_sysname:
                clean_target = re.sub(r"[^A-Za-z0-9_.-]", "_", rem_sysname.lower())
                target_id = f"dev-zbx-{clean_target}" if not clean_target.startswith("dev-") else clean_target

                # Parse RFC 802.1AB index: <timeMark>.<localPortNum>.<remIndex>
                idx_parts = idx.split(".")
                local_port_num = int(idx_parts[1]) if len(idx_parts) >= 2 and idx_parts[1].isdigit() else None

                synthetic_claim = is_synthetic or any(x in local_device_id.lower() or x in target_id.lower() for x in ("mock", "test", "simulated", "synthetic"))

                rel_id = f"rel-lldp-{hashlib.sha256(f'{tenant}:{local_device_id}:{idx}:{target_id}'.encode()).hexdigest()[:16]}"
                relationships.append(TopologyRelationship(
                    tenant=tenant,
                    relationship_id=rel_id,
                    subject_id=local_device_id,
                    predicate="connected_to_l2",
                    object_id=target_id,
                    relationship_class="discovered_l2_topology",
                    provenance_source="zabbix_snmp",
                    provenance_object_id=f"lldpRemSysName.{idx}",
                    valid_from=now,
                    valid_until=now + ttl,
                    confidence=CONFIDENCE_LLDP_CDP,
                    first_observed=now,
                    last_observed=now,
                    attributes={
                        "remote_sysname": rem_sysname,
                        "remote_port": rem_portid,
                        "remote_port_desc": rem_portdesc,
                        "remote_chassis_id": rem_chassisid,
                        "local_port_num": local_port_num,
                        "snmp_index": idx,
                        "protocol": "lldp",
                        "is_synthetic": synthetic_claim,
                    },
                ))
        return relationships


class L2DiscoveryAdapter:
    """Ingests Layer 2 discovery data: LLDP, CDP, Switch FDB/CAM, and Wireless associations."""

    @staticmethod
    def parse_lldp_neighbor(tenant: str, local_device_id: str, local_port: str,
                            remote_device_id: str, remote_port: str, now: float) -> TopologyRelationship:
        contracts.identifier(tenant)
        contracts.identifier(local_device_id)
        contracts.identifier(remote_device_id)

        rel_id = f"rel-lldp-{hashlib.sha256(f'{tenant}:{local_device_id}:{local_port}:{remote_device_id}'.encode()).hexdigest()[:16]}"
        return TopologyRelationship(
            tenant=tenant,
            relationship_id=rel_id,
            subject_id=local_device_id,
            predicate="connected_to_l2",
            object_id=remote_device_id,
            relationship_class="discovered_l2_topology",
            provenance_source="lldp_neighbor",
            provenance_object_id=f"{local_port}->{remote_port}",
            valid_from=now,
            valid_until=now + 86400 * 7,
            confidence=CONFIDENCE_LLDP_CDP,
            first_observed=now,
            last_observed=now,
            attributes={"local_port": local_port, "remote_port": remote_port, "protocol": "lldp"},
        )

    @staticmethod
    def parse_cdp_neighbor(tenant: str, local_device_id: str, local_port: str,
                           remote_device_id: str, remote_port: str, now: float) -> TopologyRelationship:
        contracts.identifier(tenant)
        contracts.identifier(local_device_id)
        contracts.identifier(remote_device_id)

        rel_id = f"rel-cdp-{hashlib.sha256(f'{tenant}:{local_device_id}:{local_port}:{remote_device_id}'.encode()).hexdigest()[:16]}"
        return TopologyRelationship(
            tenant=tenant,
            relationship_id=rel_id,
            subject_id=local_device_id,
            predicate="connected_to_l2",
            object_id=remote_device_id,
            relationship_class="discovered_l2_topology",
            provenance_source="cdp_neighbor",
            provenance_object_id=f"{local_port}->{remote_port}",
            valid_from=now,
            valid_until=now + 86400 * 7,
            confidence=CONFIDENCE_LLDP_CDP,
            first_observed=now,
            last_observed=now,
            attributes={"local_port": local_port, "remote_port": remote_port, "protocol": "cdp"},
        )


class L3DiscoveryAdapter:
    """Ingests Layer 3 routing, default gateway, and subnet observations."""

    @staticmethod
    def parse_gateway_relationship(tenant: str, source_entity_id: str, gateway_device_id: str,
                                   gateway_ip: str, now: float) -> TopologyRelationship:
        contracts.identifier(tenant)
        contracts.identifier(source_entity_id)
        contracts.identifier(gateway_device_id)

        rel_id = f"rel-gw-{hashlib.sha256(f'{tenant}:{source_entity_id}:gw:{gateway_device_id}'.encode()).hexdigest()[:16]}"
        return TopologyRelationship(
            tenant=tenant,
            relationship_id=rel_id,
            subject_id=source_entity_id,
            predicate="default_gateway_for",
            object_id=gateway_device_id,
            relationship_class="measured_l3_path",
            provenance_source="arp_table",
            provenance_object_id=gateway_ip,
            valid_from=now,
            valid_until=now + 86400 * 7,
            confidence=CONFIDENCE_ARP,
            first_observed=now,
            last_observed=now,
            attributes={"gateway_ip": gateway_ip},
        )
