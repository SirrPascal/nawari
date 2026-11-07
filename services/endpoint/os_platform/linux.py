"""Linux platform adapter for enterprise workstation and laptop diagnostics."""

from __future__ import annotations

import ipaddress
import os
import platform
import re
import socket
import struct
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import InterfaceState, InterfaceType, WifiMetrics
from services.endpoint.os_platform.base import PlatformAdapter, PlatformCapabilities


class LinuxAdapter(PlatformAdapter):
    """Platform adapter implementing Linux networking diagnostics."""

    def get_capabilities(self) -> PlatformCapabilities:
        is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
        unprivileged_icmp = False
        
        # Check kernel ping_group_range
        ping_range_file = "/proc/sys/net/ipv4/ping_group_range"
        if os.path.exists(ping_range_file):
            try:
                with open(ping_range_file, "r") as f:
                    parts = f.read().strip().split()
                    if len(parts) == 2:
                        min_gid, max_gid = int(parts[0]), int(parts[1])
                        gid = os.getgid() if hasattr(os, "getgid") else 0
                        unprivileged_icmp = (min_gid <= gid <= max_gid)
            except Exception:
                unprivileged_icmp = False

        has_wireless = os.path.exists("/proc/net/wireless") or any(
            os.path.exists(f"/sys/class/net/{d}/wireless")
            for d in (os.listdir("/sys/class/net") if os.path.exists("/sys/class/net") else [])
        )

        elevation_reqs: List[str] = []
        if not is_root and not unprivileged_icmp:
            elevation_reqs.append("raw_icmp_or_cap_net_raw")

        return PlatformCapabilities(
            os_name="Linux",
            os_version=platform.release(),
            architecture=platform.machine(),
            supports_raw_icmp=is_root,
            supports_unprivileged_icmp=unprivileged_icmp or is_root,
            supports_wifi_diagnostics=has_wireless,
            supports_gateway_discovery=os.path.exists("/proc/net/route"),
            supports_dns_discovery=os.path.exists("/etc/resolv.conf"),
            requires_elevation_for=elevation_reqs,
        )

    def get_default_gateway(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        route_file = "/proc/net/route"
        if not os.path.exists(route_file):
            return None, None, None

        gw_ip: Optional[str] = None
        iface: Optional[str] = None

        try:
            with open(route_file, "r", encoding="utf-8") as f:
                for line in f.readlines()[1:]:
                    fields = line.strip().split()
                    if len(fields) >= 8 and fields[1] == "00000000":
                        iface = fields[0]
                        gw_hex = fields[2]
                        # Little-endian 32-bit hex to dotted IPv4
                        gw_int = int(gw_hex, 16)
                        gw_ip = socket.inet_ntoa(struct.pack("<L", gw_int))
                        break
        except Exception:
            return None, None, None

        gw_mac: Optional[str] = None
        arp_file = "/proc/net/arp"
        if gw_ip and os.path.exists(arp_file):
            try:
                with open(arp_file, "r", encoding="utf-8") as f:
                    for line in f.readlines()[1:]:
                        fields = line.strip().split()
                        if len(fields) >= 4 and fields[0] == gw_ip:
                            gw_mac = fields[3].lower()
                            if gw_mac == "00:00:00:00:00:00":
                                gw_mac = None
                            break
            except Exception:
                pass

        return gw_ip, gw_mac, iface

    def get_interface_details(self, interface_name: str) -> Dict[str, Any]:
        result = {
            "local_ip": "127.0.0.1",
            "subnet_cidr": 8,
            "state": InterfaceState.UP,
            "type": InterfaceType.ETHERNET,
            "dhcp_enabled": True,
        }
        if not interface_name:
            return result

        operstate_file = f"/sys/class/net/{interface_name}/operstate"
        if os.path.exists(operstate_file):
            try:
                with open(operstate_file, "r") as f:
                    st = f.read().strip().lower()
                    result["state"] = InterfaceState.UP if st == "up" else InterfaceState.DOWN
            except Exception:
                pass

        if interface_name.startswith("lo"):
            result["type"] = InterfaceType.LOOPBACK
        elif interface_name.startswith("wl") or os.path.exists(f"/sys/class/net/{interface_name}/wireless"):
            result["type"] = InterfaceType.WIFI
        else:
            result["type"] = InterfaceType.ETHERNET

        # Parse ip via iproute2 or ifconfig
        try:
            res = subprocess.run(
                ["ip", "-4", "addr", "show", interface_name],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", res.stdout)
            if m:
                result["local_ip"] = m.group(1)
                result["subnet_cidr"] = int(m.group(2))
        except Exception:
            pass

        return result

    def get_wifi_metrics(self, interface_name: str) -> Optional[WifiMetrics]:
        wireless_file = "/proc/net/wireless"
        if not os.path.exists(wireless_file):
            return None

        try:
            with open(wireless_file, "r", encoding="utf-8") as f:
                for line in f.readlines()[2:]:
                    parts = line.strip().split()
                    if parts and parts[0].rstrip(":") == interface_name:
                        # Link quality in column 3, level (dBm) in column 4
                        quality_val = float(parts[2].rstrip("."))
                        rssi_val = int(float(parts[3].rstrip(".")))
                        return WifiMetrics(
                            ssid=None,  # Requires iw or wpa_cli
                            bssid=None,
                            rssi_dbm=rssi_val,
                            signal_quality_pct=min(100.0, max(0.0, quality_val)),
                            channel=None,
                            band_ghz=None,
                            tx_rate_mbps=None,
                        )
        except Exception:
            pass
        return None

    def get_configured_dns_servers(self) -> List[str]:
        servers: List[str] = []
        resolv_path = "/etc/resolv.conf"
        if os.path.exists(resolv_path):
            try:
                with open(resolv_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("nameserver "):
                            servers.append(line.split()[1])
            except Exception:
                pass
        return servers or ["127.0.0.1"]

    def ping(
        self, destination_ip: str, count: int = 3, timeout_seconds: float = 1.0
    ) -> Tuple[bool, Optional[float], float]:
        if destination_ip in ("127.0.0.1", "localhost", "::1"):
            return True, 0.1, 0.0

        try:
            res = subprocess.run(
                ["ping", "-c", str(count), "-W", str(int(timeout_seconds)), destination_ip],
                capture_output=True,
                text=True,
                timeout=timeout_seconds * count + 2.0,
                check=False,
            )
            out = res.stdout
            loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
            loss_pct = float(loss_match.group(1)) if loss_match else 100.0

            rtt_match = re.search(r"rtt min/avg/max/mdev = [\d\.]+/([\d\.]+)/", out)
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
        """Execute unprivileged traceroute on Linux using traceroute or tracepath."""
        if destination_ip in ("127.0.0.1", "localhost", "::1"):
            return [{
                "hop_index": 1,
                "ip_address": "127.0.0.1",
                "rtts_ms": [0.1, 0.1, 0.1],
                "probes_sent": 3,
                "probes_received": 3,
                "mpls_labels": [],
            }]

        cmd = [
            "traceroute",
            "-n",
            "-m", str(min(max(1, max_hops), 64)),
            "-q", "3",
            "-w", str(max(1, int(timeout_seconds))),
        ]
        if target_port:
            cmd.extend(["-p", str(target_port)])
        cmd.append(destination_ip)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds * max_hops + 10.0,
                check=False,
            )
            return self._parse_traceroute_output(res.stdout, destination_ip)
        except Exception:
            return []

    def _parse_traceroute_output(self, output: str, destination_ip: str) -> List[Dict[str, Any]]:
        hops: List[Dict[str, Any]] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("traceroute"):
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
                if token.startswith("[MPLS:"):
                    mpls_str = token
                    while not token.endswith("]") and i + 1 < len(parts):
                        i += 1
                        token = parts[i]
                        mpls_str += " " + token
                    if "Label" in mpls_str:
                        try:
                            idx = mpls_str.find("Label")
                            sub = mpls_str[idx + 5 :].split()[0].rstrip("]")
                            mpls_labels.append(int(sub))
                        except Exception:
                            pass
                    i += 1
                    continue

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
