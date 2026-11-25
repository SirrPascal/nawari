#!/usr/bin/env python3
"""Nawari CLI Tool for SolarWinds and Zabbix Device Identity Reconciliation.

Usage:
    python reconcile_device_identities.py dry-run [--solarwinds-file=...] [--zabbix-file=...] [--output=...]
    python reconcile_device_identities.py apply [--plan-file=...] [--zabbix-api-url=...] [--zabbix-token=...] [--yes]
    python reconcile_device_identities.py rollback [--audit-file=...] [--zabbix-api-url=...] [--zabbix-token=...] [--yes]
    python reconcile_device_identities.py drift [--solarwinds-file=...] [--zabbix-file=...]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add platform to path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from solarwinds_inventory_importer import SolarWindsInventoryImporter, SolarWindsNodeRecord
from zabbix_inventory_collector import ZabbixInventoryCollector, ZabbixHostRecord
from device_identity_reconciler import DeviceIdentityReconciler, MatchConfidence, ReconciliationItem, DeviceDriftDetector, DriftReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nawari.reconciler.cli")

DEFAULT_SW_FILE = ROOT_DIR / "network observability/evidence/solarwinds_authoritative_nodes_export.json"
DEFAULT_ZBX_FILE = ROOT_DIR / "network observability/evidence/zabbix_live_hosts_full.json"
DEFAULT_PLAN_FILE = ROOT_DIR / "network observability/evidence/reconciliation_plan.json"
DEFAULT_AUDIT_DIR = ROOT_DIR / "backups/reconciliation_audits"

DEFAULT_ZBX_API = os.getenv("ZBX_API_URL", "http://172.21.0.5:8080/api_jsonrpc.php")
DEFAULT_ZBX_TOKEN = os.getenv("ZBX_API_TOKEN", "18aec9106a9d80981efd47dd5a58cfc1")


def call_zabbix_api(api_url: str, token: str, method: str, params: Dict[str, Any], timeout: int = 15) -> Any:
    """Execute authenticated Zabbix JSON-RPC 2.0 call."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": int(time.time() * 1000) % 1000000,
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(f"Zabbix API error ({method}): {data['error']}")
        return data.get("result")


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Execute dry-run reconciliation and produce reviewable plan."""
    logger.info("Executing Device Identity Reconciliation Dry-Run...")
    logger.info("  SolarWinds file: %s", args.solarwinds_file)
    logger.info("  Zabbix file:     %s", args.zabbix_file)

    sw_nodes = SolarWindsInventoryImporter.from_json_file(args.solarwinds_file)
    zbx_hosts = ZabbixInventoryCollector.from_json_file(args.zabbix_file)

    logger.info("Loaded %d SolarWinds nodes and %d Zabbix hosts.", len(sw_nodes), len(zbx_hosts))

    reconciler = DeviceIdentityReconciler()
    items = reconciler.reconcile(sw_nodes, zbx_hosts)

    # Compile statistics
    stats: Dict[str, int] = {}
    rename_count = 0
    noop_count = 0
    review_count = 0
    blocked_count = 0

    for item in items:
        conf_name = item.confidence.value
        stats[conf_name] = stats.get(conf_name, 0) + 1
        if item.rename_operation == "RENAME":
            rename_count += 1
        elif item.rename_operation == "NOOP":
            noop_count += 1
        elif item.rename_operation == "REVIEW":
            review_count += 1
        elif item.rename_operation == "BLOCKED":
            blocked_count += 1

    print("\n" + "=" * 110)
    print("NAWARI DEVICE IDENTITY RECONCILIATION — DRY-RUN SUMMARY")
    print("=" * 110)
    print(f"{'CONFIDENCE TIER':<28} | {'COUNT':<6} | {'DESCRIPTION'}")
    print("-" * 110)
    for conf in MatchConfidence:
        c_count = stats.get(conf.value, 0)
        desc = {
            MatchConfidence.EXACT_VERIFIED_MATCH: "Corroborated by serial number or verified IP + SysName alignment",
            MatchConfidence.HIGH_CONFIDENCE_MATCH: "Consistent management IP, vendor, and active monitored candidate",
            MatchConfidence.POSSIBLE_MATCH: "IP matched but names or sites differ; operator review required",
            MatchConfidence.CONFLICTING_MATCH: "Multiple nodes/hosts registered for the same IP address",
            MatchConfidence.SOLARWINDS_ONLY: "Present in SolarWinds but not yet enrolled in Zabbix",
            MatchConfidence.ZABBIX_ONLY: "Present in Zabbix but not in SolarWinds node export",
            MatchConfidence.DUPLICATE_CANDIDATE: "Multiple Zabbix hosts share the same management IP",
            MatchConfidence.MANUAL_REVIEW_REQUIRED: "HA cluster VIP or multi-node appliance requiring manual review",
        }.get(conf, "")
        print(f"{conf.value:<28} | {c_count:<6} | {desc}")

    print("-" * 110)
    print(f"Total Discovered Assets:        {len(items)}")
    print(f"Proposed Visible Name Changes:  {rename_count} (Safe, policy-approved renames)")
    print(f"Already Correct (NOOP):         {noop_count}")
    print(f"Requires Operator Review:       {review_count}")
    print(f"Blocked by Conflict:            {blocked_count}")
    print("=" * 110 + "\n")

    # Sample proposed changes table
    print(f"{'HOSTID':<8} | {'TECHNICAL HOST':<26} | {'CURRENT VISIBLE NAME':<32} -> {'PROPOSED VISIBLE NAME':<24} | {'STATUS'}")
    print("-" * 110)
    displayed = 0
    for item in items:
        if item.rename_operation == "RENAME" and displayed < 25:
            hid = item.zabbix_host.host_id if item.zabbix_host else "-"
            print(f"{hid:<8} | {item.current_zabbix_host:<26} | {item.current_zabbix_visible_name:<32} -> {item.proposed_zabbix_visible_name:<24} | {item.confidence.value}")
            displayed += 1
    if rename_count > 25:
        print(f"  ... and {rename_count - 25} more proposed visible name updates.")
    print("-" * 110 + "\n")

    # Save plan to output file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plan_data = {
        "generated_at": time.time(),
        "solarwinds_source": str(args.solarwinds_file),
        "zabbix_source": str(args.zabbix_file),
        "total_items": len(items),
        "proposed_renames_count": rename_count,
        "statistics": stats,
        "items": [item.to_dict() for item in items],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)

    logger.info("Saved complete reconciliation plan to %s", output_path)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Apply approved visible-name renames to Zabbix and log audit trail."""
    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        logger.error("Plan file not found: %s. Run dry-run first.", plan_file)
        return 1

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    items = plan.get("items", [])
    safe_renames = [
        item for item in items
        if item.get("rename_operation") == "RENAME" and item.get("is_safe_to_rename")
    ]

    logger.info("Found %d safe, policy-approved renames to apply in plan.", len(safe_renames))
    if not safe_renames:
        logger.info("Zero renames required. System is already reconciled.")
        return 0

    if not args.yes:
        print(f"\nWARNING: About to update Zabbix visible names for {len(safe_renames)} hosts via Zabbix API.")
        print("Technical hostnames, templates, and monitoring interfaces will be PRESERVED.")
        confirm = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Operation aborted by user.")
            return 0

    audit_records = []
    success_count = 0
    fail_count = 0
    now = time.time()

    for idx, item in enumerate(safe_renames, start=1):
        host_id = item["zabbix_host_id"]
        tech_host = item["current_zabbix_host"]
        old_name = item["current_zabbix_visible_name"]
        new_name = item["proposed_zabbix_visible_name"]

        logger.info("[%d/%d] Renaming HostID %s: '%s' -> '%s' (Preserving tech host '%s')...",
                    idx, len(safe_renames), host_id, old_name, new_name, tech_host)

        if args.dry_run:
            logger.info("  [DRY-RUN] Would execute host.update({'hostid': '%s', 'name': '%s'})", host_id, new_name)
            success_count += 1
            audit_records.append({
                "host_id": host_id,
                "technical_host": tech_host,
                "old_visible_name": old_name,
                "new_visible_name": new_name,
                "canonical_id": item["canonical_id"],
                "status": "dry_run",
                "applied_at": now,
            })
            continue

        try:
            res = call_zabbix_api(
                args.zabbix_api_url,
                args.zabbix_token,
                "host.update",
                {"hostid": host_id, "name": new_name},
            )
            success_count += 1
            audit_records.append({
                "host_id": host_id,
                "technical_host": tech_host,
                "old_visible_name": old_name,
                "new_visible_name": new_name,
                "canonical_id": item["canonical_id"],
                "status": "applied",
                "applied_at": now,
            })
            # Rate limiting: 50ms pause between updates
            time.sleep(0.05)
        except Exception as e:
            logger.error("Failed to update HostID %s: %s", host_id, e)
            fail_count += 1
            audit_records.append({
                "host_id": host_id,
                "technical_host": tech_host,
                "old_visible_name": old_name,
                "new_visible_name": new_name,
                "canonical_id": item["canonical_id"],
                "status": "failed",
                "error": str(e),
                "applied_at": now,
            })

    # Save audit file
    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_filename = audit_dir / f"reconciliation_audit_{int(now)}.json"
    with open(audit_filename, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": now,
            "success_count": success_count,
            "fail_count": fail_count,
            "records": audit_records,
        }, f, indent=2)

    logger.info("Reconciliation apply completed: %d succeeded, %d failed.", success_count, fail_count)
    logger.info("Saved rollback audit journal to %s", audit_filename)
    return 0 if fail_count == 0 else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    """Roll back applied visible names using audit journal."""
    audit_path = Path(args.audit_file)
    if not audit_path.exists():
        logger.error("Audit file not found: %s", audit_path)
        return 1

    with open(audit_path, "r", encoding="utf-8") as f:
        audit_data = json.load(f)

    records = audit_data.get("records", [])
    applied_records = [r for r in records if r.get("status") == "applied"]

    logger.info("Found %d applied renames to roll back in %s.", len(applied_records), audit_path)
    if not applied_records:
        logger.info("Zero applied renames found in audit file.")
        return 0

    if not args.yes:
        confirm = input(f"Roll back {len(applied_records)} visible names to original values? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Rollback aborted.")
            return 0

    restored_count = 0
    fail_count = 0
    for idx, r in enumerate(applied_records, start=1):
        host_id = r["host_id"]
        old_name = r["old_visible_name"]
        curr_name = r["new_visible_name"]

        logger.info("[%d/%d] Restoring HostID %s: '%s' -> '%s'...",
                    idx, len(applied_records), host_id, curr_name, old_name)
        try:
            call_zabbix_api(
                args.zabbix_api_url,
                args.zabbix_token,
                "host.update",
                {"hostid": host_id, "name": old_name},
            )
            restored_count += 1
            time.sleep(0.05)
        except Exception as e:
            logger.error("Failed to restore HostID %s: %s", host_id, e)
            fail_count += 1

    logger.info("Rollback completed: %d restored, %d failed.", restored_count, fail_count)
    return 0 if fail_count == 0 else 1



