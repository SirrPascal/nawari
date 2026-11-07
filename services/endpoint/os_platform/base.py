"""Abstract base class and capability definitions for platform diagnostics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import WifiMetrics


@dataclass(frozen=True)
class PlatformCapabilities:
    """Explicit declaration of OS-supported diagnostic capabilities.

    Ensures the agent never fabricates values when an OS or privilege level
    does not support a specific diagnostic operation.
    """
    os_name: str
    os_version: str
    architecture: str
    supports_raw_icmp: bool
    supports_unprivileged_icmp: bool
    supports_wifi_diagnostics: bool
    supports_gateway_discovery: bool
    supports_dns_discovery: bool
    supports_path_tracing: bool = True
    requires_elevation_for: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "supports_raw_icmp": self.supports_raw_icmp,
            "supports_unprivileged_icmp": self.supports_unprivileged_icmp,
            "supports_wifi_diagnostics": self.supports_wifi_diagnostics,
            "supports_gateway_discovery": self.supports_gateway_discovery,
            "supports_dns_discovery": self.supports_dns_discovery,
            "supports_path_tracing": self.supports_path_tracing,
            "requires_elevation_for": list(self.requires_elevation_for),
        }


class PlatformAdapter(ABC):
    """Abstract interface isolating operating system-specific network probing."""

    @abstractmethod
    def get_capabilities(self) -> PlatformCapabilities:
        """Return the explicit diagnostic capabilities supported on this platform."""
        pass

    @abstractmethod
    def get_default_gateway(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (gateway_ip, gateway_mac, interface_name).

        Returns (None, None, None) if unavailable or unsupported.
        """
        pass

    @abstractmethod
    def get_interface_details(self, interface_name: str) -> Dict[str, Any]:
        """Return dict with keys: local_ip, subnet_cidr, state, type, dhcp_enabled."""
        pass

    @abstractmethod
    def get_wifi_metrics(self, interface_name: str) -> Optional[WifiMetrics]:
        """Return WifiMetrics if interface is Wi-Fi, otherwise None."""
        pass

    @abstractmethod
    def get_configured_dns_servers(self) -> List[str]:
        """Return list of configured DNS resolver IP addresses in order."""
        pass

    @abstractmethod
    def ping(
        self, destination_ip: str, count: int = 3, timeout_seconds: float = 1.0
    ) -> Tuple[bool, Optional[float], float]:
        """Send ICMP echo requests and return (is_reachable, avg_rtt_ms, loss_pct)."""
        pass

    @abstractmethod
    def trace_path(
        self,
        destination_ip: str,
        max_hops: int = 30,
        timeout_seconds: float = 2.0,
        target_port: Optional[int] = None,
        fixed_flow: bool = True,
    ) -> List[Dict[str, Any]]:
        """Send TTL-incremented path probes and return raw hop dictionary list."""
        pass
