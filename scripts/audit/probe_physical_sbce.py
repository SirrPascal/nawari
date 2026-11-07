#!/usr/bin/env python3
"""NAWARI — Phase 4.1 Physical Avaya SBCE Discovery & Validation Tool.

Performs safe, non-destructive, read-only SNMPv3 probes against candidate
Avaya SBCE management IP addresses (10.2.156.131 / 10.2.156.132) to:
1. Confirm network reachability and SNMPv3 authPriv handshake.
2. Retrieve system identity, enterprise OID, and uptime.
3. Enumerate physical and logical interfaces (IF-MIB ifName, ifDescr, ifAlias).
4. Discover real storage and memory table indices (HOST-RESOURCES-MIB vs UCD-SNMP).
5. Verify whether UCD-SNMP dskTable and CPU OIDs are natively exposed by Avaya OS.
6. Check Avaya enterprise MIB branch (1.3.6.1.4.1.6889) for active session counts.
7. Generate a structured JSON / Markdown compatibility audit report.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ProbeTarget:
    ip: str
    port: int = 161
    user: str = "Admin"
    auth_proto: str = "SHA256"
    auth_pass: str = ""
    priv_proto: str = "AES128"
    priv_pass: str = ""
    timeout: int = 5
    retries: int = 2


@dataclass
class ValidationReport:
    target_ip: str
    timestamp: str
    reachability: bool = False
    snmpv3_handshake: bool = False
    sys_name: str = ""
    sys_descr: str = ""
    sys_object_id: str = ""
    sys_uptime: str = ""
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    storage_entries: list[dict[str, Any]] = field(default_factory=list)
    resource_support: dict[str, Any] = field(default_factory=dict)
    avaya_enterprise_detected: bool = False
    template_compatibility: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class PhysicalSBCEProber:
    """Safe, read-only SNMPv3 probe orchestrator."""

    def __init__(self, target: ProbeTarget):
        self.target = target
        self._snmpget_cmd = shutil.which("snmpget")
        self._snmpwalk_cmd = shutil.which("snmpwalk")

    def _build_snmp_args(self) -> list[str]:
        # Normalize protocol tokens for Net-SNMP CLI
        auth_proto = "SHA" if "SHA" in self.target.auth_proto.upper() and "256" not in self.target.auth_proto else self.target.auth_proto
        priv_proto = "AES" if "AES" in self.target.priv_proto.upper() else "DES"

        # On macOS 5.6.2.1, SHA256 is not supported by host binary; fallback to SHA if needed
        return [
            "-v3",
            "-l", "authPriv",
            "-u", self.target.user,
            "-a", auth_proto,
            "-A", self.target.auth_pass,
            "-x", priv_proto,
            "-X", self.target.priv_pass,
            "-t", str(self.target.timeout),
            "-r", str(self.target.retries),
            f"{self.target.ip}:{self.target.port}",
        ]

    def snmp_get(self, oid: str) -> Optional[str]:
        """Perform a single SNMP GET query."""
        if not self._snmpget_cmd:
            return None
        cmd = [self._snmpget_cmd] + self._build_snmp_args() + [oid]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.target.timeout + 2)
            if res.returncode == 0:
                return res.stdout.strip()
            return None
        except Exception:
            return None

    def snmp_walk(self, oid: str) -> list[str]:
        """Perform an SNMP WALK query."""
        if not self._snmpwalk_cmd:
            return []
        cmd = [self._snmpwalk_cmd] + self._build_snmp_args() + [oid]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.target.timeout * 3)
            if res.returncode == 0:
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return []
        except Exception:
            return []

    @staticmethod
    def clean_val(v: str) -> str:
        v = v.strip()
        for prefix in ["STRING:", "INTEGER:", "Counter64:", "Counter32:", "Gauge32:", "OID:", "Timeticks:"]:
            if v.startswith(prefix):
                v = v[len(prefix):].strip()
        return v.strip().strip('"\\\'')

    def probe(self) -> ValidationReport:
        """Execute the structured Phase 4.1 validation sequence."""
        report = ValidationReport(
            target_ip=self.target.ip,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # 1. System Identity Handshake
        sys_descr = self.snmp_get("1.3.6.1.2.1.1.1.0")
        if not sys_descr:
            report.warnings.append(
                f"SNMPv3 query to {self.target.ip}:{self.target.port} timed out or failed authentication. "
                "Verify network firewall, IP routing, and SNMPv3 credentials."
            )
            return report

        report.reachability = True
        report.snmpv3_handshake = True
        report.sys_descr = self.clean_val(sys_descr.split("=", 1)[-1])

        sys_name = self.snmp_get("1.3.6.1.2.1.1.5.0")
        if sys_name:
            report.sys_name = self.clean_val(sys_name.split("=", 1)[-1])

        sys_obj = self.snmp_get("1.3.6.1.2.1.1.2.0")
        if sys_obj:
            report.sys_object_id = self.clean_val(sys_obj.split("=", 1)[-1])

        sys_uptime = self.snmp_get("1.3.6.1.2.1.1.3.0")
        if sys_uptime:
            report.sys_uptime = self.clean_val(sys_uptime.split("=", 1)[-1])

        # 2. Interface Enumeration (IF-MIB)
        if_names = self.snmp_walk("1.3.6.1.2.1.31.1.1.1.1")  # ifName
        if_descrs = self.snmp_walk("1.3.6.1.2.1.2.2.1.2")     # ifDescr
        if_oper = self.snmp_walk("1.3.6.1.2.1.2.2.1.8")       # ifOperStatus

        indices: set[str] = set()
        name_map = {}
        for line in if_names:
            if "=" in line:
                left, right = line.split("=", 1)
                idx = left.strip().split(".")[-1]
                name_map[idx] = self.clean_val(right)
                indices.add(idx)

        descr_map = {}
        for line in if_descrs:
            if "=" in line:
                left, right = line.split("=", 1)
                idx = left.strip().split(".")[-1]
                descr_map[idx] = self.clean_val(right)
                indices.add(idx)

        oper_map = {}
        for line in if_oper:
            if "=" in line:
                left, right = line.split("=", 1)
                idx = left.strip().split(".")[-1]
                val = self.clean_val(right)
                oper_map[idx] = "UP" if "1" in val or "up" in val.lower() else "DOWN"

        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else x):
            report.interfaces.append({
                "index": idx,
                "ifName": name_map.get(idx, ""),
                "ifDescr": descr_map.get(idx, ""),
                "status": oper_map.get(idx, "UNKNOWN"),
            })

        # 3. Storage & Memory Table Inspection (HOST-RESOURCES-MIB)
        hr_types = self.snmp_walk("1.3.6.1.2.1.25.2.3.1.2")   # hrStorageType
        hr_descrs = self.snmp_walk("1.3.6.1.2.1.25.2.3.1.3")  # hrStorageDescr
        hr_sizes = self.snmp_walk("1.3.6.1.2.1.25.2.3.1.5")   # hrStorageSize
        hr_units = self.snmp_walk("1.3.6.1.2.1.25.2.3.1.4")   # hrStorageAllocationUnits

        storage_map = {}
        for line in hr_descrs:
            if "=" in line:
                left, right = line.split("=", 1)
                idx = left.strip().split(".")[-1]
                storage_map[idx] = {"index": idx, "descr": self.clean_val(right)}

        for line in hr_types:
            if "=" in line:
                left, right = line.split("=", 1)
                idx = left.strip().split(".")[-1]
                if idx in storage_map:
                    storage_map[idx]["type"] = self.clean_val(right).split("::")[-1]

        for idx, entry in sorted(storage_map.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
            report.storage_entries.append(entry)

        # 4. Resource Metric Availability Checks
        cpu_idle = self.snmp_get("1.3.6.1.4.1.2021.11.11.0")
        report.resource_support["UCD-ssCpuIdle"] = bool(cpu_idle and "No Such" not in cpu_idle)

        load_avg = self.snmp_get("1.3.6.1.4.1.2021.10.1.3.1")
        report.resource_support["UCD-laLoad.1"] = bool(load_avg and "No Such" not in load_avg)

        disk_pct = self.snmp_get("1.3.6.1.4.1.2021.9.1.9.1")
        report.resource_support["UCD-dskPercent.1"] = bool(disk_pct and "No Such" not in disk_pct)

        ucd_mem_real = self.snmp_get("1.3.6.1.4.1.2021.4.5.0")
        report.resource_support["UCD-memTotalReal"] = bool(ucd_mem_real and "No Such" not in ucd_mem_real)

        # 5. Avaya Enterprise Tree Probe
        avaya_tree = self.snmp_walk("1.3.6.1.4.1.6889")
        report.avaya_enterprise_detected = len(avaya_tree) > 0

        # 6. Evaluate Template Compatibility
        # CPU
        if report.resource_support.get("UCD-ssCpuIdle"):
            report.template_compatibility["system.cpu.util"] = "COMPATIBLE (Native UCD-SNMP)"
        else:
            report.template_compatibility["system.cpu.util"] = "INCOMPATIBLE (Requires hrProcessorLoad discovery)"
            report.warnings.append("Appliance does not expose UCD-ssCpuIdle. Use hrProcessorLoad discovery prototype.")

        # Disk
        if report.resource_support.get("UCD-dskPercent.1"):
            report.template_compatibility["vfs.fs.used.percent[/]"] = "COMPATIBLE (UCD-SNMP dskTable)"
        else:
            # Check if root filesystem exists in hrStorageTable
            has_hr_disk = any("/" in e.get("descr", "") for e in report.storage_entries)
            if has_hr_disk:
                report.template_compatibility["vfs.fs.used.percent[/]"] = "ADAPTABLE (Via hrStorageTable discovery)"
                report.recommendations.append("Update template to discover filesystems via hrStorageTable rather than hardcoded dskPercent.1.")
            else:
                report.template_compatibility["vfs.fs.used.percent[/]"] = "UNSUPPORTED"

        # Memory
        has_hr_ram = any("physical memory" in e.get("descr", "").lower() for e in report.storage_entries)
        if has_hr_ram or report.resource_support.get("UCD-memTotalReal"):
            report.template_compatibility["vm.memory.util"] = "COMPATIBLE"
        else:
            report.template_compatibility["vm.memory.util"] = "REQUIRES_ADAPTATION"

        # Interfaces
        if_names_list = [i.get("ifName") for i in report.interfaces]
        if any(name in ["M1", "A1", "B1"] for name in if_names_list):
            report.template_compatibility["sbce.interface.discovery"] = "COMPATIBLE (M1/A1/B1 naming matches)"
        else:
            report.template_compatibility["sbce.interface.discovery"] = f"REQUIRES_FILTER_UPDATE (Observed names: {if_names_list[:6]})"
            report.recommendations.append(f"Adjust template regex macro {{$SBCE.IF.MATCHES}} to match appliance interface names: {if_names_list[:6]}")

        return report


def format_markdown_report(r: ValidationReport) -> str:
    """Format validation results into an executive Markdown report."""
    md = []
    md.append(f"# Nawari — Phase 4.1 Physical SBCE Validation Report")
    md.append(f"**Target Host:** `{r.target_ip}` | **Probe Timestamp:** `{r.timestamp}`\n")
    
    md.append("## 1. Handshake & System Identity")
    md.append(f"* **Network Reachability:** {'YES' if r.reachability else 'NO'}")
    md.append(f"* **SNMPv3 authPriv Handshake:** {'SUCCESS' if r.snmpv3_handshake else 'FAILED'}")
    if r.snmpv3_handshake:
        md.append(f"* **System Name (`sysName`):** `{r.sys_name}`")
        md.append(f"* **System Description (`sysDescr`):** `{r.sys_descr}`")
        md.append(f"* **Enterprise OID (`sysObjectID`):** `{r.sys_object_id}`")
        md.append(f"* **System Uptime (`sysUpTime`):** `{r.sys_uptime}`")
        md.append(f"* **Avaya Enterprise MIB (.1.3.6.1.4.1.6889):** {'PRESENT' if r.avaya_enterprise_detected else 'NOT_DETECTED'}")

    md.append("\n## 2. Template Key Compatibility Assessment")
    md.append("| Template Key | Target Metric | Compatibility Finding |")
    md.append("| :--- | :--- | :--- |")
    for key, status in r.template_compatibility.items():
        md.append(f"| `{key}` | Appliance Resource | **{status}** |")

    md.append("\n## 3. Discovered Interfaces (IF-MIB)")
    if r.interfaces:
        md.append("| Index | `ifName` | `ifDescr` | Status |")
        md.append("| :--- | :--- | :--- | :--- |")
        for iface in r.interfaces:
            md.append(f"| {iface['index']} | `{iface['ifName']}` | `{iface['ifDescr']}` | {iface['status']} |")
    else:
        md.append("*No interfaces enumerated.*")

    md.append("\n## 4. Discovered Storage Entities (HOST-RESOURCES-MIB)")
    if r.storage_entries:
        md.append("| Index | Description (`hrStorageDescr`) | Type (`hrStorageType`) |")
        md.append("| :--- | :--- | :--- |")
        for s in r.storage_entries:
            md.append(f"| {s['index']} | `{s.get('descr')}` | `{s.get('type', 'Unknown')}` |")
    else:
        md.append("*No storage entities enumerated.*")

    if r.warnings:
        md.append("\n## 5. Warnings & Identified Deviations")
        for w in r.warnings:
            md.append(f"- ⚠️ {w}")

    if r.recommendations:
        md.append("\n## 6. Actionable Recommendations for Production Template")
        for rec in r.recommendations:
            md.append(f"- [ ] {rec}")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Nawari Phase 4.1 Physical Avaya SBCE Prober")
    parser.add_argument("--target-ip", default=os.environ.get("AVAYA_SBCE_HOST", "10.2.156.131"), help="Target SBCE IP")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AVAYA_SBCE_SNMP_PORT", "161")), help="SNMP Port")
    parser.add_argument("--user", default=os.environ.get("AVAYA_SBCE_SNMP_SEC_NAME", "Admin"), help="SNMPv3 Security Name")
    parser.add_argument("--auth-proto", default=os.environ.get("AVAYA_SBCE_SNMP_AUTH_PROTO", "SHA"), help="Auth protocol (SHA/SHA256)")
    parser.add_argument("--auth-pass", default=os.environ.get("AVAYA_SBCE_SNMP_AUTH_PASS", ""), help="Auth passphrase")
    parser.add_argument("--priv-proto", default=os.environ.get("AVAYA_SBCE_SNMP_PRIV_PROTO", "DES"), help="Priv protocol (DES/AES)")
    parser.add_argument("--priv-pass", default=os.environ.get("AVAYA_SBCE_SNMP_PRIV_PASS", ""), help="Priv passphrase")
    parser.add_argument("--timeout", type=int, default=2, help="SNMP query timeout in seconds")
    parser.add_argument("--retries", type=int, default=1, help="SNMP query retry count")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output report format")
    parser.add_argument("--out", type=Path, help="Write output to file path")

    args = parser.parse_args()

    target = ProbeTarget(
        ip=args.target_ip,
        port=args.port,
        user=args.user,
        auth_proto=args.auth_proto,
        auth_pass=args.auth_pass,
        priv_proto=args.priv_proto,
        priv_pass=args.priv_pass,
        timeout=args.timeout,
        retries=args.retries,
    )

    prober = PhysicalSBCEProber(target)
    report = prober.probe()

    if args.format == "json":
        output = json.dumps(asdict(report), indent=2)
    else:
        output = format_markdown_report(report)

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Report written to: {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