def cmd_drift(args: argparse.Namespace) -> int:
    """Execute periodic drift detection comparing current states against baseline plan."""
    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        logger.error("Baseline plan file not found: %s. Run dry-run first.", plan_file)
        return 1

    with open(plan_file, "r", encoding="utf-8") as f:
        baseline_plan = json.load(f)

    sw_nodes = SolarWindsInventoryImporter.from_json_file(args.solarwinds_file)
    zbx_hosts = ZabbixInventoryCollector.from_json_file(args.zabbix_file)

    report = DeviceDriftDetector.detect_drift(baseline_plan, sw_nodes, zbx_hosts)

    print("\n" + "=" * 100)
    print("NAWARI INVENTORY DRIFT DETECTION REPORT")
    print("=" * 100)
    print(f"Timestamp:                      {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(report.timestamp))}")
    print(f"Total Drift Items Detected:     {report.total_drift_items}")
    print(f"New SolarWinds Devices:         {len(report.new_solarwinds_devices)}")
    print(f"New Zabbix Hosts:               {len(report.new_zabbix_hosts)}")
    print(f"Caption / Display Name Changes: {len(report.caption_changes)}")
    print(f"Management IP Changes:          {len(report.ip_changes)}")
    print(f"Missing in SolarWinds:          {len(report.missing_in_solarwinds)} (Marked stale, identities preserved)")
    print("-" * 100)

    if report.caption_changes:
        print("\nCAPTION CHANGES (Operator Review Required):")
        for cc in report.caption_changes:
            print(f"  NodeID {cc['node_id']}: '{cc['old_caption']}' -> '{cc['new_caption']}' (Canonical: {cc['canonical_id']})")

    if report.ip_changes:
        print("\nIP ADDRESS CHANGES (Corroboration Required):")
        for ipc in report.ip_changes:
            print(f"  NodeID {ipc['node_id']} ({ipc['caption']}): '{ipc['old_ip']}' -> '{ipc['new_ip']}'")

    if report.new_solarwinds_devices:
        print("\nNEW SOLARWINDS DEVICES (Candidates for Zabbix Onboarding):")
        for nsd in report.new_solarwinds_devices[:10]:
            print(f"  NodeID {nsd['node_id']}: '{nsd['caption']}' ({nsd['ip_address']}) - Model: {nsd['model']}")

    print("=" * 100 + "\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info("Saved drift report to %s", out_path)

    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Nawari Device Identity and Naming Reconciliation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Dry-run command
    p_dry = subparsers.add_parser("dry-run", help="Run deterministic reconciliation and generate plan")
    p_dry.add_argument("--solarwinds-file", default=str(DEFAULT_SW_FILE), help="Path to SolarWinds nodes JSON export")
    p_dry.add_argument("--zabbix-file", default=str(DEFAULT_ZBX_FILE), help="Path to Zabbix hosts JSON export")
    p_dry.add_argument("--output", default=str(DEFAULT_PLAN_FILE), help="Path to output reconciliation plan JSON")

    # Apply command
    p_apply = subparsers.add_parser("apply", help="Apply approved visible-name renames to Zabbix")
    p_apply.add_argument("--plan-file", default=str(DEFAULT_PLAN_FILE), help="Path to reconciliation plan JSON")
    p_apply.add_argument("--zabbix-api-url", default=DEFAULT_ZBX_API, help="Zabbix API endpoint URL")
    p_apply.add_argument("--zabbix-token", default=DEFAULT_ZBX_TOKEN, help="Zabbix API bearer token")
    p_apply.add_argument("--audit-dir", default=str(DEFAULT_AUDIT_DIR), help="Directory to save rollback audit journal")
    p_apply.add_argument("--dry-run", action="store_true", help="Simulate Zabbix API calls without modifying hosts")
    p_apply.add_argument("--yes", "-y", action="store_true", help="Automatically confirm without interactive prompt")

    # Rollback command
    p_roll = subparsers.add_parser("rollback", help="Roll back applied renames using audit journal")
    p_roll.add_argument("--audit-file", required=True, help="Path to reconciliation audit JSON file")
    p_roll.add_argument("--zabbix-api-url", default=DEFAULT_ZBX_API, help="Zabbix API endpoint URL")
    p_roll.add_argument("--zabbix-token", default=DEFAULT_ZBX_TOKEN, help="Zabbix API bearer token")
    p_roll.add_argument("--yes", "-y", action="store_true", help="Automatically confirm rollback")

    # Drift command
    p_drift = subparsers.add_parser("drift", help="Detect inventory drift and caption changes")
    p_drift.add_argument("--plan-file", default=str(DEFAULT_PLAN_FILE), help="Baseline plan JSON file")
    p_drift.add_argument("--solarwinds-file", default=str(DEFAULT_SW_FILE), help="Latest SolarWinds nodes JSON")
    p_drift.add_argument("--zabbix-file", default=str(DEFAULT_ZBX_FILE), help="Latest Zabbix hosts JSON")
    p_drift.add_argument("--output", default=str(ROOT_DIR / "network observability/evidence/drift_report.json"), help="Path to output drift report JSON")


    args = parser.parse_args()

    if args.command == "dry-run":
        return cmd_dry_run(args)
    elif args.command == "apply":
        return cmd_apply(args)
    elif args.command == "rollback":
        return cmd_rollback(args)
    elif args.command == "drift":
        return cmd_drift(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
