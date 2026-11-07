"""Windows platform adapter for enterprise laptop diagnostics."""

from __future__ import annotations

import ctypes
import ipaddress
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

    def trace_path(
        self,
        destination_ip: str,
        max_hops: int = 30,
        timeout_seconds: float = 2.0,
        target_port: Optional[int] = None,
        fixed_flow: bool = True,
    ) -> List[Dict[str, Any]]:
        """Execute unprivileged traceroute on Windows using tracert.exe."""
        if destination_ip in ("127.0.0.1", "localhost", "::1"):
            return [{
                "hop_index": 1,
                "ip_address": "127.0.0.1",
                "rtts_ms": [0.1, 0.1, 0.1],
                "probes_sent": 3,
                "probes_received": 3,
                "mpls_labels": [],
            }]

        timeout_ms = int(max(1.0, timeout_seconds) * 1000)
        cmd = [
            "tracert",
            "-d",
            "-h", str(min(max(1, max_hops), 64)),
            "-w", str(timeout_ms),
            destination_ip,
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds * max_hops + 10.0,
                check=False,
            )
            return self._parse_tracert_output(res.stdout, destination_ip)
        except Exception:
            return []

    def _parse_tracert_output(self, output: str, destination_ip: str) -> List[Dict[str, Any]]:
        hops: List[Dict[str, Any]] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = line.split()
            if not parts or not parts[0].isdigit():
                continue
            hop_index = int(parts[0])
            ip_addr: Optional[str] = None
            rtts: List[float] = []
            probes_sent = 0
            mpls_labels: List[int] = []

            i = 1
            while i < len(parts):
                token = parts[i]
                if token == "*":
                    probes_sent += 1
                    i += 1
                    continue
                if token.startswith("<"):
                    token = token[1:]

                try:
                    ipaddress.ip_address(token)
                    if ip_addr is None:
                        ip_addr = token
                    i += 1
                    continue
                except ValueError:
                    pass

                try:
                    val = float(token)
                    rtts.append(val)
                    probes_sent += 1
                    i += 1
                    if i < len(parts) and parts[i].lower() == "ms":
                        i += 1
                    continue
                except ValueError:
                    pass

                i += 1

            hops.append({
                "hop_index": hop_index,
                "ip_address": ip_addr,
                "rtts_ms": rtts,
                "probes_sent": max(probes_sent, len(rtts)),
                "probes_received": len(rtts),
                "mpls_labels": mpls_labels,
            })
        return hops
