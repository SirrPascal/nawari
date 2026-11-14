"""Canonical Enterprise Endpoint & Infrastructure Identity Registry and Reconciliation Engine.

Hardened with:
- Opaque immutable UUIDv4 endpoint identifiers
- Explicit identity provenance and trust levels
- Hardware spoofing and serial number hijacking prevention
- Cloned machine GUID and duplicate identity quarantine
- Retired asset reappearance protection
- Strict tenant boundary enforcement
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from . import contracts

# -------------------------------------------------------------------------
# Trust Levels and Source Constants
# -------------------------------------------------------------------------
TRUST_LEVEL_ENROLLMENT = "trusted_enrollment"       # Direct provisioning / enrollment token
TRUST_LEVEL_INVENTORY = "authorized_inventory"       # Authorized MDM/CMDB (Intune, SolarWinds)
TRUST_LEVEL_COLLECTOR = "authenticated_collector"   # Authenticated Netdata streaming
TRUST_LEVEL_UNVERIFIED = "unverified_telemetry"     # Self-reported / untrusted telemetry

# Only these trusted sources may establish or transfer ownership of an existing managed asset
TRUSTED_OWNERSHIP_LEVELS = {TRUST_LEVEL_ENROLLMENT, TRUST_LEVEL_INVENTORY}

VALID_LIFECYCLES = {"enrolled", "active", "stale", "quarantined", "retired"}
VALID_SOURCES = {"nawari_agent", "intune", "solarwinds", "zabbix", "manual_inventory", "telemetry_observed"}


@dataclasses.dataclass(frozen=True)
class DeviceHardwareIdentity:
    serial_number: Optional[str] = None
    chassis_uuid: Optional[str] = None
    mac_address: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class NetworkInterfaceObservation:
    interface_name: str
    interface_type: str  # ETHERNET, WIFI, VPN, LOOPBACK, CELLULAR, OTHER
    ip_address: str
    mac_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    gateway_ip: Optional[str] = None
    ssid: Optional[str] = None
    bssid: Optional[str] = None


@dataclasses.dataclass
class EndpointObservation:
    tenant: str
    hostname: str
    source_system: str  # netdata_guid, zabbix_hostid, nawari_agent_id, intune_device_id, solarwinds_nodeid
    source_identifier: str
    device_kind: str = "laptop"  # laptop, workstation, server, mobile, appliance, synthetic_probe, unknown
    os_family: str = "unknown"
    os_version: str = "unknown"
    site_id: str = "default"
    routing_domain_id: str = "default"
    trust_level: str = TRUST_LEVEL_UNVERIFIED
    authoritative: bool = False
    hardware: Optional[DeviceHardwareIdentity] = None
    interfaces: List[NetworkInterfaceObservation] = dataclasses.field(default_factory=list)
    observed_at: float = 0.0

    def __post_init__(self):
        if not self.observed_at:
            self.observed_at = time.time()
        if self.authoritative and self.trust_level == TRUST_LEVEL_UNVERIFIED:
            self.trust_level = TRUST_LEVEL_INVENTORY


@dataclasses.dataclass
class ReconciliationResult:
    endpoint_id: Optional[str]
    status: str  # matched_hardware, matched_source_mapping, created_new, quarantined, conflict
    conflict_id: Optional[str] = None
    details: str = ""


def generate_endpoint_id() -> str:
    """Generate an opaque, immutable canonical endpoint_id using cryptographically secure UUIDv4."""
    return f"ep-{uuid.uuid4().hex}"


class EndpointReconciler:
    """Deterministic, trust-hardened endpoint identity reconciliation."""

    def __init__(self, stale_threshold_seconds: float = 86400 * 7):
        self.stale_threshold_seconds = stale_threshold_seconds

    def reconcile(self, session: Any, obs: EndpointObservation, now: float) -> ReconciliationResult:
        contracts.identifier(obs.tenant)
        contracts.identifier(obs.site_id)
        contracts.identifier(obs.routing_domain_id)

        # -----------------------------------------------------------------
        # 1. Match by Strong Hardware Identity (Serial Number or Chassis UUID)
        # -----------------------------------------------------------------
        hw_match = None
        if obs.hardware:
            if obs.hardware.serial_number:
                hw_match = session.one(
                    "SELECT * FROM endpoint_registry WHERE tenant=? AND serial_number=?",
                    (obs.tenant, obs.hardware.serial_number),
                )
            if not hw_match and obs.hardware.chassis_uuid:
                hw_match = session.one(
                    "SELECT * FROM endpoint_registry WHERE tenant=? AND chassis_uuid=?",
                    (obs.tenant, obs.hardware.chassis_uuid),
                )

        # -----------------------------------------------------------------
        # 2. Match by Existing Source System Mapping (Netdata GUID, Intune ID)
        # -----------------------------------------------------------------
        mapping_match = session.one(
            "SELECT m.*, r.lifecycle_state, r.serial_number, r.primary_hostname FROM endpoint_source_mappings m "
            "JOIN endpoint_registry r ON r.tenant=m.tenant AND r.endpoint_id=m.endpoint_id "
            "WHERE m.tenant=? AND m.source_system=? AND m.source_identifier=? AND m.valid_until>?",
            (obs.tenant, obs.source_system, obs.source_identifier, now),
        )

        # -----------------------------------------------------------------
        # 3. Security Boundary: Hardware Serial Claim from Untrusted Source
        # If an unverified or collector source presents a serial number matching
        # an existing managed asset, but DOES NOT have an established source mapping,
        # it must NOT acquire ownership of the managed asset.
        # -----------------------------------------------------------------
        if hw_match and not mapping_match and obs.trust_level not in TRUSTED_OWNERSHIP_LEVELS:
            conflict_id = f"conf-{hashlib.sha256(f'{obs.tenant}:{obs.source_identifier}:{now}'.encode()).hexdigest()[:16]}"
            session.execute(
                "INSERT INTO endpoint_identity_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (
                    obs.tenant,
                    conflict_id,
                    obs.source_system,
                    obs.source_identifier,
                    None,
                    hw_match["endpoint_id"],
                    "spoofed_serial_claim",
                    now,
                    json.dumps({
                        "reason": "Untrusted source presented hardware serial number of existing managed asset without prior authorization",
                        "claimed_serial": obs.hardware.serial_number if obs.hardware else None,
                        "existing_endpoint_id": hw_match["endpoint_id"],
                        "source_identifier": obs.source_identifier,
                        "trust_level": obs.trust_level,
                    }),
                ),
            )
            # Create quarantined unverified record rather than hijacking legitimate asset
            endpoint_id = generate_endpoint_id()
            self._insert_endpoint(session, obs, endpoint_id, now, lifecycle="quarantined", auth_source="telemetry_observed")
            self._record_source_mapping(session, obs, endpoint_id, now)
            self._record_hostname_history(session, obs, endpoint_id, now)
            self._record_network_observations(session, obs, endpoint_id, now)
            return ReconciliationResult(
                endpoint_id=endpoint_id,
                status="quarantined",
                conflict_id=conflict_id,
                details=f"Untrusted claim of serial {obs.hardware.serial_number if obs.hardware else 'none'} quarantined; isolated as {endpoint_id}",
            )

        # -----------------------------------------------------------------
        # 4. Conflict Check: Cloned Machine GUIDs / Hardware Discrepancies
        # -----------------------------------------------------------------
        hw_conflict = False
        if hw_match and mapping_match and hw_match["endpoint_id"] != mapping_match["endpoint_id"]:
            hw_conflict = True
        elif mapping_match and obs.hardware and obs.hardware.serial_number:
            mapped_serial = mapping_match.get("serial_number")
            if mapped_serial and mapped_serial != obs.hardware.serial_number:
                hw_conflict = True

        if hw_conflict:
            conflict_id = f"conf-{hashlib.sha256(f'{obs.tenant}:{obs.source_identifier}:{now}'.encode()).hexdigest()[:16]}"
            claimed_id = hw_match["endpoint_id"] if hw_match else None
            existing_id = mapping_match["endpoint_id"] if mapping_match else None
            session.execute(
                "INSERT INTO endpoint_identity_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (
                    obs.tenant,
                    conflict_id,
                    obs.source_system,
                    obs.source_identifier,
                    claimed_id,
                    existing_id,
                    "duplicate_machine_guid",
                    now,
                    json.dumps({
                        "reason": "Machine GUID claimed by multiple distinct hardware assets",
                        "hw_serial": obs.hardware.serial_number if obs.hardware else None,
                        "mapped_endpoint": existing_id,
                        "incoming_hostname": obs.hostname,
                    }),
                ),
            )
            return ReconciliationResult(
                endpoint_id=None,
                status="quarantined",
                conflict_id=conflict_id,
                details=f"Source identifier {obs.source_identifier} in conflict: claimed by different hardware than mapped asset {existing_id}",
            )

        # -----------------------------------------------------------------
        # 5. Lifecycle Protection: Retired Asset Reappearance
        # -----------------------------------------------------------------
        target_candidate = hw_match or mapping_match
        if target_candidate and target_candidate.get("lifecycle_state") == "retired":
            if obs.trust_level not in TRUSTED_OWNERSHIP_LEVELS:
                conflict_id = f"conf-{hashlib.sha256(f'{obs.tenant}:retired:{target_candidate['endpoint_id']}:{now}'.encode()).hexdigest()[:16]}"
                session.execute(
                    "INSERT INTO endpoint_identity_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
                    (
                        obs.tenant,
                        conflict_id,
                        obs.source_system,
                        obs.source_identifier,
                        None,
                        target_candidate["endpoint_id"],
                        "retired_asset_reappearance",
                        now,
                        json.dumps({
                            "reason": "Telemetry received for asset marked retired in inventory",
                            "endpoint_id": target_candidate["endpoint_id"],
                            "source_identifier": obs.source_identifier,
                        }),
                    ),
                )
                return ReconciliationResult(
                    endpoint_id=target_candidate["endpoint_id"],
                    status="quarantined",
                    conflict_id=conflict_id,
                    details=f"Asset {target_candidate['endpoint_id']} is retired; new telemetry quarantined pending operator reactivation",
                )

        # -----------------------------------------------------------------
        # 6. Untrusted Hostname Spoofing / Name Clash Guard
        # -----------------------------------------------------------------
        if not hw_match and not mapping_match:
            existing_by_hostname = session.one(
                "SELECT * FROM endpoint_registry WHERE tenant=? AND primary_hostname=?",
                (obs.tenant, obs.hostname),
            )
            if existing_by_hostname and obs.trust_level not in TRUSTED_OWNERSHIP_LEVELS:
                conflict_id = f"conf-{hashlib.sha256(f'{obs.tenant}:{obs.hostname}:{obs.source_identifier}'.encode()).hexdigest()[:16]}"
                session.execute(
                    "INSERT INTO endpoint_identity_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
                    (
                        obs.tenant,
                        conflict_id,
                        obs.source_system,
                        obs.source_identifier,
                        None,
                        existing_by_hostname["endpoint_id"],
                        "hostname_clash_different_hw",
                        now,
                        json.dumps({
                            "reason": "Telemetry source reported hostname of existing asset without matching hardware credentials",
                            "existing_endpoint_id": existing_by_hostname["endpoint_id"],
                            "reported_hostname": obs.hostname,
                        }),
                    ),
                )
                endpoint_id = generate_endpoint_id()
                self._insert_endpoint(session, obs, endpoint_id, now, lifecycle="quarantined", auth_source="telemetry_observed")
                self._record_source_mapping(session, obs, endpoint_id, now)
                self._record_hostname_history(session, obs, endpoint_id, now)
                self._record_network_observations(session, obs, endpoint_id, now)
                return ReconciliationResult(
                    endpoint_id=endpoint_id,
                    status="conflict",
                    conflict_id=conflict_id,
                    details=f"Hostname {obs.hostname} clashes with managed asset {existing_by_hostname['endpoint_id']}; quarantined as separate entity {endpoint_id}",
                )

        # -----------------------------------------------------------------
        # 7. Resolve Target Endpoint ID (Update or Create)
        # -----------------------------------------------------------------
        endpoint_id = None
        status = "created_new"

        if hw_match and (obs.trust_level in TRUSTED_OWNERSHIP_LEVELS or mapping_match):
            endpoint_id = hw_match["endpoint_id"]
            status = "matched_hardware"
        elif mapping_match:
            endpoint_id = mapping_match["endpoint_id"]
            status = "matched_source_mapping"

        if endpoint_id:
            # Update existing endpoint
            self._update_endpoint(session, obs, endpoint_id, now)
        else:
            # Create new canonical endpoint with immutable random UUID
            endpoint_id = generate_endpoint_id()
            auth_source = "nawari_agent" if obs.trust_level in TRUSTED_OWNERSHIP_LEVELS else "telemetry_observed"
            initial_lifecycle = "active" if obs.trust_level != TRUST_LEVEL_UNVERIFIED else "enrolled"
            self._insert_endpoint(session, obs, endpoint_id, now, lifecycle=initial_lifecycle, auth_source=auth_source)
            status = "created_new"

        # -----------------------------------------------------------------
        # 8. Record Source Mapping, Hostname History, and Network Observations
        # -----------------------------------------------------------------
        self._record_source_mapping(session, obs, endpoint_id, now)
        self._record_hostname_history(session, obs, endpoint_id, now)
        self._record_network_observations(session, obs, endpoint_id, now)

        return ReconciliationResult(
            endpoint_id=endpoint_id,
            status=status,
            details=f"Endpoint {endpoint_id} reconciled via {status}",
        )

    def _insert_endpoint(self, session: Any, obs: EndpointObservation, endpoint_id: str, now: float, lifecycle: str, auth_source: str) -> None:
        serial = obs.hardware.serial_number if obs.hardware else None
        chassis = obs.hardware.chassis_uuid if obs.hardware else None
        mac = obs.hardware.mac_address if obs.hardware else None

        session.execute(
            "INSERT INTO endpoint_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                obs.tenant,
                endpoint_id,
                obs.hostname,
                obs.hostname,
                serial,
                chassis,
                mac,
                obs.device_kind,
                obs.os_family,
                obs.os_version,
                obs.site_id,
                obs.routing_domain_id,
                lifecycle,
                obs.trust_level,
                auth_source,
                now,
                now,
                obs.observed_at,
            ),
        )

        # Backwards compatibility: mirror into assets and topology_entities
        session.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?) ON CONFLICT (tenant, asset_id) DO UPDATE SET name=excluded.name, site_id=excluded.site_id, routing_domain_id=excluded.routing_domain_id",
            (obs.tenant, endpoint_id, obs.hostname, obs.site_id, obs.routing_domain_id),
        )
        session.execute(
            "INSERT INTO topology_entities VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (tenant, entity_id) DO UPDATE SET attributes=excluded.attributes",
            (
                obs.tenant,
                endpoint_id,
                "endpoint",
                auth_source,
                obs.source_identifier,
                obs.site_id,
                obs.routing_domain_id,
                json.dumps({"hostname": obs.hostname, "os": obs.os_family, "device_kind": obs.device_kind, "trust_level": obs.trust_level}),
            ),
        )

    def _update_endpoint(self, session: Any, obs: EndpointObservation, endpoint_id: str, now: float) -> None:
        existing = session.one(
            "SELECT * FROM endpoint_registry WHERE tenant=? AND endpoint_id=?",
            (obs.tenant, endpoint_id),
        )
        if not existing:
            return

        # Hostname updates allowed only if authoritative or current primary is blank
        new_hostname = existing["primary_hostname"]
        if obs.trust_level in TRUSTED_OWNERSHIP_LEVELS or not existing["primary_hostname"]:
            new_hostname = obs.hostname

        # Promote lifecycle to active if fresh telemetry arrives for enrolled/stale asset
        lifecycle = existing["lifecycle_state"]
        if lifecycle in ("enrolled", "stale") and now - obs.observed_at < self.stale_threshold_seconds:
            lifecycle = "active"

        # Update trust level if incoming observation has higher provenance
        current_trust = existing.get("trust_level", TRUST_LEVEL_UNVERIFIED)
        if obs.trust_level in TRUSTED_OWNERSHIP_LEVELS:
            current_trust = obs.trust_level

        session.execute(
            "UPDATE endpoint_registry SET primary_hostname=?, os_family=COALESCE(NULLIF(?,'unknown'), os_family), "
            "os_version=COALESCE(NULLIF(?,'unknown'), os_version), site_id=?, routing_domain_id=?, "
            "lifecycle_state=?, trust_level=?, updated_at=?, last_seen_at=MAX(last_seen_at, ?) WHERE tenant=? AND endpoint_id=?",
            (
                new_hostname,
                obs.os_family,
                obs.os_version,
                obs.site_id,
                obs.routing_domain_id,
                lifecycle,
                current_trust,
                now,
                obs.observed_at,
                obs.tenant,
                endpoint_id,
            ),
        )

    def _record_source_mapping(self, session: Any, obs: EndpointObservation, endpoint_id: str, now: float) -> None:
        mapping = session.one(
            "SELECT * FROM endpoint_source_mappings WHERE tenant=? AND source_system=? AND source_identifier=?",
            (obs.tenant, obs.source_system, obs.source_identifier),
        )
        if mapping:
            session.execute(
                "UPDATE endpoint_source_mappings SET last_verified_at=?, valid_until=? WHERE tenant=? AND mapping_id=?",
                (now, now + 86400 * 90, obs.tenant, mapping["mapping_id"]),
            )
        else:
            mapping_id = f"map-{hashlib.sha256(f'{obs.tenant}:{obs.source_system}:{obs.source_identifier}'.encode()).hexdigest()[:16]}"
            session.execute(
                "INSERT INTO endpoint_source_mappings VALUES (?,?,?,?,?,1,?,?,?,?,?)",
                (
                    obs.tenant,
                    mapping_id,
                    endpoint_id,
                    obs.source_system,
                    obs.source_identifier,
                    obs.trust_level,
                    now,
                    now,
                    now - 86400,
                    now + 86400 * 90,
                ),
            )

    def _record_hostname_history(self, session: Any, obs: EndpointObservation, endpoint_id: str, now: float) -> None:
        entry = session.one(
            "SELECT * FROM endpoint_hostname_history WHERE tenant=? AND endpoint_id=? AND hostname=?",
            (obs.tenant, endpoint_id, obs.hostname),
        )
        if entry:
            session.execute(
                "UPDATE endpoint_hostname_history SET last_seen_at=? WHERE tenant=? AND history_id=?",
                (obs.observed_at, obs.tenant, entry["history_id"]),
            )
        else:
            hist_id = f"hst-{hashlib.sha256(f'{obs.tenant}:{endpoint_id}:{obs.hostname}'.encode()).hexdigest()[:16]}"
            session.execute(
                "INSERT INTO endpoint_hostname_history VALUES (?,?,?,?,?,?,?)",
                (obs.tenant, hist_id, endpoint_id, obs.hostname, obs.observed_at, obs.observed_at, obs.source_system),
            )

    def _record_network_observations(self, session: Any, obs: EndpointObservation, endpoint_id: str, now: float) -> None:
        for iface in obs.interfaces:
            obs_id = f"obs-{hashlib.sha256(f'{obs.tenant}:{endpoint_id}:{iface.interface_name}:{iface.ip_address}'.encode()).hexdigest()[:16]}"
            session.execute(
                "INSERT INTO endpoint_network_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT (tenant, observation_id) DO UPDATE SET observed_at=excluded.observed_at, valid_until=excluded.valid_until, gateway_ip=excluded.gateway_ip, ssid=excluded.ssid, bssid=excluded.bssid",
                (
                    obs.tenant,
                    obs_id,
                    endpoint_id,
                    iface.interface_name,
                    iface.interface_type,
                    iface.mac_address,
                    iface.ip_address,
                    iface.subnet_mask,
                    iface.gateway_ip,
                    iface.ssid,
                    iface.bssid,
                    obs.observed_at,
                    now + 86400 * 7,
                    obs.source_system,
                ),
            )
