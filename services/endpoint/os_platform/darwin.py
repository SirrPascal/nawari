"""macOS (Darwin) platform adapter for local development and testing."""

from __future__ import annotations

import ipaddress
import os
import platform
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from services.endpoint.models import InterfaceState, InterfaceType, WifiMetrics
from services.endpoint.os_platform.base import PlatformAdapter, PlatformCapabilities


class DarwinAdapter(PlatformAdapter):
    """Platform adapter implementing macOS networking diagnostics."""

    def get_capabilities(self) -> PlatformCapabilities:
        is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
        return PlatformCapabilities(
            os_name="Darwin",
            os_version=platform.mac_ver()[0] or platform.release(),
            architecture=platform.machine(),
            supports_raw_icmp=is_root,
            supports_unprivileged_icmp=True,  # Through standard /sbin/ping
            supports_wifi_diagnostics=True,
            supports_gateway_discovery=True,
            supports_dns_discovery=True,
            requires_elevation_for=["raw_sockets", "promiscuous_mode"] if not is_root else [],
        )

    def get_default_gateway(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            res = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            gw_ip = None
            iface = None
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.startswith("gateway:"):
                    gw_ip = line.split(":", 1)[1].strip()
                elif line.startswith("interface:"):
                    iface = line.split(":", 1)[1].strip()
            
            # ARP lookup for MAC if gateway is found
            gw_mac = None
            if gw_ip:
                arp_res = subprocess.run(
                    ["arp", "-n", gw_ip],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                m = re.search(r"at\s+([0-9a-fA-F:]+)", arp_res.stdout)
                if m:
                    gw_mac = m.group(1).lower()

            return gw_ip, gw_mac, iface
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
        if not interface_name:
            return result

        try:
            res = subprocess.run(
                ["ifconfig", interface_name],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            out = res.stdout
            # Extract status
            if "status: active" in out:
                result["state"] = InterfaceState.UP
            elif "status: inactive" in out:
                result["state"] = InterfaceState.DOWN

            # Extract IP and netmask
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("inet "):
                    parts = line.split()
                    result["local_ip"] = parts[1]
                    if len(parts) >= 4 and parts[2] == "netmask":
                        mask_hex = parts[3]
                        try:
                            mask_int = int(mask_hex, 16)
                            result["subnet_cidr"] = bin(mask_int).count("1")
                        except ValueError:
                            result["subnet_cidr"] = 24
                    break

            # Infer Wi-Fi vs Ethernet vs Loopback
            if interface_name.startswith("lo"):
                result["type"] = InterfaceType.LOOPBACK
            elif interface_name.startswith("en0"):
                result["type"] = InterfaceType.WIFI
            else:
                result["type"] = InterfaceType.ETHERNET

        except Exception:
            pass

        return result

    def get_wifi_metrics(self, interface_name: str) -> Optional[WifiMetrics]:
        airport_cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if not os.path.exists(airport_cmd):
            return None

        try:
            res = subprocess.run(
                [airport_cmd, "-I"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return None

            data: Dict[str, str] = {}
            for line in res.stdout.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip()

            if "agrCtlRSSI" in data and "SSID" in data:
                rssi = int(data["agrCtlRSSI"])
                quality = max(0.0, min(100.0, (rssi + 100) * 2.0))
                channel_str = data.get("channel", "0").split(",")[0]
                channel = int(channel_str) if channel_str.isdigit() else 1
                band = 5.0 if channel > 14 else 2.4

                return WifiMetrics(
                    ssid=data.get("SSID"),
                    bssid=data.get("BSSID"),
                    rssi_dbm=rssi,
                    signal_quality_pct=quality,
                    channel=channel,
                    band_ghz=band,
                    tx_rate_mbps=float(data.get("lastTxRate", "0.0")),
                )
        except Exception:
            pass
        return None

    def get_configured_dns_servers(self) -> List[str]:
        servers: List[str] = []
        try:
            with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
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
            timeout_ms = int(timeout_seconds * 1000)
            res = subprocess.run(
                ["ping", "-c", str(count), "-W", str(timeout_ms), destination_ip],
                capture_output=True,
                text=True,
                timeout=timeout_seconds * count + 2.0,
                check=False,
            )
            out = res.stdout
            loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
            loss_pct = float(loss_match.group(1)) if loss_match else 100.0

            rtt_match = re.search(r"round-trip min/avg/max/stddev = [\d\.]+/([\d\.]+)/", out)
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
        """Execute unprivileged Paris traceroute on macOS using /usr/sbin/traceroute."""
        if destination_ip in ("127.0.0.1", "localhost", "::1"):
            return [{
                "hop_index": 1,
                "ip_address": "127.0.0.1",
                "rtts_ms": [0.1, 0.1, 0.1],
                "probes_sent": 3,
                "probes_received": 3,
                "mpls_labels": [],
            }]

        traceroute_bin = "/usr/sbin/traceroute"
        if not os.path.exists(traceroute_bin):
            return []

        cmd = [
            traceroute_bin,
            "-n",
            "-m", str(min(max(1, max_hops), 64)),
            "-q", "3",
            "-w", str(max(1, int(timeout_seconds))),
        ]
        if fixed_flow:
            cmd.append("-e")
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
