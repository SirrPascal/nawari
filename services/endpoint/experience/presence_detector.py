"""
services/endpoint/experience/presence_detector.py

Corporate Network Presence Detector for Nawari EU-NEM.
Differentiates endpoints located within the Kenya Airways enterprise network
from remote / off-net laptops without mistaking a corporate DNS or gateway
failure for a change in physical location.
"""

from __future__ import annotations

import ipaddress
from typing import List, Tuple

from services.endpoint.experience.models import (
    CorporatePresenceState,
    NetworkDiagnostics,
)

# Standard Kenya Airways Corporate Network Attributes
DEFAULT_CORPORATE_DNS_SERVERS = [
    "10.2.1.10",
    "10.2.1.11",
    "10.10.1.10",
    "10.20.1.10",
]

DEFAULT_CORPORATE_DOMAINS = [
    "kenya-airways.com",
    "kq.internal",
    "corp.kenya-airways.com",
]

DEFAULT_CORPORATE_SUBNETS = [
    ipaddress.ip_network("10.2.0.0/16"),    # Pride Center DC / HQ
    ipaddress.ip_network("10.10.0.0/16"),   # Mombasa (MBA)
    ipaddress.ip_network("10.20.0.0/16"),   # Kisumu (KIS)
    ipaddress.ip_network("10.102.0.0/16"),  # JKIA Airport Operations
    ipaddress.ip_network("172.16.50.0/24"), # Corporate Staff VPN Pool
]

DEFAULT_CORPORATE_SSIDS = [
    "KQ-Corporate",
    "KQ-PrideCenter-Corp",
    "KQ-Secure-Staff",
    "KQ-Airport-Ops",
]


class CorporatePresenceDetector:
    """Evaluates multi-signal evidence to determine corporate network presence."""

    def __init__(
        self,
        corporate_dns_servers: List[str] = None,
        corporate_domains: List[str] = None,
        corporate_subnets: List[ipaddress.IPv4Network] = None,
        corporate_ssids: List[str] = None,
    ):
        self.corporate_dns_servers = corporate_dns_servers or DEFAULT_CORPORATE_DNS_SERVERS
        self.corporate_domains = corporate_domains or DEFAULT_CORPORATE_DOMAINS
        self.corporate_subnets = corporate_subnets or DEFAULT_CORPORATE_SUBNETS
        self.corporate_ssids = corporate_ssids or DEFAULT_CORPORATE_SSIDS

    def _is_ip_in_subnets(self, ip_str: str) -> bool:
        """Check if an IP string falls within corporate subnets."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in subnet for subnet in self.corporate_subnets)
        except ValueError:
            return False

    def evaluate(self, net: NetworkDiagnostics) -> Tuple[CorporatePresenceState, float]:
        """
        Evaluate corporate presence from network diagnostics.
        Returns: (CorporatePresenceState, confidence_score: 0.0 - 1.0)
        """
        score = 0.0
        total_signals = 4

        # Signal 1: Default Gateway IP
        is_corp_gateway = self._is_ip_in_subnets(net.gateway_ip)
        if is_corp_gateway:
            score += 1.0

        # Signal 2: DNS Server configuration
        is_corp_dns = net.dns_server_ip in self.corporate_dns_servers or self._is_ip_in_subnets(net.dns_server_ip)
        if is_corp_dns:
            score += 1.0

        # Signal 3: DNS Domain suffix match
        is_corp_domain = any(net.dns_domain.lower().endswith(dom) for dom in self.corporate_domains)
        if is_corp_domain:
            score += 1.0

        # Signal 4: Wi-Fi SSID or Active Corporate VPN
        is_corp_wifi = net.wifi_ssid in self.corporate_ssids if net.wifi_ssid else False
        is_corp_vpn = net.vpn_active and (self._is_ip_in_subnets(net.vpn_gateway) if net.vpn_gateway else True)

        if is_corp_wifi or is_corp_vpn:
            score += 1.0

        confidence = score / total_signals

        # Decision Logic:
        # 1. Strong presence (score >= 2.0 or confirmed VPN)
        if score >= 3.0 or is_corp_vpn:
            if net.gateway_reachable and net.dns_success:
                return CorporatePresenceState.CORPORATE_CONFIRMED, min(1.0, confidence + 0.1)
            else:
                # Gateway or DNS degraded, but presence is verified
                return CorporatePresenceState.CORPORATE_DEGRADED, confidence

        # 2. Borderline / Degraded corporate presence (e.g. gateway matches but DNS failed)
        if score >= 1.0 and (is_corp_gateway or is_corp_wifi):
            if not net.gateway_reachable or not net.dns_success:
                return CorporatePresenceState.CORPORATE_DEGRADED, confidence
            return CorporatePresenceState.CORPORATE_CONFIRMED, confidence

        # 3. Off-Net / Remote (home Wi-Fi, public internet, zero corporate markers)
        return CorporatePresenceState.OFF_NET_REMOTE, 1.0 - confidence

