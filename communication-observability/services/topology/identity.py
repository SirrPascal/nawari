"""Canonical Device Identity Resolver & Evidentiary Scorer for Nawari Topology."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any

from services.topology.models.device import ConfidenceLevel


def normalize_mac_address(mac: str | None) -> str | None:
    """Normalize MAC address string to lower-case colon-separated format (e.g. 00:1a:2b:3c:4d:5e)."""
    if not mac:
        return None
    # Strip any delimiters (colons, hyphens, dots)
    clean = re.sub(r"[^0-9a-fA-F]", "", mac).lower()
    if len(clean) != 12:
        return None
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def normalize_ip_address(ip: str | None) -> str | None:
    """Normalize IP address string."""
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def generate_device_id(
    chassis_mac: str | None = None,
    serial_number: str | None = None,
    zabbix_host_id: int | None = None,
    management_ip: str | None = None,
    fallback_name: str | None = None,
) -> str:
    """Generate deterministic device_id based on identity cascade:

    Chassis MAC > Serial Number > Zabbix Host ID > Management IP > Fallback Name.
    Format: dev-{sha256(canonical_key)[:16]}
    """
    norm_mac = normalize_mac_address(chassis_mac)
    if norm_mac:
        key = f"mac:{norm_mac}"
    elif serial_number and serial_number.strip():
        key = f"serial:{serial_number.strip().upper()}"
    elif zabbix_host_id is not None and zabbix_host_id > 0:
        key = f"zbx:{zabbix_host_id}"
    elif management_ip:
        norm_ip = normalize_ip_address(management_ip)
        key = f"ip:{norm_ip or management_ip.strip()}"
    elif fallback_name:
        key = f"name:{fallback_name.strip().lower()}"
    else:
        raise ValueError("Cannot generate device_id without at least one identifier")

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"dev-{digest}"


def generate_interface_id(device_id: str, if_index: int) -> str:
    """Generate deterministic interface_id: if-{device_id}-{if_index}."""
    return f"if-{device_id}-{if_index}"


def generate_link_id(source_interface_id: str, target_interface_id: str) -> str:
    """Generate canonical undirected link ID ensuring link(A, B) == link(B, A)."""
    ordered = sorted([source_interface_id, target_interface_id])
    return f"link-{ordered[0]}-{ordered[1]}"


def generate_subnet_id(network_cidr: str) -> str:
    """Generate deterministic subnet_id from CIDR notation."""
    try:
        net = ipaddress.ip_network(network_cidr.strip(), strict=False)
        canon = str(net)
    except ValueError:
        canon = network_cidr.strip().lower()
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    return f"sub-{digest}"


def generate_dependency_id(service_id: str, dependent_id: str) -> str:
    """Generate deterministic service dependency ID."""
    return f"dep-{service_id.strip()}-{dependent_id.strip()}"


class EvidentiaryScorer:
    """Calculates evidentiary confidence score and classification for network topology links."""

    PROTOCOL_BASE_CONFIDENCE: dict[str, float] = {
        "LLDP_RECIPROCAL": 0.98,
        "LLDP": 0.90,
        "CDP_RECIPROCAL": 0.95,
        "CDP": 0.88,
        "ROUTING_OSPF_FULL": 0.92,
        "ROUTING_BGP_ESTABLISHED": 0.92,
        "BRIDGE_FDB_EXCLUSIVE": 0.85,
        "BRIDGE_FDB": 0.70,
        "ENDPOINT_TRACEROUTE": 0.65,
        "ARP_CACHE": 0.60,
        "MANUAL_CONFIG": 1.00,
    }

    @classmethod
    def score_link(
        cls,
        discovery_protocol: str,
        is_reciprocal: bool = False,
        extra_evidence: dict[str, Any] | None = None,
    ) -> tuple[float, ConfidenceLevel]:
        """Compute confidence score and ConfidenceLevel based on discovery evidence."""
        proto = discovery_protocol.upper()
        if is_reciprocal:
            key = f"{proto}_RECIPROCAL"
            base_score = cls.PROTOCOL_BASE_CONFIDENCE.get(
                key, cls.PROTOCOL_BASE_CONFIDENCE.get(proto, 0.70)
            )
        else:
            base_score = cls.PROTOCOL_BASE_CONFIDENCE.get(proto, 0.50)

        # Modifiers based on corroborating evidence
        if extra_evidence:
            if extra_evidence.get("vlan_match"):
                base_score = min(1.00, base_score + 0.02)
            if extra_evidence.get("speed_match"):
                base_score = min(1.00, base_score + 0.02)
            if extra_evidence.get("multiple_observations", 0) > 3:
                base_score = min(1.00, base_score + 0.03)

        score = round(base_score, 2)
        if score >= 0.95:
            level = ConfidenceLevel.CONFIRMED
        elif score >= 0.75:
            level = ConfidenceLevel.PROBABLE
        elif score >= 0.50:
            level = ConfidenceLevel.INFERRED
        else:
            level = ConfidenceLevel.UNKNOWN

        return score, level

