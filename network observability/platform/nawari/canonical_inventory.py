"""Canonical Infrastructure Identity Model and Multi-Source Reconciliation for Nawari.

Reconciles devices across Zabbix, Netdata, and synthetic lab fixtures into unified
canonical entities with strict environment segregation (production, staging, lab, synthetic)
to prevent lab fixtures from contaminating production views.
"""

from __future__ import annotations
import hashlib
import json
import time
from typing import Dict, Any, List, Optional


class CanonicalInventoryManager:
    """Manages canonical infrastructure inventory and cross-system identity reconciliation."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def generate_canonical_id(management_ip: Optional[str] = None, mac_address: Optional[str] = None, serial_number: Optional[str] = None, name: str = "") -> str:
        """Derive a deterministic canonical ID using hardware/network identifiers."""
        if serial_number and serial_number.strip():
            seed = f"sn:{serial_number.strip().upper()}"
        elif mac_address and mac_address.strip():
            clean_mac = mac_address.strip().lower().replace(":", "").replace("-", "")
            seed = f"mac:{clean_mac}"
        elif management_ip and management_ip.strip():
            seed = f"ip:{management_ip.strip()}"
        else:
            seed = f"name:{name.strip().lower()}"
        
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"dev-{digest}"

    def reconcile_device(
        self,
        name: str,
        source_system: str,
        source_id: str,
        management_ip: Optional[str] = None,
        mac_address: Optional[str] = None,
        serial_number: Optional[str] = None,
        vendor: Optional[str] = None,
        model: Optional[str] = None,
        device_type: str = "switch",
        environment: str = "production",
        authoritative_source: str = "zabbix",
        trust_score: float = 1.0,
        observed_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Reconcile a reported device into the canonical device registry."""
        now = time.time()
        obs_at = observed_at or now
        
        # Enforce valid environment
        valid_envs = {"production", "staging", "lab", "synthetic"}
        env = environment.lower()
        if env not in valid_envs:
            raise ValueError("invalid_environment")
        
        # Generate canonical ID
        canonical_id = self.generate_canonical_id(management_ip, mac_address, serial_number, name)

        with self.store.db.transaction() as session:
            result = session.one(
                """
                INSERT INTO canonical_devices (
                    canonical_id, name, management_ip, mac_address, serial_number,
                    vendor, model, device_type, environment, authoritative_source,
                    trust_score, is_stale, source_system, source_id, observed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, ?, ?, ?, ?, ?)
                ON CONFLICT (canonical_id) DO UPDATE SET
                    name=excluded.name,
                    management_ip=COALESCE(excluded.management_ip, canonical_devices.management_ip),
                    mac_address=COALESCE(excluded.mac_address, canonical_devices.mac_address),
                    serial_number=COALESCE(excluded.serial_number, canonical_devices.serial_number),
                    vendor=COALESCE(excluded.vendor, canonical_devices.vendor),
                    model=COALESCE(excluded.model, canonical_devices.model),
                    device_type=excluded.device_type,
                    authoritative_source=excluded.authoritative_source,
                    trust_score=excluded.trust_score,
                    is_stale=FALSE,
                    source_system=excluded.source_system,
                    source_id=excluded.source_id,
                    observed_at=excluded.observed_at,
                    updated_at=excluded.updated_at
                WHERE canonical_devices.environment=excluded.environment
                    AND canonical_devices.observed_at <= excluded.observed_at
                RETURNING canonical_id
                """,
                (canonical_id, name, management_ip, mac_address, serial_number, vendor, model, device_type,
                 env, authoritative_source, trust_score, source_system, source_id, obs_at, now, now),
            )
            if not result:
                previous = session.one("SELECT environment FROM canonical_devices WHERE canonical_id=?", (canonical_id,))
                if previous["environment"] != env:
                    raise ValueError("canonical_environment_conflict")

        return {
            "canonical_id": canonical_id,
            "name": name,
            "management_ip": management_ip,
            "environment": env,
            "status": "reconciled" if result else "stale_observation",
        }

    def register_interface(
        self,
        canonical_id: str,
        if_name: str,
        source_system: str,
        if_index: Optional[int] = None,
        if_descr: Optional[str] = None,
        mac_address: Optional[str] = None,
        speed_bps: int = 0,
        duplex: str = "full",
        admin_status: str = "up",
        oper_status: str = "up",
        vlan_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        observed_at: Optional[float] = None,
    ) -> str:
        """Register or update an interface for a canonical device."""
        now = time.time()
        obs_at = observed_at or now
        interface_id = f"if-{canonical_id}-{if_name.replace('/', '_')}"

        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO canonical_interfaces (
                    interface_id, canonical_id, if_index, if_name, if_descr,
                    mac_address, speed_bps, duplex, admin_status, oper_status,
                    vlan_id, ip_address, source_system, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (interface_id) DO UPDATE SET
                    canonical_id=excluded.canonical_id,
                    if_index=excluded.if_index,
                    if_name=excluded.if_name,
                    if_descr=excluded.if_descr,
                    mac_address=excluded.mac_address,
                    speed_bps=excluded.speed_bps,
                    duplex=excluded.duplex,
                    admin_status=excluded.admin_status,
                    oper_status=excluded.oper_status,
                    vlan_id=excluded.vlan_id,
                    ip_address=excluded.ip_address,
                    source_system=excluded.source_system,
                    observed_at=excluded.observed_at
                """,
                (
                    interface_id,
                    canonical_id,
                    if_index,
                    if_name,
                    if_descr,
                    mac_address,
                    speed_bps,
                    duplex,
                    admin_status,
                    oper_status,
                    vlan_id,
                    ip_address,
                    source_system,
                    obs_at,
                ),
            )
        return interface_id

    def list_devices(self, environment: Optional[str] = None, include_synthetic: bool = False) -> List[Dict[str, Any]]:
        """List canonical devices, filtering by environment to prevent lab fixture leakage."""
        with self.store.db.transaction() as session:
            if environment:
                rows = session.all(
                    "SELECT * FROM canonical_devices WHERE environment = ? ORDER BY name ASC",
                    (environment,),
                )
            elif not include_synthetic:
                rows = session.all(
                    "SELECT * FROM canonical_devices WHERE environment != 'synthetic' ORDER BY environment ASC, name ASC"
                )
            else:
                rows = session.all("SELECT * FROM canonical_devices ORDER BY environment ASC, name ASC")
            
            return [dict(r) for r in rows]

    def get_device(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        with self.store.db.transaction() as session:
            row = session.first("SELECT * FROM canonical_devices WHERE canonical_id = ?", (canonical_id,))
            if not row:
                return None
            dev = dict(row)
            ifaces = session.all("SELECT * FROM canonical_interfaces WHERE canonical_id = ?", (canonical_id,))
            dev["interfaces"] = [dict(i) for i in ifaces]
            return dev

    def register_ha_cluster(
        self,
        cluster_id: str,
        name: str,
        cluster_type: str,
        vip_ip: Optional[str] = None,
        primary_canonical_id: Optional[str] = None,
        secondary_canonical_id: Optional[str] = None,
        failover_mode: str = "active_standby",
        status: str = "healthy",
        attributes: Optional[Dict[str, Any]] = None,
        observed_at: Optional[float] = None,
    ) -> str:
        """Register or update a logical High Availability (HA) cluster (e.g. SBCE pair, CM Duplex)."""
        now = time.time()
        obs_at = observed_at or now
        attr_json = json.dumps(attributes or {})

        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO canonical_ha_clusters (
                    cluster_id, name, cluster_type, vip_ip, primary_canonical_id,
                    secondary_canonical_id, failover_mode, status, attributes_json,
                    observed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cluster_id) DO UPDATE SET
                    name=excluded.name,
                    cluster_type=excluded.cluster_type,
                    vip_ip=excluded.vip_ip,
                    primary_canonical_id=excluded.primary_canonical_id,
                    secondary_canonical_id=excluded.secondary_canonical_id,
                    failover_mode=excluded.failover_mode,
                    status=excluded.status,
                    attributes_json=excluded.attributes_json,
                    observed_at=excluded.observed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    cluster_id, name, cluster_type, vip_ip, primary_canonical_id,
                    secondary_canonical_id, failover_mode, status, attr_json,
                    obs_at, now, now
                ),
            )
        return cluster_id

    def get_ha_cluster(self, cluster_id: str) -> Optional[Dict[str, Any]]:
        with self.store.db.transaction() as session:
            row = session.first("SELECT * FROM canonical_ha_clusters WHERE cluster_id = ?", (cluster_id,))
            if not row:
                return None
            res = dict(row)
            try:
                res["attributes"] = json.loads(res.get("attributes_json") or "{}")
            except Exception:
                res["attributes"] = {}
            return res

    def list_ha_clusters(self, cluster_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.store.db.transaction() as session:
            if cluster_type:
                rows = session.all("SELECT * FROM canonical_ha_clusters WHERE cluster_type = ? ORDER BY name ASC", (cluster_type,))
            else:
                rows = session.all("SELECT * FROM canonical_ha_clusters ORDER BY cluster_type ASC, name ASC")
            
            result = []
            for r in rows:
                item = dict(r)
                try:
                    item["attributes"] = json.loads(item.get("attributes_json") or "{}")
                except Exception:
                    item["attributes"] = {}
                result.append(item)
            return result

    def associate_device_site(
        self,
        canonical_id: str,
        site_id: str,
        location_name: Optional[str] = None,
        rack_unit: Optional[str] = None,
        network_segment: Optional[str] = None,
        valid_from: Optional[float] = None,
        valid_until: Optional[float] = None,
    ) -> None:
        """Associate a canonical device with a physical site and network segment."""
        now = time.time()
        vf = valid_from or now
        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO canonical_device_sites (
                    canonical_id, site_id, location_name, rack_unit, network_segment, valid_from, valid_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (canonical_id, site_id) DO UPDATE SET
                    location_name=excluded.location_name,
                    rack_unit=excluded.rack_unit,
                    network_segment=excluded.network_segment,
                    valid_from=excluded.valid_from,
                    valid_until=excluded.valid_until
                """,
                (canonical_id, site_id, location_name, rack_unit, network_segment, vf, valid_until),
            )

    def record_entity_state(
        self,
        entity_id: str,
        entity_type: str,
        measurement_state: str,
        operational_health: str,
        evidence_category: str = "observed",
        source_system: str = "zabbix",
        evidence_summary: Optional[str] = None,
        last_measured_at: Optional[float] = None,
    ) -> None:
        """Record or update the canonical measurement state and operational health for an entity."""
        now = time.time()
        l_meas = last_measured_at or now
        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO canonical_entity_states (
                    entity_id, entity_type, measurement_state, operational_health,
                    evidence_category, last_measured_at, source_system, evidence_summary, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    measurement_state=excluded.measurement_state,
                    operational_health=excluded.operational_health,
                    evidence_category=excluded.evidence_category,
                    last_measured_at=excluded.last_measured_at,
                    source_system=excluded.source_system,
                    evidence_summary=excluded.evidence_summary,
                    updated_at=excluded.updated_at
                """,
                (entity_id, entity_type, measurement_state, operational_health,
                 evidence_category, l_meas, source_system, evidence_summary, now),
            )

    def get_entity_state(self, entity_id: str, entity_type: str) -> Optional[Dict[str, Any]]:
        with self.store.db.transaction() as session:
            row = session.first(
                "SELECT * FROM canonical_entity_states WHERE entity_id = ? AND entity_type = ?",
                (entity_id, entity_type),
            )
            return dict(row) if row else None

