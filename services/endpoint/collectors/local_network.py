"""Collector for edge connectivity and local network configuration."""

from __future__ import annotations

import logging
from typing import Optional

from services.endpoint.core.logger import setup_agent_logger
from services.endpoint.models import (
    InterfaceState,
    InterfaceType,
    LocalNetworkTelemetry,
    WifiMetrics,
)
from services.endpoint.os_platform.base import PlatformAdapter

logger = setup_agent_logger()


class LocalNetworkCollector:
    """Collects local default gateway, network interface, and Wi-Fi performance metrics."""

    def __init__(self, platform_adapter: PlatformAdapter) -> None:
        self.adapter = platform_adapter

    def collect(self) -> LocalNetworkTelemetry:
        """Execute local network diagnostics and return validated telemetry."""
        # 1. Gateway discovery
        gw_ip, gw_mac, iface_name = self.adapter.get_default_gateway()
        if not iface_name:
            iface_name = "default"

        # 2. Interface details
        iface_info = self.adapter.get_interface_details(iface_name)
        local_ip = iface_info.get("local_ip", "127.0.0.1")
        subnet_cidr = iface_info.get("subnet_cidr", 24)
        iface_state = iface_info.get("state", InterfaceState.UP)
        iface_type = iface_info.get("type", InterfaceType.ETHERNET)
        dhcp_enabled = iface_info.get("dhcp_enabled", True)

        # 3. Wi-Fi metrics (Invariant 2: isolated strictly to Wi-Fi interfaces)
        wifi_metrics: Optional[WifiMetrics] = None
        if iface_type == InterfaceType.WIFI:
            wifi_metrics = self.adapter.get_wifi_metrics(iface_name)

        # 4. Configured DNS servers
        dns_servers = self.adapter.get_configured_dns_servers()

        # 5. Default gateway reachability ping
        gw_reachable = False
        gw_rtt: Optional[float] = None
        gw_loss = 100.0

        if gw_ip:
            try:
                gw_reachable, gw_rtt, gw_loss = self.adapter.ping(
                    gw_ip, count=3, timeout_seconds=1.0
                )
            except Exception as exc:
                logger.warning(f"Error pinging default gateway {gw_ip}: {exc}")
                gw_reachable = False
                gw_rtt = None
                gw_loss = 100.0
        else:
            logger.info("No default gateway detected on active interface")

        return LocalNetworkTelemetry(
            default_gateway_ip=gw_ip,
            default_gateway_mac=gw_mac,
            gateway_is_reachable=gw_reachable,
            gateway_rtt_ms=gw_rtt,
            gateway_loss_pct=gw_loss,
            interface_name=iface_name,
            interface_type=iface_type,
            interface_state=iface_state,
            local_ip=local_ip,
            subnet_cidr=subnet_cidr,
            dhcp_enabled=dhcp_enabled,
            configured_dns_servers=dns_servers,
            wifi=wifi_metrics,
        )
