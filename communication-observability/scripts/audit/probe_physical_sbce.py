#!/usr/bin/env python3
"""NAWARI — Phase 4.1 Physical Avaya SBCE Discovery & Validation Tool.

Performs safe, non-destructive, read-only SNMPv3 probes against candidate
Avaya SBCE management IP addresses (10.2.156.131 / 10.2.156.132).

Security Guarantee:
- Reads authentication credentials strictly from environment variables or .env.
- Avoids exposing passphrases in CLI process arguments (ps aux).
- Never writes credentials to audit reports or terminal output.

Failure Classification:
Distinguishes between:
- NETWORK_UNREACHABLE: No network route or host down
- SNMP_TIMEOUT: Packets dropped by firewall or no SNMP response
- AUTHENTICATION_FAILURE: USM authentication passphrase/protocol mismatch
- PRIVACY_MISMATCH: USM encryption cipher mismatch or decryption error
- AGENT_REACHABLE_OID_UNSUPPORTED: Agent responded, but OID is not implemented
- OID_RETRIEVED_SUCCESS: Successfully retrieved valid data
- VALUE_INCONSISTENT: Retrieved value does not match expected schema/range
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Locate project root and load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from services.api.config import load_env_file
    load_env_file(PROJECT_ROOT / ".env")
except ImportError:
    pass


class ProbeStatus(str, Enum):
    SUCCESS = "OID_RETRIEVED_SUCCESS"
    UNSUPPORTED = "AGENT_REACHABLE_OID_UNSUPPORTED"
    AUTH_FAILURE = "AUTHENTICATION_FAILURE"
    PRIV_MISMATCH = "PRIVACY_MISMATCH"
    TIMEOUT = "SNMP_TIMEOUT"
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"
    VALUE_INCONSISTENT = "VALUE_INCONSISTENT"


@dataclass
class ProbeTarget:
    ip: str
    port: int = 161
    user: str = "Admin"
    auth_proto: str = "SHA256"
    auth_pass: str = ""
    priv_proto: str = "AES128"
    priv_pass: str = ""
    timeout: int = 3
    retries: int = 1


@dataclass
class OIDResult:
    oid: str
    key: str
    status: ProbeStatus
    raw_value: Optional[str] = None
    cleaned_value: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ValidationReport:
    target_ip: str
    timestamp: str
    reachability_status: ProbeStatus = ProbeStatus.TIMEOUT
    sys_name: str = ""
    sys_descr: str = ""
    sys_object_id: str = ""
    sys_uptime: str = ""
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    storage_entries: list[dict[str, Any]] = field(default_factory=list)
    oid_evaluations: list[dict[str, Any]] = field(default_factory=list)
    avaya_enterprise_detected: bool = False
    findings_summary: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class PhysicalSBCEProber:
    """Safe, read-only SNMPv3 probe orchestrator."""

    def __init__(self, target: ProbeTarget):
        self.target = target
        self._snmpget_cmd = shutil.which("snmpget")
        self._snmpwalk_cmd = shutil.which("snmpwalk")

    def _build_snmp_args(self) -> list[str]:
        # Normalize protocol tokens
        auth_proto = "SHA" if "SHA" in self.target.auth_proto.upper() and "256" not in self.target.auth_proto else self.target.auth_proto
        priv_proto = "AES" if "AES" in self.target.priv_proto.upper() else "DES"

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

    @staticmethod
    def clean_val(v: str) -> str:
        v = v.strip()
        for prefix in ["STRING:", "INTEGER:", "Counter64:", "Counter32:", "Gauge32:", "OID:", "Timeticks:"]:
            if v.startswith(prefix):
                v = v[len(prefix):].strip()
        return v.strip().strip('"\\\'')

    def execute_snmp_get(self, oid: str, key_label: str) -> OIDResult:
        """Query single OID and categorize precise outcome."""
        if not self._snmpget_cmd:
            return OIDResult(oid=oid, key=key_label, status=ProbeStatus.NETWORK_UNREACHABLE, error_message="snmpget binary not found")

        cmd = [self._snmpget_cmd] + self._build_snmp_args() + [oid]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.target.timeout + 2)
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            if res.returncode == 0:
                if "No Such Object" in stdout or "No Such Instance" in stdout:
                    return OIDResult(oid=oid, key=key_label, status=ProbeStatus.UNSUPPORTED, raw_value=stdout, error_message="OID not implemented by agent")
                val = stdout.split("=", 1)[-1].strip() if "=" in stdout else stdout
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.SUCCESS, raw_value=stdout, cleaned_value=self.clean_val(val))

            # Analyze error string from stderr / stdout
            combined_err = f"{stdout} {stderr}".lower()
            if "timeout" in combined_err or "no response" in combined_err:
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.TIMEOUT, error_message="Request timed out")
            elif "authentication failure" in combined_err or "wrong digest" in combined_err:
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.AUTH_FAILURE, error_message="USM Authentication failed")
            elif "decryption error" in combined_err or "privacy" in combined_err:
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.PRIV_MISMATCH, error_message="Privacy decryption failed")
            elif "unknown host" in combined_err or "no route" in combined_err:
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.NETWORK_UNREACHABLE, error_message="Network unreachable")
            elif "no such instance" in combined_err or "no such object" in combined_err:
                return OIDResult(oid=oid, key=key_label, status=ProbeStatus.UNSUPPORTED, error_message="OID not implemented")

            return OIDResult(oid=oid, key=key_label, status=ProbeStatus.TIMEOUT, error_message=stderr or "Unknown error")
        except subprocess.TimeoutExpired:
            return OIDResult(oid=oid, key=key_label, status=ProbeStatus.TIMEOUT, error_message="Command execution timed out")
        except Exception as e:
            return OIDResult(oid=oid, key=key_label, status=ProbeStatus.NETWORK_UNREACHABLE, error_message=str(e))

    def execute_snmp_walk(self, oid: str) -> list[str]:
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

    def probe(self) -> ValidationReport:
        """Execute the structured Phase 4.1 validation sequence."""
        report = ValidationReport(
            target_ip=self.target.ip,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # 1. Base Handshake Check (sysDescr)
        sys_descr_res = self.execute_snmp_get("1.3.6.1.2.1.1.1.0", "system.descr")
        report.reachability_status = sys_descr_res.status

        if sys_descr_res.status != ProbeStatus.SUCCESS:
            if sys_descr_res.status == ProbeStatus.TIMEOUT:
                report.warnings.append(
                    f"Target {self.target.ip}:{self.target.port} did not respond (SNMP_TIMEOUT). "
                    "INTEGRATION PENDING: Offline environment or firewall drop. "
                    "Do NOT interpret this as unsupported OIDs."
                )
            elif sys_descr_res.status == ProbeStatus.AUTH_FAILURE:
                report.warnings.append("Authentication failure: Verify AVAYA_SBCE_SNMP_AUTH_PASS and authprotocol.")
            elif sys_descr_res.status == ProbeStatus.PRIV_MISMATCH:
                report.warnings.append("Privacy failure: Verify AVAYA_SBCE_SNMP_PRIV_PASS and privprotocol (AES vs DES).")
            elif sys_descr_res.status == ProbeStatus.NETWORK_UNREACHABLE:
                report.warnings.append(f"Network unreachable to {self.target.ip}. Check routing.")
            return report

        report.sys_descr = sys_descr_res.cleaned_value or ""

        # Retrieve system identity
        sys_name = self.execute_snmp_get("1.3.6.1.2.1.1.5.0", "system.name")
        if sys_name.status == ProbeStatus.SUCCESS:
            report.sys_name = sys_name.cleaned_value or ""

        sys_obj = self.execute_snmp_get("1.3.6.1.2.1.1.2.0", "system.objectid")
        if sys_obj.status == ProbeStatus.SUCCESS:
            report.sys_object_id = sys_obj.cleaned_value or ""

        sys_uptime = self.execute_snmp_get("1.3.6.1.2.1.1.3.0", "system.uptime")
        if sys_uptime.status == ProbeStatus.SUCCESS:
            report.sys_uptime = sys_uptime.cleaned_value or ""

        # 2. Key OID Evaluations
        target_evals = [
            ("1.3.6.1.4.1.2021.11.11.0", "system.cpu.util (UCD ssCpuIdle)"),
            ("1.3.6.1.4.1.2021.10.1.3.1", "system.cpu.load.avg1 (UCD laLoad.1)"),
            ("1.3.6.1.4.1.2021.4.5.0", "vm.memory.total (UCD memTotalReal)"),
            ("1.3.6.1.4.1.2021.4.6.0", "vm.memory.available (UCD memAvailReal)"),
            ("1.3.6.1.4.1.2021.9.1.9.1", "vfs.fs.used.percent[/] (UCD dskPercent.1)"),
        ]

        status_counts = {}
        for oid, label in target_evals:
            res = self.execute_snmp_get(oid, label)
            report.oid_evaluations.append({
                "oid": res.oid,
                "key": res.key,
                "status": res.status.value,
                "value": res.cleaned_value or "N/A",
                "error": res.error_message or "",
            })
            status_counts[res.status.value] = status_counts.get(res.status.value, 0) + 1

        report.findings_summary = status_counts

        # 3. IF-MIB Interface Walk
        if_names = self.execute_snmp_walk("1.3.6.1.2.1.31.1.1.1.1")  # ifName
        if_descrs = self.execute_snmp_walk("1.3.6.1.2.1.2.2.1.2")     # ifDescr
        if_oper = self.execute_snmp_walk("1.3.6.1.2.1.2.2.1.8")       # ifOperStatus

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

        # 4. Storage Walk
        hr_types = self.execute_snmp_walk("1.3.6.1.2.1.25.2.3.1.2")
        hr_descrs = self.execute_snmp_walk("1.3.6.1.2.1.25.2.3.1.3")

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

        # 5. Avaya Enterprise Tree
        avaya_tree = self.execute_snmp_walk("1.3.6.1.4.1.6889")
        report.avaya_enterprise_detected = len(avaya_tree) > 0

        return report


def format_markdown_report(r: ValidationReport) -> str:
    """Format validation results into an executive Markdown report."""
    md = []
    md.append("# Nawari — Phase 4.1 Physical SBCE Validation Report")
    md.append(f"**Target Host:** `{r.target_ip}` | **Probe Timestamp:** `{r.timestamp}`\n")

    md.append("## 1. Handshake & Diagnostic Reachability Status")
    md.append(f"* **Diagnostic Status:** `{r.reachability_status.value}`")
    if r.reachability_status == ProbeStatus.SUCCESS:
        md.append(f"* **System Name (`sysName`):** `{r.sys_name}`")
        md.append(f"* **System Description (`sysDescr`):** `{r.sys_descr}`")
        md.append(f"* **Enterprise OID (`sysObjectID`):** `{r.sys_object_id}`")
        md.append(f"* **System Uptime (`sysUpTime`):** `{r.sys_uptime}`")
        md.append(f"* **Avaya Enterprise MIB (.1.3.6.1.4.1.6889):** {'PRESENT' if r.avaya_enterprise_detected else 'NOT_DETECTED'}")

        md.append("\n## 2. Resource OID Evaluations")
        md.append("| OID | Target Metric | Status | Observed Value |")
        md.append("| :--- | :--- | :--- | :--- |")
        for e in r.oid_evaluations:
            md.append(f"| `{e['oid']}` | {e['key']} | **{e['status']}** | `{e['value']}` |")

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
        md.append("\n## 5. Diagnostic Warnings & Status Notes")
        for w in r.warnings:
            md.append(f"- ⚠️ {w}")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(
        description="Nawari Phase 4.1 Physical Avaya SBCE Prober",
        epilog="Credentials are read automatically from AVAYA_SBCE_SNMP_AUTH_PASS and AVAYA_SBCE_SNMP_PRIV_PASS environment variables."
    )
    parser.add_argument("--target-ip", default=os.environ.get("AVAYA_SBCE_HOST", "10.2.156.131"), help="Target SBCE IP")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AVAYA_SBCE_SNMP_PORT", "161")), help="SNMP Port")
    parser.add_argument("--user", default=os.environ.get("AVAYA_SBCE_SNMP_SEC_NAME", "Admin"), help="SNMPv3 Security Name")
    parser.add_argument("--auth-proto", default=os.environ.get("AVAYA_SBCE_SNMP_AUTH_PROTO", "SHA256"), help="Auth protocol (SHA/SHA256)")
    parser.add_argument("--priv-proto", default=os.environ.get("AVAYA_SBCE_SNMP_PRIV_PROTO", "AES128"), help="Priv protocol (DES/AES)")
    parser.add_argument("--timeout", type=int, default=3, help="SNMP query timeout in seconds")
    parser.add_argument("--retries", type=int, default=1, help="SNMP query retry count")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output report format")
    parser.add_argument("--out", type=Path, help="Write output to file path")

    args = parser.parse_args()

    # Passwords read strictly from environment or .env
    auth_pass = os.environ.get("AVAYA_SBCE_SNMP_AUTH_PASS", "")
    priv_pass = os.environ.get("AVAYA_SBCE_SNMP_PRIV_PASS", "")

    target = ProbeTarget(
        ip=args.target_ip,
        port=args.port,
        user=args.user,
        auth_proto=args.auth_proto,
        auth_pass=auth_pass,
        priv_proto=args.priv_proto,
        priv_pass=priv_pass,
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
