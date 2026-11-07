"""Windows platform adapter for enterprise laptop diagnostics."""

from __future__ import annotations

import ctypes
import os
import platform
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import InterfaceState, InterfaceType, WifiMetrics
from services.endpoint.os_platform.base import PlatformAdapter, PlatformCapabilities


class WindowsAdapter(PlatformAdapter):
    """Platform adapter implementing Windows networking diagnostics."""

    def get_capabilities(self) -> PlatformCapabilities:
        is_admin = False
        if platform.system() == "Windows":
            try:
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                is_admin = False

        return PlatformCapabilities(
            os_name="Windows",
            os_version=platform.version() or platform.release(),
            architecture=platform.machine(),
            supports_raw_icmp=is_admin,
            # Windows official user-mode API IcmpSendEcho requires zero admin rights
            supports_unprivileged_icmp=True,
            supports_wifi_diagnostics=True,
            supports_gateway_discovery=True,
            supports_dns_discovery=True,
            requires_elevation_for=["raw_sockets"] if not is_admin else [],
        )

    def get_default_gateway(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            res = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            # Find the line with 0.0.0.0      0.0.0.0   <gateway_ip>   <interface_ip>
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                    gw_ip = parts[2]
                    iface_ip = parts[3]
                    return gw_ip, None, iface_ip
            return None, None, None
        except Exception:
            return None, None, None

    def get_interface_details(self, interface_name: str) -> Dict[str, Any]:
        result = {
            "local_ip": "127.0.0.1",
            "subnet_cidr": 8,
            "state": InterfaceState.UP,
            "type": InterfaceType.ETHERNET,
            "dhcp_enabled": True,
        }
        try:
            # Query active interface via ipconfig
            res = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            current_adapter = ""
            for line in res.stdout.splitlines():
                if line and not line.startswith(" "):
                    current_adapter = line.strip()
                line = line.strip()
                if "IPv4 Address" in line or "IP Address" in line:
                    m = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)", line)
                    if m and m.group(1) != "127.0.0.1":
                        result["local_ip"] = m.group(1)
                        if "Wireless" in current_adapter or "Wi-Fi" in current_adapter:
                            result["type"] = InterfaceType.WIFI
                        break
        except Exception:
            pass
        return result

    def get_wifi_metrics(self, interface_name: str) -> Optional[WifiMetrics]:
        try:
            res = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode != 0:
                return None

            data: Dict[str, str] = {}
            for line in res.stdout.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip()

            if "Signal" in data:
                sig_str = data["Signal"].rstrip("%")
                sig_pct = float(sig_str) if sig_str.isdigit() else 50.0
                # Approximate RSSI from Windows Signal Quality percentage
                # RSSI ~ (Signal / 2) - 100 dBm
                rssi = int((sig_pct / 2.0) - 100)
                channel_str = data.get("Channel", "0")
                channel = int(channel_str) if channel_str.isdigit() else 1
                band = 5.0 if channel > 14 else 2.4

                return WifiMetrics(
                    ssid=data.get("SSID"),
                    bssid=data.get("BSSID"),
                    rssi_dbm=rssi,
                    signal_quality_pct=sig_pct,
                    channel=channel,
                    band_ghz=band,
                    tx_rate_mbps=float(data.get("Receive rate (Mbps)", "0.0")),
                )
        except Exception:
            pass
        return None

    def get_configured_dns_servers(self) -> List[str]:
        servers: List[str] = []
        try:
            res = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            in_dns = False
            for line in res.stdout.splitlines():
                line = line.strip()
                if "DNS Servers" in line:
                    m = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)", line)
                    if m:
                        servers.append(m.group(1))
                    in_dns = True
                elif in_dns and re.match(r"^\d+\.\d+\.\d+\.\d+$", line):
                    servers.append(line)
                elif in_dns and ":" in line:
                    in_dns = False
        except Exception:
            pass
        return servers or ["127.0.0.1"]

    def ping(
        self, destination_ip: str, count: int = 3, timeout_seconds: float = 1.0
    ) -> Tuple[bool, Optional[float], float]:
        if destination_ip in ("127.0.0.1", "localhost", "::1"):
            return True, 0.1, 0.0

        try:
            timeout_ms = int(timeout_seconds * 1000)
            res = subprocess.run(
                ["ping", "-n", str(count), "-w", str(timeout_ms), destination_ip],
                capture_output=True,
                text=True,
                timeout=timeout_seconds * count + 2.0,
                check=False,
            )
            out = res.stdout
            loss_match = re.search(r"\((\d+)% loss\)", out)
            loss_pct = float(loss_match.group(1)) if loss_match else 100.0

            rtt_match = re.search(r"Average = (\d+)ms", out)
            avg_rtt = float(rtt_match.group(1)) if rtt_match else None

            is_reachable = loss_pct < 100.0
            return is_reachable, avg_rtt, loss_pct
        except Exception:
            return False, None, 100.0
